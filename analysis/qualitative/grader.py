"""정성 등급 판정기 — 관측값 JSON → 항목 등급·종합등급·배수·판정.

`.claude/정성 평가 규칙.md` 3절의 구현. 결정적이다: 같은 관측값이면 같은 결과. 채점자(LLM·사람)의
주관은 관측값의 점수·근거에만 있고, 여기서는 수치 재계산·weak 상한·결격·가중 평균·배수만 한다.
배수는 산출하되 집행률과 곱하지 않는다 — 이 프로그램은 절대 비중을 내지 않는다.
"""

from dataclasses import dataclass

import analysis.qualitative.weights as w
from analysis.qualitative.rubric import recompute_score, veto_reasons_for_governance
from analysis.qualitative.schema import EVIDENCE_GRADE_WEAK_MIN, STATUS_WEAK, Observation, ObservationSet
from collection.qualitative.items import ITEM_CODES, ITEMS_BY_CODE


@dataclass
class ItemResult:
    code: str
    score: float | None
    grade: str | None
    weak: bool
    recomputed: bool


@dataclass
class GradeResult:
    items: dict[str, ItemResult]
    composite: str | None
    score: float | None
    multiplier: float | None
    decision: str
    veto_reasons: list[str]
    cap_reasons: list[str]
    watch_items: list[str]
    valid_items: int


def grade_of(score: float) -> str:
    return next(grade for threshold, grade in w.GRADE_BANDS if score >= threshold)


def _is_weak(observation: Observation) -> bool:
    if observation.status == STATUS_WEAK:
        return True
    graded = [evidence.grade for evidence in observation.evidence]
    return bool(graded) and min(graded) >= EVIDENCE_GRADE_WEAK_MIN


def score_item(code: str, observation: Observation | None) -> ItemResult:
    """항목 점수. 결측·미조사·근거 없음은 None. raw 수치가 있으면 재계산, weak는 상한."""
    empty = ItemResult(code, None, None, False, False)
    if observation is None or observation.is_excluded() or not observation.rationale.strip():
        return empty
    recomputed = recompute_score(code, observation.raw)
    score = recomputed if recomputed is not None else observation.score
    if score is None:
        return empty
    weak = _is_weak(observation)
    if weak:
        score = min(float(score), w.WEAK_SCORE_CAP)
    score = min(max(float(score), w.SCORE_MIN), w.SCORE_MAX)
    return ItemResult(code, round(score, 1), grade_of(score), weak, recomputed is not None)


def _grade_at_most(grade: str | None, ceiling: str) -> bool:
    return grade is not None and w.GRADE_ORDER.index(grade) >= w.GRADE_ORDER.index(ceiling)


def multiplier_with_caps(composite: str, items: dict[str, ItemResult]) -> tuple[float, list[str]]:
    multiplier = w.MULTIPLIER_BY_GRADE[composite]
    reasons: list[str] = []
    if _grade_at_most(items[w.GOVERNANCE_ITEM].grade, w.GRADE_C):
        multiplier = min(multiplier, w.CAP_WHEN_GOVERNANCE_AT_MOST_C)
        reasons.append("CAP_GOVERNANCE_AT_MOST_C")
    return multiplier, reasons


def _decision(multiplier: float) -> str:
    if multiplier >= w.DECISION_MIN_MULTIPLIER_ADOPT:
        return w.DECISION_ADOPT
    if multiplier >= w.DECISION_MIN_MULTIPLIER_LIMITED:
        return w.DECISION_LIMITED
    if multiplier > w.DECISION_MIN_MULTIPLIER_HOLD:
        return w.DECISION_HOLD
    return w.DECISION_REJECT


def qualitative_grade(observation_set: ObservationSet) -> GradeResult:
    observations = observation_set.by_code()
    items = {code: score_item(code, observations.get(code)) for code in ITEM_CODES}
    watch = [code for code, result in items.items() if _grade_at_most(result.grade, w.WATCH_GRADE_AT_MOST)]
    valid = {code: result for code, result in items.items() if result.score is not None}

    governance = observations.get(w.GOVERNANCE_ITEM)
    vetoes = veto_reasons_for_governance(governance.raw) if governance and not governance.is_excluded() else []
    if vetoes:
        return GradeResult(items, w.GRADE_F, None, 0.0, w.DECISION_REJECT, vetoes, [], watch, len(valid))

    if len(valid) < w.MIN_VALID_ITEMS:
        return GradeResult(items, None, None, None, w.DECISION_INCOMPLETE, [], [], watch, len(valid))

    weight_sum = sum(w.ITEM_WEIGHTS[code] for code in valid)
    score = sum(result.score * w.ITEM_WEIGHTS[code] for code, result in valid.items()) / weight_sum
    composite = grade_of(score)
    multiplier, cap_reasons = multiplier_with_caps(composite, items)
    return GradeResult(
        items, composite, round(score, 1), multiplier, _decision(multiplier), [], cap_reasons, watch, len(valid)
    )


def item_title(code: str) -> str:
    return ITEMS_BY_CODE[code].title
