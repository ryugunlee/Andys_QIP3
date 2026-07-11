"""네이버증권(국내 KRX/KOSPI/KOSDAQ) 전용 종목 데이터 컨테이너.

curated 팩터 정의와 기술적 지표 계산은 `collection/stock_base.py`의 `BaseStock`이
전담하고, 이 파일은 네이버 raw 데이터 수집(fetch)과 국내 재무 팩터 계산만 담당한다.

야후와 달리 현금흐름표/내부자거래/기관투자자 비중 데이터를 제공하지 않으므로
관련 curated 컬럼(PCR/PFCR/Coverage Ratio/ARP/Depreciation Capex Ratio/NCAV/
Current Ratio/ROC/GPTOA/Asset Turnover/Interest Ratio/Debt Growth/EV 계열/
Buyback 계열/Insider Buy Ratio/Institutionpercent/Insiderpercent)은 결측(None)으로
남는다. 자세한 내용은 .claude/PROBLEMS.md 참고.

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
)
from collection.naver import client
from collection.naver.parsers import (
    get_statement_value,
    latest_actual_periods,
    parse_financial_statements,
    parse_number,
    parse_price_history,
    parse_won_amount,
)
from collection.stock_base import BaseStock

_ANNUAL_STATEMENT_TYPE = "finance_annual"


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

        self.is_valid = True

    def compute_curated_factors(self) -> None:
        """raw 데이터로부터 curated 팩터들을 계산해 속성에 채운다."""
        self._compute_valuation_factors()
        self._compute_technical_factors()
        self._compute_financial_statement_factors()
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

    def _integration_totals(self) -> dict:
        return {
            item["code"]: item.get("value")
            for item in self.integration_payload.get("totalInfos", [])
        }

    def _raw_row(self) -> dict:
        row: dict = {}
        row.update(self._prefixed_row("raw_naver_basic", self.basic_payload))
        row.update(self._prefixed_row("raw_naver_integration_total", self._integration_totals()))
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
        return self._with_identity_columns(self.annual_statements)
