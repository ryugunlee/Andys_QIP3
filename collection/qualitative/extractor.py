"""관측값 추출기 (L2) — 원문 문서 → 표준 관측값 JSON.

`.claude/정성 평가 규칙.md` 4-2·4-3의 운영 규칙을 코드로 강제한다:
- A·B급 항목만 LLM에 맡기고 C급(수동 판독)은 `not_investigated`로 남긴다.
- 인용 대조: 추출된 quote가 원문에 실제로 있는지 문자열로 확인한다. 없으면 `weak`.
  이것이 환각을 막는 유일한 기계적 장치다(로케이터만 요구하면 로케이터도 지어낸다).
- 핵심 항목(G1·G2)은 2회 독립 추출해 raw가 다르면 `weak`로 강등하고 메모를 남긴다.
- 자기참조 어휘(부록 B)가 인용·메모에 섞이면 그 항목은 `not_investigated`로 돌린다 —
  문서 4-3의 "검출 시 판정 미완료"를 항목 단위로 적용한 것이다.
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
from analysis.qualitative.weights import CYCLICAL_SECTOR_GROUP
from collection.qualitative.items import (
    AUTOMATION_MANUAL,
    AXIS_CODES,
    ItemSpec,
    automated_items_of_axis,
    items_of_axis,
)
from collection.qualitative.lexicon_filter import find_blocked_terms
from collection.qualitative.llm_client import extract_structured
from collection.qualitative.prompts import SYSTEM_PROMPT, build_axis_request, build_axis_schema
from collection.qualitative.sources import SourceDocument

# 2회 독립 추출로 대조하는 핵심 항목 (문서 4-2 ④). D1·D2·I6도 핵심이지만 C급이라 LLM 대상이 아니다.
DOUBLE_CHECK_ITEMS: tuple[str, ...] = ("G1", "G2")
CYCLE_ITEM: str = "I5"

NOTE_MANUAL: str = "C급 수동 판독 항목 — 사람이 채운다"
NOTE_NOT_CYCLICAL: str = "사이클 산업이 아니라 판정 대상 아님"
NOTE_QUOTE_UNVERIFIED: str = "인용 대조 실패(원문에서 발췌문을 찾지 못함)"
NOTE_DOUBLE_CHECK_MISMATCH: str = "2회 독립 추출 불일치 — 원문 확인 필요"
NOTE_BLOCKED_TERMS: str = "자기참조 어휘 검출"

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
    if payload["status"] == STATUS_MISSING:
        return Observation(item=spec.code, status=STATUS_MISSING, raw=None, evidence=[], note=payload.get("note", ""))

    evidence = _evidence_from_payload(payload.get("evidence", []))
    notes: list[str] = [payload.get("note", "")] if payload.get("note") else []
    status = STATUS_OBSERVED
    if not evidence:
        status = STATUS_MISSING  # 로케이터 없는 값은 채택하지 않는다 (4-2 ②)
        notes.append("증거 없음")
        return Observation(item=spec.code, status=status, raw=None, evidence=[], note="; ".join(notes))

    if document.can_verify_quotes and not any(_quote_found(item.quote, document) for item in evidence):
        status = STATUS_WEAK
        notes.append(NOTE_QUOTE_UNVERIFIED)

    blocked = find_blocked_terms(" ".join([*notes, *(item.quote for item in evidence)]))
    if blocked:
        status = STATUS_NOT_INVESTIGATED
        notes.append(f"{NOTE_BLOCKED_TERMS}: {', '.join(blocked)}")

    return Observation(item=spec.code, status=status, raw=payload["raw"], evidence=evidence, note="; ".join(notes))


def _extract_axis(client, document: SourceDocument, axis: str, specs: list[ItemSpec]) -> dict:
    return extract_structured(
        client,
        system=SYSTEM_PROMPT,
        document=document,
        request_text=build_axis_request(axis, specs),
        schema=build_axis_schema(specs),
    )


def _apply_double_check(observations: dict[str, Observation], second: dict) -> None:
    for code in DOUBLE_CHECK_ITEMS:
        first = observations.get(code)
        if first is None or code not in second or first.is_excluded():
            continue
        if second[code]["status"] == STATUS_MISSING or second[code]["raw"] != first.raw:
            first.status = STATUS_WEAK
            first.note = "; ".join(filter(None, [first.note, NOTE_DOUBLE_CHECK_MISMATCH]))


def extract_observations(
    client,
    document: SourceDocument,
    ticker: str,
    asof: str,
    sector_group: str | None,
    axes: tuple[str, ...] = AXIS_CODES,
    double_check: bool = True,
) -> ObservationSet:
    """축 단위로 LLM을 호출해 관측값을 만든다. 요청하지 않은 축은 결과에 넣지 않는다."""
    observations: list[Observation] = []
    for axis in axes:
        automated = automated_items_of_axis(axis)
        if axis == "I" and sector_group != CYCLICAL_SECTOR_GROUP:
            automated = [spec for spec in automated if spec.code != CYCLE_ITEM]

        payload = _extract_axis(client, document, axis, automated) if automated else {}
        axis_observations: dict[str, Observation] = {
            spec.code: _observation_from_payload(spec, payload[spec.code], document) for spec in automated
        }
        if double_check and any(code in axis_observations for code in DOUBLE_CHECK_ITEMS):
            _apply_double_check(axis_observations, _extract_axis(client, document, axis, automated))

        for spec in items_of_axis(axis):
            if spec.code in axis_observations:
                observations.append(axis_observations[spec.code])
            elif spec.automation == AUTOMATION_MANUAL:
                observations.append(Observation(item=spec.code, status=STATUS_NOT_INVESTIGATED, note=NOTE_MANUAL))
            else:
                observations.append(Observation(item=spec.code, status=STATUS_MISSING, note=NOTE_NOT_CYCLICAL))

    return ObservationSet(
        ticker=ticker, asof=asof, sector_group=sector_group,
        observations=observations, source_title=document.title,
    )


def blank_observations(ticker: str, asof: str, sector_group: str | None) -> ObservationSet:
    """수동 입력용 빈 관측값 — 파일럿에서 사람이 채우는 템플릿."""
    observations = [
        Observation(item=spec.code, status=STATUS_NOT_INVESTIGATED, raw={name: None for name in spec.fields})
        for axis in AXIS_CODES
        for spec in items_of_axis(axis)
    ]
    return ObservationSet(ticker=ticker, asof=asof, sector_group=sector_group, observations=observations)
