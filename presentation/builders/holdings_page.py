"""보유 판단 페이지(holdings/index.html) 빌더.

시장별 생존 종목(관문·효율성·신뢰도 통과) 중 QIP4 종합점수 상위 20%를 **빠짐없이** 표로 나열한다.
"지금 이 종목이 보유할 만한 위치인가"를 목록에서 바로 읽게 하는 것이 목적이다 — 종합 점수와
"생존 종목 N개 중 M등"을 함께 보여주고, 구간 밖으로 밀려난 종목은 목록에서 사라진다.

필터(정렬 기준)를 바꾸면 **구간 안에서** 그 축의 등수로 다시 줄을 세운다. 등수는 여기서 미리
계산해 행에 실어 두고, `static/holdings.js`는 줄 순서와 등수 칸만 바꾼다.
순위 모집단이 시장(KOSPI/KOSDAQ/NASDAQ/NYSE)이라 시장끼리 섞어 보여주지 않는다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
from jinja2 import Environment

from presentation.holding_ranks import HOLDING_TOP_PERCENT
from presentation.models import HoldingEntry
from presentation.repository.base import StockRepository


@dataclass(frozen=True)
class HoldingFilter:
    """정렬 기준 하나. key는 행의 data-* 속성 이름에 쓰인다."""

    key: str
    label: str
    description: str
    score_of: Callable[[HoldingEntry], float | None]


HOLDING_FILTERS: tuple[HoldingFilter, ...] = (
    HoldingFilter("total", "종합", "QIP4 종합 점수 (가치·성장 × 효율성 승수)",
                  lambda entry: entry.stock.qip4_score),
    HoldingFilter("value", "가치", "QIP4 가치 점수", lambda entry: entry.value_score),
    HoldingFilter("growth", "성장", "QIP4 성장성 점수", lambda entry: entry.growth_score),
    HoldingFilter("momentum", "모멘텀", "QIP4 모멘텀 점수 (선정이 아니라 집행률에 쓰이는 축)",
                  lambda entry: entry.momentum_score),
    HoldingFilter("stability", "안정성", "QIP3 안정성 점수 — QIP4는 안정성을 통과/탈락으로만 보므로 빌려 쓴다",
                  lambda entry: entry.stability_score),
)


@dataclass(frozen=True)
class HoldingRowView:
    entry: HoldingEntry
    selected: bool  # QIP4 선별(시장 상위 10%)에도 들었는가
    scores: dict[str, float | None]  # 필터 key → 점수
    ranks: dict[str, int | None]  # 필터 key → 구간 안에서의 등수


@dataclass(frozen=True)
class HoldingMarketView:
    market: str
    survivor_count: int
    rows: list[HoldingRowView]


def _zone_ranks(entries: list[HoldingEntry], holding_filter: HoldingFilter) -> list[int | None]:
    """구간 안에서 한 축의 등수 (높을수록 앞, 동점 같은 등수, 결측은 None)."""
    scores = pd.Series([holding_filter.score_of(entry) for entry in entries], dtype=float)
    ranks = scores.rank(ascending=False, method="min")
    return [None if pd.isna(rank) else int(rank) for rank in ranks]


def _market_view(
    market: str, entries: list[HoldingEntry], selected_tickers: set[str]
) -> HoldingMarketView:
    ranks_by_filter = {f.key: _zone_ranks(entries, f) for f in HOLDING_FILTERS}
    rows = [
        HoldingRowView(
            entry=entry,
            selected=entry.stock.ticker in selected_tickers,
            scores={f.key: f.score_of(entry) for f in HOLDING_FILTERS},
            ranks={key: ranks[index] for key, ranks in ranks_by_filter.items()},
        )
        for index, entry in enumerate(entries)
    ]
    return HoldingMarketView(
        market=market, survivor_count=entries[0].survivor_count, rows=rows
    )


def holding_market_views(
    entries: list[HoldingEntry], selected_tickers: set[str]
) -> list[HoldingMarketView]:
    """repository 순서(시장 → 종합 등수)를 유지한 채 시장별로 묶는다."""
    by_market: dict[str, list[HoldingEntry]] = {}
    for entry in entries:
        by_market.setdefault(entry.stock.market, []).append(entry)
    return [
        _market_view(market, market_entries, selected_tickers)
        for market, market_entries in by_market.items()
    ]


def build_holdings_page(
    repository: StockRepository, env: Environment, output_dir: Path
) -> None:
    holdings_dir = output_dir / "holdings"
    holdings_dir.mkdir(parents=True, exist_ok=True)

    selected_tickers = {stock.ticker for stock in repository.qip4_stocks()}
    template = env.get_template("holdings.html")
    html = template.render(
        root="..",
        active_page="holdings",
        updated_date=repository.updated_date(),
        holding_markets=holding_market_views(repository.holding_stocks(), selected_tickers),
        holding_filters=HOLDING_FILTERS,
        holding_top_percent=HOLDING_TOP_PERCENT,
    )
    (holdings_dir / "index.html").write_text(html, encoding="utf-8")
