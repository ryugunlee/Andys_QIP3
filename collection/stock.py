"""yfinance(미국 등 해외 주식) 전용 종목 데이터 컨테이너.

curated 팩터 정의와 기술적 지표 계산은 `collection/stock_base.py`의 `BaseStock`이
전담하고, 이 파일은 yfinance raw 데이터 수집(fetch)과 그로부터 계산 가능한
재무 팩터(밸류에이션/현금흐름/재무제표/대차대조표/내부자거래)만 담당한다.

- raw 속성: `info`, `history`, `cashflow`, `financials`, `balance_sheet`, `insider_purchases` —
  yfinance가 주는 원본 그대로 보관 (history는 기술적 지표 계산 후 컬럼이 추가된 채로 보관됨).
- `fetch()`: yfinance에서 raw 데이터를 채움 (필수 데이터 없으면 `is_valid=False`로 조기 종료).
- `compute_curated_factors()`: valuation → technical(BaseStock) → cashflow → financials →
  balance_sheet → insider → buyback_to_income(BaseStock) 순서로 curated 팩터를 계산
  (원본 계산 순서/의존관계 그대로 유지. 뒤 단계가 앞 단계의 결과를 사용하는 숨은 의존성이 있다).

**주의**: percentile 기반 점수(1차/2차 정제, `analysis/` 패키지가 하는 일)는 시장 전체 데이터가
있어야 계산 가능하므로 이 클래스의 책임이 아니다 — 종목 하나만으로는 계산할 수 없는 값이기 때문.
"""

import json
import time

import pandas as pd
import yfinance as yf

from collection.constants import (
    EPS_ZERO_SUBSTITUTE,
    GROWTH_RATE_PERCENT_SCALE,
    HISTORY_PERIOD,
    MIN_HISTORY_TRADING_DAYS,
    RATIO_LOOKBACK_1Y_DAYS,
    REQUEST_THROTTLE_SECONDS,
)
from collection.stock_base import BaseStock
from collection.technical import lookback_index


