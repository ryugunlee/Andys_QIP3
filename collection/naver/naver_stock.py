"""네이버증권(국내 KRX/KOSPI/KOSDAQ) 전용 종목 데이터 컨테이너.

curated 팩터 정의와 기술적 지표 계산은 `collection/stock_base.py`의 `BaseStock`이
전담하고, 이 파일은 네이버 raw 데이터 수집(fetch)과 국내 재무 팩터 계산만 담당한다.

재무 데이터는 두 소스를 함께 쓴다:
- 모바일 API(`finance/annual`): ROE/부채비율/당좌비율 같은 이미 계산된 비율, EPS/매출액 성장률.
- WiseFn(`navercomp.wisereport.co.kr`, 네이버 coinfo 페이지의 "재무분석" 탭이 iframe으로
  불러오는 실제 소스): 손익계산서/재무상태표/현금흐름표 원본 계정 금액. 현금흐름표를 포함해
  Buyback Yield/PFCR/Coverage Ratio/NCAV/Current Ratio/ROC/GPTOA/ARP/Interest Ratio/
  Debt Growth/EV 계열까지 계산할 수 있게 해준다.

여전히 야후에 있는 내부자거래/기관투자자 비중 데이터는 네이버에서 제공하지 않아
Insider Buy Ratio/Institutionpercent/Insiderpercent는 결측(None)으로 남는다.
자세한 내용은 .claude/PROBLEMS.md 참고.

업종(Sector/Industry) 컬럼은 네이버가 한글 업종명을 제공하는 공개 API를 찾지 못해
숫자 업종 코드(industryCode)를 임시로 사용한다 — 이 또한 PROBLEMS.md에 기록되어 있다.
"""

import json
from datetime import datetime, timedelta

import pandas as pd

from collection.constants import (
    HISTORY_PERIOD_YEARS,
    MIN_HISTORY_TRADING_DAYS,
    NAVER_EOK_TO_WON,
    NAVER_ROE_PERCENT_TO_FRACTION,
    NAVER_WISE_FRQ_QUARTER,
    NAVER_WISE_ACCODE_CAPEX,
    NAVER_WISE_ACCODE_CASH_AND_EQUIVALENTS,
    NAVER_WISE_ACCODE_COGS,
    NAVER_WISE_ACCODE_CURRENT_ASSETS,
    NAVER_WISE_ACCODE_CURRENT_LIABILITIES,
    NAVER_WISE_ACCODE_DEPRECIATION,
    NAVER_WISE_ACCODE_GROSS_PROFIT,
    NAVER_WISE_ACCODE_INCOME_TAX,
    NAVER_WISE_ACCODE_INTEREST_EXPENSE,
    NAVER_WISE_ACCODE_INVENTORY,
    NAVER_WISE_ACCODE_NET_INCOME,
    NAVER_WISE_ACCODE_OPERATING_CASH_FLOW,
    NAVER_WISE_ACCODE_OPERATING_INCOME,
    NAVER_WISE_ACCODE_PRETAX_INCOME,
    NAVER_WISE_ACCODE_REVENUE,
    NAVER_WISE_ACCODE_TOTAL_ASSETS,
    NAVER_WISE_ACCODE_TOTAL_DEBT,
    NAVER_WISE_ACCODE_TOTAL_EQUITY,
    NAVER_WISE_ACCODE_TOTAL_LIABILITIES,
    NAVER_WISE_ACCODE_TRADE_RECEIVABLES,
    NAVER_WISE_ACCODE_TREASURY_STOCK_ACQUISITION,
    NAVER_WISE_ACCODE_TREASURY_STOCK_DISPOSAL,
    NAVER_WISE_RPT_BALANCE_SHEET,
    NAVER_WISE_RPT_CASH_FLOW,
    NAVER_WISE_RPT_INCOME_STATEMENT,
)
from collection.financial_trend import evaluate_uptrend
from collection.naver import client
from collection.naver.parsers import (
    get_statement_value,
    get_wise_value,
    latest_actual_periods,
    latest_period_wise_values,
    parse_financial_statements,
    parse_number,
    parse_price_history,
    parse_wise_financial_statement,
    parse_won_amount,
    series_by_accode,
)
from collection.stock_base import BaseStock

