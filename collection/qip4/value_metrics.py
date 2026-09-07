"""가치 축이 쓰는 지표.

원 규칙의 "주주환원수익률 = (배당 + 자사주 **소각**) ÷ 시총"에서 소각은 취득과
구분되지 않는다 — 현금흐름표는 자기주식 취득만 보여주고 그중 얼마를 소각했는지는
알려주지 않는다. 그래서 **순자사주매입** 기준으로 정의를 바꿨다
(기존 `Buyback Yield` 팩터가 이미 발행분을 차감하고 있어 그대로 쓴다).

EV는 미국이 `info["enterpriseValue"]`를 주지만, 두 시장이 같은 방식으로 계산되도록
여기서는 양쪽 모두 `시총 + 이자발생부채 − 현금`으로 직접 조립한다.
"""

from dataclasses import dataclass

from collection.qip4.series_adapter import FinancialSeries, recent_values

# 순현금 상태가 몇 년 이어졌는지 보는 기간 (밸류 트랩 보정 조건).
NET_CASH_WINDOW_YEARS: int = 3


@dataclass(frozen=True)
class ValueMetrics:
    """가치 축의 원시 입력값. 계산 불가한 항목은 None."""

    fcf_yield: float | None
    ev_to_ebit: float | None
    dividend_payout_yield: float | None
    net_cash_years: int | None


def _fcf_yield(series: FinancialSeries, market_cap: float | None) -> float | None:
    """(영업CF − 설비투자) ÷ 시가총액.

    현금 기준이라 조작 난이도가 가장 높은 가치 지표다. 분자가 음수면(잉여현금 유출)
    그대로 음수로 둔다 — 순위에서 아래로 가는 게 맞는 신호이기 때문이다.
    """
    if not market_cap or market_cap <= 0:
        return None
    operating_cash_flow = series.latest_annual("operating_cash_flow")
    capex = series.latest_annual("capex")
    if operating_cash_flow is None or capex is None:
        return None
    return (operating_cash_flow - capex) / market_cap


def _ev_to_ebit(series: FinancialSeries, market_cap: float | None) -> float | None:
    """기업가치 ÷ 영업이익. 자본구조 중립이고, EBITDA가 아니라 EBIT을 써서
    감가상각을 실제 비용으로 인정한다."""
    if not market_cap or market_cap <= 0:
        return None
    debt = series.latest_annual("total_debt")
    cash = series.latest_annual("cash")
    ebit = series.latest_annual("operating_income")
    if debt is None or cash is None or ebit is None or ebit <= 0:
        return None
    return (market_cap + debt - cash) / ebit


def _dividend_payout_yield(
    series: FinancialSeries, market_cap: float | None
) -> float | None:
    """배당 지급액 ÷ 시가총액.

    자사주 매입분은 기존 `Buyback Yield` 팩터가 이미 계산하므로 여기서 중복하지 않는다.
    주주환원수익률은 두 값을 `analysis/`에서 합쳐 만든다.
    """
    if not market_cap or market_cap <= 0:
        return None
    dividends = series.latest_annual("dividends_paid")
    if dividends is None:
        return None
    return dividends / market_cap


def _net_cash_years(series: FinancialSeries) -> int | None:
    """최근 3년 중 순현금(현금 > 이자발생부채) 상태였던 연도 수.

    주주환원이 0인데 순현금이 계속 쌓이면 자본배분을 하지 않는다는 뜻이라
    밸류 트랩 보정 대상이 된다.
    """
    cash = recent_values(series.annual("cash"), NET_CASH_WINDOW_YEARS)
    debt = recent_values(series.annual("total_debt"), NET_CASH_WINDOW_YEARS)
    if len(cash) < NET_CASH_WINDOW_YEARS or len(debt) < NET_CASH_WINDOW_YEARS:
        return None
    return sum(1 for held, owed in zip(cash, debt) if held > owed)


def compute_value_metrics(
    series: FinancialSeries, market_cap: float | None
) -> ValueMetrics:
    """가치 축 입력값을 한 번에 계산한다."""
    return ValueMetrics(
        fcf_yield=_fcf_yield(series, market_cap),
        ev_to_ebit=_ev_to_ebit(series, market_cap),
        dividend_payout_yield=_dividend_payout_yield(series, market_cap),
        net_cash_years=_net_cash_years(series),
    )
