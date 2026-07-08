"""한 종목의 원본(raw) 데이터와 자주 쓰는 계산된 팩터(curated)를 함께 담는 컨테이너.

- raw: yfinance가 주는 원본 그대로 (info, history, cashflow, financials, balance_sheet, insider_purchases)
- curated: 기존 get_stock_basic_infomation이 계산하던 ~60개 팩터 (PER, PBR, ROE, ... )

`to_row()`가 이 둘을 하나의 dict(표의 한 행)로 합친다. percentile 기반 점수(1차/2차 정제)는
시장 전체 데이터가 있어야 계산 가능하므로 이 클래스의 책임이 아니다 — `analysis/` 패키지가
`get_stock_basic_infomation`이 만든 전체 표를 받아서 처리한다.
"""

import json
import time

import pandas as pd
import yfinance as yf

from collection.constants import (
    EPS_ZERO_SUBSTITUTE,
    GROWTH_RATE_PERCENT_SCALE,
    MACD_LONG_SPAN,
    MACD_SHORT_SPAN,
    MACD_SIGNAL_SPAN,
    MA_WINDOWS,
    MIN_HISTORY_TRADING_DAYS,
    RATIO_LOOKBACK_1Y_DAYS,
    RATIO_LOOKBACK_3M_DAYS,
    RATIO_LOOKBACK_6M_DAYS,
    REQUEST_THROTTLE_SECONDS,
    RSI_OVERHEAT_THRESHOLD,
    RSI_SIGNAL_WINDOW,
    RSI_SPAN,
    RSI_UNDERHEAT_THRESHOLD,
    VOLUME_LOOKBACK_10D_DAYS,
)

# 표의 컬럼명 -> Stock 인스턴스 속성명. to_row()가 이 순서대로 curated 컬럼을 만든다.
CURATED_COLUMNS: list[tuple[str, str]] = [
    ("Ticker", "ticker"),
    ("Company Name", "company_name"),
    ("Sector", "sector"),
    ("Industry", "industry"),
    ("Country", "country"),
    ("Market Cap", "market_cap"),
    ("Close", "close"),
    ("PER", "per"),
    ("PBR", "pbr"),
    ("PSR", "psr"),
    ("PCR", "pcr"),
    ("EV/Revenue", "ev_to_revenue"),
    ("EV/EBITDA", "ev_to_ebitda"),
    ("Dividend Yield", "dividend_yield"),
    ("ROE", "roe"),
    ("ROA", "roa"),
    ("EPSgrowth", "eps_growth"),
    ("Revenuegrowth", "revenue_growth"),
    ("Insiderpercent", "insider_percent"),
    ("Institutionpercent", "institution_percent"),
    ("PEGR", "pegr"),
    ("Operating Cashflow", "operating_cashflow"),
    ("Revenue", "revenue"),
    ("Debt to Equity", "debt_to_equity"),
    ("EPS", "eps"),
    ("Net Income", "net_income"),
    ("Dividend to Income", "dividend_to_income"),
    ("3M Ratio", "ratio_3m"),
    ("6M Ratio", "ratio_6m"),
    ("1Y Ratio", "ratio_1y"),
    ("3M Turnover", "turnover_3m"),
    ("1Y Turnover", "turnover_1y"),
    ("10D Turnover", "turnover_10d"),
    ("3M Overheat", "overheat_3m"),
    ("10D Overheat", "overheat_10d"),
    ("3M Volatility", "volatility_3m"),
    ("1Y Volatility", "volatility_1y"),
    ("Buyback Yield", "buyback_yield"),
    ("Interest Ratio", "interest_ratio"),
    ("Debt Growth", "debt_growth"),
    ("Insider Buy Ratio", "insider_buy_ratio"),
    ("ARP", "arp"),
    ("Depreciation Capex Ratio", "depreciation_capex_ratio"),
    ("Asset to Equity", "asset_to_equity"),
    ("Coverage Ratio", "coverage_ratio"),
    ("MACD Signal", "macd_signal"),
    ("RSI Signal", "rsi_signal"),
    ("RSI", "rsi"),
    ("MA5", "ma5"),
    ("MA20", "ma20"),
    ("MA60", "ma60"),
    ("MA120", "ma120"),
    ("MA200", "ma200"),
    ("NCAV", "ncav"),
    ("Current Ratio", "current_ratio"),
    ("ROC", "roc"),
    ("GPTOA", "gptoa"),
    ("Asset Turnover", "asset_turnover"),
    ("PFCR", "pfcr"),
    ("Buyback to Income", "buyback_to_income"),
]


