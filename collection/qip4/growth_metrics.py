"""성장성 축이 쓰는 다년 지표.

원 규칙의 "유기적 성장(매출 성장률 − 인수 기여분 − 환율 효과)"은 구현하지 않는다 —
인수가 매출에 얼마나 기여했는지는 사업보고서 서술에만 있고, 현금흐름표의
환율변동효과는 **현금 환산차이**지 매출 환산효과가 아니라 대입하면 틀린 값이 나온다.
대신 인수 지출 규모를 플래그로 남겨 정성 검토 대상임을 알린다(`.claude/투자 규칙.md`).

"성장 연속성"의 원 규칙은 12분기 YoY지만 그러려면 16분기가 필요하고 지금은 5~7분기뿐이다.
여기서는 **연간 기준 대체값**만 계산하고, 분기가 충분히 쌓이면
`collection/qip4_history.py`가 12분기 기준으로 덮어쓴다(하이브리드 자동 승격).
"""

from dataclasses import dataclass
from statistics import mean, pstdev

from collection.qip4.series_adapter import FinancialSeries, recent_values

# 성장 지표가 보는 회계연도 수.
GROWTH_WINDOW_YEARS: int = 3
# 변동계수는 표본 3개로는 통계적으로 너무 얕아 5개년(성장률 4개)을 쓴다.
VOLATILITY_WINDOW_YEARS: int = 5
# 연간 대체 기준의 성장 연속성이 보는 연수 (YoY 4회 → 5개년 필요).
CONTINUITY_WINDOW_YEARS: int = 5
# 성장률 계산에 최소한 필요한 기간 수.
MIN_PERIODS_REQUIRED: int = 3

# 성장 연속성을 어느 기준으로 판정했는지 나타내는 라벨. 화면에 그대로 노출된다.
CONTINUITY_BASIS_ANNUAL: str = "연간"
CONTINUITY_BASIS_QUARTERLY: str = "분기"


@dataclass(frozen=True)
class GrowthMetrics:
    """성장성 축의 원시 입력값. 계산 불가한 항목은 None."""

    revenue_growth_volatility: float | None
    capital_intensity: float | None
    growth_self_funding: float | None
    revenue_cagr: float | None
    margin_direction: str | None
    growth_continuity: float | None
    growth_continuity_basis: str | None


def _growth_rates(values: list[float]) -> list[float]:
    """연속한 값들의 기간별 성장률. 직전 값이 0 이하인 구간은 건너뛴다
    (적자·무매출 구간에서 성장률이 폭주하는 것을 막는다)."""
    rates = []
    for previous, current in zip(values, values[1:]):
        if previous > 0:
            rates.append(current / previous - 1)
    return rates


def _invested_capital(series: FinancialSeries) -> dict[str, float]:
    """투하자본 시계열. 야후는 계정이 그대로 있고, 네이버는 직접 조립한다.

    투하자본 = 자기자본 + 이자발생부채 − 현금
    """
    direct = series.annual("invested_capital")
    if direct:
        return direct

    equity = series.annual("total_equity")
    debt = series.annual("total_debt")
    cash = series.annual("cash")
    periods = set(equity) & set(debt) & set(cash)
    return {period: equity[period] + debt[period] - cash[period] for period in periods}


def _revenue_growth_volatility(series: FinancialSeries) -> float | None:
    """매출 성장률의 변동계수(표준편차 ÷ 평균). 낮을수록 성장이 고르다."""
    revenues = recent_values(series.annual("revenue"), VOLATILITY_WINDOW_YEARS)
    rates = _growth_rates(revenues)
    if len(rates) < 2:
        return None
    average = mean(rates)
    # 평균 성장률이 0 이하이면 변동계수의 부호가 뒤집혀 "고른 성장"과
    # "고르게 역성장"이 구분되지 않는다 → 산출 제외.
    if average <= 0:
        return None
    return pstdev(rates) / average


