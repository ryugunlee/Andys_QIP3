"""안정성 관문(S1~S3, 상환연수, 실질 자기자본)이 쓰는 **원시 숫자**를 계산한다.

여기서 합격/탈락을 판정하지 않는다. 0.7 / 5년 / 0.75 같은 임계값은
`analysis/qip4_gate.py`가 판정한다 — 그래야 규칙이 바뀌어도 몇 시간짜리 재수집 없이
재채점만으로 반영된다.

조정 순부채는 **시장별로 정의가 다르다.** 원 규칙의 5개 구성요소 중 계열사 지급보증·
전환사채·특수관계자 대여금은 재무제표 **주석**에만 있어 어느 소스에서도 못 얻는다.
관측 가능한 것만으로 축소하되, 야후는 `Total Debt`에 리스부채가 이미 포함돼 있어
(CAT 실측: 장기+유동 = Total Debt) 별도로 더하면 이중계상이 된다.
→ 두 시장의 상환연수를 직접 비교하면 안 된다 (PROBLEMS #9와 같은 종류의 함정).
"""

from dataclasses import dataclass

from collection.qip4.series_adapter import FinancialSeries, recent_values

# 관문 판정에 쓰는 회계연도 수. 원 규칙이 "3년"을 기준으로 쓴다.
GATE_YEARS: int = 3
# S1/S2 판정에 최소한 필요한 연도 수. 이보다 적으면 판정을 유보한다
# (신규 상장사를 데이터 부족만으로 탈락시키지 않기 위해).
MIN_YEARS_REQUIRED: int = 3
# 이자보상배율 연속 미달 판정 기간.
INTEREST_COVERAGE_YEARS: int = 2
# 이자비용이 이 값 이하이면 "무차입 = 해당 없음"으로 보고 S3를 통과시킨다.
NEGLIGIBLE_INTEREST: float = 0.0


@dataclass(frozen=True)
class StabilityMetrics:
    """안정성 관문 입력값. 계산 불가한 항목은 None(판정 유보)이다."""

    operating_cf_negative_years: int | None
    cash_conversion_3y: float | None
    interest_coverage_below_one_years: int | None
    adjusted_net_debt: float | None
    debt_repayment_years: float | None
    # 상환연수의 분모. 상환연수가 inf일 때 그 원인이 "재원 없음"임을 화면에서
    # 설명하려면 분모 자체가 필요하다.
    average_operating_cash_flow: float | None
    tangible_equity_ratio: float | None
    goodwill_to_assets: float | None


def _sum_or_none(values: list[float], required: int) -> float | None:
    """`required`개가 모두 있을 때만 합계를 반환한다."""
    return sum(values) if len(values) >= required else None


def _operating_cf_negative_years(series: FinancialSeries) -> int | None:
    """최근 3년 중 영업활동현금흐름이 음수인 연도 수."""
    values = recent_values(series.annual("operating_cash_flow"), GATE_YEARS)
    if len(values) < MIN_YEARS_REQUIRED:
        return None
    return sum(1 for value in values if value < 0)


def _cash_conversion(series: FinancialSeries) -> float | None:
    """3년 누적 영업CF ÷ 3년 누적 순이익.

    **누적 순이익이 0 이하이면 None을 반환한다.** 분모가 음수면 비율이 음수가 되어
    "0.7 미만"에 걸려 자동 탈락하는데, 그건 이미 S1이 잡는 영역이고 감가상각이 큰
    초기 인프라 기업을 억울하게 죽인다.
    """
    cash_flows = recent_values(series.annual("operating_cash_flow"), GATE_YEARS)
    net_incomes = recent_values(series.annual("net_income"), GATE_YEARS)
    cumulative_cf = _sum_or_none(cash_flows, MIN_YEARS_REQUIRED)
    cumulative_income = _sum_or_none(net_incomes, MIN_YEARS_REQUIRED)
    if cumulative_cf is None or cumulative_income is None or cumulative_income <= 0:
        return None
    return cumulative_cf / cumulative_income


def _interest_coverage_below_one_years(series: FinancialSeries) -> int | None:
    """최근 2년 중 이자보상배율이 1 미만인 **연속** 연도 수.

    이자비용이 0이거나 없으면 무차입 기업이므로 0(=미달 없음)을 반환한다 —
    결측을 탈락으로 다루면 무차입 우량기업이 걸린다.
    """
    operating_incomes = recent_values(
        series.annual("operating_income"), INTEREST_COVERAGE_YEARS
    )
    interests = recent_values(series.annual("interest_expense"), INTEREST_COVERAGE_YEARS)
    if not operating_incomes:
        return None
    if not interests or all(value <= NEGLIGIBLE_INTEREST for value in interests):
        return 0

    below = 0
    for operating_income, interest in zip(operating_incomes, interests):
        if interest <= NEGLIGIBLE_INTEREST:
            continue
        if operating_income / interest < 1:
            below += 1
    return below


