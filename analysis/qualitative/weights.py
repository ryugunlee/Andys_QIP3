"""정성 등급 체계의 가중치·밴드·배수·임계값 단일 소스.

원문은 `.claude/정성 평가 규칙.md`. 문서가 스스로 밝히듯 **모든 임계값은 설계 추론**이며
파일럿 10종목 실측 후 1차 개정 대상이다. 그래서 `qip4_weights.py`와 같은 이유로 한 파일에
모은다 — 값을 바꿔도 관측값 JSON은 그대로 두고 재판정만 하면 된다.

QIP4 정량 체계와 맞지 않아 **1단계에서 보류**한 규칙(문서 6-4 태그 교차, 7-5, 8-1 티어,
6-3 비중 계산, ⑤-3 국면 가중치)은 여기에 없다. 사유는 `.claude/정성 평가 규칙.md`의
「QIP4 번역표」 참고.
"""

from collection.sector_groups import GROUP_CYCLICAL

# --- 축 가중 (합 1.0) ---
AXIS_WEIGHTS: dict[str, float] = {
    "G": 0.20, "C": 0.15, "D": 0.25, "P": 0.15, "I": 0.15, "X": 0.10,
}

# --- 항목 점수 ---
ITEM_MAX_POINTS: int = 2
# 증거가 3~4급뿐이거나 인용 대조에 실패한(weak) 항목은 이 점수를 넘지 못한다.
WEAK_ITEM_MAX_POINTS: int = 1

# --- 등급 밴드 (달성률 이상 기준, 위에서부터 첫 일치) ---
GRADE_SPLUS: str = "S+"
GRADE_S: str = "S"
GRADE_A: str = "A"
GRADE_B: str = "B"
GRADE_C: str = "C"
GRADE_D: str = "D"
GRADE_F: str = "F"
GRADE_NA: str = "NA"

AXIS_BANDS: tuple[tuple[float, str], ...] = (
    (0.90, GRADE_SPLUS), (0.80, GRADE_S), (0.70, GRADE_A), (0.60, GRADE_B),
    (0.45, GRADE_C), (0.30, GRADE_D), (0.00, GRADE_F),
)
GRADE_SCORE: dict[str, float] = {
    GRADE_SPLUS: 95, GRADE_S: 85, GRADE_A: 75, GRADE_B: 65,
    GRADE_C: 50, GRADE_D: 30, GRADE_F: 0,
}
COMPOSITE_BANDS: tuple[tuple[float, str], ...] = (
    (90, GRADE_SPLUS), (82, GRADE_S), (74, GRADE_A), (65, GRADE_B),
    (55, GRADE_C), (40, GRADE_D), (0, GRADE_F),
)
# "C 이하"를 판정할 때 쓰는 순서. 앞이 좋은 등급.
GRADE_ORDER: tuple[str, ...] = (
    GRADE_SPLUS, GRADE_S, GRADE_A, GRADE_B, GRADE_C, GRADE_D, GRADE_F,
)

# --- 결측 처리 ---
# 축의 유효 항목이 만점 기준 절반 미만이면 판정불가(NA).
AXIS_NA_MIN_VALID_RATIO: float = 0.5
# 미조사(not_investigated) 항목이 전체의 이 비율을 넘으면 등급을 내지 않는다.
INCOMPLETE_MAX_NOT_INVESTIGATED_SHARE: float = 0.30
# 이 섹터군만 I5(사이클 위치)를 판정한다. 나머지는 결측으로 만점을 줄인다.
CYCLICAL_SECTOR_GROUP: str = GROUP_CYCLICAL

