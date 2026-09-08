"""QIP4 정량 규칙의 가중치·임계값 단일 소스.

원문은 `.claude/투자 규칙.md`. QIP3와 달리 QIP4는 네 축의 역할이 서로 다르다:

    안정성  관문   Pass / Fail
    성장성  선정   0~100 점수
    가치    선정   0~100 점수
    효율성  감사   승수 0.8~1.0 또는 탈락
    모멘텀  비중   집행률만 결정 (선정에 관여하지 않음)

**임계값이 전부 여기 모여 있는 이유**: 수집 계층은 원시 숫자만 내고 판정은
`analysis/qip4_gate.py`가 한다. 그래서 임계값을 바꿔도 몇 시간짜리 재수집 없이
재채점(수 초)만으로 반영된다.
"""

# --- 안정성 1단계: 탈락 조건 ---
# S1: 최근 3년 중 영업활동현금흐름이 음수인 해가 이 수 이상이면 탈락.
GATE_MAX_NEGATIVE_OCF_YEARS: int = 2
# S2: 3년 누적 영업CF ÷ 3년 누적 순이익이 이 값 미만이면 탈락.
#     누적 순이익이 0 이하면 계산되지 않고(None) 판정을 유보한다.
GATE_MIN_CASH_CONVERSION: float = 0.7
# S3: 이자보상배율이 1 미만인 해가 연속 이 수 이상이면 탈락.
#     이자비용이 없는 무차입 기업은 None이라 "해당 없음 = 통과"가 된다.
GATE_MAX_INTEREST_FAIL_YEARS: int = 2

# --- 안정성 2단계: 상환연수 ---
# 조정 순부채 ÷ 3년 평균 영업CF가 이 값을 넘으면 탈락.
GATE_MAX_REPAYMENT_YEARS: float = 5.0
# 유틸리티·리츠·인프라는 구조적으로 부채를 많이 써서 같은 잣대로 재면 정상 기업이
# 전부 탈락한다. 완화 임계값을 따로 둔다.
GATE_MAX_REPAYMENT_YEARS_TOLERANT: float = 8.0

# --- 자산형(은행·보험·증권·지주) 전용 관문 ---
# 현금흐름 기반 조건(S1~S3·상환연수)은 금융사에 맞지 않는다(이자비용이 조달원가이고
# 영업현금흐름이 대출 잔액 변동으로 흔들린다). 면제만 하면 관문이 비어버리므로,
# 금융사에도 의미가 살아있는 두 조건으로 대체한다.
#
# F1: 최근 3년 중 당기순손실이 이 수 이상이면 탈락 (S1의 대응물).
GATE_MAX_NET_LOSS_YEARS: int = 2
# F2: 자기자본비율(자본총계 ÷ 자산총계)이 이 값 미만이면 탈락.
#     바젤III 레버리지비율 최소 기준이 3%(기본자본 ÷ 총익스포저)다. 자기자본비율은
#     위험가중을 하지 않은 거친 근사라 그보다 조금 높게 잡아 4%를 하한으로 둔다.
#     실측 참고: KB금융 7.6% / 메리츠금융지주 8.3% / 삼성생명 18.5% / 삼성화재 22.1%.
#     정상 금융사는 여유 있게 통과하고, 자본이 실제로 잠식된 곳만 걸린다.
GATE_MIN_EQUITY_RATIO: float = 0.04

# --- 안정성 3단계: 자산 품질 경고 (탈락이 아니라 경고) ---
# 실질 자기자본 ÷ 자기자본이 이 값 미만이면 경고.
# 원 규칙은 0.6이지만 자산화된 개발비·특수관계자 대여금을 어느 소스에서도 분리할 수
# 없어 차감 항목이 4개에서 2개로 줄었다. 같은 0.6을 쓰면 필터가 훨씬 느슨해지므로
# 원 규칙의 엄격도를 보존하려고 0.75로 올린다 (.claude/투자 규칙.md에 근거 기록).
WARN_MIN_TANGIBLE_EQUITY_RATIO: float = 0.75
# 영업권 ÷ 총자산이 이 값을 넘으면 경고.
WARN_MAX_GOODWILL_TO_ASSETS: float = 0.20

# --- 효율성 감사: 경보 개수 → 승수 ---
# 어느 경보가 더 나쁜지 구분할 근거가 없어 개수 기반으로 단순화한다(원문 판단).
EFFICIENCY_MULTIPLIERS: dict[int, float] = {0: 1.0, 1: 0.9, 2: 0.8}
# 경보가 이 수 이상이면 탈락. 승수 0.0으로 표현해 종합점수가 0이 되게 한다 —
# 이 저장소의 분석 계층은 연속값만 다루므로 불리언 탈락 개념을 새로 만들지 않는다.
EFFICIENCY_FAIL_ALARM_COUNT: int = 3
EFFICIENCY_FAIL_MULTIPLIER: float = 0.0
# 발생액 경보: 업종 내 상위 이 분위수를 넘으면 경보(이익과 현금의 괴리).
ACCRUAL_ALARM_QUANTILE: float = 0.90

