"""LLM 추출 프롬프트와 축별 JSON 스키마 — `.claude/정성 평가 규칙.md` 4-2의 규칙을 구현한다.

1. 판정 금지: "좋은가"를 묻지 않는다. 사실(raw 필드)만 요구한다.
2. 인용 의무: 모든 값에 원문 발췌(quote)와 위치(locator)를 요구한다. 로케이터 없는 값은
   추출기가 채택하지 않는다.
3. 없음의 허용: "찾을 수 없음"(status=missing)을 정답으로 명시한다.
4. 요약 금지, 발췌만.
5. 정량 점수·주가 정보는 프롬프트에 넣지 않는다(앵커링 차단).

시스템 프롬프트는 고정 문자열이다 — 프롬프트 캐시가 접두 일치라 여기에 날짜나 종목명을
넣으면 캐시가 매번 깨진다. 종목·축별로 바뀌는 내용은 요청 본문(build_axis_request)에 둔다.
"""

from collection.qualitative.items import AXIS_NAMES, ItemSpec

SYSTEM_PROMPT: str = """당신은 기업 공시 문서(사업보고서, 10-K, 주석, 공시)에서 **사실만 추출하는** 추출기다.

역할의 한계:
- 어떤 항목에 대해서도 좋다/나쁘다를 판단하지 않는다. 판단은 다른 프로그램이 규칙으로 한다.
- 문서에 없는 것을 추정하거나 일반 지식으로 채우지 않는다. 문서에서 확인되지 않으면 status를 "missing"으로 두고 raw 필드는 null로 둔다. "찾을 수 없음"은 정답이다.
- 요약하지 않는다. 필요한 표·문장을 그대로 발췌한다.

각 항목의 출력 규칙:
- raw: 요청된 필드에 문서에서 확인한 값만 넣는다. 비율은 0~1 소수로 쓴다. 확인되지 않은 필드는 null.
- evidence: 값을 뒷받침하는 원문 발췌. quote는 문서의 문장·표 셀을 **한 글자도 바꾸지 않고** 그대로 복사한다(번역·요약 금지). locator는 문서 내 위치(항목 제목, 주석 번호, 페이지 등). source는 문서 이름·종류, date는 문서 기준일(모르면 빈 문자열). grade는 증거 등급: 1=사업보고서·주석·공시 원문, 2=산업 통계·거래상대방 공개 발언, 3=애널리스트 리포트, 4=언론·커뮤니티.
- 하나의 값이 여러 곳에서 확인되면 evidence를 여러 개 넣는다.
- note에는 값의 해석에 필요한 사실 관계만 짧게 적는다(예: "연결 기준", "회계연도 변경"). 평가 어휘를 쓰지 않는다.
- 주가·수급·시장 심리·목표주가·테마에 관한 서술은 어떤 필드에도 넣지 않는다."""


def _evidence_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "date": {"type": "string"},
                "grade": {"type": "integer", "enum": [1, 2, 3, 4]},
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
            "raw": {
                "type": "object",
                "properties": spec.fields,
                "required": list(spec.fields),
                "additionalProperties": False,
            },
            "evidence": _evidence_schema(),
            "note": {"type": "string"},
        },
        "required": ["status", "raw", "evidence", "note"],
        "additionalProperties": False,
    }


def build_axis_schema(items: list[ItemSpec]) -> dict:
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


def build_axis_request(axis: str, items: list[ItemSpec]) -> str:
    """축 하나에 속한 항목들의 추출 요청문. 종목명·정량 점수는 넣지 않는다."""
    blocks = [
        f"첨부한 문서에서 아래 {len(items)}개 항목의 사실을 추출하라. 축: {axis} — {AXIS_NAMES[axis]}.",
        "항목 코드를 키로 하는 JSON 하나로 답하라.",
        "",
    ]
    for spec in items:
        blocks.append(f"[{spec.code}] {spec.title}")
        blocks.append(f"  어디를 보나: {spec.guidance}")
        blocks.append("  필드:")
        blocks.append(_describe_fields(spec))
        blocks.append("")
    return "\n".join(blocks)
