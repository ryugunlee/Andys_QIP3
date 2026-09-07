"""재무제표 long format → 정규화된 다년 시계열.

야후와 네이버는 같은 계정을 전혀 다른 이름으로 부른다 — 야후는 영문 라벨
("Total Revenue"), 네이버 WiseFn은 ACCODE 접두사("200000:매출액(수익)").
게다가 WiseFn 금액 단위는 **억원**이라 시가총액(원)과 섞어 쓰면 1억 배가 틀린다.

이 파일이 그 차이를 전부 흡수한다. 다른 qip4 모듈은 `"revenue"` 같은 정규화된
이름만 알면 되고, 소스가 무엇인지 몰라도 된다.

입력은 `BaseStock.to_financial_statement_rows()`가 만드는 long format 그대로다
— 두 소스가 이미 같은 형태로 내주므로 별도 변환이 필요 없다.
"""

import pandas as pd

from collection.constants import NAVER_EOK_TO_WON

# 정규화 지표 이름 → 야후 손익계산서/재무상태표/현금흐름표의 항목 라벨.
_YAHOO_ITEMS: dict[str, str] = {
    "revenue": "Total Revenue",
    "operating_income": "Operating Income",
    "net_income": "Net Income",
    "cogs": "Cost Of Revenue",
    "interest_expense": "Interest Expense",
    "operating_cash_flow": "Operating Cash Flow",
    "capex": "Capital Expenditure",
    "dividends_paid": "Cash Dividends Paid",
    "total_assets": "Total Assets",
    "total_equity": "Stockholders Equity",
    "total_debt": "Total Debt",
    "cash": "Cash And Cash Equivalents",
    "inventory": "Inventory",
    "receivables": "Accounts Receivable",
    "payables": "Accounts Payable",
    "goodwill": "Goodwill",
    "deferred_tax_assets": "Non Current Deferred Taxes Assets",
    "invested_capital": "Invested Capital",
}

# 정규화 지표 이름 → 네이버 WiseFn ACCODE.
_NAVER_ACCODES: dict[str, str] = {
    "revenue": "200000",
    "operating_income": "201370",
    "net_income": "203170",
    "cogs": "200360",
    "interest_expense": "202560",
    "operating_cash_flow": "400000",
    "capex": "191000",
    "dividends_paid": "404320",
    "interest_paid": "402100",
    "total_assets": "110000",
    "total_equity": "120000",
    "total_debt": "190980",
    "cash": "190650",
    "inventory": "112840",
    "receivables": "190560",
    "payables": "132010",
    "goodwill": "190170",
    "deferred_tax_assets": "112340",
    "lease_liability": "190780",
    "lease_liability_current": "131850",
    "employee_benefit_obligation": "130880",
    "pension_plan_assets": "190400",
    "advances_received": "401820",
}

# 소스별 (연간 statement_type들, 분기 statement_type들).
_YAHOO_ANNUAL = ("financials", "balance_sheet", "cashflow")
_YAHOO_QUARTERLY = ("financials_q", "balance_sheet_q", "cashflow_q")
_NAVER_ANNUAL = ("wise_income_statement", "wise_balance_sheet", "wise_cash_flow")
_NAVER_QUARTERLY = (
    "wise_income_statement_q",
    "wise_balance_sheet_q",
    "wise_cash_flow_q",
)

# 현금 유출 항목은 소스마다 부호 규약이 제각각이다 (실측):
#   설비투자   야후 음수 / 네이버 양수
#   배당금지급 야후 음수 / 네이버 음수
#   이자지급   네이버 음수 (야후는 현금흐름표에 항목 자체가 없다)
# 이 값들은 전부 "얼마나 나갔는가"라는 규모로만 쓰이므로 절대값으로 통일한다.
# 부호 규약을 소스별로 외우게 두면 호출부에서 반드시 틀린다.
_MAGNITUDE_ITEMS: frozenset[str] = frozenset(
    {"capex", "dividends_paid", "interest_paid"}
)


class FinancialSeries:
    """한 종목의 정규화된 재무 시계열. 값의 단위는 원(KRW) 또는 달러(USD)로 통일된다."""

    def __init__(self, statements: pd.DataFrame, source: str):
        self._source = source
        self._is_naver = source == "naver"
        self._scale = NAVER_EOK_TO_WON if self._is_naver else 1.0
        self._items = _NAVER_ACCODES if self._is_naver else _YAHOO_ITEMS
        self._annual_types = _NAVER_ANNUAL if self._is_naver else _YAHOO_ANNUAL
        self._quarterly_types = _NAVER_QUARTERLY if self._is_naver else _YAHOO_QUARTERLY
        self._statements = (
            statements[~statements["is_consensus"]]
            if not statements.empty
            else statements
        )

    def _series(self, metric: str, statement_types: tuple[str, ...]) -> dict[str, float]:
        """{회계기간: 값}. 항목을 못 찾으면 빈 dict."""
        key = self._items.get(metric)
        if key is None or self._statements.empty:
            return {}

        rows = self._statements[self._statements["statement_type"].isin(statement_types)]
        if self._is_naver:
            matched = rows[rows["item"].str.startswith(f"{key}:")]
        else:
            matched = rows[rows["item"] == key]
        if matched.empty:
            return {}

        as_magnitude = metric in _MAGNITUDE_ITEMS
        # 같은 기간에 여러 행이 잡히면(계정 트리 중복) 첫 값을 쓴다.
        deduped = matched.drop_duplicates(subset="period", keep="first")
        return {
            str(period): (abs(float(value)) if as_magnitude else float(value)) * self._scale
            for period, value in zip(deduped["period"], deduped["value"])
        }

    def annual(self, metric: str) -> dict[str, float]:
        """연간 시계열 {회계기간: 값}."""
        return self._series(metric, self._annual_types)

    def quarterly(self, metric: str) -> dict[str, float]:
        """분기 시계열 {회계기간: 값}."""
        return self._series(metric, self._quarterly_types)

    def latest_annual(self, metric: str) -> float | None:
        """가장 최근 연간 값. 없으면 None."""
        series = self.annual(metric)
        if not series:
            return None
        return series[max(series)]


def recent_values(series: dict[str, float], years: int) -> list[float]:
    """최근 `years`개 기간의 값을 **오래된 순**으로 반환한다.

    기간 라벨이 "YYYYMM" 형식이라 문자열 정렬이 곧 시간 정렬이다.
    보유 기간이 요청보다 적으면 있는 만큼만 반환한다 — 호출부가 개수를 보고
    판정 유보를 결정한다.
    """
    if not series:
        return []
    ordered = sorted(series)[-years:]
    return [series[period] for period in ordered]
