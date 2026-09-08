"""데이터 소스(야후/네이버 등)와 무관한 curated 팩터 정의와 공통 계산 로직.

raw 데이터 수집(fetch)과 소스 고유 팩터 계산(재무제표 기반)은 하위 클래스
(`collection/stock.py`의 `YahooStock`, `collection/naver/naver_stock.py`의
`NaverStock`)가 구현한다. history(OHLCV DataFrame)만 있으면 계산 가능한 기술적
지표와 curated 컬럼 표현은 이 클래스가 전담해 두 소스가 동일한 로직을 공유한다.
"""

from datetime import date

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
# 컨센서스 이력(consensus_history) long format 컬럼 순서.
# storage/consensus_repository.py의 _CONSENSUS_COLUMNS와 반드시 같아야 한다.
CONSENSUS_COLUMNS: list[str] = [
    "ticker",
    "source",
    "observed_on",
    "fiscal_period",
    "item",
    "value",
]

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
    # --- 다년간 실적 오름세 판정 (Y/N/None, collection/financial_trend.py) ---
    ("Revenue Trend (5Y)", "revenue_trend_5y"),
    ("Operating Income Trend (5Y)", "operating_income_trend_5y"),
    # --- QIP4 안정성 관문 입력값 (collection/qip4/stability_metrics.py) ---
    # 여기 등록하지 않으면 storage/report_export.py의 _POPULATION_COLUMNS
    # 화이트리스트에서 걸러져 재채점 시 조용히 사라진다.
    ("QIP4 OCF Negative Years", "qip4_ocf_negative_years"),
    ("QIP4 Cash Conversion 3Y", "qip4_cash_conversion_3y"),
    ("QIP4 Interest Coverage Fail Years", "qip4_interest_coverage_fail_years"),
    ("QIP4 Adjusted Net Debt", "qip4_adjusted_net_debt"),
    ("QIP4 Debt Repayment Years", "qip4_debt_repayment_years"),
    ("QIP4 Average Operating CF", "qip4_average_operating_cf"),
    ("QIP4 Tangible Equity Ratio", "qip4_tangible_equity_ratio"),
    ("QIP4 Goodwill to Assets", "qip4_goodwill_to_assets"),
    # 자산형 전용 관문 입력값 (현금흐름 조건을 대체한다)
    ("QIP4 Equity Ratio", "qip4_equity_ratio"),
    ("QIP4 Net Loss Years", "qip4_net_loss_years"),
    # --- QIP4 성장성 (collection/qip4/growth_metrics.py) ---
    ("QIP4 Revenue Growth Volatility", "qip4_revenue_growth_volatility"),
    ("QIP4 Capital Intensity", "qip4_capital_intensity"),
    ("QIP4 Growth Self Funding", "qip4_growth_self_funding"),
    ("QIP4 Revenue CAGR", "qip4_revenue_cagr"),
    ("QIP4 Margin Direction", "qip4_margin_direction"),
    ("QIP4 Growth Continuity", "qip4_growth_continuity"),
    ("QIP4 Growth Continuity Basis", "qip4_growth_continuity_basis"),
    # --- QIP4 가치 (collection/qip4/value_metrics.py) ---
    ("QIP4 FCF Yield", "qip4_fcf_yield"),
    ("QIP4 EV to EBIT", "qip4_ev_to_ebit"),
    ("QIP4 Dividend Payout Yield", "qip4_dividend_payout_yield"),
    ("QIP4 Net Cash Years", "qip4_net_cash_years"),
    # --- QIP4 효율성 경보 (collection/qip4/efficiency_metrics.py) ---
    # 경보는 True/False/None인데 pandas에서 None이 섞이면 object dtype이 되어
    # DuckDB 컬럼이 VARCHAR로 굳는다. 이후 실수 UPDATE가 실패하므로 1.0/0.0/None
    # 실수로 저장한다 (storage/snapshot_repository.py의 _duckdb_type_for 참고).
    ("QIP4 Inventory Alarm", "qip4_inventory_alarm"),
    ("QIP4 Receivables Alarm", "qip4_receivables_alarm"),
    ("QIP4 CCC Deteriorating", "qip4_ccc_deteriorating"),
    ("QIP4 Accrual Ratio", "qip4_accrual_ratio"),
    ("QIP4 Advances Growing", "qip4_advances_growing"),
    # --- QIP4 섹터군 분류 (collection/sector_groups.py) ---
    ("QIP4 Sector Group", "qip4_sector_group"),
    ("QIP4 Leverage Tolerant", "qip4_leverage_tolerant"),
    # --- QIP4 이익 모멘텀 ---
    # 야후는 eps_trend가 90일 전 추정치를 직접 줘서 수집 시점에 채워진다.
    # 네이버는 과거 추정치를 주지 않아 여기서는 비고, consensus_history에 쌓인
    # 관측 이력으로 채점 직전에 채운다.
    ("QIP4 Earnings Revision", "qip4_earnings_revision"),
]