# --- 가치: 섹터군별 4지표 가중치 (각 행의 합 = 1.0) ---
# 은행에 FCF Yield를 묻는 것은 무의미하고 소프트웨어에 PBR을 묻는 것도 마찬가지라,
# 섹터군마다 다른 가중치를 준다. 키는 collection/sector_groups.py의 상수와 같아야 한다.
VALUE_WEIGHTS_BY_GROUP: dict[str, dict[str, float]] = {
    "일반": {"fcf_yield": 0.40, "ev_to_ebit": 0.35, "pbr": 0.10, "shareholder_yield": 0.15},
    "자산형": {"fcf_yield": 0.0, "ev_to_ebit": 0.0, "pbr": 0.55, "shareholder_yield": 0.45},
    "무형자산형": {"fcf_yield": 0.55, "ev_to_ebit": 0.35, "pbr": 0.0, "shareholder_yield": 0.10},
    "자본집약사이클": {"fcf_yield": 0.25, "ev_to_ebit": 0.30, "pbr": 0.30, "shareholder_yield": 0.15},
}

# --- 밸류 트랩 보정 승수 ---
# 싸 보이는 데는 이유가 있는 경우를 깎는다.
VALUE_TRAP_SHRINKING_REVENUE_MULTIPLIER: float = 0.7  # 5년 매출 CAGR < 0 (구조적 역성장)
VALUE_TRAP_IDLE_NET_CASH_MULTIPLIER: float = 0.8  # 주주환원 0 + 순현금 3년 지속
# 순현금이 이 연수 이상 이어지는데 주주환원이 없으면 자본배분을 하지 않는다는 뜻.
VALUE_TRAP_NET_CASH_YEARS: int = 3

# --- 성장성 내부 가중치 (합 1.0) ---
GROWTH_CONTINUITY_WEIGHT: float = 0.25  # 성장의 지속성
GROWTH_STABILITY_WEIGHT: float = 0.15  # 변동계수(낮을수록 좋음)
GROWTH_SELF_FUNDING_WEIGHT: float = 0.25  # 남의 돈 없이 크는가 — 성장의 질을 가장 잘 압축
GROWTH_CAPITAL_INTENSITY_WEIGHT: float = 0.15  # 매출 1원을 벌기 위해 넣은 자본(낮을수록 좋음)
GROWTH_RELATIVE_WEIGHT: float = 0.20  # 업종 대비 상대 성장률(점유율 확대형인가)

# --- 모멘텀 내부 가중치 (합 1.0) ---
# 이익 모멘텀에 충분한 몫을 주는 게 핵심이다. 나머지 둘은 결국 가격에서 나온 숫자라
# 서로 상관이 높은데, 이익 모멘텀만 애널리스트 추정치라는 다른 원천에서 온다.
MOMENTUM_PRICE_12_1_WEIGHT: float = 0.40
MOMENTUM_RELATIVE_STRENGTH_WEIGHT: float = 0.30
MOMENTUM_EARNINGS_REVISION_WEIGHT: float = 0.30

# --- 종합점수: 성장·가치 두 축만 (모멘텀은 선정에 관여하지 않는다) ---
TOTAL_VALUE_WEIGHT: float = 0.50
TOTAL_GROWTH_WEIGHT: float = 0.50

# --- 모멘텀 → 집행률(%) ---
# "무엇을 살지"가 아니라 "얼마나 살지"만 정한다. 절대 비중(5%/3%/1.5%)은 포트폴리오
# 크기에 종속되므로 산출하지 않고 집행률만 정보로 제시한다.
EXECUTION_RATE_BANDS: list[tuple[float, float]] = [
    (70.0, 100.0),  # M점수 70 이상 → 100%
    (40.0, 60.0),  # 40~70 → 60%
    (0.0, 30.0),  # 40 미만 → 30%
]

# --- 선별 상수 ---
SELECTION_RATIO: float = 0.10  # 시장별 상위 10%
RELIABILITY_THRESHOLD: float = 50  # 결측 중립 50점 누적으로 위장 진입 방지(QIP3와 동일)

# --- 상대강도·이익 모멘텀 조회 구간 ---
RELATIVE_STRENGTH_LOOKBACK_DAYS: int = 126  # 6개월(거래일)
EARNINGS_REVISION_LOOKBACK_DAYS: int = 90  # 3개월(달력일)
