"""채점 추출기 — 원문 문서 → 관측값 JSON (점수·근거·raw·증거).

`.claude/정성 평가 규칙.md` 6절의 운영 규칙을 코드로 강제한다:
- LLM 1회 호출로 요청한 항목을 전부 채점한다.
- 인용 대조: 추출된 quote가 원문에 실제로 있는지 문자열로 확인한다. 없으면 `weak`.
  이것이 환각을 막는 유일한 기계적 장치다(로케이터만 요구하면 로케이터도 지어낸다).
- 증거가 하나도 없는 값은 채택하지 않는다(`missing`).
- 자기참조 어휘(부록 A)가 근거·인용에 섞이면 `weak`로 강등하고 검출 어휘를 메모에 남긴다.
"""

import re

from analysis.qualitative.schema import (
    STATUS_MISSING,
    STATUS_NOT_INVESTIGATED,
    STATUS_OBSERVED,
    STATUS_WEAK,
    Evidence,
    Observation,
    ObservationSet,
)
from collection.qualitative.items import ITEM_CODES, ITEM_SPECS, ITEMS_BY_CODE, ItemSpec
from collection.qualitative.lexicon_filter import find_blocked_terms
from collection.qualitative.llm_client import extract_structured
from collection.qualitative.prompts import SYSTEM_PROMPT, build_request, build_schema
from collection.qualitative.sources import SourceDocument

NOTE_QUOTE_UNVERIFIED: str = "인용 대조 실패(원문에서 발췌문을 찾지 못함)"
NOTE_BLOCKED_TERMS: str = "자기참조 어휘 검출"
NOTE_NO_EVIDENCE: str = "증거 없음"
NOTE_NOT_REQUESTED: str = "이번 추출에서 요청하지 않은 항목"

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub("", text)


def _quote_found(quote: str, document: SourceDocument) -> bool:
    if not document.can_verify_quotes or not quote.strip():
        return False
    return _normalize(quote) in _normalize(document.text or "")


def _evidence_from_payload(entries: list[dict]) -> list[Evidence]:
    return [
        Evidence(
            source=entry["source"], date=entry["date"], grade=int(entry["grade"]),
            quote=entry["quote"], locator=entry["locator"],
        )
        for entry in entries
        if entry.get("locator") or entry.get("quote")
    ]


def _observation_from_payload(spec: ItemSpec, payload: dict, document: SourceDocument) -> Observation:
    note = payload.get("note", "")
    if payload["status"] == STATUS_MISSING:
        return Observation(item=spec.code, status=STATUS_MISSING, note=note)

    evidence = _evidence_from_payload(payload.get("evidence", []))
    if not evidence:
        return Observation(item=spec.code, status=STATUS_MISSING, note="; ".join(filter(None, [note, NOTE_NO_EVIDENCE])))

    notes: list[str] = [note] if note else []
    status = STATUS_OBSERVED
    if document.can_verify_quotes and not any(_quote_found(item.quote, document) for item in evidence):
        status = STATUS_WEAK
        notes.append(NOTE_QUOTE_UNVERIFIED)
    blocked = find_blocked_terms(" ".join([payload.get("rationale", ""), *(item.quote for item in evidence)]))
    if blocked:
        status = STATUS_WEAK
        notes.append(f"{NOTE_BLOCKED_TERMS}: {', '.join(blocked)}")

    return Observation(
        item=spec.code, status=status, score=payload.get("score"), rationale=payload.get("rationale", ""),
        raw=payload["raw"], evidence=evidence, note="; ".join(notes),
    )


def extract_observations(
    client,
    document: SourceDocument,
    ticker: str,
    asof: str,
    sector_group: str | None,
    items: tuple[str, ...] = ITEM_CODES,
) -> ObservationSet:
    """LLM 1회 호출로 요청 항목을 채점한다. 요청하지 않은 항목은 not_investigated로 남긴다."""
    specs = [ITEMS_BY_CODE[code] for code in items]
    payload = extract_structured(
        client, system=SYSTEM_PROMPT, document=document,
        request_text=build_request(specs), schema=build_schema(specs),
    )
    scored = {spec.code: _observation_from_payload(spec, payload[spec.code], document) for spec in specs}
    observations = [
        scored.get(spec.code, Observation(item=spec.code, status=STATUS_NOT_INVESTIGATED, note=NOTE_NOT_REQUESTED))
        for spec in ITEM_SPECS
    ]
    return ObservationSet(
        ticker=ticker, asof=asof, sector_group=sector_group,
        observations=observations, source_title=document.title,
    )


def blank_observations(ticker: str, asof: str, sector_group: str | None) -> ObservationSet:
    """수동 입력용 빈 관측값 — 사람이 점수·근거·raw를 채우는 템플릿."""
    observations = [
        Observation(item=spec.code, status=STATUS_NOT_INVESTIGATED, raw={name: None for name in spec.fields})
        for spec in ITEM_SPECS
    ]
    return ObservationSet(ticker=ticker, asof=asof, sector_group=sector_group, observations=observations)
