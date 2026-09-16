"""정성 평가 9항목의 계약 — 무엇을 묻고, 어떤 사실(raw)을 받고, 채점 앵커가 무엇인가.

원문은 `.claude/정성 평가 규칙.md` 1·2절. 여기가 raw 필드명·앵커 문구의 단일 소스다:
- LLM 채점 프롬프트(`prompts.py`)가 이 앵커와 필드를 JSON 스키마로 요구하고,
- 사람이 손으로 채울 때 같은 스키마를 따르며,
- 수치 재계산 루브릭(`analysis/qualitative/rubric.py`)이 이 필드명으로 raw를 읽는다.

가중치·임계값은 `analysis/qualitative/weights.py`에 있다. 여기에는 없다.
"""

from dataclasses import dataclass

ITEM_CODES: tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9")

# 파이프라인 확실성 5단계 (문서 1절). 계수는 analysis 쪽 상수가 갖는다.
PIPELINE_STAGE_MIN: int = 1
PIPELINE_STAGE_MAX: int = 5


@dataclass(frozen=True)
class ItemSpec:
    code: str
    title: str
    short: str
    question: str
    anchor_s: str
    anchor_b: str
    anchor_f: str
    sources: str
    fields: dict[str, dict]


def _number(description: str) -> dict:
    return {"type": ["number", "null"], "description": description}


def _integer(description: str) -> dict:
    return {"type": ["integer", "null"], "description": description}


def _boolean(description: str) -> dict:
    return {"type": ["boolean", "null"], "description": description}


def _string(description: str) -> dict:
    return {"type": ["string", "null"], "description": description}


def _enum(description: str, values: tuple[str, ...]) -> dict:
    # Anthropic 구조화 출력은 enum에 null을 섞는 것을 거부한다 — anyOf로 nullable enum을 표현한다.
    return {"anyOf": [{"type": "string", "enum": list(values)}, {"type": "null"}], "description": description}


TREND_VALUES: tuple[str, ...] = ("decreasing", "flat", "increasing")
DIRECTION_VALUES: tuple[str, ...] = ("shrinking", "flat", "growing")
REGULATION_VALUES: tuple[str, ...] = ("headwind", "uncertain", "favorable")
SURVIVAL_VALUES: tuple[str, ...] = ("extinction_path", "uncertain", "no_extinction_path")
SUBSTITUTABILITY_VALUES: tuple[str, ...] = ("low", "mid", "high")

_PIPELINES_FIELD: dict = {
    "type": ["array", "null"],
    "description": "현매출 대비 5% 이상인 진행 사업·신사업 목록 (MOU·검토 중은 1단계)",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "stage": {"type": "integer", "description": "확실성 단계 1(구상·MOU)~5(양산)"},
            "revenue_ratio": {"type": "number", "description": "완전 가동 시 예상 매출 ÷ 현매출"},
        },
        "required": ["name", "stage", "revenue_ratio"],
        "additionalProperties": False,
    },
}

