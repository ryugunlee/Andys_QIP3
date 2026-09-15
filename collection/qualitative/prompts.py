"""LLM 채점 프롬프트와 JSON 스키마 — `.claude/정성 평가 규칙.md` 2·5·6절의 규칙을 구현한다.

1. 앵커에 맞춰 채점하고 근거(rationale)를 쓴다. 근거 없는 점수는 판정기가 버린다.
2. 인용 의무: 모든 항목에 원문 발췌(quote)와 위치(locator). 코드가 원문과 대조한다.
3. 없음의 허용: 원문에 없으면 status=missing이 정답이다.
4. 주가·수급·목표주가·테마 서술은 어떤 필드에도 넣지 않는다.
5. 정량 점수·주가는 프롬프트에 넣지 않는다(앵커링 차단).

시스템 프롬프트는 고정 문자열이다 — 프롬프트 캐시가 접두 일치라 여기에 날짜나 종목명을
넣으면 캐시가 매번 깨진다. 종목별로 바뀌는 내용은 요청 본문(build_request)에 둔다.
"""

from analysis.qualitative.weights import ANCHOR_B, ANCHOR_F, ANCHOR_S, SCORE_MAX, SCORE_MIN
from collection.qualitative.items import ItemSpec

SYSTEM_PROMPT: str = f"""당신은 기업 공시 문서(사업보고서, 10-K, 주석, 공시)를 읽고 정해진 항목을 채점하는 채점자다.

채점 규칙:
- 항목마다 S({ANCHOR_S:.0f}점 이상) / B({ANCHOR_B:.0f}점) / F({ANCHOR_F:.0f}점 미만) 앵커 문장이 주어진다. 문서의 사실이 어느 앵커에 가까운지로 {SCORE_MIN}~{SCORE_MAX} 정수 점수를 정한다. 앵커 사이는 비례해서 준다.
- rationale에는 점수의 근거를 사실 중심으로 2~3문장 쓴다. 수치에는 기준 시점을 붙인다. "성장성이 뛰어나다" 같은 형용사 단독 서술은 금지한다.
- raw에는 요청된 필드에 문서에서 확인한 값만 넣는다. 비율은 0~1 소수. 확인되지 않은 필드는 null.
- 문서에서 항목을 판단할 사실을 전혀 찾지 못하면 status를 "missing"으로 두고 score는 null, rationale은 빈 문자열로 둔다. "찾을 수 없음"은 정답이다. 일반 지식으로 채우지 않는다.
- evidence: 근거가 된 원문 발췌. quote는 문서의 문장·표 셀을 한 글자도 바꾸지 않고 그대로 복사한다(번역·요약 금지). locator는 문서 내 위치(항목 제목, 주석 번호, 페이지). source는 문서 이름·종류, date는 문서 기준일(모르면 빈 문자열). grade는 증거 등급: 1=공시 원문·주석·계약, 2=산업 통계·거래상대방 발언, 3=리포트·언론.
- note에는 값의 해석에 필요한 사실 관계만 짧게 적는다(예: "연결 기준").
- 주가, 수급, 시장 심리, 목표주가, 테마·관련주에 관한 서술은 어떤 필드에도 넣지 않는다. 그런 정보는 근거가 아니다."""


def _evidence_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "date": {"type": "string"},
                "grade": {"type": "integer", "enum": [1, 2, 3]},
                "quote": {"type": "string"},
                "locator": {"type": "string"},
            },
            "required": ["source", "date", "grade", "quote", "locator"],
            "additionalProperties": False,
        },
    }


def _item_schema(spec: ItemSpec) -> dict:
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["observed", "missing"]},
            "score": {"type": ["integer", "null"], "minimum": SCORE_MIN, "maximum": SCORE_MAX},
            "rationale": {"type": "string"},
            "raw": {
                "type": "object",
                "properties": spec.fields,
                "required": list(spec.fields),
                "additionalProperties": False,
            },
            "evidence": _evidence_schema(),
            "note": {"type": "string"},
        },
        "required": ["status", "score", "rationale", "raw", "evidence", "note"],
        "additionalProperties": False,
    }


def build_schema(items: list[ItemSpec]) -> dict:
    return {
        "type": "object",
        "properties": {spec.code: _item_schema(spec) for spec in items},
        "required": [spec.code for spec in items],
        "additionalProperties": False,
    }


def _describe_fields(spec: ItemSpec) -> str:
    lines = []
    for name, schema in spec.fields.items():
        description = schema.get("description", "")
        allowed = [value for value in schema.get("enum", []) if value is not None]
        suffix = f" (허용값: {', '.join(allowed)})" if allowed else ""
        lines.append(f"    - {name}: {description}{suffix}")
    return "\n".join(lines)


def build_request(items: list[ItemSpec]) -> str:
    """항목 채점 요청문. 종목명·정량 점수·주가는 넣지 않는다."""
    blocks = [
        f"첨부한 문서를 읽고 아래 {len(items)}개 항목을 채점하라. 항목 코드를 키로 하는 JSON 하나로 답하라.",
        "",
    ]
    for spec in items:
        blocks.append(f"[{spec.code}] {spec.title}")
        blocks.append(f"  질문: {spec.question}")
        blocks.append(f"  S({ANCHOR_S:.0f}+): {spec.anchor_s}")
        blocks.append(f"  B({ANCHOR_B:.0f}): {spec.anchor_b}")
        blocks.append(f"  F({ANCHOR_F:.0f} 미만): {spec.anchor_f}")
        blocks.append(f"  어디를 보나: {spec.sources}")
        blocks.append("  raw 필드:")
        blocks.append(_describe_fields(spec))
        blocks.append("")
    return "\n".join(blocks)
