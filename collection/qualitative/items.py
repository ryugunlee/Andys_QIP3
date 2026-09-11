"""정성 평가 33개 항목의 관측값 계약 — 어떤 사실(raw 필드)을 추출하는가.

원문은 `.claude/정성 평가 규칙.md` 2절(축별 루브릭)과 부록 A. 여기에는 **판정 기준이 없다.**
"사외이사 5명 중 3명"이라는 사실을 어떤 필드에 담을지만 정한다. 좋고 나쁨은
`analysis/qualitative/rubric.py`가 정한다 — 추출과 판정을 물리적으로 분리하는 것이
그 문서의 첫 번째 설계 원칙이다.

이 계약은 세 곳이 함께 쓴다:
- LLM 추출 프롬프트(`prompts.py`)가 이 필드를 JSON 스키마로 요구하고,
- 사람이 파일럿 종목을 손으로 채울 때 같은 스키마를 따르며,
- 루브릭이 이 필드명으로 raw를 읽는다.

자동화 등급(A/B/C)은 문서 3-3의 분류다. **C급(판단·조사가 필요한 항목)은 LLM에게
맡기지 않는다** — 프록시가 개념을 대체하는 오류가 서사 편향보다 나쁘다는 문서의 판단.
"""

from dataclasses import dataclass

AXIS_CODES: tuple[str, ...] = ("G", "C", "D", "P", "I", "X")
AXIS_NAMES: dict[str, str] = {
    "G": "지배구조·이해정합성",
    "C": "자본배분 역량",
    "D": "수익 영속성",
    "P": "성장 파이프라인 실현성",
    "I": "산업 구조 위치",
    "X": "외부 충격 내성",
}

AUTOMATION_API: str = "A"
AUTOMATION_SEMI: str = "B"
AUTOMATION_MANUAL: str = "C"

# 파이프라인 확실성 5단계 (문서 2-4, 규칙서 ③-2). 계수는 analysis 쪽 상수가 갖는다.
PIPELINE_STAGE_MIN: int = 1
PIPELINE_STAGE_MAX: int = 5


@dataclass(frozen=True)
class ItemSpec:
    code: str
    axis: str
    title: str
    automation: str
    fields: dict[str, dict]
    guidance: str
    counts_toward_axis: bool = True


def _number(description: str) -> dict:
    return {"type": ["number", "null"], "description": description}


def _integer(description: str) -> dict:
    return {"type": ["integer", "null"], "description": description}


def _boolean(description: str) -> dict:
    return {"type": ["boolean", "null"], "description": description}


def _enum(description: str, values: tuple[str, ...]) -> dict:
    return {"type": ["string", "null"], "enum": [*values, None], "description": description}


TREND_VALUES: tuple[str, ...] = ("decreasing", "flat", "increasing")
MOAT_TYPES: tuple[str, ...] = (
    "brand", "network_effect", "switching_cost", "scale", "regulation", "patent_technology",
)

