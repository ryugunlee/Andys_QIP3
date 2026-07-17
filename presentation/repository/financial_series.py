"""재무제표 long DataFrame → 실적(매출·영업이익·순이익) 계열 변환기. 연간·분기 겸용.

수집 소스마다 항목 식별자가 다르다:
- naver(WiseFn 손익계산서): statement_type="wise_income_statement"(연간)/
  "wise_income_statement_q"(분기), item이 "ACCODE:계정명" 형태 →
  ACCODE 접두사(200000/201370/203170)로 매칭.
- yahoo(yfinance 손익계산서): statement_type="financials",
  item이 영문 라벨("Total Revenue"/"Operating Income"/"Net Income").
  분기(quarterly_financials)는 아직 수집하지 않아(.claude/PROBLEMS.md #10) 분기 계열은
  네이버만 채워진다.

이 소스별 지식을 이 파일 한 곳에 캡슐화한다. 빌더/모델은 정리된
AnnualFinancials 리스트만 받는다. is_consensus(컨센서스 추정치)는 제외한다.
"""

import pandas as pd

from collection.constants import NAVER_EOK_TO_WON
from presentation.repository import row_mapping as rows
from presentation.models import AnnualFinancials

# 소스별 (statement_type, {계열키: 항목 매칭 기준})
_NAVER_ANNUAL_STATEMENT = "wise_income_statement"
_NAVER_QUARTERLY_STATEMENT = "wise_income_statement_q"
_YAHOO_STATEMENT = "financials"

# WiseFn 원본 값은 "억원" 단위로 온다(collection/naver/naver_stock.py가 스냅샷
# 팩터에 적용하는 것과 같은 상수) — financial_statements에는 원 단위 미변환으로
# 저장되므로, 원(₩) 단위를 기대하는 표현 계층 포맷터에 맞춰 여기서 변환한다.
_NAVER_UNIT_SCALE = NAVER_EOK_TO_WON

# WiseFn ACCODE 접두사 (collection/constants.py와 동일한 값)
_NAVER_PREFIXES: dict[str, str] = {
    "revenue": "200000:",
    "operating_income": "201370:",
    "net_income": "203170:",
}
# yfinance 손익계산서 항목 라벨
_YAHOO_ITEMS: dict[str, str] = {
    "revenue": "Total Revenue",
    "operating_income": "Operating Income",
    "net_income": "Net Income",
}

# WiseFn 분기 period는 분기 말월(YYYYMM)로 온다 — 표시용 "YYYY Qn" 라벨로 변환.
_QUARTER_END_MONTH_LABEL: dict[str, str] = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}


def _series_key_for_item(item: str, source: str) -> str | None:
    """항목 문자열이 어느 계열(revenue/operating_income/net_income)인지 판별."""
    if source == "naver":
        for key, prefix in _NAVER_PREFIXES.items():
            if item.startswith(prefix):
                return key
        return None
    for key, label in _YAHOO_ITEMS.items():
        if item == label:
            return key
    return None


def _period_series(df: pd.DataFrame, statement_type: str, source: str) -> dict[str, dict[str, float]]:
    """재무제표 long DataFrame에서 "period -> {계열키: 값}" 매핑을 뽑는다.

    연간/분기 공통 추출 로직 — statement_type만 다르게 넘겨 재사용한다.
    """
    income = df[df["statement_type"] == statement_type]
    if "is_consensus" in income.columns:
        income = income[income["is_consensus"] != True]  # noqa: E712 (NaN 안전 비교)
    if income.empty:
        return {}

    by_period: dict[str, dict[str, float]] = {}
    for row in income.itertuples(index=False):
        key = _series_key_for_item(str(row.item), source)
        if key is None:
            continue
        value = rows.to_float(row.value)
        if value is None:
            continue
        if source == "naver":
            value *= _NAVER_UNIT_SCALE
        by_period.setdefault(str(row.period), {})[key] = value
    return by_period


def _quarter_label(period: str) -> str:
    """"202509" -> "2025 Q3". 분기 말월이 아니면(예상 밖 데이터) period를 그대로 쓴다."""
    quarter = _QUARTER_END_MONTH_LABEL.get(period[4:6])
    return f"{period[:4]} {quarter}" if quarter else period


def annual_financials_from_df(df: pd.DataFrame, source: str) -> list[AnnualFinancials]:
    """재무제표 long DataFrame에서 연간 3계열을 뽑아 연도 오름차순으로 반환한다.

    세 계열이 모두 비는 기간은 제외한다. 값이 하나라도 있으면 그 해를 포함한다.
    """
    if df.empty:
        return []
    statement_type = _NAVER_ANNUAL_STATEMENT if source == "naver" else _YAHOO_STATEMENT
    by_period = _period_series(df, statement_type, source)

    result: list[AnnualFinancials] = []
    for period in sorted(by_period):
        series = by_period[period]
        result.append(
            AnnualFinancials(
                period=period[:4],  # "202312" -> "2023"
                revenue=series.get("revenue"),
                operating_income=series.get("operating_income"),
                net_income=series.get("net_income"),
            )
        )
    return result


def quarterly_financials_from_df(df: pd.DataFrame, source: str) -> list[AnnualFinancials]:
    """재무제표 long DataFrame에서 분기 3계열을 뽑아 기간 오름차순으로 반환한다.

    분기 수집은 현재 네이버(WiseFn frq=1)만 지원한다(.claude/PROBLEMS.md #10) — 그 외
    소스는 빈 리스트를 반환해 상세 페이지에서 분기 토글이 자동으로 숨겨지게 한다.
    """
    if df.empty or source != "naver":
        return []
    by_period = _period_series(df, _NAVER_QUARTERLY_STATEMENT, source)

    result: list[AnnualFinancials] = []
    for period in sorted(by_period):
        series = by_period[period]
        result.append(
            AnnualFinancials(
                period=_quarter_label(period),
                revenue=series.get("revenue"),
                operating_income=series.get("operating_income"),
                net_income=series.get("net_income"),
            )
        )
    return result