# --- 종합등급 → 배수 (6-1) ---
MULTIPLIER_BY_GRADE: dict[str, float] = {
    GRADE_SPLUS: 1.25, GRADE_S: 1.20, GRADE_A: 1.10, GRADE_B: 1.00,
    GRADE_C: 0.75, GRADE_D: 0.50, GRADE_F: 0.0,
}
# --- 축별 하한 규칙 (6-2, 종합등급보다 우선) ---
CAP_WHEN_G_OR_D_AT_MOST_C: float = 1.0
CAP_WHEN_NA_AXIS: float = 1.0
CAP_WHEN_MOAT_UNSPECIFIED: float = 1.0
CAP_WHEN_TWO_D_AXES: float = 0.75
HOLD_WHEN_D_AXES_AT_LEAST: int = 3
D_AXES_FOR_CAP: int = 2

# --- 판정 문구 ---
DECISION_ADOPT: str = "채택"
DECISION_LIMITED: str = "제한 채택"
DECISION_HOLD: str = "보류"
DECISION_REJECT: str = "기각"
DECISION_INCOMPLETE: str = "판정 미완료"
# 배수 → 판정. 문서 6-1의 표를 배수 구간으로 옮긴 것이다.
DECISION_MIN_MULTIPLIER_ADOPT: float = 1.0
DECISION_MIN_MULTIPLIER_LIMITED: float = 0.75
DECISION_MIN_MULTIPLIER_HOLD: float = 0.0  # 0.0 초과 ~ 0.75 미만 = 보류

# 정성 등급 유효기간 (7-3). 만료 시 보류로 강등하는 것은 표현·감시 계층의 몫이다.
GRADE_VALID_MONTHS: int = 6

# --- 루브릭 임계값 (2절) ---
RELATED_PARTY_GOOD_MAX: float = 0.05  # G2 5% 미만
RELATED_PARTY_BAD_MIN: float = 0.15  # G2 15% 이상
POLICY_YEARS_FULL: int = 3  # G3 3년 이행
IMPAIRMENT_BAD_MIN: int = 2  # C1 손상 2회 이상
DIVIDEND_EXCESS_YEARS_GOOD_MAX: int = 0  # C4 영업CF 내 충당(초과 0년)
MOAT_EVIDENCE_TOP_GRADE: int = 1  # D1 1급 증거
MOAT_EVIDENCE_SECOND_GRADE: int = 2
EROSION_BAD_MIN: int = 2  # D2 2개 이상 악화
SEGMENT_SHARE_GOOD_MAX: float = 0.60  # D3
SEGMENT_SHARE_BAD_MIN: float = 0.80
CUSTOMER_SHARE_GOOD_MAX: float = 0.10  # D4
CUSTOMER_SHARE_BAD_MIN: float = 0.20
RECURRING_SHARE_GOOD_MIN: float = 0.50  # D6
RECURRING_SHARE_MID_MIN: float = 0.20
PIPELINE_STAGE_COEFFICIENTS: dict[int, float] = {1: 0.0, 2: 0.2, 3: 0.5, 4: 0.8, 5: 1.0}
PIPELINE_RATIO_GOOD_MIN: float = 0.30  # P1
PIPELINE_RATIO_MID_MIN: float = 0.10
PIPELINE_STAGE_GOOD_MIN: int = 4  # P2 계약·수주 이상
PIPELINE_STAGE_MID: int = 3  # 인허가·인증
GUIDANCE_HIT_GOOD_MIN: float = 0.90  # P3
GUIDANCE_HIT_MID_MIN: float = 0.70
SUBSTITUTE_STAGE_GOOD_MAX: int = 2  # I4 ①②단계
SUBSTITUTE_STAGE_MID: int = 3
FLOATING_DEBT_GOOD_MAX: float = 0.30  # X1
FLOATING_DEBT_BAD_MIN: float = 0.60
INTEREST_COVERAGE_GOOD_MIN: float = 5.0
INTEREST_COVERAGE_BAD_MAX: float = 2.0
REGIONS_GOOD_MIN: int = 3  # X3
REGIONS_MID: int = 2
COUNTRY_SHARE_GOOD_MAX: float = 0.30  # X5
COUNTRY_SHARE_BAD_MIN: float = 0.50