_ANNUAL_STATEMENT_TYPE = "finance_annual"
_WISE_INCOME_STATEMENT_TYPE = "wise_income_statement"
_WISE_BALANCE_SHEET_TYPE = "wise_balance_sheet"
_WISE_CASH_FLOW_TYPE = "wise_cash_flow"
# 분기(frq=1) 통계는 연간과 같은 계정과목·응답 형태를 쓰므로 접미사만 붙여 구분한다.
_WISE_INCOME_STATEMENT_Q_TYPE = "wise_income_statement_q"
_WISE_BALANCE_SHEET_Q_TYPE = "wise_balance_sheet_q"
_WISE_CASH_FLOW_Q_TYPE = "wise_cash_flow_q"


class NaverStock(BaseStock):
    """네이버증권 기반 국내 종목 하나의 raw 데이터 + curated 팩터 컨테이너."""

    SOURCE_NAME = "naver"

    def __init__(self, ticker: str):
        """ticker는 네이버 6자리 종목 코드(예: '005930')."""
        super().__init__(ticker)

        # --- raw: 원본 그대로 ---
        self.basic_payload: dict = {}
        self.integration_payload: dict = {}
        self.annual_statements: pd.DataFrame = pd.DataFrame()
        self.wise_income_statement: pd.DataFrame = pd.DataFrame()
        self.wise_balance_sheet: pd.DataFrame = pd.DataFrame()
        self.wise_cash_flow: pd.DataFrame = pd.DataFrame()
        # 분기 실적(연간과 별도 조회, 재무 팩터 계산에는 쓰지 않고 실적 시계열 표시용)
        self.wise_income_statement_q: pd.DataFrame = pd.DataFrame()
        self.wise_balance_sheet_q: pd.DataFrame = pd.DataFrame()
        self.wise_cash_flow_q: pd.DataFrame = pd.DataFrame()

    def fetch(self) -> None:
        """네이버증권에서 raw 데이터를 가져온다. 필수 데이터가 없으면 is_valid=False로 남긴다."""
        basic = client.fetch_basic(self.ticker)
        if basic is None:
            return
        self.basic_payload = basic

        end_date = datetime.today()
        start_date = end_date - timedelta(days=365 * HISTORY_PERIOD_YEARS + 10)
        price_text = client.fetch_price_history(
            self.ticker, start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")
        )
        if price_text is None:
            return
        history = parse_price_history(price_text)
        if len(history) < MIN_HISTORY_TRADING_DAYS:
            return
        self.history = history

        integration = client.fetch_integration(self.ticker)
        if integration is None:
            return
        self.integration_payload = integration

        annual_payload = client.fetch_finance_annual(self.ticker)
        self.annual_statements = (
            parse_financial_statements(annual_payload, _ANNUAL_STATEMENT_TYPE)
            if annual_payload is not None
            else pd.DataFrame()
        )

        self._fetch_wise_statements()

        self.is_valid = True

    def _fetch_wise_statements(self) -> None:
        """WiseFn 손익계산서/재무상태표/현금흐름표를 연간·분기 두 주기로 가져온다.

        encparam 토큰 발급에 실패해도(예: 페이지 구조 변경, 일시적 오류) 종목 자체는
        유효하게 남긴다 — 이 데이터로만 채워지는 팩터들만 결측이 된다. 분기(frq=1)
        조회 실패도 같은 원칙으로 종목을 무효화하지 않고 분기 시계열만 비워둔다
        (재무 팩터 계산은 연간 데이터만 쓰므로 영향 없음)."""
        encparam = client.fetch_wise_encparam(self.ticker)
        if encparam is None:
            return

        income_payload = client.fetch_wise_financial_statement(
            self.ticker, encparam, NAVER_WISE_RPT_INCOME_STATEMENT
        )
        if income_payload is not None:
            self.wise_income_statement = parse_wise_financial_statement(
                income_payload, _WISE_INCOME_STATEMENT_TYPE
            )

        balance_payload = client.fetch_wise_financial_statement(
            self.ticker, encparam, NAVER_WISE_RPT_BALANCE_SHEET
        )
        if balance_payload is not None:
            self.wise_balance_sheet = parse_wise_financial_statement(
                balance_payload, _WISE_BALANCE_SHEET_TYPE
            )

        cash_flow_payload = client.fetch_wise_financial_statement(
            self.ticker, encparam, NAVER_WISE_RPT_CASH_FLOW
        )
        if cash_flow_payload is not None:
            self.wise_cash_flow = parse_wise_financial_statement(
                cash_flow_payload, _WISE_CASH_FLOW_TYPE
            )

        self._fetch_wise_quarterly_statements(encparam)

    def _fetch_wise_quarterly_statements(self, encparam: str) -> None:
        """분기(frq=1) 손익계산서/재무상태표/현금흐름표 — 실적 시계열(막대그래프) 전용.

        재무 팩터(curated factors)는 여전히 연간 데이터만 사용한다."""
        income_payload_q = client.fetch_wise_financial_statement(
            self.ticker, encparam, NAVER_WISE_RPT_INCOME_STATEMENT, frq=NAVER_WISE_FRQ_QUARTER
        )
        if income_payload_q is not None:
            self.wise_income_statement_q = parse_wise_financial_statement(
                income_payload_q, _WISE_INCOME_STATEMENT_Q_TYPE
            )

        balance_payload_q = client.fetch_wise_financial_statement(
            self.ticker, encparam, NAVER_WISE_RPT_BALANCE_SHEET, frq=NAVER_WISE_FRQ_QUARTER
        )
        if balance_payload_q is not None:
            self.wise_balance_sheet_q = parse_wise_financial_statement(
                balance_payload_q, _WISE_BALANCE_SHEET_Q_TYPE
            )

        cash_flow_payload_q = client.fetch_wise_financial_statement(
            self.ticker, encparam, NAVER_WISE_RPT_CASH_FLOW, frq=NAVER_WISE_FRQ_QUARTER
        )
        if cash_flow_payload_q is not None:
            self.wise_cash_flow_q = parse_wise_financial_statement(
                cash_flow_payload_q, _WISE_CASH_FLOW_Q_TYPE
            )

    def compute_curated_factors(self) -> None:
        """raw 데이터로부터 curated 팩터들을 계산해 속성에 채운다."""
        self._compute_valuation_factors()
        self._compute_technical_factors()
        self._compute_financial_statement_factors()
        self._compute_wise_factors()
        self._compute_financial_trend_factors()
        self._compute_buyback_to_income()

    def _compute_valuation_factors(self) -> None:
        totals = self._integration_totals()

        self.company_name = self.basic_payload.get("stockName")
        # 네이버가 한글 업종명을 주는 공개 API를 찾지 못해 숫자 코드를 임시로 쓴다.
        self.sector = str(self.integration_payload.get("industryCode") or "") or None
        self.industry = self.sector
        self.country = "South Korea"

        self.market_cap = parse_won_amount(totals.get("marketValue"))
        self.close = float(self.history["Close"].iloc[-1]) if not self.history.empty else None
        self.per = parse_number(totals.get("per"))
        self.pbr = parse_number(totals.get("pbr"))
        self.eps = parse_number(totals.get("eps"))
        self.dividend_yield = parse_number(totals.get("dividendYieldRatio")) or 0

        self.dividend_to_income = (
            (self.dividend_yield * self.close / self.eps) / 100
            if self.close is not None and self.eps not in (None, 0)
            else None
        )

    def _compute_financial_statement_factors(self) -> None:
        """모바일 API(finance/annual)의 이미 계산된 비율(ROE/부채비율/성장률)을 채운다."""
        statements = self.annual_statements
        periods = latest_actual_periods(statements, count=2)
        if not periods:
            return
        latest_period = periods[0]
        previous_period = periods[1] if len(periods) > 1 else None

        revenue_eok = get_statement_value(statements, latest_period, "매출액")
        net_income_eok = get_statement_value(statements, latest_period, "당기순이익")
        roe_percent = get_statement_value(statements, latest_period, "ROE")
        debt_to_equity = get_statement_value(statements, latest_period, "부채비율")
        eps_latest = get_statement_value(statements, latest_period, "EPS")

        self.revenue = revenue_eok * NAVER_EOK_TO_WON if revenue_eok is not None else None
        self.net_income = net_income_eok * NAVER_EOK_TO_WON if net_income_eok is not None else None
        self.debt_to_equity = debt_to_equity
        self.roe = (
            roe_percent / NAVER_ROE_PERCENT_TO_FRACTION if roe_percent is not None else None
        )
        # WiseFn의 자산총계/자본총계로 더 정확한 값을 얻을 수 있으면 _compute_wise_factors가
        # 이 근사치를 덮어쓴다. WiseFn 조회가 실패했을 때의 대체값으로 여기서 먼저 채운다.
        self.asset_to_equity = 1 + debt_to_equity / 100 if debt_to_equity is not None else None
        self.roa = (
            self.roe / self.asset_to_equity
            if self.roe is not None and self.asset_to_equity not in (None, 0)
            else None
        )
        self.psr = (
            self.market_cap / self.revenue
            if self.market_cap is not None and self.revenue not in (None, 0)
            else None
        )

        if previous_period is not None:
            revenue_prev_eok = get_statement_value(statements, previous_period, "매출액")
            eps_prev = get_statement_value(statements, previous_period, "EPS")
            self.revenue_growth = (
                (revenue_eok / revenue_prev_eok - 1) * 100
                if revenue_eok is not None and revenue_prev_eok not in (None, 0)
                else None
            )
            self.eps_growth = (
                (eps_latest / eps_prev - 1) * 100
                if eps_latest is not None and eps_prev not in (None, 0)
                else None
            )
        self.pegr = (
            self.per / self.eps_growth
            if self.per is not None and self.eps_growth not in (None, 0)
            else None
        )

    def _compute_wise_factors(self) -> None:
        """WiseFn 원본 계정 금액(억원)으로 현금흐름/재무상태표 기반 팩터를 계산한다.

        WiseFn 조회에 실패했으면(빈 DataFrame) 아무 것도 하지 않고 조용히 넘어간다 —
        이 팩터들만 결측으로 남고 종목 자체는 여전히 유효하다."""
        periods = latest_actual_periods(self.wise_balance_sheet, count=2)
        if not periods:
            return
        latest_period = periods[0]
        previous_period = periods[1] if len(periods) > 1 else None

        def income(accode: str, period: str = latest_period) -> float | None:
            return get_wise_value(self.wise_income_statement, period, accode)

        def balance(accode: str, period: str = latest_period) -> float | None:
            return get_wise_value(self.wise_balance_sheet, period, accode)

        def cash_flow(accode: str, period: str = latest_period) -> float | None:
            return get_wise_value(self.wise_cash_flow, period, accode)

        def won(value_eok: float | None) -> float | None:
            return value_eok * NAVER_EOK_TO_WON if value_eok is not None else None

        gross_profit = won(income(NAVER_WISE_ACCODE_GROSS_PROFIT))
        operating_income = won(income(NAVER_WISE_ACCODE_OPERATING_INCOME))
        interest_expense = won(income(NAVER_WISE_ACCODE_INTEREST_EXPENSE))

        total_assets = won(balance(NAVER_WISE_ACCODE_TOTAL_ASSETS))
        current_assets = won(balance(NAVER_WISE_ACCODE_CURRENT_ASSETS))
        cash = won(balance(NAVER_WISE_ACCODE_CASH_AND_EQUIVALENTS))
        total_liabilities = won(balance(NAVER_WISE_ACCODE_TOTAL_LIABILITIES))
        current_liabilities = won(balance(NAVER_WISE_ACCODE_CURRENT_LIABILITIES))
        total_debt = won(balance(NAVER_WISE_ACCODE_TOTAL_DEBT))
        # WiseFn의 *CAPEX는 양수(지출 규모)다. yfinance의 Capital Expenditure는 음수라
        # 부호가 반대이므로, 아래 계산식은 부호에 맞게 새로 쓴 것이지 Yahoo 쪽 식을
        # 그대로 옮긴 것이 아니다.
        capex = won(balance(NAVER_WISE_ACCODE_CAPEX))
        total_equity = won(balance(NAVER_WISE_ACCODE_TOTAL_EQUITY))
        inventory = won(balance(NAVER_WISE_ACCODE_INVENTORY))
        receivables = won(balance(NAVER_WISE_ACCODE_TRADE_RECEIVABLES))
        cogs = won(income(NAVER_WISE_ACCODE_COGS))
        income_tax = won(income(NAVER_WISE_ACCODE_INCOME_TAX))
        pretax_income = won(income(NAVER_WISE_ACCODE_PRETAX_INCOME))

        operating_cashflow = won(cash_flow(NAVER_WISE_ACCODE_OPERATING_CASH_FLOW))
        depreciation = won(cash_flow(NAVER_WISE_ACCODE_DEPRECIATION))
        treasury_disposal = won(cash_flow(NAVER_WISE_ACCODE_TREASURY_STOCK_DISPOSAL)) or 0
        treasury_acquisition = won(cash_flow(NAVER_WISE_ACCODE_TREASURY_STOCK_ACQUISITION)) or 0

        self.operating_cashflow = operating_cashflow
        self.pcr = (
            self.market_cap / operating_cashflow
            if self.market_cap is not None and operating_cashflow not in (None, 0)
            else None
        )

        if total_assets is not None and total_equity not in (None, 0):
            self.asset_to_equity = total_assets / total_equity
            self.roa = self.roe / self.asset_to_equity if self.roe is not None else None

        if operating_income is not None and interest_expense not in (None, 0):
            self.interest_ratio = operating_income / interest_expense

        if self.net_income is not None and operating_cashflow is not None and self.market_cap:
            self.arp = (self.net_income - operating_cashflow) / self.market_cap * 100

        if depreciation is not None and capex not in (None, 0):
            self.depreciation_capex_ratio = depreciation / capex

        if current_assets is not None and current_liabilities is not None:
            self.current_ratio = (
                current_assets / current_liabilities if current_liabilities != 0 else None
            )
            if self.market_cap:
                self.ncav = (current_assets - current_liabilities) / self.market_cap

        if operating_income is not None and total_assets is not None and total_liabilities is not None:
            equity_like = total_assets - total_liabilities
            self.roc = operating_income / equity_like if equity_like != 0 else None

        if gross_profit is not None and total_assets not in (None, 0):
            self.gptoa = gross_profit / total_assets

        if self.revenue is not None and total_assets not in (None, 0):
            self.asset_turnover = self.revenue / total_assets

        if operating_cashflow is not None and total_debt not in (None, 0):
            self.coverage_ratio = operating_cashflow / total_debt

        if operating_cashflow is not None and capex is not None and self.market_cap:
            free_cash_flow = operating_cashflow + capex
            self.pfcr = self.market_cap / free_cash_flow if free_cash_flow != 0 else None

        if self.market_cap is not None and total_debt is not None and cash is not None:
            enterprise_value = self.market_cap + total_debt - cash
            if operating_income is not None and depreciation is not None:
                ebitda = operating_income + depreciation
                self.ev_to_ebitda = enterprise_value / ebitda if ebitda != 0 else None
            if self.revenue not in (None, 0):
                self.ev_to_revenue = enterprise_value / self.revenue

        # 자기주식의취득(자사주매입, 현금유출)을 Yahoo의 음수 Repurchase와 같은 부호로,
        # 자기주식의처분(현금유입)을 Yahoo의 양수 Issuance와 같은 부호로 맞춘 뒤 같은 식 적용.
        if self.market_cap:
            net_buyback = -treasury_acquisition + treasury_disposal
            self.buyback_yield = -(net_buyback / self.market_cap) * 100

        # --- 신규 팩터 (수익성/재무건전성/효율성). 비율이라 억원 스케일은 서로 상쇄된다. ---
        if operating_income is not None and self.revenue not in (None, 0):
            self.operating_margin = operating_income / self.revenue
        if gross_profit is not None and self.revenue not in (None, 0):
            self.gross_margin = gross_profit / self.revenue
        if self.net_income is not None and self.revenue not in (None, 0):
            self.net_margin = self.net_income / self.revenue
        if total_debt is not None and cash is not None and total_equity not in (None, 0):
            self.net_debt_to_equity = (total_debt - cash) / total_equity
        if cash is not None and current_liabilities not in (None, 0):
            self.cash_ratio = cash / current_liabilities
        # 네이버 CAPEX는 양수(지출 규모)라 매출 대비 절대규모로 바로 쓴다.
        if capex is not None and self.revenue not in (None, 0):
            self.capex_to_revenue = capex / self.revenue
        if cogs is not None and inventory not in (None, 0):
            self.inventory_turnover = cogs / inventory
        if current_assets is not None and inventory is not None and current_liabilities not in (None, 0):
            self.quick_ratio = (current_assets - inventory) / current_liabilities
        if income_tax is not None and pretax_income not in (None, 0):
            self.effective_tax_rate = income_tax / pretax_income
        if self.revenue is not None and receivables not in (None, 0):
            self.receivables_turnover = self.revenue / receivables

        if previous_period is not None:
            total_debt_prev = won(balance(NAVER_WISE_ACCODE_TOTAL_DEBT, previous_period))
            self.debt_growth = (
                (total_debt - total_debt_prev) / total_debt_prev * 100
                if total_debt is not None and total_debt_prev not in (None, 0)
                else None
            )

    def _compute_financial_trend_factors(self) -> None:
        """5개년 손익계산서(컨센서스 제외)로 매출·영업이익 오름세를 판정한다."""
        revenue_series = series_by_accode(self.wise_income_statement, NAVER_WISE_ACCODE_REVENUE)
        operating_income_series = series_by_accode(
            self.wise_income_statement, NAVER_WISE_ACCODE_OPERATING_INCOME
        )
        self.revenue_trend_5y = evaluate_uptrend(revenue_series)
        self.operating_income_trend_5y = evaluate_uptrend(operating_income_series)

    def _integration_totals(self) -> dict:
        return {
            item["code"]: item.get("value")
            for item in self.integration_payload.get("totalInfos", [])
        }

    def _raw_row(self) -> dict:
        row: dict = {}
        row.update(self._prefixed_row("raw_naver_basic", self.basic_payload))
        row.update(self._prefixed_row("raw_naver_integration_total", self._integration_totals()))
        row.update(self._prefixed_row("raw_naver_wise_income", latest_period_wise_values(self.wise_income_statement)))
        row.update(self._prefixed_row("raw_naver_wise_balance", latest_period_wise_values(self.wise_balance_sheet)))
        row.update(self._prefixed_row("raw_naver_wise_cashflow", latest_period_wise_values(self.wise_cash_flow)))
        row.update(self._raw_history_row())
        return row

    @staticmethod
    def _prefixed_row(prefix: str, payload: dict) -> dict:
        row = {}
        for key, value in payload.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, default=str)
            row[f"{prefix}__{key}"] = value
        return row

    def to_financial_statement_rows(self) -> pd.DataFrame:
        frames = [
            self.annual_statements,
            self.wise_income_statement,
            self.wise_balance_sheet,
            self.wise_cash_flow,
            self.wise_income_statement_q,
            self.wise_balance_sheet_q,
            self.wise_cash_flow_q,
        ]
        non_empty = [self._with_identity_columns(frame) for frame in frames if not frame.empty]
        if not non_empty:
            return pd.DataFrame(columns=["ticker", "source", "statement_type", "period", "item", "value", "is_consensus"])
        return pd.concat(non_empty, ignore_index=True)