_RAW_COLUMN_PREFIX: str = "raw_"


def _as_float(value: bool | int | None) -> float | None:
    """불리언·정수를 실수로 바꾼다(None은 그대로).

    True/False/None이 섞인 컬럼은 pandas에서 object dtype이 되고, 그러면 DuckDB
    컬럼이 VARCHAR로 굳어 이후 실수 UPDATE가 실패한다. 실수로 통일해 그 함정을 피한다.
    """
    return None if value is None else float(value)


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
        # --- 다년간 실적 오름세 판정 (Y/N, 데이터 4개년 미만이면 None) ---
        self.revenue_trend_5y: str | None = None
        self.operating_income_trend_5y: str | None = None
        # QIP4 안정성 관문 입력값 (수집 후 _compute_qip4_factors가 채운다)
        self.qip4_ocf_negative_years: float | None = None
        self.qip4_cash_conversion_3y: float | None = None
        self.qip4_interest_coverage_fail_years: float | None = None
        self.qip4_adjusted_net_debt: float | None = None
        self.qip4_debt_repayment_years: float | None = None
        self.qip4_average_operating_cf: float | None = None
        self.qip4_tangible_equity_ratio: float | None = None
        self.qip4_goodwill_to_assets: float | None = None
        self.qip4_equity_ratio: float | None = None
        self.qip4_net_loss_years: float | None = None
        self.qip4_revenue_growth_volatility: float | None = None
        self.qip4_capital_intensity: float | None = None
        self.qip4_growth_self_funding: float | None = None
        self.qip4_revenue_cagr: float | None = None
        self.qip4_margin_direction: str | None = None
        self.qip4_growth_continuity: float | None = None
        self.qip4_growth_continuity_basis: str | None = None
        self.qip4_fcf_yield: float | None = None
        self.qip4_ev_to_ebit: float | None = None
        self.qip4_dividend_payout_yield: float | None = None
        self.qip4_net_cash_years: float | None = None
        self.qip4_inventory_alarm: float | None = None
        self.qip4_receivables_alarm: float | None = None
        self.qip4_ccc_deteriorating: float | None = None
        self.qip4_accrual_ratio: float | None = None
        self.qip4_advances_growing: float | None = None
        self.qip4_sector_group: str | None = None
        self.qip4_leverage_tolerant: float | None = None
        self.qip4_earnings_revision: float | None = None

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

    def compute_qip4_factors(self) -> None:
        """QIP4 안정성 관문 입력값을 채운다. 두 소스가 공유한다.

        `to_financial_statement_rows()`가 이미 소스 차이를 흡수한 long format을 주므로,
        여기서는 소스 이름만 넘기면 `FinancialSeries`가 나머지를 처리한다.
        관문 판정(임계값 비교)은 하지 않는다 — 그건 `analysis/qip4_gate.py`의 일이다.
        """
        # 순환 import를 피하려고 지연 import한다 (qip4가 stock_base를 참조하지는
        # 않지만, 수집 계층 안에서 의존 방향을 단순하게 유지하기 위함).
        from collection.qip4.efficiency_metrics import compute_efficiency_metrics
        from collection.qip4.growth_metrics import compute_growth_metrics
        from collection.qip4.series_adapter import FinancialSeries
        from collection.qip4.stability_metrics import compute_stability_metrics
        from collection.qip4.value_metrics import compute_value_metrics
        from collection.sector_groups import is_leverage_tolerant, sector_group

        series = FinancialSeries(self.to_financial_statement_rows(), self.SOURCE_NAME)

        stability = compute_stability_metrics(series, self.SOURCE_NAME)
        self.qip4_ocf_negative_years = stability.operating_cf_negative_years
        self.qip4_cash_conversion_3y = stability.cash_conversion_3y
        self.qip4_interest_coverage_fail_years = stability.interest_coverage_below_one_years
        self.qip4_adjusted_net_debt = stability.adjusted_net_debt
        self.qip4_debt_repayment_years = stability.debt_repayment_years
        self.qip4_average_operating_cf = stability.average_operating_cash_flow
        self.qip4_tangible_equity_ratio = stability.tangible_equity_ratio
        self.qip4_goodwill_to_assets = stability.goodwill_to_assets
        self.qip4_equity_ratio = stability.equity_ratio
        self.qip4_net_loss_years = _as_float(stability.net_loss_years)

        growth = compute_growth_metrics(series)
        self.qip4_revenue_growth_volatility = growth.revenue_growth_volatility
        self.qip4_capital_intensity = growth.capital_intensity
        self.qip4_growth_self_funding = growth.growth_self_funding
        self.qip4_revenue_cagr = growth.revenue_cagr
        self.qip4_margin_direction = growth.margin_direction
        self.qip4_growth_continuity = growth.growth_continuity
        self.qip4_growth_continuity_basis = growth.growth_continuity_basis

        value = compute_value_metrics(series, self.market_cap)
        self.qip4_fcf_yield = value.fcf_yield
        self.qip4_ev_to_ebit = value.ev_to_ebit
        self.qip4_dividend_payout_yield = value.dividend_payout_yield
        self.qip4_net_cash_years = _as_float(value.net_cash_years)

        efficiency = compute_efficiency_metrics(series)
        self.qip4_inventory_alarm = _as_float(efficiency.inventory_alarm)
        self.qip4_receivables_alarm = _as_float(efficiency.receivables_alarm)
        self.qip4_ccc_deteriorating = _as_float(efficiency.ccc_deteriorating)
        self.qip4_accrual_ratio = efficiency.accrual_ratio
        self.qip4_advances_growing = _as_float(efficiency.advances_growing)

        self.qip4_sector_group = sector_group(self.sector, self.industry)
        self.qip4_leverage_tolerant = _as_float(
            is_leverage_tolerant(self.sector, self.industry)
        )

    def to_consensus_rows(self, observed_on: date) -> pd.DataFrame:
        """관측일이 붙은 컨센서스 추정치를 long format으로 반환한다.

        컬럼: ticker, source, observed_on, fiscal_period, item, value —
        `storage.upsert_consensus_history`가 그대로 저장할 수 있는 형태다.

        컨센서스는 재수집할 때마다 값이 바뀌므로 `financial_statements`처럼
        덮어쓰면 과거 추정치가 사라진다. 이익 모멘텀이 그 과거 값을 쓰기 때문에
        관측일과 함께 따로 쌓는다.

        기본 구현은 빈 DataFrame이다 — 컨센서스를 주지 않는 소스도 있고,
        yfinance처럼 과거 추정치를 직접 주는 소스는 누적이 필요 없다.
        """
        return pd.DataFrame(columns=CONSENSUS_COLUMNS)

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