def _adjusted_net_debt(series: FinancialSeries, source: str) -> float | None:
    """조정 순부채. 시장별로 관측 가능한 항목만 더한다."""
    total_debt = series.latest_annual("total_debt")
    cash = series.latest_annual("cash")
    if total_debt is None or cash is None:
        return None

    if source == "yahoo":
        # Total Debt에 리스부채가 이미 포함돼 있어 별도 가산하면 이중계상이다.
        # 운용리스 부채(ASC842)는 아예 잡히지 않아 과소평가된다 — 정성 평가로 이관.
        return total_debt - cash

    lease = series.latest_annual("lease_liability") or 0.0
    lease_current = series.latest_annual("lease_liability_current") or 0.0
    benefit_obligation = series.latest_annual("employee_benefit_obligation") or 0.0
    pension_assets = series.latest_annual("pension_plan_assets") or 0.0
    unfunded_benefit = max(benefit_obligation - pension_assets, 0.0)
    return total_debt + lease + lease_current + unfunded_benefit - cash


def _debt_repayment_years(
    series: FinancialSeries, adjusted_net_debt: float | None
) -> float | None:
    """조정 순부채 ÷ 3년 평균 영업현금흐름.

    순부채가 0 이하(순현금)면 0년. 평균 영업CF가 0 이하이면 상환 불가이므로
    `float("inf")`를 반환해 임계값 판정에서 탈락하게 한다.
    """
    if adjusted_net_debt is None:
        return None
    if adjusted_net_debt <= 0:
        return 0.0

    cash_flows = recent_values(series.annual("operating_cash_flow"), GATE_YEARS)
    if len(cash_flows) < MIN_YEARS_REQUIRED:
        return None
    average_cf = sum(cash_flows) / len(cash_flows)
    if average_cf <= 0:
        return float("inf")
    return adjusted_net_debt / average_cf


def _tangible_equity_ratio(series: FinancialSeries) -> float | None:
    """실질 자기자본 ÷ 자기자본. 실질 = 자기자본 − 영업권 − 이연법인세자산.

    원 규칙은 자산화된 개발비·특수관계자 대여금도 뺐지만 두 항목 모두 어느 소스에서도
    분리되지 않는다(정성 이관). 차감 항목이 줄어든 만큼 임계값을 0.6이 아니라 0.75로
    올려 원 규칙의 엄격도를 보존한다 — 그 판정은 `analysis/qip4_gate.py`가 한다.
    """
    equity = series.latest_annual("total_equity")
    if equity is None or equity <= 0:
        return None
    goodwill = series.latest_annual("goodwill") or 0.0
    deferred_tax = series.latest_annual("deferred_tax_assets") or 0.0
    return (equity - goodwill - deferred_tax) / equity


def _goodwill_to_assets(series: FinancialSeries) -> float | None:
    """영업권 ÷ 총자산."""
    assets = series.latest_annual("total_assets")
    if assets is None or assets <= 0:
        return None
    return (series.latest_annual("goodwill") or 0.0) / assets


def _average_operating_cash_flow(series: FinancialSeries) -> float | None:
    """3년 평균 영업현금흐름 (상환연수의 분모).

    상환연수가 None일 때 "연도 수가 모자라 계산 불가"인지 "재원이 없어 무한대"인지를
    화면에서 구분하려면 분모 자체가 필요하다.
    """
    cash_flows = recent_values(series.annual("operating_cash_flow"), GATE_YEARS)
    if len(cash_flows) < MIN_YEARS_REQUIRED:
        return None
    return sum(cash_flows) / len(cash_flows)


def compute_stability_metrics(series: FinancialSeries, source: str) -> StabilityMetrics:
    """안정성 관문 입력값을 한 번에 계산한다."""
    adjusted_net_debt = _adjusted_net_debt(series, source)
    return StabilityMetrics(
        operating_cf_negative_years=_operating_cf_negative_years(series),
        cash_conversion_3y=_cash_conversion(series),
        interest_coverage_below_one_years=_interest_coverage_below_one_years(series),
        adjusted_net_debt=adjusted_net_debt,
        debt_repayment_years=_debt_repayment_years(series, adjusted_net_debt),
        average_operating_cash_flow=_average_operating_cash_flow(series),
        tangible_equity_ratio=_tangible_equity_ratio(series),
        goodwill_to_assets=_goodwill_to_assets(series),
    )