ITEM_SPECS: tuple[ItemSpec, ...] = (
    # --- G 지배구조 ---
    ItemSpec("G1", "G", "이사회 독립성", AUTOMATION_SEMI, {
        "outside_directors": _integer("사외이사 수"),
        "total_directors": _integer("총 이사 수"),
        "dissent_votes_3y": _integer("최근 3년 이사회 반대·수정 의결 건수"),
    }, "이사회 구성표와 의결 현황표에서 인원수와 반대·수정 의결 건수를 찾는다."),
    ItemSpec("G2", "G", "특수관계자 거래", AUTOMATION_API, {
        "related_party_ratio": _number("특수관계자 매출+매입액 ÷ 총매출 (0~1)"),
        "trend_3y": _enum("최근 3년 비중 추세", TREND_VALUES),
    }, "특수관계자 거래 주석의 매출·매입 합계를 총매출로 나눈다."),
    ItemSpec("G3", "G", "주주환원의 명문화·이행", AUTOMATION_SEMI, {
        "has_return_policy": _boolean("배당·주주환원 정책 공시 존재 여부"),
        "years_policy_met_3y": _integer("최근 3년 중 정책대로 이행한 연수 (0~3)"),
    }, "배당정책 공시 유무와 3년 배당·자사주 실적을 정책과 대조한다."),
    ItemSpec("G4", "G", "인센티브 KPI 연동 대상", AUTOMATION_SEMI, {
        "kpi_type": _enum("임원 성과급 연동 지표 유형",
                          ("capital_efficiency", "mixed", "top_line", "undisclosed")),
    }, "임원 보수 산정기준에서 ROIC·EPS·TSR(자본효율) 연동인지 매출·외형 연동인지 본다."),
    ItemSpec("G5", "G", "자본거래 정합성 (결격)", AUTOMATION_MANUAL, {
        "spinoff_relisting": _boolean("핵심 사업 물적분할 후 중복상장 이력"),
        "executive_fraud_5y": _boolean("최근 5년 지배주주·경영진 배임·횡령·분식 확정 판결 또는 기소 진행"),
        "unfair_merger_ratio": _boolean("소액주주에 불리한 합병·분할 비율 강행 이력"),
    }, "합병·분할 공시와 판결·기소 이력. 점수가 아니라 결격 검사에만 쓴다.", counts_toward_axis=False),
    # --- C 자본배분 ---
    ItemSpec("C1", "C", "M&A 사후 성적", AUTOMATION_API, {
        "goodwill_impairment_count_10y": _integer("최근 10년 영업권 손상차손 인식 횟수 (M&A 없음이면 0)"),
    }, "영업권·무형자산 손상 주석에서 손상차손 인식 연도를 센다."),
    ItemSpec("C2", "C", "증설 CAPEX 사후 ROIC", AUTOMATION_SEMI, {
        "post_capex_roic_trend": _enum("대형 투자 후 3년 ROIC 방향", ("improved", "mixed", "declined")),
    }, "CAPEX 급증 연도 이후 3년 ROIC·가동률이 개선·유지됐는지 하락했는지."),
    ItemSpec("C3", "C", "자사주 정책", AUTOMATION_API, {
        "buybacks_exist": _boolean("최근 5년 자기주식 취득 존재"),
        "cancelled": _boolean("취득분 소각 여부"),
        "purchase_band_position": _enum("매입 당시 PBR 밴드 위치", ("low", "mid", "high")),
        "reissued_or_exchangeable": _boolean("재출연 또는 교환사채 활용 여부"),
    }, "자기주식 취득·처분·소각 이력과 매입 시점 밸류에이션."),
    ItemSpec("C4", "C", "배당의 원천", AUTOMATION_API, {
        "years_dividend_exceeded_ocf_3y": _integer("최근 3년 중 배당총액이 영업CF를 초과한 연수 (0~3)"),
        "funded_by_debt_or_asset_sale": _boolean("차입·자산매각으로 배당을 유지했는지"),
    }, "배당총액과 영업현금흐름, 차입금 변동을 3년 대조한다."),
    ItemSpec("C5", "C", "조달 목적-사용 일치", AUTOMATION_SEMI, {
        "capital_raise_exists": _boolean("최근 3년 유상증자·CB 등 조달 존재"),
        "use_matches_purpose": _enum("공시 목적 대비 실제 사용처", ("match", "partial", "mismatch")),
        "repeated_raises_3y": _boolean("3년 내 반복 조달 여부"),
    }, "조달 공시의 목적과 자금사용내역 보고를 대조한다."),
    # --- D 수익 영속성 ---
    ItemSpec("D1", "D", "해자 유형 특정", AUTOMATION_MANUAL, {
        "moat_type": _enum("해자 유형", (*MOAT_TYPES, "none")),
        "best_evidence_grade": _integer("근거 자료의 최고 증거 등급 (1~4)"),
    }, "해자를 주장하려면 유형을 특정해야 한다. '경쟁력이 있다'는 서술은 인정하지 않는다."),
    ItemSpec("D2", "D", "침식 신호 상태", AUTOMATION_MANUAL, {
        "erosion_signals_worsening": _integer("유형별 지정 신호 3개 중 악화 개수 (0~3)"),
    }, "해자 유형별 침식 지표(재계약률·점유율·광고비/매출 등) 중 악화 중인 것의 수."),
    ItemSpec("D3", "D", "이익 집중도", AUTOMATION_API, {
        "top_segment_op_income_share": _number("최대 세그먼트 영업이익 비중 (0~1)"),
    }, "영업부문(세그먼트) 주석의 부문별 영업이익."),
    ItemSpec("D4", "D", "고객 집중도", AUTOMATION_API, {
        "top_customer_sales_share": _number("최대 고객 매출 비중 (0~1)"),
    }, "주요 고객 정보 주석(매출 10% 이상 고객)."),
    ItemSpec("D5", "D", "가격 전가력", AUTOMATION_SEMI, {
        "margin_defense": _enum("최근 원가 상승기 마진 방어", ("defended", "recovered_within_2q", "eroded")),
    }, "원재료 단가 상승 구간과 분기 영업이익률 시계열을 대조한다."),
    ItemSpec("D6", "D", "계약·매출 구조", AUTOMATION_SEMI, {
        "recurring_revenue_share": _number("장기계약·반복매출 비중 (0~1)"),
    }, "수주잔고·계약 기간·구독/반복 매출 비중."),
    # --- P 파이프라인 ---
    ItemSpec("P1", "P", "유효 파이프라인 규모", AUTOMATION_SEMI, {
        "pipelines": {
            "type": ["array", "null"],
            "description": "현매출 대비 5% 이상인 진행 사업 목록",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "stage": {"type": "integer", "description": "확실성 단계 1(구상)~5(양산)"},
                    "revenue_ratio": {"type": "number", "description": "완전 가동 시 예상 매출 ÷ 현매출"},
                },
                "required": ["name", "stage", "revenue_ratio"],
                "additionalProperties": False,
            },
        },
    }, "사업별 예상 매출과 확실성 단계. MOU·검토 중은 1단계(계수 0)."),
    ItemSpec("P2", "P", "최상위 파이프라인 확실성", AUTOMATION_SEMI, {
        "top_stage": _integer("가장 진척된 파이프라인의 단계 (1~5)"),
    }, "계약 공시·인허가 등록·CAPEX 집행 증거로 단계를 정한다."),
    ItemSpec("P3", "P", "가이던스 달성 이력", AUTOMATION_MANUAL, {
        "guidance_hit_rate_3y": _number("최근 3년 제시 목표 대비 달성률 (0~1)"),
    }, "IR 자료·컨퍼런스콜의 과거 목표와 실적."),
    ItemSpec("P4", "P", "자금 조달 정합성", AUTOMATION_SEMI, {
        "funding": _enum("필요 CAPEX 조달 방식", ("internal_cash", "debt_capacity", "equity_needed")),
    }, "필요 CAPEX 대비 보유현금·차입 여력."),
    ItemSpec("P5", "P", "기존 역량 인접성", AUTOMATION_MANUAL, {
        "adjacency": _enum("신사업의 기존 기술·고객·채널 인접도", ("adjacent", "partial", "unrelated")),
    }, "사업 내용의 고객·기술 중복도."),
    # --- I 산업 구조 ---
    ItemSpec("I1", "I", "자사 점유율 추세", AUTOMATION_SEMI, {
        "share_trend_3y": _enum("3년 점유율 방향", ("up", "flat", "down")),
    }, "산업 총규모 대비 자사 매출 3년 추이."),
    ItemSpec("I2", "I", "진입장벽 방향", AUTOMATION_MANUAL, {
        "barrier_direction": _enum("진입장벽 방향", ("strengthening", "stable", "weakening")),
    }, "신규 진입 건수, 규제·기술 변화."),
    ItemSpec("I3", "I", "규제 방향", AUTOMATION_MANUAL, {
        "regulation_direction": _enum("규제 방향", ("favorable_or_neutral", "uncertain", "headwind")),
    }, "법안·고시 개정안, 규제기관 발표 원문."),
    ItemSpec("I4", "I", "기술 대체 위협", AUTOMATION_MANUAL, {
        "substitute_tech_stage": _integer("대체기술 상용화 단계 (1~5, ③-2 척도)"),
    }, "대체 기술에 파이프라인 5단계 척도를 그대로 적용한다."),
    ItemSpec("I5", "I", "사이클 위치 (사이클 산업만)", AUTOMATION_SEMI, {
        "cycle_position": _enum("업계 재고·가동률 사이클 위치", ("trough_turning", "neutral", "peak")),
    }, "업계 재고일수·가동률·증설 계획. 사이클 산업이 아니면 결측."),
    ItemSpec("I6", "I", "10년 존속성 (결격)", AUTOMATION_MANUAL, {
        "survival_10y": _enum("구조적 소멸 경로", ("no_extinction_path", "uncertain", "extinction_path")),
    }, "산업 수요 장기 추세와 대체재. 소멸 경로 확인이면 결격."),
    # --- X 외부 충격 ---
    ItemSpec("X1", "X", "금리", AUTOMATION_SEMI, {
        "has_interest_bearing_debt": _boolean("이자발생부채 존재 여부"),
        "floating_rate_debt_share": _number("변동금리 부채 비중 (0~1)"),
        "interest_coverage": _number("이자보상배율 (영업이익 ÷ 이자비용)"),
    }, "차입금 금리 구조 주석과 이자보상배율."),
    ItemSpec("X2", "X", "환율", AUTOMATION_SEMI, {
        "fx_hedge": _enum("환위험 헤지 구조", ("natural_or_hedged_70", "partial", "unhedged_one_way")),
    }, "금융위험관리 주석의 환위험 민감도와 헤지 비율."),
    ItemSpec("X3", "X", "통상·관세", AUTOMATION_SEMI, {
        "regions_count": _integer("생산지·매출지가 분산된 권역 수"),
    }, "지역별 매출과 생산 설비 소재."),
    ItemSpec("X4", "X", "원자재", AUTOMATION_MANUAL, {
        "price_passthrough": _enum("판가 연동 조항", ("linked_within_1q", "lag_2q_plus", "none")),
    }, "주요 계약 조건과 원재료 비중."),
    ItemSpec("X5", "X", "지정학", AUTOMATION_SEMI, {
        "top_country_share": _number("단일 국가 매출 또는 생산 비중 중 큰 값 (0~1)"),
    }, "지역별 매출, 생산기지 위치."),
)

ITEMS_BY_CODE: dict[str, ItemSpec] = {spec.code: spec for spec in ITEM_SPECS}


def items_of_axis(axis: str) -> list[ItemSpec]:
    return [spec for spec in ITEM_SPECS if spec.axis == axis]


def automated_items_of_axis(axis: str) -> list[ItemSpec]:
    """LLM 추출 대상 — C급(수동 판독)은 제외한다."""
    return [spec for spec in items_of_axis(axis) if spec.automation != AUTOMATION_MANUAL]
