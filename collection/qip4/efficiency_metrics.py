"""효율성 감사(승수)가 쓰는 경보 지표.

원 규칙의 경보 4개 중 3개(재고·채권·CCC)는 종목 하나만 보면 판정할 수 있어 여기서
계산한다. **발생액 경보만 "업종 상위 10%"라 횡단면**이라 `analysis/qip4_gate.py`가
맡는다 — 여기서는 발생액 원시값만 낸다.

원 규칙은 "2분기 연속"을 요구하지만 분기 데이터가 5~7개뿐이라 YoY 증가율을 2번
연속 구하려면 최소 8분기가 필요하다. 그래서 분기가 충분하면 분기로, 아니면 연간
2개년으로 판정한다(성장 연속성과 같은 하이브리드 방식).

재고 경보 해제 조건도 바뀌었다. 원 규칙은 수주잔고 증가를 해제 조건으로 두지만
수주잔고는 정기 공시 항목이 아니라 사업보고서 본문에만 있어 수집할 수 없다.
대신 **선수금 증가**를 쓴다 — 수주잔고 증가의 실질 대리 변수이고 한국 현금흐름표에
실제로 있다(`401820`). 미국은 해당 항목이 없어 해제가 불가능하다.
"""

from dataclasses import dataclass

from collection.qip4.series_adapter import FinancialSeries

# 경보 판정에 필요한 최소 분기 수. YoY 증가율을 2회 연속 구하려면
# (t, t-4), (t-1, t-5) → 6개가 필요하다.
MIN_QUARTERS_FOR_ALARM: int = 6
# YoY 비교 간격(분기).
QUARTERS_PER_YEAR: int = 4
# 연간 대체 판정에 필요한 최소 연수.
MIN_YEARS_FOR_ALARM: int = 3
# 재고·채권 증가율이 매출 증가율을 이만큼(%p) 넘어서면 경보.
ALARM_GAP_THRESHOLD: float = 0.10
# CCC 추세를 보는 기간 수.
CCC_WINDOW: int = 3
# 회전일수 환산에 쓰는 1년 일수.
DAYS_PER_YEAR: float = 365.0


@dataclass(frozen=True)
class EfficiencyMetrics:
    """효율성 경보 입력값. 판정 불가한 항목은 None."""

    inventory_alarm: bool | None
    receivables_alarm: bool | None
    ccc_deteriorating: bool | None
    accrual_ratio: float | None
    advances_growing: bool | None


def _paired_growth_gap(
    numerator: dict[str, float], revenue: dict[str, float], lag: int
) -> list[float] | None:
    """같은 기간에 대해 (항목 증가율 − 매출 증가율)을 최신순으로 반환한다.

    `lag`는 비교 간격이다 — 분기면 4(전년 동기), 연간이면 1(전년).
    계절성을 피하려고 분기는 QoQ가 아니라 YoY로 본다.
    """
    periods = sorted(set(numerator) & set(revenue), reverse=True)
    gaps: list[float] = []
    for index, period in enumerate(periods):
        past_index = index + lag
        if past_index >= len(periods):
            break
        past = periods[past_index]
        if numerator[past] <= 0 or revenue[past] <= 0:
            continue
        item_growth = numerator[period] / numerator[past] - 1
        revenue_growth = revenue[period] / revenue[past] - 1
        gaps.append(item_growth - revenue_growth)
    return gaps or None


def _alarm(series: FinancialSeries, metric: str) -> bool | None:
    """항목 증가율이 매출 증가율을 2기 연속 10%p 넘게 앞질렀는가.

    분기가 충분하면 분기(YoY), 아니면 연간으로 본다.
    """
    quarterly_item = series.quarterly(metric)
    quarterly_revenue = series.quarterly("revenue")
    if (
        len(quarterly_item) >= MIN_QUARTERS_FOR_ALARM
        and len(quarterly_revenue) >= MIN_QUARTERS_FOR_ALARM
    ):
        gaps = _paired_growth_gap(quarterly_item, quarterly_revenue, QUARTERS_PER_YEAR)
    else:
        annual_item = series.annual(metric)
        annual_revenue = series.annual("revenue")
        if len(annual_item) < MIN_YEARS_FOR_ALARM or len(annual_revenue) < MIN_YEARS_FOR_ALARM:
            return None
        gaps = _paired_growth_gap(annual_item, annual_revenue, 1)

    if gaps is None or len(gaps) < 2:
        return None
    return all(gap > ALARM_GAP_THRESHOLD for gap in gaps[:2])


def _cash_conversion_cycle(series: FinancialSeries) -> list[float] | None:
    """현금전환주기(DSO + DIO − DPO) 시계열을 오래된 순으로 반환한다."""
    revenue = series.annual("revenue")
    cogs = series.annual("cogs")
    inventory = series.annual("inventory")
    receivables = series.annual("receivables")
    payables = series.annual("payables")

    periods = sorted(
        set(revenue) & set(cogs) & set(inventory) & set(receivables) & set(payables)
    )[-CCC_WINDOW:]
    cycles: list[float] = []
    for period in periods:
        if revenue[period] <= 0 or cogs[period] <= 0:
            continue
        days_sales_outstanding = receivables[period] / revenue[period] * DAYS_PER_YEAR
        days_inventory = inventory[period] / cogs[period] * DAYS_PER_YEAR
        days_payable = payables[period] / cogs[period] * DAYS_PER_YEAR
        cycles.append(days_sales_outstanding + days_inventory - days_payable)
    return cycles or None


def _ccc_deteriorating(series: FinancialSeries) -> bool | None:
    """현금전환주기가 2기 연속 악화(증가)했는가 — 운전자본 관리 실패 신호."""
    cycles = _cash_conversion_cycle(series)
    if cycles is None or len(cycles) < CCC_WINDOW:
        return None
    return cycles[-1] > cycles[-2] > cycles[-3]


def _accrual_ratio(series: FinancialSeries) -> float | None:
    """(순이익 − 영업CF) ÷ 총자산. 이익과 현금의 괴리.

    기존 `ARP` 팩터는 분모가 시가총액이라 규칙이 요구하는 총자산 기준과 다르다.
    업종 상위 10% 판정은 횡단면이라 `analysis/`가 맡고 여기서는 원시값만 낸다.
    """
    net_income = series.latest_annual("net_income")
    operating_cash_flow = series.latest_annual("operating_cash_flow")
    assets = series.latest_annual("total_assets")
    if net_income is None or operating_cash_flow is None or assets is None or assets <= 0:
        return None
    return (net_income - operating_cash_flow) / assets


def _advances_growing(series: FinancialSeries) -> bool | None:
    """선수금이 늘고 있는가 — 수주잔고 증가의 대리 변수(재고 경보 해제 조건).

    한국 현금흐름표에만 있는 항목이라 미국은 항상 None(해제 불가)이다.
    """
    # 이 계정("선수금의증가")은 잔액이 아니라 이미 증감액이므로 값 하나로 판정된다.
    latest = series.latest_annual("advances_received")
    if latest is None:
        return None
    return latest > 0


def compute_efficiency_metrics(series: FinancialSeries) -> EfficiencyMetrics:
    """효율성 경보 입력값을 한 번에 계산한다."""
    return EfficiencyMetrics(
        inventory_alarm=_alarm(series, "inventory"),
        receivables_alarm=_alarm(series, "receivables"),
        ccc_deteriorating=_ccc_deteriorating(series),
        accrual_ratio=_accrual_ratio(series),
        advances_growing=_advances_growing(series),
    )
