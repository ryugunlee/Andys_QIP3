"""메인 페이지(index.html) 빌더.

세계 경제 지표(placeholder), 추천 종목 미리보기, 뉴스(placeholder)를 담는다.
"""

from pathlib import Path

from jinja2 import Environment

from presentation import config
from presentation.repository.base import StockRepository
from presentation.repository.indicators_provider import load_economic_indicators
from presentation.repository.news_provider import load_news


def build_index_page(
    repository: StockRepository, env: Environment, output_dir: Path
) -> None:
    template = env.get_template("index.html")
    html = template.render(
        root=".",
        active_page="home",
        updated_date=repository.updated_date(),
        indicators=load_economic_indicators(),
        news=load_news(),
        recommended=repository.good_stocks(
            limit=config.INDEX_RECOMMENDED_PREVIEW_LIMIT
        ),
    )
    (output_dir / "index.html").write_text(html, encoding="utf-8")
