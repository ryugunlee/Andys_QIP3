"""업종명 → 가치 평가용 섹터군(4분류) + 상환연수 완화 대상 판정.

같은 가치 지표라도 업종에 따라 의미가 전혀 다르다. 은행에 FCF Yield를 묻는 것은
무의미하고, 소프트웨어에 PBR을 묻는 것도 마찬가지다. 그래서 원 규칙은 섹터군마다
가치 4지표의 가중치를 다르게 준다.

한국은 업종명이 GICS 스타일(`반도체와반도체장비`, `은행`, `전기유틸리티`)이고
미국(yfinance)은 영문 sector/industry라 양쪽 표기를 함께 받는다. 어디에도 걸리지
않으면 `일반`으로 떨어뜨린다 — 분류 실패로 종목을 잃는 것보다 낫다.
"""

# 섹터군 이름. `analysis/qip4_weights.py`의 가중치 표 키와 반드시 같아야 한다.
GROUP_GENERAL: str = "일반"
GROUP_ASSET: str = "자산형"
GROUP_INTANGIBLE: str = "무형자산형"
GROUP_CYCLICAL: str = "자본집약사이클"

# 업종명에 이 조각이 들어 있으면 해당 섹터군으로 본다(부분 일치, 소문자 비교).
# 순서가 곧 우선순위다 — 앞선 규칙이 먼저 걸린다.
_GROUP_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        GROUP_ASSET,
        (
            "은행", "생명보험", "손해보험", "보험", "증권", "카드", "기타금융",
            "창업투자", "부동산", "지주", "복합기업",
            "bank", "insurance", "capital markets", "financial", "reit",
            "asset management", "credit services", "mortgage",
        ),
    ),
    (
        GROUP_INTANGIBLE,
        (
            "소프트웨어", "it서비스", "인터넷", "게임", "양방향미디어",
            "생물공학", "제약", "건강관리", "생명과학", "교육서비스", "광고",
            "software", "internet", "biotech", "pharmaceutical", "health",
            "media", "entertainment", "information technology services",
        ),
    ),
    (
        GROUP_CYCLICAL,
        (
            "반도체", "화학", "철강", "조선", "비철금속", "종이와목재", "포장재",
            "석유와가스", "에너지장비", "디스플레이", "자동차", "해운",
            "semiconductor", "chemical", "steel", "shipbuilding", "oil", "gas",
            "energy", "metals", "mining", "auto manufacturers",
        ),
    ),
]

# 상환연수 임계를 완화(5년 → 8년)하는 업종. 구조적으로 부채를 많이 쓰는 업이라
# 같은 잣대로 재면 정상 기업이 전부 탈락한다.
_LEVERAGE_TOLERANT_KEYWORDS: tuple[str, ...] = (
    "유틸리티", "전기유틸리티", "가스유틸리티", "복합유틸리티",
    "운송인프라", "부동산", "도로와철도운송",
    "utilities", "utility", "reit", "infrastructure", "real estate",
)


def _matches(labels: tuple[str | None, ...], keywords: tuple[str, ...]) -> bool:
    """업종/섹터 라벨 중 하나라도 키워드를 포함하면 True."""
    for label in labels:
        if not label:
            continue
        lowered = label.lower()
        if any(keyword in lowered for keyword in keywords):
            return True
    return False


def sector_group(sector: str | None, industry: str | None) -> str:
    """가치 가중치를 고를 섹터군을 반환한다. 분류 실패 시 `일반`."""
    labels = (sector, industry)
    for group, keywords in _GROUP_KEYWORDS:
        if _matches(labels, keywords):
            return group
    return GROUP_GENERAL


def is_leverage_tolerant(sector: str | None, industry: str | None) -> bool:
    """상환연수 완화 대상(유틸리티·리츠·인프라)인지 판정한다."""
    return _matches((sector, industry), _LEVERAGE_TOLERANT_KEYWORDS)
