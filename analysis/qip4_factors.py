"""QIP4가 새로 채점하는 팩터의 방향성 단일 소스.

기존 파이프라인이 이미 점수 컬럼({이름}S/SS/SecS…)을 만든 팩터는 여기 등록하지 않는다
— QIP4 컴포지트가 그 점수를 그대로 재사용한다 (PBR, Buyback Yield, Dividend Yield,
12-1Y Ratio, 6M Ratio 등). `analysis/qip3_factors.py`와 같은 규약이다.

방향성 선택 규칙(`analysis/factors.py`의 Direction 참고):
- 음수/0이 정상값일 수 있는 팩터는 `1/x`가 순서를 파괴하므로 RECIPROCAL이 아니라
  NEGATED를 쓴다. QIP4에서는 상환연수·자본집약도·변동계수·EV/EBIT·발생액이 여기 해당한다.
- 상환연수는 순현금 기업이 0, 상환 불가 기업이 inf라 값의 범위가 극단적이다.
  그래도 NEGATED면 순서는 보존된다(0이 가장 좋고 inf가 가장 나쁨).

**문자열 컬럼(관문 결과·성장 기준·섹터군)은 절대 여기 넣지 않는다** — 채점 엔진이
숫자를 기대하므로 넣으면 죽는다.
"""

from analysis.factors import Direction, FactorSpec

QIP4_SCORED_FACTORS: list[FactorSpec] = [
    # 성장성
    FactorSpec("QIP4 Growth Continuity", Direction.HIGHER_IS_BETTER),
    FactorSpec("QIP4 Growth Self Funding", Direction.HIGHER_IS_BETTER),
    FactorSpec("QIP4 Revenue CAGR", Direction.HIGHER_IS_BETTER),
    # 변동계수·자본집약도는 낮을수록 좋다. 0에 가까운 값이 정상이라 NEGATED.
    FactorSpec("QIP4 Revenue Growth Volatility", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("QIP4 Capital Intensity", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("QIP4 Relative Revenue Growth", Direction.HIGHER_IS_BETTER),
    # 가치
    FactorSpec("QIP4 FCF Yield", Direction.HIGHER_IS_BETTER),
    FactorSpec("QIP4 EV to EBIT", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("QIP4 Shareholder Yield", Direction.HIGHER_IS_BETTER),
    # 모멘텀 (선정에는 관여하지 않고 집행률만 정한다)
    FactorSpec("QIP4 Relative Strength", Direction.HIGHER_IS_BETTER),
    FactorSpec("QIP4 Earnings Revision", Direction.HIGHER_IS_BETTER),
]

# 재수집 이전 옛 스냅샷에는 없을 수 있는 원천 컬럼. 파이프라인 진입부에서
# 존재를 보장(없으면 NaN)해 KeyError로 사이트 빌드 전체가 죽는 것을 막는다.
QIP4_RAW_FACTOR_NAMES: list[str] = [spec.name for spec in QIP4_SCORED_FACTORS] + [
    "QIP4 OCF Negative Years",
    "QIP4 Cash Conversion 3Y",
    "QIP4 Interest Coverage Fail Years",
    "QIP4 Debt Repayment Years",
    "QIP4 Tangible Equity Ratio",
    "QIP4 Goodwill to Assets",
    "QIP4 Accrual Ratio",
    "QIP4 Inventory Alarm",
    "QIP4 Receivables Alarm",
    "QIP4 CCC Deteriorating",
    "QIP4 Advances Growing",
    "QIP4 Net Cash Years",
    "QIP4 Leverage Tolerant",
    "QIP4 Dividend Payout Yield",
]

# 채점하지 않고 그대로 실어 나르는 문자열 컬럼.
QIP4_TEXT_COLUMNS: list[str] = [
    "QIP4 Sector Group",
    "QIP4 Margin Direction",
    "QIP4 Growth Continuity Basis",
]