def _add_moving_averages(ohlcv: pd.DataFrame) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    for window in MA_WINDOWS:
        ohlcv[f"ma{window}"] = ohlcv["Close"].rolling(window=window).mean()
    return ohlcv


def _add_macd(ohlcv: pd.DataFrame) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    ohlcv["ema12"] = ohlcv["Close"].ewm(span=MACD_SHORT_SPAN).mean()
    ohlcv["ema26"] = ohlcv["Close"].ewm(span=MACD_LONG_SPAN).mean()
    ohlcv["macd"] = ohlcv["ema12"] - ohlcv["ema26"]
    ohlcv["signal"] = ohlcv["macd"].ewm(span=MACD_SIGNAL_SPAN).mean()
    ohlcv["stdmacd"] = ohlcv["macd"] / ohlcv["ma20"] * 100
    return ohlcv


def _add_rsi(ohlcv: pd.DataFrame) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    ohlcv["diff"] = ohlcv["Close"].diff()
    ohlcv["AU"] = ohlcv["diff"].apply(lambda x: x if x > 0 else 0)
    ohlcv["AD"] = ohlcv["diff"].apply(lambda x: -x if x < 0 else 0)
    ohlcv["AU"] = ohlcv["AU"].ewm(span=RSI_SPAN).mean()
    ohlcv["AD"] = ohlcv["AD"].ewm(span=RSI_SPAN).mean()
    ohlcv["RSI"] = ohlcv["AU"] / (ohlcv["AU"] + ohlcv["AD"]) * 100
    ohlcv["RSI_signal"] = ohlcv["RSI"].rolling(window=RSI_SIGNAL_WINDOW).mean()
    return ohlcv