def _capital_intensity(series: FinancialSeries) -> float | None:
    """Δ투하자본 ÷ Δ매출. 매출 1원을 더 벌기 위해 자본을 얼마나 넣었는가.

    업종마다 자릿수가 달라 **업종 내 상대 비교로만** 의미가 있다(반도체와 소프트웨어를
    같은 잣대로 볼 수 없다). Δ매출이 0 이하이면 분모 부호가 뒤집혀 의미가 파괴되므로
    산출하지 않는다.
    """
    revenues = recent_values(series.annual("revenue"), GROWTH_WINDOW_YEARS)
    capitals = recent_values(_invested_capital(series), GROWTH_WINDOW_YEARS)
    if len(revenues) < MIN_PERIODS_REQUIRED or len(capitals) < MIN_PERIODS_REQUIRED:
        return None
    revenue_delta = revenues[-1] - revenues[0]
    if revenue_delta <= 0:
        return None
    return (capitals[-1] - capitals[0]) / revenue_delta


def _growth_self_funding(series: FinancialSeries) -> float | None:
    """3년 누적 영업CF ÷ 3년 누적 (설비투자 + 배당 + 이자).

    1을 넘으면 남의 돈 없이 스스로 크는 회사다. 유상증자·차입 위험이 구조적으로 낮다.

    이자는 한국이 **실제 현금 지급액**(402100), 미국은 현금흐름표에 항목이 없어
    발생주의 이자비용을 쓴다 — 시장 간 미세한 정의 차이가 있다.
    """
    inflow = recent_values(series.annual("operating_cash_flow"), GROWTH_WINDOW_YEARS)
    if len(inflow) < MIN_PERIODS_REQUIRED:
        return None

    interest = series.annual("interest_paid") or series.annual("interest_expense")
    outflow = 0.0
    for metric_series in (
        series.annual("capex"),
        series.annual("dividends_paid"),
        interest,
    ):
        outflow += sum(recent_values(metric_series, GROWTH_WINDOW_YEARS))
    if outflow <= 0:
        return None
    return sum(inflow) / outflow


def _revenue_cagr(series: FinancialSeries) -> float | None:
    """매출 연평균 성장률. 구조적 역성장(음수) 판정에 쓴다."""
    revenues = recent_values(series.annual("revenue"), CONTINUITY_WINDOW_YEARS)
    if len(revenues) < MIN_PERIODS_REQUIRED or revenues[0] <= 0:
        return None
    years = len(revenues) - 1
    return (revenues[-1] / revenues[0]) ** (1 / years) - 1


def _margin_direction(series: FinancialSeries) -> str | None:
    """매출이 성장하는 동안 영업이익률이 유지·상승했는가 → 가격결정력의 증거.

    "Y"/"N"으로 낸다 (`financial_trend.evaluate_uptrend`와 같은 표기 규약).
    """
    revenues = recent_values(series.annual("revenue"), GROWTH_WINDOW_YEARS)
    incomes = recent_values(series.annual("operating_income"), GROWTH_WINDOW_YEARS)
    if len(revenues) < MIN_PERIODS_REQUIRED or len(incomes) < MIN_PERIODS_REQUIRED:
        return None
    if revenues[0] <= 0 or revenues[-1] <= revenues[0]:
        return None  # 매출이 늘지 않았으면 "성장 중 마진 방향"이라는 질문이 성립하지 않는다
    return "Y" if incomes[-1] / revenues[-1] >= incomes[0] / revenues[0] else "N"


def _annual_growth_continuity(series: FinancialSeries) -> tuple[float | None, str | None]:
    """연간 기준 성장 연속성 — YoY 플러스 연수의 **비율**(0~1).

    분기 기준(12분기 중 플러스 분기 수)과 척도를 맞추려고 개수가 아니라 비율로 낸다.
    분기가 16개 이상 쌓이면 같은 척도의 분기 기준 값으로 대체된다.
    """
    revenues = recent_values(series.annual("revenue"), CONTINUITY_WINDOW_YEARS)
    rates = _growth_rates(revenues)
    if len(rates) < 2:
        return None, None
    positive = sum(1 for rate in rates if rate > 0)
    return positive / len(rates), CONTINUITY_BASIS_ANNUAL


def compute_growth_metrics(series: FinancialSeries) -> GrowthMetrics:
    """성장성 축 입력값을 한 번에 계산한다."""
    continuity, basis = _annual_growth_continuity(series)
    return GrowthMetrics(
        revenue_growth_volatility=_revenue_growth_volatility(series),
        capital_intensity=_capital_intensity(series),
        growth_self_funding=_growth_self_funding(series),
        revenue_cagr=_revenue_cagr(series),
        margin_direction=_margin_direction(series),
        growth_continuity=continuity,
        growth_continuity_basis=basis,
    )
