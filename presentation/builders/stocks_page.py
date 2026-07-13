"""주식 분석 페이지(stocks/index.html) 빌더.

추천 종목 카드, 한국/미국 시가총액 상위 표(CSS 탭), 뉴스 placeholder를 담는다.
"""

from pathlib import Path

from jinja2 import Environment

from presentation import config
from presentation.repository.base import StockRepository
from presentation.repository.news_provider import load_news


def build_stocks_page(
    repository: StockRepository, env: Environment, output_dir: Path
) -> None:
    stocks_dir = output_dir / "stocks"
    stocks_dir.mkdir(parents=True, exist_ok=True)

    template = env.get_template("stocks.html")
    html = template.render(
        root="..",
        active_page="stocks",
        updated_date=repository.updated_date(),
        market_counts=repository.market_counts(),
        recommended=repository.good_stocks(limit=config.RECOMMENDED_DISPLAY_LIMIT),
        top_kr=repository.top_by_market_cap(
            config.REGION_KR, config.TOP_MARKET_CAP_LIMIT
        ),
        top_us=repository.top_by_market_cap(
            config.REGION_US, config.TOP_MARKET_CAP_LIMIT
        ),
        news=load_news(),
    )
    (stocks_dir / "index.html").write_text(html, encoding="utf-8")