class Stock:
    """종목 하나의 raw 데이터 + curated 팩터 컨테이너."""

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.is_valid: bool = False

        # --- raw: 원본 그대로 ---
        self.info: dict = {}
        self.history: pd.DataFrame = pd.DataFrame()
        self.cashflow: pd.DataFrame = pd.DataFrame()
        self.financials: pd.DataFrame = pd.DataFrame()
        self.balance_sheet: pd.DataFrame = pd.DataFrame()
        self.insider_purchases: pd.DataFrame = pd.DataFrame()

        # --- curated: 자주 쓰는 계산된 팩터 ---
        self.company_name: str | None = None
        self.sector: str | None = None
        self.industry: str | None = None
        self.country: str | None = None
        self.market_cap: float | None = None
        self.close: float | None = None
        self.per: float | None = None
        self.pbr: float | None = None
        self.psr: float | None = None
        self.pcr: float | None = None
        self.ev_to_revenue: float | None = None
        self.ev_to_ebitda: float | None = None
        self.dividend_yield: float | None = None
        self.roe: float | None = None
        self.roa: float | None = None
        self.eps_growth: float | None = None
        self.revenue_growth: float | None = None
        self.insider_percent: float | None = None
        self.institution_percent: float | None = None
        self.pegr: float | None = None
        self.operating_cashflow: float | None = None
        self.revenue: float | None = None
        self.debt_to_equity: float | None = None
        self.eps: float | None = None
        self.net_income: float | None = None
        self.dividend_to_income: float | None = None
        self.ratio_3m: float | None = None
        self.ratio_6m: float | None = None
        self.ratio_1y: float | None = None
        self.turnover_3m: float | None = None
        self.turnover_1y: float | None = None
        self.turnover_10d: float | None = None
        self.overheat_3m: float | None = None
        self.overheat_10d: float | None = None
        self.volatility_3m: float | None = None
        self.volatility_1y: float | None = None
        self.buyback_yield: float | None = None
        self.interest_ratio: float | None = None
        self.debt_growth: float | None = None
        self.insider_buy_ratio: float | None = None
        self.arp: float | None = None
        self.depreciation_capex_ratio: float | None = None
        self.asset_to_equity: float | None = None
        self.coverage_ratio: float | None = None
        self.macd_signal: str | None = None
        self.rsi_signal: str | int | None = None
        self.rsi: str | None = None
        self.ma5: str | None = None
        self.ma20: str | None = None
        self.ma60: str | None = None
        self.ma120: str | None = None
        self.ma200: str | None = None
        self.ncav: float | None = None
        self.current_ratio: float | None = None
        self.roc: float | None = None
        self.gptoa: float | None = None
        self.asset_turnover: float | None = None
        self.pfcr: float | None = None
        self.buyback_to_income: float | None = None

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

        history = ticker_obj.history(period="1y")
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
        self.buyback_to_income = ((self.buyback_yield * self.close) / self.eps) / 100

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
        self.dividend_to_income = (self.dividend_yield * self.close / eps) / 100

    def _compute_technical_factors(self) -> None:
        history = _add_moving_averages(self.history)
        history = _add_macd(history)
        history = _add_rsi(history)
        self.history = history

        if history["macd"].iloc[-1] > history["signal"].iloc[-1]:
            self.macd_signal = "Heating"
            if history["macd"].iloc[-2] < history["signal"].iloc[-2]:
                self.macd_signal = "Heat Timing"
        else:
            self.macd_signal = "Cooling"
            if history["macd"].iloc[-2] > history["signal"].iloc[-2]:
                self.macd_signal = "Sell Timing"

        if (
            rsi_signal := history["RSI"].iloc[-1] > history["RSI_signal"].iloc[-1]
        ):
            rsi_signal = "Heating"
            if history["RSI"].iloc[-2] < history["RSI_signal"].iloc[-2]:
                rsi_signal = "Heat Timing"
        else:
            rsi_signal = 0
            if history["RSI"].iloc[-2] > history["RSI_signal"].iloc[-2]:
                rsi_signal = -1
        self.rsi_signal = rsi_signal

        if history["RSI"].iloc[-1] > RSI_OVERHEAT_THRESHOLD:
            self.rsi = "OVERHEAT"
        elif history["RSI"].iloc[-1] < RSI_UNDERHEAT_THRESHOLD:
            self.rsi = "UNDERHEAT"
        else:
            self.rsi = "NORMAL"

        self.ma5 = "Hit" if history["Close"].iloc[-1] > history["ma5"].iloc[-1] else "Miss"
        self.ma20 = "Hit" if history["Close"].iloc[-1] > history["ma20"].iloc[-1] else "Miss"
        self.ma60 = "Hit" if history["Close"].iloc[-1] > history["ma60"].iloc[-1] else "Miss"
        self.ma120 = "Hit" if history["Close"].iloc[-1] > history["ma120"].iloc[-1] else "Miss"
        self.ma200 = "Hit" if history["Close"].iloc[-1] > history["ma200"].iloc[-1] else "Miss"

        self.ratio_1y = (history["Close"].iloc[-1] / history["Close"].iloc[0]) * 100 - 100
        self.ratio_6m = (
            history["Close"].iloc[-1] / history["Close"].iloc[-RATIO_LOOKBACK_6M_DAYS]
        ) * 100 - 100
        self.ratio_3m = (
            history["Close"].iloc[-1] / history["Close"].iloc[-RATIO_LOOKBACK_3M_DAYS]
        ) * 100 - 100

        avgvol_1y = history["Volume"][-RATIO_LOOKBACK_1Y_DAYS:].mean()
        avgvol_3m = history["Volume"][-RATIO_LOOKBACK_3M_DAYS:].mean()
        avgvol_10d = history["Volume"][-VOLUME_LOOKBACK_10D_DAYS:].mean()
        money_10d = avgvol_10d * history["Close"].iloc[-1]
        money_3m = avgvol_3m * history["Close"].iloc[-1]
        money_1y = avgvol_1y * history["Close"].iloc[-1]
        self.turnover_1y = money_1y / self.market_cap
        self.turnover_3m = money_3m / self.market_cap
        self.turnover_10d = money_10d / self.market_cap
        self.overheat_10d = self.turnover_10d / self.turnover_3m
        self.overheat_3m = self.turnover_3m / self.turnover_1y
        self.volatility_3m = (
            history["Close"][-RATIO_LOOKBACK_3M_DAYS:].pct_change().abs().mean()
        )
        self.volatility_1y = (
            history["Close"][-RATIO_LOOKBACK_1Y_DAYS:].pct_change().abs().mean()
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
        self.insider_buy_ratio = (
            (net_shares_purchased * self.history["Close"].iloc[0] / self.market_cap * 100)
            if net_shares_purchased is not None
            else None
        )

    def to_row(self) -> dict:
        """raw(출처별 접두사) + curated 데이터를 하나의 dict(표의 한 행)로 합친다."""
        row: dict = {}
        row.update(self._raw_info_row())
        row.update(self._raw_statement_row("raw_cashflow", self.cashflow))
        row.update(self._raw_statement_row("raw_financials", self.financials))
        row.update(self._raw_statement_row("raw_balance_sheet", self.balance_sheet))
        row.update(self._raw_insider_row())
        row.update(self._raw_history_row())
        row.update(self._curated_row())
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

    def _raw_history_row(self) -> dict:
        if self.history.empty:
            return {}
        latest = self.history.iloc[-1]
        return {f"raw_history__{name}": value for name, value in latest.items()}

    def _curated_row(self) -> dict:
        return {column: getattr(self, attribute) for column, attribute in CURATED_COLUMNS}
