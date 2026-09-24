"""주식 분석 페이지(stocks/index.html) 빌더.

QIP4 정량 규칙 선별, 추천 종목 카드(기존 goodstock), QIP3 5요인 선별(각각 섹터/시장 쏠림),
한국/미국 시가총액 상위 표(CSS 탭), 뉴스 placeholder를 담는다.

카드 섹션 세 개는 모두 **전체 / 한국 / 미국** 시장 탭을 갖는다. 한국과 미국이 한 그리드에
섞이면 통화·시총 단위가 뒤섞여 비교가 어렵고, 시장별로 따로 선별되는 규칙(run 하나 = 시장
하나)과도 어긋나 보인다.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from jinja2 import Environment

from presentation import config
from presentation.models import StockSummary
from presentation.repository.base import StockRepository
from presentation.repository.news_provider import load_news


@dataclass(frozen=True)
class MarketGroup:
    """시장 탭 하나 — 라벨, 그 시장의 선별 총수, 카드로 보여줄 상위 N개."""

    key: str  # 템플릿의 radio/panel 클래스 접미사 (all/kr/us)
    label: str
    total: int
    stocks: list["StockSummary"]


# (탭 키, 라벨, 소속 판정). 전체 탭이 첫 번째이므로 기본 선택이 된다.
_MARKET_GROUP_SPECS: tuple[tuple[str, str, Callable[[StockSummary], bool]], ...] = (
    ("all", "전체", lambda stock: True),
    ("kr", "한국", lambda stock: config.is_korean_market_name(stock.market)),
    ("us", "미국", lambda stock: not config.is_korean_market_name(stock.market)),
)


def market_groups(stocks: list[StockSummary], limit: int) -> list[MarketGroup]:
    """종목 목록을 전체/한국/미국 탭으로 나눈다. 표시 개수 제한은 탭마다 따로 적용한다."""
    groups: list[MarketGroup] = []
    for key, label, belongs in _MARKET_GROUP_SPECS:
        members = [stock for stock in stocks if belongs(stock)]
        groups.append(
            MarketGroup(key=key, label=label, total=len(members), stocks=members[:limit])
        )
    return groups


@dataclass(frozen=True)
class ConcentrationRow:
    """선별 종목의 특정 기준(섹터·시장) 쏠림 한 줄."""

    label: str
    count: int
    percent: float  # 선별 종목 중 비중 (%)


def build_stocks_page(
    repository: StockRepository, env: Environment, output_dir: Path
) -> None:
    stocks_dir = output_dir / "stocks"
    stocks_dir.mkdir(parents=True, exist_ok=True)

    good_all = repository.good_stocks()
    qip3_all = repository.qip3_stocks()
    qip4_all = repository.qip4_stocks()

    template = env.get_template("stocks.html")
    html = template.render(
        root="..",
        active_page="stocks",
        updated_date=repository.updated_date(),
        market_counts=repository.market_counts(),
        recommended=market_groups(
            good_all, config.RECOMMENDED_DISPLAY_LIMIT
        ),
        recommended_total=len(good_all),
        qip3_recommended=market_groups(qip3_all, config.QIP3_DISPLAY_LIMIT),
        qip3_total=len(qip3_all),
        qip3_by_sector=_concentration(qip3_all, lambda s: s.sector),
        qip3_by_market=_concentration(qip3_all, lambda s: s.market),
        qip4_recommended=market_groups(qip4_all, config.QIP4_DISPLAY_LIMIT),
        qip4_total=len(qip4_all),
        qip4_by_sector=_concentration(qip4_all, lambda s: s.sector),
        qip4_by_market=_concentration(qip4_all, lambda s: s.market),
        top_kr=repository.top_by_market_cap(
            config.REGION_KR, config.TOP_MARKET_CAP_LIMIT
        ),
        top_us=repository.top_by_market_cap(
            config.REGION_US, config.TOP_MARKET_CAP_LIMIT
        ),
        news=load_news(),
    )
    (stocks_dir / "index.html").write_text(html, encoding="utf-8")


def _concentration(
    stocks: list[StockSummary], key: Callable[[StockSummary], str | None]
) -> list[ConcentrationRow]:
    """선별 종목을 key(섹터/시장)별로 집계해 비중 내림차순 상위 N개를 반환한다."""
    total = len(stocks)
    if total == 0:
        return []
    counts = Counter(key(stock) or "미분류" for stock in stocks)
    top = counts.most_common(config.QIP3_CONCENTRATION_TOP_N)
    return [
        ConcentrationRow(label=str(label), count=count, percent=count / total * 100)
        for label, count in top
    ]
