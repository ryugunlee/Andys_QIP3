"""주식 분석 페이지(stocks/index.html) 빌더.

추천 종목 카드(기존 goodstock), QIP3 5요인 선별 종목·섹터/시장 쏠림,
한국/미국 시가총액 상위 표(CSS 탭), 뉴스 placeholder를 담는다.
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

    qip3_all = repository.qip3_stocks()

    template = env.get_template("stocks.html")
    html = template.render(
        root="..",
        active_page="stocks",
        updated_date=repository.updated_date(),
        market_counts=repository.market_counts(),
        recommended=repository.good_stocks(limit=config.RECOMMENDED_DISPLAY_LIMIT),
        qip3_recommended=qip3_all[: config.QIP3_DISPLAY_LIMIT],
        qip3_total=len(qip3_all),
        qip3_by_sector=_concentration(qip3_all, lambda s: s.sector),
        qip3_by_market=_concentration(qip3_all, lambda s: s.market),
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
