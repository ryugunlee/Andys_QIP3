"""QIP3 5요인 점수 체계의 가중치·선별 상수 (단일 소스).

각 요인 점수는 구성 팩터 점수(0~100)의 가중평균이라, 요인 내부 가중치의 합이 1이면
요인 점수도 0~100이 된다. 근거는 QUANT2.md의 요인 정의표 참고
(O'Shaughnessy VC2 / Piotroski / Altman Z / Jegadeesh-Titman / Novy-Marx / Greenblatt).
"""

# --- 가치성(Value): O'Shaughnessy Value Composite 방식 동일가중 6개 컴포넌트 ---
# PER·PBR·PSR·PCR·EV/EBITDA + 주주환원수익률(배당+자사주). 각 1/6.
VALUE_COMPONENT_COUNT: float = 6

# --- 성장성(Growth): 성장률 2종 + 성장의 질(GP/A, Novy-Marx) ---
GROWTH_EPS_WEIGHT: float = 0.35
GROWTH_REVENUE_WEIGHT: float = 0.35
GROWTH_GPTOA_WEIGHT: float = 0.30

# --- 모멘텀(Momentum): 12-1 중심(Jegadeesh-Titman) + 중·단기 보조 ---
MOMENTUM_12_1_WEIGHT: float = 0.50
MOMENTUM_6M_WEIGHT: float = 0.30
MOMENTUM_3M_WEIGHT: float = 0.20

# --- 안정성(Stability): 생존 리스크(Altman Z 정신) — 하드 필터 전용 ---
STABILITY_NET_DEBT_WEIGHT: float = 0.30
STABILITY_QUICK_WEIGHT: float = 0.15
STABILITY_INTEREST_WEIGHT: float = 0.15
STABILITY_COVERAGE_WEIGHT: float = 0.15
STABILITY_LOW_VOLATILITY_WEIGHT: float = 0.25  # 1Y 변동성 점수를 반전(100-S)해 사용

# --- 재무건전성(Health): Piotroski F-Score 정신 + Novy-Marx 마진 ---
HEALTH_ROA_WEIGHT: float = 0.10
HEALTH_ARP_WEIGHT: float = 0.15  # 발생액(현금흐름의 질). 이미 NEGATED로 등록됨
HEALTH_GROSS_MARGIN_WEIGHT: float = 0.10
HEALTH_OPERATING_MARGIN_WEIGHT: float = 0.10
HEALTH_NET_MARGIN_WEIGHT: float = 0.05
HEALTH_ASSET_TURNOVER_WEIGHT: float = 0.10
HEALTH_INVENTORY_TURNOVER_WEIGHT: float = 0.075
HEALTH_RECEIVABLES_TURNOVER_WEIGHT: float = 0.075
HEALTH_DEBT_GROWTH_WEIGHT: float = 0.10  # 부채 추세. 이미 NEGATED로 등록됨
HEALTH_CASH_RATIO_WEIGHT: float = 0.10
HEALTH_CAPEX_WEIGHT: float = 0.05

# --- 종합점수(QIP3 Score): 가치 우선, 성장·모멘텀 동급, 재무건전성 부차 ---
TOTAL_VALUE_WEIGHT: float = 0.35
TOTAL_GROWTH_WEIGHT: float = 0.25
TOTAL_MOMENTUM_WEIGHT: float = 0.25
TOTAL_HEALTH_WEIGHT: float = 0.15

# --- 안정성 하드 필터 블렌드 ---
# 시장 전체 안정성과 섹터 내 안정성을 절반씩 섞는다. 은행·보험처럼 레버리지가
# 구조적으로 높은 섹터가 시장 전체 기준에서 일괄 탈락하는 왜곡을 완화한다
# (한국 종목 Sector는 숫자 업종코드라 이름 기반 예외가 불가능 — PROBLEMS #20).
STABILITY_FILTER_MARKET_WEIGHT: float = 0.5
STABILITY_FILTER_SECTOR_WEIGHT: float = 0.5

# --- 선별(get_goodstock2) 상수 ---
STABILITY_CUT_QUANTILE: float = 0.20  # 안정성 하위 20% 무조건 제외
SELECTION_RATIO: float = 0.10  # 시장 전체 종목 수의 약 10% 선별
RELIABILITY_THRESHOLD: float = 50  # 결측 중립 50점 누적으로 위장 진입 방지
