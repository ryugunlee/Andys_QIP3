"""정성 등급 판정기 (L3) — 관측값 JSON → 6축 등급·종합등급·배수·판정.

`.claude/정성 평가 규칙.md` 5-1 의사코드의 구현. 결정적이다: 같은 관측값이면 같은 등급이
나온다. 판정에 사람이나 LLM이 개입하는 지점은 없다 — 주관은 L2(관측값)에만 있고,
그래서 재현성 검증(5-3)은 관측값 diff만 보면 된다.

QIP4와 맞지 않아 1단계에서 보류한 규칙(태그 교차·티어·비중 계산)은 구현하지 않았다.
배수는 산출하되 집행률과 곱하지 않는다 — 이 프로그램은 절대 비중을 내지 않는다.
"""

from dataclasses import dataclass, field

import analysis.qualitative.weights as w
from analysis.qualitative.rubric import (
    is_survival_veto,
    score_raw,
    veto_reasons_for_governance,
)
from analysis.qualitative.schema import (
    EVIDENCE_GRADE_WEAK_MIN,
    STATUS_NOT_INVESTIGATED,
    STATUS_WEAK,
    Observation,
    ObservationSet,
)
from collection.qualitative.items import AXIS_CODES, ITEMS_BY_CODE, items_of_axis

VETO_SURVIVAL: str = "I6_EXTINCTION_PATH"
CYCLE_ITEM: str = "I5"
MOAT_ITEM: str = "D1"


@dataclass
class AxisResult:
    axis: str
    grade: str
    ratio: float | None
    earned: int
    max_points: int
    item_points: dict[str, int | None] = field(default_factory=dict)


@dataclass
class GradeResult:
    axes: dict[str, AxisResult]
    composite: str | None
    score: float | None
    multiplier: float | None
    decision: str
    veto_reasons: list[str]
    cap_reasons: list[str]
    watch_items: list[str]
    not_investigated_share: float


def _is_weak(observation: Observation) -> bool:
    if observation.status == STATUS_WEAK:
        return True
    graded = [evidence.grade for evidence in observation.evidence]
    return bool(graded) and min(graded) >= EVIDENCE_GRADE_WEAK_MIN


def score_observation(observation: Observation) -> int | None:
    """항목 점수. 결측·미조사·판정 불가는 None, weak는 상한 1점."""
    if observation.is_excluded():
        return None
    points = score_raw(observation.item, observation.raw)
    if points is None:
        return None
    if _is_weak(observation):
        return min(points, w.WEAK_ITEM_MAX_POINTS)
    return points


def _band(value: float, bands: tuple[tuple[float, str], ...]) -> str:
    return next(grade for threshold, grade in bands if value >= threshold)


def _applicable_items(axis: str, sector_group: str | None) -> list[str]:
    codes = [spec.code for spec in items_of_axis(axis) if spec.counts_toward_axis]
    if axis == "I" and sector_group != w.CYCLICAL_SECTOR_GROUP:
        codes = [code for code in codes if code != CYCLE_ITEM]
    return codes


def grade_axis(axis: str, observations: dict[str, Observation], sector_group: str | None) -> AxisResult:
    codes = _applicable_items(axis, sector_group)
    total_max = len(codes) * w.ITEM_MAX_POINTS
    earned = 0
    max_points = 0
    item_points: dict[str, int | None] = {}
    for code in codes:
        observation = observations.get(code)
        points = score_observation(observation) if observation else None
        item_points[code] = points
        if points is None:
            continue
        earned += points
        max_points += w.ITEM_MAX_POINTS
    if max_points < total_max * w.AXIS_NA_MIN_VALID_RATIO or max_points == 0:
        return AxisResult(axis, w.GRADE_NA, None, earned, max_points, item_points)
    ratio = earned / max_points
    return AxisResult(axis, _band(ratio, w.AXIS_BANDS), ratio, earned, max_points, item_points)


def veto_reasons(observations: dict[str, Observation]) -> list[str]:
    reasons: list[str] = []
    governance = observations.get("G5")
    if governance and not governance.is_excluded():
        reasons.extend(veto_reasons_for_governance(governance.raw))
    survival = observations.get("I6")
    if survival and not survival.is_excluded() and is_survival_veto(survival.raw):
        reasons.append(VETO_SURVIVAL)
    return reasons


def _grade_at_most(grade: str, ceiling: str) -> bool:
    """grade가 ceiling과 같거나 더 나쁜가. NA는 비교 대상이 아니다."""
    if grade == w.GRADE_NA:
        return False
    return w.GRADE_ORDER.index(grade) >= w.GRADE_ORDER.index(ceiling)


