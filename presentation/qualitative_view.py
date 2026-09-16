"""정성 등급카드 뷰 — DB 한 행(qualitative_grades) + 관측값 JSON → 상세 페이지가 그릴 모델.

분석 계층은 사유·플래그를 코드로만 남기고("VETO_EXECUTIVE_FRAUD", "UNEXPLAINED_DOWN"), 언어는 표현
계층 책임이라 코드→한국어 변환은 이 파일 한 곳에만 둔다(`qip4_view.py`와 같은 층위).

점수·weak·해당 없음은 DB의 item_scores를 믿지 않고 관측값 JSON을 다시 판정해서 얻는다 — 판정기는
결정적이라 결과가 같고, 근거 서술·인용은 JSON에만 있기 때문이다. JSON이 없으면(저장소에서 지워진
경우) DB의 점수만으로 항목 칩을 그리고 근거는 비운다.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from analysis.qualitative import load_observations, qualitative_grade
from analysis.qualitative.weights import GRADE_VALID_MONTHS, ITEM_WEIGHTS, WEAK_SCORE_CAP
from collection.qualitative.items import ITEM_CODES, ITEMS_BY_CODE

_VETO_LABELS: dict[str, str] = {
    "VETO_SPINOFF_RELISTING": "핵심 사업 물적분할 후 중복상장 이력",
    "VETO_EXECUTIVE_FRAUD": "최근 5년 지배주주·경영진 배임·횡령·분식 판결 또는 기소",
    "VETO_UNFAIR_MERGER": "소액주주에 불리한 합병·분할 비율 강행 이력",
}
_CAP_LABELS: dict[str, str] = {
    "CAP_GOVERNANCE_AT_MOST_C": "지배구조(Q6)가 C 이하라 배수 상한 1.0",
}
_FLAG_LABELS: dict[str, str] = {
    "UNEXPLAINED_UP": "설명되지 않는 상승 — 6개월 주가는 크게 올랐는데 연간 영업이익 변화가 이를 뒷받침하지 않는다. 근거의 실체를 되물을 것",
    "UNEXPLAINED_DOWN": "설명되지 않는 하락 — 6개월 주가는 크게 내렸는데 연간 영업이익은 그렇지 않다. 기회일 수도, 미공개 악재일 수도 있다",
}
_STATUS_LABELS: dict[str, str] = {
    "missing": "원문에 없음",
    "not_investigated": "미조사",
}
_EVIDENCE_GRADE_LABELS: dict[int, str] = {1: "공시 원문", 2: "산업 통계·상대방 발언", 3: "리포트·언론"}
_TIER_LABELS: dict[str, str] = {"quick": "빠른 검사", "deep": "정밀 검사"}
_ORDER_BOOK_FIELD: str = "order_book_business"
_MAX_EVIDENCE_PER_ITEM: int = 2


@dataclass(frozen=True)
class EvidenceView:
    grade_label: str
    locator: str
    quote: str


@dataclass(frozen=True)
class QualitativeItemView:
    code: str
    title: str
    short: str
    weight: int
    score: float | None
    grade: str | None
    weak: bool
    status_label: str  # 점수가 없을 때의 이유 ("해당 없음", "원문에 없음", "미조사")
    rationale: str
    note: str
    evidence: list[EvidenceView] = field(default_factory=list)

    @property
    def grade_class(self) -> str:
        return f"qual-grade-{self.grade.lower()}" if self.grade else "qual-grade-none"


@dataclass(frozen=True)
class QualitativeCardView:
    composite: str | None
    score: float | None
    multiplier: float | None
    decision: str
    graded_on: str
    observed_asof: str
    valid_until: str
    expired: bool
    scorer_label: str  # "빠른 검사 · deepseek-flash"
    source_title: str
    trend_flag_label: str | None
    veto_labels: list[str]
    cap_labels: list[str]
    watch_items: list[QualitativeItemView]
    items: list[QualitativeItemView]
    weak_cap: float = WEAK_SCORE_CAP

    @property
    def composite_class(self) -> str:
        return f"qual-grade-{self.composite.lower()}" if self.composite else "qual-grade-none"


def _iso(value: object) -> str:
    if value is None:
        return ""
    return str(value)[:10]


def _scorer_label(tier: str | None, model: str | None) -> str:
    tier_label = _TIER_LABELS.get(tier or "", "")
    if tier_label and model:
        return f"{tier_label} · {model}"
    return tier_label or model or "사람 직접 채점"


def _items_from_observations(observation_set) -> list[QualitativeItemView]:
    result = qualitative_grade(observation_set)
    by_code = observation_set.by_code()
    views: list[QualitativeItemView] = []
    for code in ITEM_CODES:
        spec = ITEMS_BY_CODE[code]
        item = result.items[code]
        observation = by_code.get(code)
        status_label = ""
        if item.score is None and observation is not None:
            if (observation.raw or {}).get(_ORDER_BOOK_FIELD) is False:
                status_label = "해당 없음 (수주형 사업 아님)"
            else:
                status_label = _STATUS_LABELS.get(observation.status, "근거 없음")
        evidence = [
            EvidenceView(_EVIDENCE_GRADE_LABELS.get(e.grade, f"{e.grade}급"), e.locator, " ".join(e.quote.split()))
            for e in (observation.evidence if observation else [])[:_MAX_EVIDENCE_PER_ITEM]
        ]
        views.append(QualitativeItemView(
            code=code, title=spec.title, short=spec.short, weight=int(ITEM_WEIGHTS[code]),
            score=item.score, grade=item.grade, weak=item.weak, status_label=status_label,
            rationale=observation.rationale if observation else "", note=observation.note if observation else "",
            evidence=evidence,
        ))
    return views


def _items_from_db_scores(item_scores: str | None) -> list[QualitativeItemView]:
    scores = json.loads(item_scores) if item_scores else {}
    views: list[QualitativeItemView] = []
    for code in ITEM_CODES:
        spec = ITEMS_BY_CODE[code]
        entry = scores.get(code) or {}
        views.append(QualitativeItemView(
            code=code, title=spec.title, short=spec.short, weight=int(ITEM_WEIGHTS[code]),
            score=entry.get("score"), grade=entry.get("grade"), weak=False,
            status_label="" if entry.get("score") is not None else "근거 파일 없음", rationale="", note="",
        ))
    return views


def build_qualitative_card(row: dict, today: date | None = None) -> QualitativeCardView:
    """qualitative_grades 한 행(dict)에서 카드 뷰를 만든다. 관측값 JSON은 row["observations_path"]에서 읽는다."""
    today = today or date.today()
    observations_path = Path(row.get("observations_path") or "")
    observation_set = load_observations(observations_path) if observations_path.is_file() else None
    items = _items_from_observations(observation_set) if observation_set else _items_from_db_scores(row.get("item_scores"))
    watch_codes = [code for code in (row.get("watch_items") or "").split("|") if code]
    valid_until = _iso(row.get("valid_until"))
    return QualitativeCardView(
        composite=row.get("composite"),
        score=row.get("score"),
        multiplier=row.get("multiplier"),
        decision=str(row.get("decision") or ""),
        graded_on=_iso(row.get("graded_on")),
        observed_asof=_iso(row.get("observed_asof")),
        valid_until=valid_until,
        expired=bool(valid_until) and date.fromisoformat(valid_until) < today,
        scorer_label=_scorer_label(row.get("tier"), row.get("model")),
        source_title=observation_set.source_title if observation_set else "",
        trend_flag_label=_FLAG_LABELS.get(row.get("trend_flag") or ""),
        veto_labels=[_VETO_LABELS.get(code, code) for code in (row.get("veto_reasons") or "").split("|") if code],
        cap_labels=[_CAP_LABELS.get(code, code) for code in (row.get("cap_reasons") or "").split("|") if code],
        watch_items=[item for item in items if item.code in watch_codes],
        items=items,
    )


VALID_MONTHS: int = GRADE_VALID_MONTHS
