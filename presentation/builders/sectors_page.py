"""섹터·산업 비교 페이지(sectors/index.html) 빌더.

repository의 그룹 평가(GroupScore)를 표시용 문자열로 변환해 렌더링한다.
템플릿은 포맷을 모르고, 포맷터 선택은 이 빌더가 담당한다.
"""

from pathlib import Path

from jinja2 import Environment

from presentation.formatters import (
    format_fraction_percent,
    format_multiple,
    format_score,
    format_signed_percent,
)
from presentation.models import GroupScore
from presentation.repository.base import StockRepository


def _to_row(score: GroupScore) -> dict[str, object]:
    return {
        "name": score.name,
        "region": score.region,
        "ticker_count": score.ticker_count,
        "relative_score": score.relative_score,
        "median_finalscore_text": format_score(score.median_finalscore),
        "median_per_text": format_multiple(score.median_per),
        "median_roe_text": format_fraction_percent(score.median_roe),
        "median_ratio_3m": score.median_ratio_3m,
        "median_ratio_3m_text": format_signed_percent(score.median_ratio_3m),
    }


def build_sectors_page(
    repository: StockRepository, env: Environment, output_dir: Path
) -> None:
    sectors_dir = output_dir / "sectors"
    sectors_dir.mkdir(parents=True, exist_ok=True)

    template = env.get_template("sectors.html")
    html = template.render(
        root="..",
        active_page="sectors",
        updated_date=repository.updated_date(),
        sector_rows=[_to_row(score) for score in repository.group_scores("sector")],
        industry_rows=[_to_row(score) for score in repository.group_scores("industry")],
    )
    (sectors_dir / "index.html").write_text(html, encoding="utf-8")
