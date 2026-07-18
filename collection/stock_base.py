"""데이터 소스(야후/네이버 등)와 무관한 curated 팩터 정의와 공통 계산 로직.

raw 데이터 수집(fetch)과 소스 고유 팩터 계산(재무제표 기반)은 하위 클래스
(`collection/stock.py`의 `YahooStock`, `collection/naver/naver_stock.py`의
`NaverStock`)가 구현한다. history(OHLCV DataFrame)만 있으면 계산 가능한 기술적
지표와 curated 컬럼 표현은 이 클래스가 전담해 두 소스가 동일한 로직을 공유한다.
"""

import pandas as pd

from collection.constants import (
    RATIO_LOOKBACK_1M_DAYS,
    RATIO_LOOKBACK_1Y_DAYS,
    RATIO_LOOKBACK_3M_DAYS,
    RATIO_LOOKBACK_6M_DAYS,
    RSI_OVERHEAT_THRESHOLD,
    RSI_UNDERHEAT_THRESHOLD,
    VOLUME_LOOKBACK_10D_DAYS,
)
from collection.technical import add_macd, add_moving_averages, add_rsi, lookback_index

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
    ("12-1Y Ratio", "ratio_12_1y"),
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
    # --- 신규 팩터 (수집만, 아직 스코어링 미연결) ---
    ("Operating Margin", "operating_margin"),
    ("Net Margin", "net_margin"),
    ("Gross Margin", "gross_margin"),
    ("Net Debt to Equity", "net_debt_to_equity"),
    ("Cash Ratio", "cash_ratio"),
    ("Capex to Revenue", "capex_to_revenue"),
    ("Inventory Turnover", "inventory_turnover"),
    ("Quick Ratio", "quick_ratio"),
    ("Effective Tax Rate", "effective_tax_rate"),
    ("Receivables Turnover", "receivables_turnover"),
]

_RAW_COLUMN_PREFIX: str = "raw_"


def split_raw_and_curated(row: dict) -> tuple[dict, dict]:
    """`to_row()` 결과를 raw_* 접두사 여부로 나눈다.

    DuckDB에는 curated+점수만 담는 넓은 typed 테이블(snapshot_factors)과, 소스별
    raw 원본을 종목당 최신본만 담는 JSON 테이블(raw_latest)을 분리해서 저장하므로
    (자세한 이유는 storage/database.py 참고) 이 둘을 나누는 지점이 필요하다.
    """
    raw = {key: value for key, value in row.items() if key.startswith(_RAW_COLUMN_PREFIX)}
    curated = {key: value for key, value in row.items() if not key.startswith(_RAW_COLUMN_PREFIX)}
    return raw, curated


class BaseStock:
    """종목 하나의 curated 팩터 컨테이너 + 소스 공용 계산 로직."""

    # 하위 클래스가 재정의: financial_statements/raw_latest 테이블의 source 컬럼 값.
    SOURCE_NAME: str = ""

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.is_valid: bool = False

        self.history: pd.DataFrame = pd.DataFrame()

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
        self.ratio_12_1y: float | None = None
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
        # --- 신규 팩터 (수집만, 아직 스코어링 미연결) ---
        self.operating_margin: float | None = None
        self.net_margin: float | None = None
        self.gross_margin: float | None = None
        self.net_debt_to_equity: float | None = None
        self.cash_ratio: float | None = None
        self.capex_to_revenue: float | None = None
        self.inventory_turnover: float | None = None
        self.quick_ratio: float | None = None
        self.effective_tax_rate: float | None = None
        self.receivables_turnover: float | None = None

    def _compute_technical_factors(self) -> None:
        history = add_moving_averages(self.history)
        history = add_macd(history)
        history = add_rsi(history)
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

        one_year_ago = lookback_index(history, RATIO_LOOKBACK_1Y_DAYS)
        self.ratio_1y = (history["Close"].iloc[-1] / history["Close"].iloc[one_year_ago]) * 100 - 100
        # 12-1 모멘텀: 최근 1개월을 제외한 12개월 수익률(단기 반전 회피, Jegadeesh-Titman)
        self.ratio_12_1y = (
            history["Close"].iloc[-RATIO_LOOKBACK_1M_DAYS] / history["Close"].iloc[one_year_ago]
        ) * 100 - 100
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

    def _compute_buyback_to_income(self) -> None:
        """buyback_yield/close/eps 중 하나라도 없으면(예: 네이버는 buyback_yield를
        계산하지 않음) 결측으로 남긴다."""
        if self.buyback_yield is not None and self.close is not None and self.eps is not None:
            self.buyback_to_income = ((self.buyback_yield * self.close) / self.eps) / 100
        else:
            self.buyback_to_income = None

    def _curated_row(self) -> dict:
        return {column: getattr(self, attribute) for column, attribute in CURATED_COLUMNS}

    def _raw_history_row(self) -> dict:
        """history 마지막 행(기술적 지표 계산 후 컬럼이 추가된 상태)을 raw_history__
        접두사 dict로 반환한다. history 컬럼 구성은 소스와 무관하게 동일하다."""
        if self.history.empty:
            return {}
        latest = self.history.iloc[-1]
        return {f"raw_history__{name}": value for name, value in latest.items()}

    def _raw_row(self) -> dict:
        """소스별 raw 데이터를 접두사 붙은 dict로 반환한다. 하위 클래스가 구현해야 한다."""
        raise NotImplementedError

    def to_financial_statement_rows(self) -> pd.DataFrame:
        """long format(ticker, source, statement_type, period, item, value, is_consensus)
        재무제표를 반환한다. `storage.upsert_financial_statements`가 그대로 저장할 수
        있는 형태다. 하위 클래스가 구현해야 한다."""
        raise NotImplementedError

    def _with_identity_columns(self, rows: pd.DataFrame) -> pd.DataFrame:
        """long format 재무제표 앞에 ticker/source 컬럼을 붙인다."""
        if rows.empty:
            return rows
        rows = rows.copy()
        rows.insert(0, "ticker", self.ticker)
        rows.insert(1, "source", self.SOURCE_NAME)
        return rows

    def to_row(self) -> dict:
        """raw(출처별 접두사) + curated 데이터를 하나의 dict(표의 한 행)로 합친다."""
        row: dict = {}
        row.update(self._raw_row())
        row.update(self._curated_row())
        return row
