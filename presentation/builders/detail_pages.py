"""전 종목 상세 페이지(stocks/{티커}.html) 빌더.

metrics.METRIC_SPECS를 순회하며 그룹별 표를 조립하므로, 분석 영역에서
지표가 추가되면 metrics.py에 스펙 한 줄만 추가하면 여기에 자동 반영된다.
템플릿은 CSV 컬럼명을 모르고, 이 빌더가 만든 (라벨, 문자열) 목록만 받는다.
"""

import re
from pathlib import Path

from jinja2 import Environment

from presentation.formatters import (
    MISSING,
    format_metric,
    format_money,
    format_percent,
    format_signed_percent,
)
from presentation.metrics import (
    HEADLINE_SCORE_COLUMNS,
    METRIC_SPECS,
    MetricGroup,
    specs_by_group,
)
from presentation.models import AnnualFinancials, StockCharts, StockDetail
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


def _chart_data(charts: StockCharts | None) -> dict[str, object] | None:
    """StockCharts를 charts.js가 읽는 콤팩트 dict로 변환한다.

    일봉은 병렬 배열(d/c/v)로 담아 페이지 임베드 용량을 줄인다.
    데이터가 전혀 없으면 None(→ 템플릿에서 차트 섹션 미표시).
    """
    if charts is None:
        return None
    prices = charts.prices
    price_block: dict[str, list[object]] | None = None
    if prices:
        price_block = {
            "d": [point.date for point in prices],
            "c": [point.close for point in prices],
            "v": [point.volume for point in prices],
        }
    annual_block = _financial_series_block(charts.annual)
    quarterly_block = _financial_series_block(charts.quarterly)
    if price_block is None and not annual_block and not quarterly_block:
        return None
    return {"prices": price_block, "annual": annual_block, "quarterly": quarterly_block}


def _financial_series_block(series: list[AnnualFinancials]) -> list[dict[str, object]]:
    return [
        {"p": point.period, "r": point.revenue, "o": point.operating_income, "n": point.net_income}
        for point in series
    ]


def _financial_rows(series: list[AnnualFinancials], market: str) -> list[dict[str, str]]:
    """실적 시계열(연간 또는 분기)을 표로 보여줄 행 목록(포맷 완료 문자열)으로 만든다.

    막대그래프로 흐름을 보고, 정확한 수치·비율(영업이익률·성장률)은 표로 본다.
    최근 기간이 위로 오도록 내림차순 정렬한다. 성장률은 입력 순서상 직전 기간
    대비이므로, 연간이면 YoY, 분기면 QoQ가 된다.
    """
    rows_out: list[dict[str, str]] = []
    previous_revenue: float | None = None
    for point in series:  # 기간 오름차순 입력 (성장률 계산에 직전 기간 필요)
        revenue = point.revenue
        op_income = point.operating_income
        margin = (
            op_income / revenue * 100
            if op_income is not None and revenue not in (None, 0)
            else None
        )
        growth = (
            (revenue / previous_revenue - 1) * 100
            if revenue is not None and previous_revenue not in (None, 0)
            else None
        )
        rows_out.append(
            {
                "year": point.period,
                "revenue": format_money(revenue, market),
                "operating_income": format_money(op_income, market),
                "net_income": format_money(point.net_income, market),
                "op_margin": format_percent(margin) if margin is not None else MISSING,
                "rev_growth": format_signed_percent(growth)
                if growth is not None
                else MISSING,
            }
        )
        if revenue is not None:
            previous_revenue = revenue
    rows_out.reverse()  # 최근 기간부터 표시
    return rows_out


def _financial_table(charts: StockCharts | None, market: str) -> list[dict[str, str]] | None:
    if charts is None or not charts.annual:
        return None
    return _financial_rows(charts.annual, market)


def _financial_table_quarterly(
    charts: StockCharts | None, market: str
) -> list[dict[str, str]] | None:
    if charts is None or not charts.quarterly:
        return None
    return _financial_rows(charts.quarterly, market)


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
        charts = repository.chart_bundle(detail.ticker, detail.market)
        html = template.render(
            root="..",
            active_page="stocks",
            updated_date=updated_date,
            detail=detail,
            headline_scores=_headline_scores(detail),
            metric_groups=_metric_groups(detail),
            chart_data=_chart_data(charts),
            financial_table=_financial_table(charts, detail.market),
            financial_table_quarterly=_financial_table_quarterly(charts, detail.market),
        )
        (stocks_dir / ticker_filename(detail.ticker)).write_text(
            html, encoding="utf-8"
        )
        count += 1
    return count
