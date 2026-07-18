"""QIP3 5요인 점수 체계가 새로 채점하는 팩터의 방향성 단일 소스.

기존 SCORED_FACTORS(analysis/factors.py)에 이미 방향성이 부여된 팩터는 여기서
다시 등록하지 않는다 — QIP3 컴포지트는 그 기존 점수 컬럼({이름}S/SS/Sec…)을
그대로 재사용한다. 이 목록은 "수집만 되고 스코어링이 연결되지 않았던" 신규 재무
팩터 10종과, 12-1 모멘텀 컬럼만 담는다 (.claude/DECISIONS.md 2026-07-18 후속).

방향성 규칙(analysis/factors.py Direction 참고):
- 순부채비율(Net Debt to Equity)·설비투자부담(Capex to Revenue)·유효법인세율은
  음수/0이 정상값일 수 있어 1/x(RECIPROCAL)가 순서를 파괴하므로 NEGATED(-x)를 쓴다.
- 유효법인세율은 이월결손금·일회성 세액공제로 극단값이 과거 부실 신호일 수 있어
  화면·섹터 비교용으로만 채점하고 어떤 컴포지트에도 넣지 않는다 (QUANT2.md 참고).
"""

from analysis.factors import Direction, FactorSpec

# 신규 채점 팩터 (기존 SCORED_FACTORS와 이름이 겹치지 않는 것만).
QIP3_SCORED_FACTORS: list[FactorSpec] = [
    FactorSpec("Operating Margin", Direction.HIGHER_IS_BETTER),
    FactorSpec("Net Margin", Direction.HIGHER_IS_BETTER),
    FactorSpec("Gross Margin", Direction.HIGHER_IS_BETTER),
    FactorSpec("Cash Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("Quick Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("Inventory Turnover", Direction.HIGHER_IS_BETTER),
    FactorSpec("Receivables Turnover", Direction.HIGHER_IS_BETTER),
    FactorSpec("Net Debt to Equity", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("Capex to Revenue", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("Effective Tax Rate", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("12-1Y Ratio", Direction.HIGHER_IS_BETTER),
]

# 컴포지트가 참조하지만 QIP3가 새로 채점하지 않는 팩터(=기존 파이프라인이 이미
# {이름}S/SS/Sec… 를 만든 팩터). 재수집 이전 옛 run 스냅샷에 원천 컬럼이 없을 수
# 있는 신규 팩터와 함께, 파이프라인 진입부에서 컬럼 존재를 보장(없으면 NaN)한다.
QIP3_RAW_FACTOR_NAMES: list[str] = [spec.name for spec in QIP3_SCORED_FACTORS]