class YahooStock(BaseStock):
    """yfinance 기반 종목 하나의 raw 데이터 + curated 팩터 컨테이너."""

    SOURCE_NAME = "yahoo"

    def __init__(self, ticker: str):
        super().__init__(ticker)

        # --- raw: 원본 그대로 ---
        self.info: dict = {}
        self.cashflow: pd.DataFrame = pd.DataFrame()
        self.financials: pd.DataFrame = pd.DataFrame()
        self.balance_sheet: pd.DataFrame = pd.DataFrame()
        self.insider_purchases: pd.DataFrame = pd.DataFrame()

        # --- 계산 과정에서만 쓰이는 중간값 (표에는 직접 나가지 않음) ---
        self._capex: float | None = None
        self._depreciation: float | None = None
        self._gross_profit: float | None = None
        self._ebit: float | None = None
        self._debt: float | None = None
        self._asset: float | None = None
        self._equity: float | None = None
        self._current_assets: float | None = None
        self._current_liabilities: float | None = None
        self._liabilities: float | None = None

    def fetch(self) -> None:
        """yfinance에서 raw 데이터를 가져온다. 필수 데이터가 없으면 is_valid=False로 남긴다."""
        ticker_obj = yf.Ticker(self.ticker)
        time.sleep(REQUEST_THROTTLE_SECONDS)
        self.info = ticker_obj.info

        if self.info.get("previousClose") is None or self.info.get("marketCap") is None:
            return

        history = ticker_obj.history(period=HISTORY_PERIOD)
        if len(history) < MIN_HISTORY_TRADING_DAYS:
            return
        self.history = history

        self.cashflow = ticker_obj.cashflow
        self.financials = ticker_obj.financials
        self.balance_sheet = ticker_obj.balance_sheet
        self.insider_purchases = ticker_obj.insider_purchases
        self.is_valid = True

    def compute_curated_factors(self) -> None:
        """raw 데이터로부터 curated 팩터들을 계산해 속성에 채운다."""
        self._compute_valuation_factors()
        self._compute_technical_factors()
        self._compute_cashflow_factors()
        self._compute_financials_factors()
        self._compute_balance_sheet_factors()
        self._compute_insider_factors()
        self._compute_buyback_to_income()

    def _compute_valuation_factors(self) -> None:
        info = self.info
        self.company_name = info.get("shortName", None)
        self.sector = info.get("sector", None)
        self.industry = info.get("industry", None)
        self.country = info.get("country", None)
        self.market_cap = info.get("marketCap", None)
        self.close = info.get("previousClose", None)

        self.dividend_yield = info.get("dividendYield", 0)
        self.ev_to_ebitda = info.get("enterpriseToEbitda", None)
        self.pbr = info.get("priceToBook", None)
        self.psr = info.get("priceToSalesTrailing12Months", None)
        self.operating_cashflow = info.get("operatingCashflow", None)
        self.pcr = (
            self.market_cap / self.operating_cashflow
            if self.operating_cashflow is not None
            else None
        )
        self.ev_to_revenue = info.get("enterpriseToRevenue", None)
        self.net_income = info.get("netIncomeToCommon", None)
        self.revenue = info.get("totalRevenue", None)
        self.roe = info.get("returnOnEquity", None)
        self.roa = info.get("returnOnAssets", None)

        eps = info.get("trailingEps", None)
        if eps == 0:
            eps = EPS_ZERO_SUBSTITUTE
        self.eps = eps
        self.per = self.close / eps if eps is not None else None

        self.eps_growth = info.get("earningsGrowth", 0) * GROWTH_RATE_PERCENT_SCALE
        self.revenue_growth = info.get("revenueGrowth", 0) * GROWTH_RATE_PERCENT_SCALE
        self.insider_percent = info.get("heldPercentInsiders", 0)
        self.institution_percent = info.get("heldPercentInstitutions", 0)
        self.pegr = info.get("trailingPegRatio", None)
        self.debt_to_equity = info.get("debtToEquity", None)
        self.dividend_to_income = (
            (self.dividend_yield * self.close / eps) / 100
            if self.dividend_yield is not None and eps is not None
            else None
        )

    def _compute_cashflow_factors(self) -> None:
        cashflow = self.cashflow
        repurchase_of_capital_stock = (
            cashflow.loc["Repurchase Of Capital Stock"].iloc[0]
            if "Repurchase Of Capital Stock" in cashflow.index
            else 0
        )
        issuance_of_capital_stock = (
            cashflow.loc["Issuance Of Capital Stock"].iloc[0]
            if "Issuance Of Capital Stock" in cashflow.index
            else 0
        )
        self._capex = (
            cashflow.loc["Capital Expenditure"].iloc[0]
            if "Capital Expenditure" in cashflow.index
            else None
        )
        self.buyback_yield = (
            -((repurchase_of_capital_stock + issuance_of_capital_stock) / self.market_cap) * 100
        )

    def _compute_financials_factors(self) -> None:
        financials = self.financials
        interest_expense = (
            financials.loc["Interest Expense"].iloc[0]
            if "Interest Expense" in financials.index
            else None
        )
        operating_income = (
            financials.loc["Operating Income"].iloc[0]
            if "Operating Income" in financials.index
            else None
        )
        if "Net Income" in financials.index and self.net_income is None:
            self.net_income = financials.loc["Net Income"].iloc[0]
        self._gross_profit = (
            financials.loc["Gross Profit"].iloc[0]
            if "Gross Profit" in financials.index
            else None
        )
        self._ebit = financials.loc["EBIT"].iloc[0] if "EBIT" in financials.index else None
        self._depreciation = (
            financials.loc["Reconciled Depreciation"].iloc[0]
            if "Reconciled Depreciation" in financials.index
            else None
        )

        self.interest_ratio = (
            operating_income / interest_expense
            if interest_expense is not None and operating_income is not None
            else None
        )
        self.arp = (
            (self.net_income - self.operating_cashflow) / self.market_cap * 100
            if self.net_income is not None and self.operating_cashflow is not None
            else None
        )

    def _compute_balance_sheet_factors(self) -> None:
        balance_sheet = self.balance_sheet

        self.depreciation_capex_ratio = (
            -(self._depreciation / self._capex)
            if self._capex is not None and self._depreciation is not None
            else None
        )

        self._debt = (
            balance_sheet.loc["Total Debt"].iloc[0] if "Total Debt" in balance_sheet.index else None
        )
        debt_1y_ago = (
            balance_sheet.loc["Total Debt"].iloc[1]
            if "Total Debt" in balance_sheet.index and len(balance_sheet.loc["Total Debt"]) > 1
            else None
        )
        self.debt_growth = (
            (self._debt - debt_1y_ago) / debt_1y_ago * 100
            if self._debt is not None and debt_1y_ago is not None
            else None
        )

        self._asset = (
            balance_sheet.loc["Total Assets"].iloc[0]
            if "Total Assets" in balance_sheet.index
            else None
        )
        self._equity = (
            balance_sheet.loc["Stockholders Equity"].iloc[0]
            if "Stockholders Equity" in balance_sheet.index
            else None
        )
        self._current_assets = (
            balance_sheet.loc["Current Assets"].iloc[0]
            if "Current Assets" in balance_sheet.index
            else None
        )
        self._current_liabilities = (
            balance_sheet.loc["Current Liabilities"].iloc[0]
            if "Current Liabilities" in balance_sheet.index
            else None
        )
        self._liabilities = (
            balance_sheet.loc["Total Liabilities Net Minority Interest"].iloc[0]
            if "Total Liabilities Net Minority Interest" in balance_sheet.index
            else None
        )

        self.asset_to_equity = (
            self._asset / self._equity
            if self._equity is not None and self._asset is not None
            else None
        )
        self.coverage_ratio = (
            self.operating_cashflow / self._debt
            if self._debt is not None and self.operating_cashflow is not None
            else None
        )
        self.ncav = (
            (self._current_assets - self._current_liabilities) / self.market_cap
            if self._current_assets is not None and self._current_liabilities is not None
            else None
        )
        self.current_ratio = (
            self._current_assets / self._current_liabilities
            if self._current_assets is not None and self._current_liabilities is not None
            else None
        )
        self.roc = (
            self._ebit / (self._asset - self._liabilities)
            if self._ebit is not None and self._liabilities is not None and self._asset is not None
            else None
        )
        self.gptoa = (
            self._gross_profit / self._asset
            if self._gross_profit is not None and self._asset is not None
            else None
        )
        self.asset_turnover = (
            self.revenue / self._asset
            if self.revenue is not None and self._asset is not None
            else None
        )
        self.pfcr = (
            self.market_cap / (self.operating_cashflow - self._capex)
            if self.operating_cashflow is not None and self._capex is not None
            else None
        )

    def _compute_insider_factors(self) -> None:
        insider_info = self.insider_purchases
        if insider_info.empty:
            self.insider_buy_ratio = None
            return
        net_shares_purchased = insider_info.loc[2]["Shares"]
        one_year_ago = lookback_index(self.history, RATIO_LOOKBACK_1Y_DAYS)
        self.insider_buy_ratio = (
            (net_shares_purchased * self.history["Close"].iloc[one_year_ago] / self.market_cap * 100)
            if net_shares_purchased is not None
            else None
        )

    def _raw_row(self) -> dict:
        row: dict = {}
        row.update(self._raw_info_row())
        row.update(self._raw_statement_row("raw_cashflow", self.cashflow))
        row.update(self._raw_statement_row("raw_financials", self.financials))
        row.update(self._raw_statement_row("raw_balance_sheet", self.balance_sheet))
        row.update(self._raw_insider_row())
        row.update(self._raw_history_row())
        return row

    def _raw_info_row(self) -> dict:
        row = {}
        for key, value in self.info.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, default=str)
            row[f"raw_info__{key}"] = value
        return row

    @staticmethod
    def _raw_statement_row(prefix: str, statement: pd.DataFrame) -> dict:
        if statement.empty:
            return {}
        latest_period = statement.iloc[:, 0]
        return {f"{prefix}__{name}": value for name, value in latest_period.items()}

    def _raw_insider_row(self) -> dict:
        if self.insider_purchases.empty:
            return {}
        row = {}
        value_columns = self.insider_purchases.columns[1:]
        for _, record in self.insider_purchases.iterrows():
            label = record.iloc[0]
            for column in value_columns:
                row[f"raw_insider__{label}__{column}"] = record[column]
        return row

    def to_financial_statement_rows(self) -> pd.DataFrame:
        """cashflow/financials/balance_sheet 전체 회계기간을 long format으로 변환한다."""
        frames = [
            self._statement_to_long_format("cashflow", self.cashflow),
            self._statement_to_long_format("financials", self.financials),
            self._statement_to_long_format("balance_sheet", self.balance_sheet),
        ]
        non_empty = [frame for frame in frames if not frame.empty]
        if not non_empty:
            combined = pd.DataFrame(columns=["statement_type", "period", "item", "value", "is_consensus"])
        else:
            combined = pd.concat(non_empty, ignore_index=True)
        return self._with_identity_columns(combined)

    @staticmethod
    def _statement_to_long_format(statement_type: str, statement: pd.DataFrame) -> pd.DataFrame:
        if statement.empty:
            return pd.DataFrame(columns=["statement_type", "period", "item", "value", "is_consensus"])
        rows = []
        for period in statement.columns:
            period_label = period.strftime("%Y%m") if hasattr(period, "strftime") else str(period)
            for item, value in statement[period].items():
                if pd.isna(value):
                    continue
                rows.append(
                    {
                        "statement_type": statement_type,
                        "period": period_label,
                        "item": item,
                        "value": float(value),
                        "is_consensus": False,
                    }
                )
        return pd.DataFrame(rows, columns=["statement_type", "period", "item", "value", "is_consensus"])


# 기존 코드 호환용 별칭. collection/basic_information.py 등이 `Stock`을 참조한다.
Stock = YahooStock
