"""정성 등급 체계의 가중치·밴드·배수·임계값 단일 소스.

원문은 `.claude/정성 평가 규칙.md` 2~4절. 값은 전부 설계 추론이라 `qip4_weights.py`와 같은
이유로 한 파일에 모은다 — 값을 바꿔도 관측값 JSON은 그대로 두고 재판정만 하면 된다.
"""

# --- 항목 가중 (합 100) ---
ITEM_WEIGHTS: dict[str, float] = {
    "Q1": 15, "Q2": 15, "Q3": 10, "Q4": 10, "Q5": 10, "Q6": 15, "Q7": 10, "Q8": 10, "Q9": 5,
}

SCORE_MIN: int = 0
SCORE_MAX: int = 100

# --- 등급 밴드 (점수 이상 기준, 위에서부터 첫 일치). 항목·종합 공통 ---
GRADE_S: str = "S"
GRADE_A: str = "A"
GRADE_B: str = "B"
GRADE_C: str = "C"
GRADE_D: str = "D"
GRADE_F: str = "F"
GRADE_BANDS: tuple[tuple[float, str], ...] = (
    (90, GRADE_S), (80, GRADE_A), (65, GRADE_B), (50, GRADE_C), (35, GRADE_D), (0, GRADE_F),
)
GRADE_ORDER: tuple[str, ...] = (GRADE_S, GRADE_A, GRADE_B, GRADE_C, GRADE_D, GRADE_F)

# 앵커 점수 (문서 2절): S 90 / B 65 / F 35 미만
ANCHOR_S: float = 90
ANCHOR_B: float = 65
ANCHOR_F: float = 35
SCORE_BELOW_F: float = 34  # "F 고정" 상한
# 증거가 3급뿐이거나 인용 대조에 실패한(weak) 항목은 B 앵커를 넘지 못한다.
WEAK_SCORE_CAP: float = ANCHOR_B

# --- 결측 ---
# 유효 항목(observed·weak)이 이 수보다 적으면 판정 미완료.
MIN_VALID_ITEMS: int = 6

# --- 종합등급 → 배수, 하한 ---
MULTIPLIER_BY_GRADE: dict[str, float] = {
    GRADE_S: 1.25, GRADE_A: 1.10, GRADE_B: 1.00, GRADE_C: 0.75, GRADE_D: 0.50, GRADE_F: 0.0,
}
GOVERNANCE_ITEM: str = "Q6"
CAP_WHEN_GOVERNANCE_AT_MOST_C: float = 1.0

# --- 판정 문구 ---
DECISION_ADOPT: str = "채택"
DECISION_LIMITED: str = "제한 채택"
DECISION_HOLD: str = "보류"
DECISION_REJECT: str = "기각"
DECISION_INCOMPLETE: str = "판정 미완료"
DECISION_MIN_MULTIPLIER_ADOPT: float = 1.0
DECISION_MIN_MULTIPLIER_LIMITED: float = 0.75
DECISION_MIN_MULTIPLIER_HOLD: float = 0.0  # 0.0 초과 ~ 0.75 미만 = 보류

# 주의 항목 = 이 등급 이하 (문서 3절)
WATCH_GRADE_AT_MOST: str = GRADE_C

# 정성 등급 유효기간 (문서 3절). 만료 처리는 표현 계층 몫.
GRADE_VALID_MONTHS: int = 6

# --- 수치 재계산 앵커 (문서 2절). (raw 값, 점수) 꺾은선 — 사이는 선형 보간 ---
COMMITTED_REVENUE_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 15), (0.2, ANCHOR_F), (0.5, ANCHOR_B), (1.0, ANCHOR_S), (1.5, SCORE_MAX),
)
RELATED_PARTY_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 95), (0.05, ANCHOR_S), (0.15, ANCHOR_F), (0.30, 15),
)
CUSTOMER_SHARE_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 95), (0.10, ANCHOR_S), (0.20, ANCHOR_B), (0.30, ANCHOR_F), (0.50, 15),
)
SEGMENT_SHARE_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 95), (0.60, ANCHOR_S), (0.80, ANCHOR_B), (0.90, ANCHOR_F), (1.0, 20),
)
COUNTRY_SHARE_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 95), (0.30, ANCHOR_S), (0.40, ANCHOR_B), (0.50, 45), (0.80, 20),
)
# Q6 사외이사 과반 미달 → B 앵커 상한. Q9 미헤지 → B 앵커 상한. Q1 구속력 없음 → F 고정.
BOARD_MINORITY_CAP: float = ANCHOR_B
UNHEDGED_CAP: float = ANCHOR_B
PIPELINE_STAGE_COEFFICIENTS: dict[int, float] = {1: 0.0, 2: 0.2, 3: 0.5, 4: 0.8, 5: 1.0}

# --- ★ 플래그 (문서 4절) ---
TREND_WINDOW_DAYS: int = 182  # 6개월
TREND_RETURN_MIN_ABS: float = 0.30
TREND_INCOME_CHANGE_FLAT_ABS: float = 0.10
FLAG_UNEXPLAINED_UP: str = "UNEXPLAINED_UP"
FLAG_UNEXPLAINED_DOWN: str = "UNEXPLAINED_DOWN"