def multiplier_with_caps(
    composite: str, axes: dict[str, AxisResult], observations: dict[str, Observation]
) -> tuple[float, list[str]]:
    """6-1 기본 배수에 6-2 하한 규칙을 적용한다. 사유 코드를 함께 돌려준다."""
    multiplier = w.MULTIPLIER_BY_GRADE[composite]
    reasons: list[str] = []

    def cap(limit: float, reason: str) -> None:
        # 배수가 이미 상한 이하여도 사유는 남긴다 — 등급카드의 "축별 하한 규칙" 칸에 보여야 한다.
        nonlocal multiplier
        multiplier = min(multiplier, limit)
        reasons.append(reason)

    d_count = sum(1 for result in axes.values() if result.grade == w.GRADE_D)
    if d_count >= w.HOLD_WHEN_D_AXES_AT_LEAST:
        return 0.0, ["HOLD_THREE_D_AXES"]
    if d_count >= w.D_AXES_FOR_CAP:
        cap(w.CAP_WHEN_TWO_D_AXES, "CAP_TWO_D_AXES")
    if _grade_at_most(axes["G"].grade, w.GRADE_C):
        cap(w.CAP_WHEN_G_OR_D_AT_MOST_C, "CAP_G_AT_MOST_C")
    if _grade_at_most(axes["D"].grade, w.GRADE_C):
        cap(w.CAP_WHEN_G_OR_D_AT_MOST_C, "CAP_D_AT_MOST_C")
    if any(result.grade == w.GRADE_NA for result in axes.values()):
        cap(w.CAP_WHEN_NA_AXIS, "CAP_NA_AXIS")
    moat = observations.get(MOAT_ITEM)
    if moat and score_observation(moat) == 0:
        cap(w.CAP_WHEN_MOAT_UNSPECIFIED, "CAP_MOAT_UNSPECIFIED")
    return multiplier, reasons


def _decision(multiplier: float) -> str:
    if multiplier >= w.DECISION_MIN_MULTIPLIER_ADOPT:
        return w.DECISION_ADOPT
    if multiplier >= w.DECISION_MIN_MULTIPLIER_LIMITED:
        return w.DECISION_LIMITED
    if multiplier > w.DECISION_MIN_MULTIPLIER_HOLD:
        return w.DECISION_HOLD
    return w.DECISION_REJECT


def _not_investigated_share(observation_set: ObservationSet) -> float:
    applicable = [
        code for axis in AXIS_CODES for code in _applicable_items(axis, observation_set.sector_group)
    ]
    by_code = observation_set.by_code()
    uninvestigated = sum(
        1 for code in applicable
        if code not in by_code or by_code[code].status == STATUS_NOT_INVESTIGATED
    )
    return uninvestigated / len(applicable)


def _watch_items(axes: dict[str, AxisResult]) -> list[str]:
    """0·1점 항목은 자동으로 감시 대상(반증 조건표)이 된다 (7-1)."""
    return [
        code
        for result in axes.values()
        for code, points in result.item_points.items()
        if points is not None and points < w.ITEM_MAX_POINTS
    ]


def qualitative_grade(observation_set: ObservationSet) -> GradeResult:
    observations = observation_set.by_code()
    axes = {axis: grade_axis(axis, observations, observation_set.sector_group) for axis in AXIS_CODES}
    uninvestigated = _not_investigated_share(observation_set)
    watch = _watch_items(axes)

    vetoes = veto_reasons(observations)
    if vetoes:
        return GradeResult(axes, w.GRADE_F, None, 0.0, w.DECISION_REJECT, vetoes, [], watch, uninvestigated)

    if uninvestigated > w.INCOMPLETE_MAX_NOT_INVESTIGATED_SHARE:
        return GradeResult(axes, None, None, None, w.DECISION_INCOMPLETE, [], [], watch, uninvestigated)

    active = {axis: w.AXIS_WEIGHTS[axis] for axis, result in axes.items() if result.grade != w.GRADE_NA}
    if not active:
        return GradeResult(axes, None, None, None, w.DECISION_INCOMPLETE, [], [], watch, uninvestigated)
    scale = 1.0 / sum(active.values())
    score = sum(w.GRADE_SCORE[axes[axis].grade] * weight * scale for axis, weight in active.items())
    composite = _band(score, w.COMPOSITE_BANDS)
    multiplier, cap_reasons = multiplier_with_caps(composite, axes, observations)
    return GradeResult(
        axes, composite, round(score, 1), multiplier, _decision(multiplier), [], cap_reasons, watch, uninvestigated
    )


def item_title(code: str) -> str:
    return ITEMS_BY_CODE[code].title
