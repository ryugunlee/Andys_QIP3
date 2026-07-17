"""메인 페이지(index.html) 빌더.

세계 경제 지표(placeholder), 추천 종목 미리보기, 뉴스(placeholder),
우측 6개월 추이 사이드바를 담는다.
"""

from pathlib import Path

from jinja2 import Environment

from collection.macro.indicators import MacroCategory
from presentation import config
from presentation.models import EconomicIndicator
from presentation.repository.base import StockRepository
from presentation.repository.indicators_provider import load_economic_indicators
from presentation.repository.news_provider import load_news


def _group_by_category(
    indicators: list[EconomicIndicator] | None,
) -> list[tuple[str, list[EconomicIndicator]]]:
    """지표를 MacroCategory 선언 순서대로 묶는다 (우측 추이 사이드바의 카테고리별 접기 섹션).

    Jinja의 groupby 필터는 그룹 키를 알파벳순으로 재정렬하므로, 선언 순서를 지키려면
    여기서 미리 묶어 전달한다.
    """
    if not indicators:
        return []
    groups: list[tuple[str, list[EconomicIndicator]]] = []
    for category in MacroCategory:
        members = [ind for ind in indicators if ind.category == category.value and len(ind.history) >= 2]
        if members:
            groups.append((category.value, members))
    return groups


def build_index_page(
    repository: StockRepository, env: Environment, output_dir: Path
) -> None:
    template = env.get_template("index.html")
    indicators = load_economic_indicators()
    html = template.render(
        root=".",
        active_page="home",
        updated_date=repository.updated_date(),
        indicators=indicators,
        trend_groups=_group_by_category(indicators),
        news=load_news(),
        recommended=repository.good_stocks(
            limit=config.INDEX_RECOMMENDED_PREVIEW_LIMIT
        ),
    )
    (output_dir / "index.html").write_text(html, encoding="utf-8")