ITEM_SPECS: tuple[ItemSpec, ...] = (
    ItemSpec(
        "Q1", "확정 이익 (수주잔고·계약)", "확정이익",
        "수주잔고·장기계약·반복매출이 연매출 대비 얼마이고, 구속력이 있는가",
        "확정 매출(수주잔고 + 1년 내 확정 반복매출) ÷ 연매출 1.0배 이상, 구속력 있는 계약",
        "0.5배 안팎",
        "0.2배 미만, 또는 MOU·구두 수준뿐(구속력 없음)",
        "사업보고서 수주상황·주요계약, 공급계약 공시 / 10-K RPO·Backlog. 자산형은 여신 건전성으로 치환",
        {
            "committed_to_revenue": _number("(수주잔고 + 1년 내 확정 반복매출) ÷ 연매출"),
            "binding_contracts": _boolean("확정분이 구속력 있는 계약(공급계약·수주 공시)에 근거하는가"),
        },
    ),
    ItemSpec(
        "Q2", "시장 지위 (점유율·인지도)", "시장지위",
        "점유율 순위·수준과 3년 추세, 고객·브랜드 인지도",
        "점유율 1~2위이고 3년 상승, 인지도가 원문·통계로 확인",
        "중위권 유지",
        "하위권이거나 3년 하락",
        "사업의 내용(시장 현황·경쟁), 산업통계",
        {
            "market_share": _number("주력 사업 점유율 (0~1)"),
            "market_rank": _integer("주력 사업 점유율 순위"),
            "share_trend_3y": _enum("3년 점유율 추세", TREND_VALUES),
        },
    ),
    ItemSpec(
        "Q3", "기술·제품 차별성", "기술",
        "기술 세분화 수준, 경쟁사가 대체하기 어려운가, 특허·고객 인증",
        "대체 난이도 높음 — 특허·인증·공정 세분화로 경쟁사가 단기 복제 불가",
        "차별성 있으나 대체 가능",
        "범용 제품·가격 경쟁",
        "연구개발 실적, 특허·인증 현황, 사업의 내용",
        {
            "substitutability": _enum("경쟁사의 대체 용이성 (low=대체 어려움)", SUBSTITUTABILITY_VALUES),
            "protections": _string("대체를 막는 요소 요약 (특허·인증·공정·표준 등)"),
        },
    ),
    ItemSpec(
        "Q4", "산업·섹터 전망", "산업전망",
        "수요 방향, 규제 방향, 10년 존속성. 정량 산업 PER·섹터 지표와 대조",
        "수요 성장 + 규제 우호·중립 + 10년 존속 의심 없음",
        "수요 정체, 규제 불확실",
        "수요 축소, 규제 역풍, 또는 소멸 경로 확인",
        "산업통계, 규제 원문·개정안, 사업의 내용(산업 현황)",
        {
            "demand_direction": _enum("산업 수요 방향", DIRECTION_VALUES),
            "regulation_direction": _enum("규제 방향", REGULATION_VALUES),
            "survival_10y": _enum("10년 존속성", SURVIVAL_VALUES),
        },
    ),
    ItemSpec(
        "Q5", "확장 잠재력 (섹터 연결·신사업)", "잠재력",
        "다른 산업의 수요와 연결돼 새 시장이 생기는가(예: 전력→데이터센터), 신사업의 단계",
        "다른 산업의 확정 수요와 계약·양산 단계로 연결, 또는 신사업이 계약·양산(④⑤) 단계",
        "개발·인허가(②③) 단계",
        "구상·MOU(①) 단계뿐이거나 없음",
        "수시공시(계약·투자), 인허가, CAPEX 집행, 사업의 내용(신규 사업)",
        {
            "pipelines": _PIPELINES_FIELD,
            "linked_sectors": _string("연결되는 다른 산업·섹터와 연결 근거 요약"),
        },
    ),
    ItemSpec(
        "Q6", "지배구조·주주 정합성 (결격 보유)", "지배구조",
        "이사회 독립성, 특수관계자 거래, 물적분할·배임 이력",
        "사외이사 과반 + 특수관계자 거래(연결 종속회사 제외) 매출 5% 미만 + 결격 없음",
        "과반 미달, 또는 특수관계자 거래 5~15%",
        "15% 이상 또는 3년 증가 추세. 결격 해당 시 F 고정",
        "이사회 등 회사의 기관, 대주주 등과의 거래, 합병·분할 공시, 판결·기소 / DEF 14A",
        {
            "outside_directors": _integer("사외이사 수"),
            "total_directors": _integer("총 이사 수"),
            "related_party_ratio": _number(
                "지배주주·총수 일가·비연결 계열회사와의 매출+매입 ÷ 총매출 (0~1). "
                "연결 종속회사(해외 판매·생산법인 등)와의 내부거래는 연결에서 제거되므로 제외한다"
            ),
            "related_party_trend_3y": _enum("특수관계자 거래 비중 3년 추세", TREND_VALUES),
            "spinoff_relisting": _boolean("핵심 사업 물적분할 후 중복상장 이력"),
            "executive_fraud_5y": _boolean("최근 5년 지배주주·경영진 배임·횡령·분식 확정 판결 또는 기소 진행"),
            "unfair_merger_ratio": _boolean("소액주주에 불리한 합병·분할 비율 강행 이력"),
        },
    ),
    ItemSpec(
        "Q7", "자본배분", "자본배분",
        "자사주 소각 여부, 배당 원천(영업CF 내), M&A 손상 이력",
        "소각 이력 + 배당이 영업CF 내 + 영업권 손상 0회",
        "소각 없는 매입, 손상 1회",
        "차입 배당, 또는 손상 2회 이상",
        "자기주식 취득·소각 현황, 배당·현금흐름표, 영업권 손상 주석, 주요사항보고",
        {
            "buyback_cancelled": _boolean("최근 5년 취득한 자기주식을 소각했는가 (취득 없으면 null)"),
            "dividend_within_ocf": _boolean("최근 3년 배당총액이 영업현금흐름 안에서 충당됐는가"),
            "goodwill_impairment_count_10y": _integer("최근 10년 영업권 손상차손 인식 횟수 (M&A 없음이면 0)"),
        },
    ),
    ItemSpec(
        "Q8", "이익 집중도", "집중도",
        "최대 고객·최대 세그먼트 의존도",
        "최대 고객 10% 미만 그리고 최대 세그먼트 영업이익 60% 미만",
        "고객 20% / 세그먼트 80%",
        "고객 30% 이상 또는 세그먼트 90% 이상",
        "영업부문(세그먼트) 주석, 주요 고객 정보 / ASC 280",
        {
            "top_customer_sales_share": _number("최대 고객 매출 비중 (0~1)"),
            "top_segment_op_income_share": _number("최대 세그먼트 영업이익 비중 (0~1)"),
        },
    ),
    ItemSpec(
        "Q9", "외부 충격 노출", "외부충격",
        "단일 국가 매출·생산 의존, 환위험 헤지",
        "단일 국가 매출·생산 30% 미만이고 환위험 헤지",
        "30~50%",
        "50% 이상이고 미헤지",
        "지역별 매출·생산 설비 소재, 금융위험관리 주석(환위험) / 10-K Item 7A",
        {
            "top_country_share": _number("단일 국가 매출 또는 생산 비중 중 큰 값 (0~1)"),
            "fx_hedged": _boolean("자연 헤지 구조이거나 헤지 비율이 유의미한가"),
        },
    ),
)

ITEMS_BY_CODE: dict[str, ItemSpec] = {spec.code: spec for spec in ITEM_SPECS}
