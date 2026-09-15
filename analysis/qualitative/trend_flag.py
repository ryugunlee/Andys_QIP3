"""★ 플래그 — 설명되지 않는 주가 추세를 DB 수치로만 계산한다.

`.claude/정성 평가 규칙.md` 4절. 뉴스는 쓰지 않는다(주가 서술은 근거 금지). 6개월 수익률이 크게
움직였는데 최근 연간 영업이익 변화가 같은 방향이 아니거나 거의 없으면 플래그를 세운다.
점수가 아니라 "사람이 원인을 찾아라"는 신호다.
"""

from dataclasses import dataclass
from datetime import timedelta

import duckdb
import pandas as pd

import analysis.qualitative.weights as w
from collection.qip4.series_adapter import FinancialSeries, recent_values
from storage import get_financial_statements, get_price_history

_INCOME_YEARS: int = 2


@dataclass(frozen=True)
class TrendFlag:
    code: str | None
    return_6m: float | None
    income_change: float | None


def _return_6m(prices: pd.DataFrame) -> float | None:
    if prices.empty:
        return None
    prices = prices.sort_values("date")
    last = prices.iloc[-1]
    cutoff = pd.Timestamp(last["date"]) - timedelta(days=w.TREND_WINDOW_DAYS)
    earlier = prices[pd.to_datetime(prices["date"]) <= cutoff]
    if earlier.empty:
        return None
    base = float(earlier.iloc[-1]["close"])
    return float(last["close"]) / base - 1.0 if base > 0 else None


def _income_change(statements: pd.DataFrame, source: str) -> float | None:
    incomes = recent_values(FinancialSeries(statements, source).annual("operating_income"), _INCOME_YEARS)
    if len(incomes) < _INCOME_YEARS or incomes[0] <= 0:
        return None
    return incomes[-1] / incomes[0] - 1.0


def _flag_code(return_6m: float | None, income_change: float | None) -> str | None:
    if return_6m is None or income_change is None or abs(return_6m) < w.TREND_RETURN_MIN_ABS:
        return None
    explained = (
        abs(income_change) >= w.TREND_INCOME_CHANGE_FLAT_ABS
        and (income_change > 0) == (return_6m > 0)
    )
    if explained:
        return None
    return w.FLAG_UNEXPLAINED_UP if return_6m > 0 else w.FLAG_UNEXPLAINED_DOWN


def compute_trend_flag(conn: duckdb.DuckDBPyConnection, ticker: str, source: str) -> TrendFlag:
    return_6m = _return_6m(get_price_history(conn, ticker))
    income_change = _income_change(get_financial_statements(conn, ticker, source), source)
    return TrendFlag(_flag_code(return_6m, income_change), return_6m, income_change)
