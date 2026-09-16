"""LLM 응답 JSON을 항목별로 전체 스키마에 대조한다 — provider 공통 사후 검증.

두 provider 모두 출력은 `prompts.build_output_schema`(observations 배열, raw는 JSON 문자열) 형태로 받는다 —
Anthropic은 nullable 필드 수·문법 크기 제한, OpenAI 호환은 JSON 모드라 스키마 강제가 없어서다. 어느 쪽이든 여기서 항목 하나씩
전체 스키마(`prompts.build_schema`)로 검사해, 어긋난 항목만 결측으로 바꾸고 나머지는 살린다.
"""

import json

import jsonschema

MISSING_ITEM: dict = {"status": "missing", "score": None, "rationale": "", "raw": None, "evidence": [], "note": ""}
NOTE_SCHEMA_VIOLATION: str = "응답이 스키마를 어겨 결측 처리"


def normalize_payload(payload: dict) -> dict:
    """출력 형태(observations 배열, raw JSON 문자열) → 항목 코드를 키로 하는 dict. 못 푸는 raw는 그대로
    두어 validate_items가 결측 처리하게 한다."""
    entries = payload.get("observations") if isinstance(payload, dict) else None
    if isinstance(entries, list):
        # 검증 스키마(build_schema)의 항목에는 item 키가 없다(additionalProperties:false) — 키로 옮기고 뺀다.
        by_code = {entry["item"]: {k: v for k, v in entry.items() if k != "item"}
                   for entry in entries if isinstance(entry, dict) and "item" in entry}
    else:
        by_code = payload if isinstance(payload, dict) else {}
    for item in by_code.values():
        if isinstance(item.get("raw"), str):
            try:
                item["raw"] = json.loads(item["raw"])
            except json.JSONDecodeError:
                pass
    return by_code


def validate_items(payload: dict, schema: dict) -> tuple[dict, list[str]]:
    """항목별 스키마 검사. (검사 통과한 payload, 결측으로 바꾼 항목 코드 목록)."""
    repaired: dict = {}
    replaced: list[str] = []
    for code, item_schema in schema["properties"].items():
        item = payload.get(code) if isinstance(payload, dict) else None
        try:
            jsonschema.validate(item, item_schema)
            repaired[code] = item
        except jsonschema.ValidationError:
            repaired[code] = {**MISSING_ITEM, "note": NOTE_SCHEMA_VIOLATION}
            replaced.append(code)
    return repaired, replaced
