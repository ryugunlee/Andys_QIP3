"""전 종목 상세 페이지(stocks/{티커}.html) 빌더.

metrics.METRIC_SPECS를 순회하며 그룹별 표를 조립하므로, 분석 영역에서
지표가 추가되면 metrics.py에 스펙 한 줄만 추가하면 여기에 자동 반영된다.
템플릿은 CSV 컬럼명을 모르고, 이 빌더가 만든 (라벨, 문자열) 목록만 받는다.
"""

import re
from pathlib import Path

from jinja2 import Environment

from presentation.formatters import format_metric
from presentation.metrics import (
    HEADLINE_SCORE_COLUMNS,
    METRIC_SPECS,
    MetricGroup,
    specs_by_group,
)
from presentation.models import StockDetail
from presentation.repository.base import StockRepository

# 티커는 원래 [A-Za-z0-9.\-]만 오지만(get_tickers 필터), 파일명 안전을 위해 방어한다.
# 카드/검색의 링크는 urlencode(티커)를 쓰므로, 안전 문자 집합 안에서는 둘이 일치한다.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")

_LABEL_BY_COLUMN: dict[str, str] = {spec.column: spec.label for spec in METRIC_SPECS}


def ticker_filename(ticker: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", ticker) + ".html"


def _headline_scores(detail: StockDetail) -> list[dict[str, object]]:
    return [
        {"label": _LABEL_BY_COLUMN[column], "value": detail.values.get(column)}
        for column in HEADLINE_SCORE_COLUMNS
    ]


def _metric_groups(detail: StockDetail) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for group, specs in specs_by_group().items():
        rows = [
            {
                "label": spec.label,
                "text": format_metric(
                    detail.values.get(spec.column), spec.format, detail.market
                ),
            }
            for spec in specs
            # 대표 점수는 상단 타일로 이미 보여주므로 표에서는 제외
            if not (
                group is MetricGroup.SCORES
                and spec.column in HEADLINE_SCORE_COLUMNS
            )
        ]
        if rows:
            groups.append({"title": group.value, "rows": rows})
    return groups


def build_detail_pages(
    repository: StockRepository, env: Environment, output_dir: Path
) -> int:
    """전 종목 상세 페이지를 생성하고 만든 페이지 수를 반환한다."""
    stocks_dir = output_dir / "stocks"
    stocks_dir.mkdir(parents=True, exist_ok=True)

    template = env.get_template("stock_detail.html")
    updated_date = repository.updated_date()

    count = 0
    for detail in repository.iter_stock_details():
        html = template.render(
            root="..",
            active_page="stocks",
            updated_date=updated_date,
            detail=detail,
            headline_scores=_headline_scores(detail),
            metric_groups=_metric_groups(detail),
        )
        (stocks_dir / ticker_filename(detail.ticker)).write_text(
            html, encoding="utf-8"
        )
        count += 1
    return count
