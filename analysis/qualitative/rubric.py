"""항목별 루브릭 — raw 사실 → 0 / 1 / 2점 (또는 판정 불가 None).

`.claude/정성 평가 규칙.md` 2절의 표를 함수로 옮겼다. 각 함수는 `collection/qualitative/items.py`가
정한 raw 필드만 읽고, 임계값은 전부 `weights.py`에서 가져온다.

None을 돌려주는 경우는 "필드가 비어 있어 판정할 수 없다"는 뜻이고, 판정기는 그 항목을
결측으로 취급한다(분자·분모 동시 제외). 0점(나쁨)과 결측(모름)을 섞지 않는 것이 문서의
네 번째 설계 원칙이다.
"""

from collections.abc import Callable

import analysis.qualitative.weights as w
from collection.qualitative.items import PIPELINE_STAGE_MAX, PIPELINE_STAGE_MIN

RubricFunction = Callable[[dict], int | None]

_POINTS_BEST: int = 2
_POINTS_MID: int = 1
_POINTS_WORST: int = 0


def _missing(raw: dict, *keys: str) -> bool:
    return any(raw.get(key) is None for key in keys)


def _three_way(value: str | None, best: tuple[str, ...], mid: tuple[str, ...]) -> int | None:
    """열거형 값 하나를 2/1/0으로 바꾼다. best·mid에 없으면 0."""
    if value is None:
        return None
    if value in best:
        return _POINTS_BEST
    if value in mid:
        return _POINTS_MID
    return _POINTS_WORST


def _lower_is_better(value: float | None, good_max: float, bad_min: float) -> int | None:
    if value is None:
        return None
    if value < good_max:
        return _POINTS_BEST
    if value < bad_min:
        return _POINTS_MID
    return _POINTS_WORST


def _higher_is_better(value: float | None, good_min: float, mid_min: float) -> int | None:
    if value is None:
        return None
    if value >= good_min:
        return _POINTS_BEST
    if value >= mid_min:
        return _POINTS_MID
    return _POINTS_WORST


# --- G ---
def _g1(raw: dict) -> int | None:
    if _missing(raw, "outside_directors", "total_directors"):
        return None
    majority = raw["outside_directors"] * 2 > raw["total_directors"]
    if not majority:
        return _POINTS_WORST
    dissent = raw.get("dissent_votes_3y")
    if dissent is None:
        return _POINTS_MID
    return _POINTS_BEST if dissent >= 1 else _POINTS_MID


def _g2(raw: dict) -> int | None:
    ratio = raw.get("related_party_ratio")
    if ratio is None:
        return None
    increasing = raw.get("trend_3y") == "increasing"
    if ratio >= w.RELATED_PARTY_BAD_MIN or increasing:
        return _POINTS_WORST
    if ratio < w.RELATED_PARTY_GOOD_MAX:
        return _POINTS_BEST
    return _POINTS_MID


def _g3(raw: dict) -> int | None:
    has_policy = raw.get("has_return_policy")
    if has_policy is None:
        return None
    if not has_policy:
        return _POINTS_WORST
    met = raw.get("years_policy_met_3y")
    if met is None:
        return _POINTS_MID
    return _POINTS_BEST if met >= w.POLICY_YEARS_FULL else _POINTS_MID


def _g4(raw: dict) -> int | None:
    return _three_way(raw.get("kpi_type"), ("capital_efficiency",), ("mixed",))


# --- C ---
def _c1(raw: dict) -> int | None:
    count = raw.get("goodwill_impairment_count_10y")
    if count is None:
        return None
    if count >= w.IMPAIRMENT_BAD_MIN:
        return _POINTS_WORST
    return _POINTS_BEST if count == 0 else _POINTS_MID


def _c2(raw: dict) -> int | None:
    return _three_way(raw.get("post_capex_roic_trend"), ("improved",), ("mixed",))


def _c3(raw: dict) -> int | None:
    exists = raw.get("buybacks_exist")
    if exists is None:
        return None
    if not exists:
        return None  # 자사주 정책 자체가 없으면 판정 대상이 아니다(결측)
    if raw.get("reissued_or_exchangeable") or raw.get("purchase_band_position") == "high":
        return _POINTS_WORST
    if raw.get("cancelled") and raw.get("purchase_band_position") == "low":
        return _POINTS_BEST
    return _POINTS_MID


def _c4(raw: dict) -> int | None:
    if raw.get("funded_by_debt_or_asset_sale"):
        return _POINTS_WORST
    years = raw.get("years_dividend_exceeded_ocf_3y")
    if years is None:
        return None
    return _POINTS_BEST if years <= w.DIVIDEND_EXCESS_YEARS_GOOD_MAX else _POINTS_MID


def _c5(raw: dict) -> int | None:
    exists = raw.get("capital_raise_exists")
    if exists is None:
        return None
    if not exists:
        return _POINTS_BEST  # 조달이 없으면 목적-사용 불일치도 없다 (C1의 "M&A 없음"과 같은 취급)
    if raw.get("repeated_raises_3y"):
        return _POINTS_WORST
    return _three_way(raw.get("use_matches_purpose"), ("match",), ("partial",))


# --- D ---
def _d1(raw: dict) -> int | None:
    moat = raw.get("moat_type")
    if moat is None:
        return None
    if moat == "none":
        return _POINTS_WORST
    grade = raw.get("best_evidence_grade")
    if grade is None or grade > w.MOAT_EVIDENCE_SECOND_GRADE:
        return _POINTS_MID  # 유형은 특정했지만 증거가 약하다 — weak 상한이 별도로 걸린다
    return _POINTS_BEST if grade <= w.MOAT_EVIDENCE_TOP_GRADE else _POINTS_MID


def _d2(raw: dict) -> int | None:
    worsening = raw.get("erosion_signals_worsening")
    if worsening is None:
        return None
    if worsening >= w.EROSION_BAD_MIN:
        return _POINTS_WORST
    return _POINTS_BEST if worsening == 0 else _POINTS_MID


def _d3(raw: dict) -> int | None:
    return _lower_is_better(
        raw.get("top_segment_op_income_share"), w.SEGMENT_SHARE_GOOD_MAX, w.SEGMENT_SHARE_BAD_MIN
    )


def _d4(raw: dict) -> int | None:
    return _lower_is_better(
        raw.get("top_customer_sales_share"), w.CUSTOMER_SHARE_GOOD_MAX, w.CUSTOMER_SHARE_BAD_MIN
    )


def _d5(raw: dict) -> int | None:
    return _three_way(raw.get("margin_defense"), ("defended",), ("recovered_within_2q",))


def _d6(raw: dict) -> int | None:
    return _higher_is_better(
        raw.get("recurring_revenue_share"), w.RECURRING_SHARE_GOOD_MIN, w.RECURRING_SHARE_MID_MIN
    )


# --- P ---
def pipeline_ratio(pipelines: list[dict] | None) -> float | None:
    """Σ(확실성 계수 × 규모/현매출). 목록이 None이면 판정 불가, 빈 목록이면 0."""
    if pipelines is None:
        return None
    total = 0.0
    for entry in pipelines:
        stage = int(entry["stage"])
        stage = min(max(stage, PIPELINE_STAGE_MIN), PIPELINE_STAGE_MAX)
        total += w.PIPELINE_STAGE_COEFFICIENTS[stage] * float(entry["revenue_ratio"])
    return total


def _p1(raw: dict) -> int | None:
    return _higher_is_better(
        pipeline_ratio(raw.get("pipelines")), w.PIPELINE_RATIO_GOOD_MIN, w.PIPELINE_RATIO_MID_MIN
    )


def _p2(raw: dict) -> int | None:
    stage = raw.get("top_stage")
    if stage is None:
        return None
    if stage >= w.PIPELINE_STAGE_GOOD_MIN:
        return _POINTS_BEST
    return _POINTS_MID if stage == w.PIPELINE_STAGE_MID else _POINTS_WORST


def _p3(raw: dict) -> int | None:
    return _higher_is_better(
        raw.get("guidance_hit_rate_3y"), w.GUIDANCE_HIT_GOOD_MIN, w.GUIDANCE_HIT_MID_MIN
    )


def _p4(raw: dict) -> int | None:
    return _three_way(raw.get("funding"), ("internal_cash",), ("debt_capacity",))


def _p5(raw: dict) -> int | None:
    return _three_way(raw.get("adjacency"), ("adjacent",), ("partial",))


# --- I ---
def _i1(raw: dict) -> int | None:
    return _three_way(raw.get("share_trend_3y"), ("up",), ("flat",))


def _i2(raw: dict) -> int | None:
    return _three_way(raw.get("barrier_direction"), ("strengthening",), ("stable",))


def _i3(raw: dict) -> int | None:
    return _three_way(raw.get("regulation_direction"), ("favorable_or_neutral",), ("uncertain",))


def _i4(raw: dict) -> int | None:
    stage = raw.get("substitute_tech_stage")
    if stage is None:
        return None
    if stage <= w.SUBSTITUTE_STAGE_GOOD_MAX:
        return _POINTS_BEST
    return _POINTS_MID if stage == w.SUBSTITUTE_STAGE_MID else _POINTS_WORST


def _i5(raw: dict) -> int | None:
    return _three_way(raw.get("cycle_position"), ("trough_turning",), ("neutral",))


def _i6(raw: dict) -> int | None:
    return _three_way(raw.get("survival_10y"), ("no_extinction_path",), ("uncertain",))


# --- X ---
def _x1(raw: dict) -> int | None:
    has_debt = raw.get("has_interest_bearing_debt")
    if has_debt is None:
        return None
    if not has_debt:
        return _POINTS_BEST  # 무차입은 금리 충격에 노출이 없다
    share = raw.get("floating_rate_debt_share")
    coverage = raw.get("interest_coverage")
    if share is None or coverage is None:
        return None
    if share >= w.FLOATING_DEBT_BAD_MIN or coverage < w.INTEREST_COVERAGE_BAD_MAX:
        return _POINTS_WORST
    if share < w.FLOATING_DEBT_GOOD_MAX and coverage >= w.INTEREST_COVERAGE_GOOD_MIN:
        return _POINTS_BEST
    return _POINTS_MID


def _x2(raw: dict) -> int | None:
    return _three_way(raw.get("fx_hedge"), ("natural_or_hedged_70",), ("partial",))


def _x3(raw: dict) -> int | None:
    regions = raw.get("regions_count")
    if regions is None:
        return None
    if regions >= w.REGIONS_GOOD_MIN:
        return _POINTS_BEST
    return _POINTS_MID if regions == w.REGIONS_MID else _POINTS_WORST


def _x4(raw: dict) -> int | None:
    return _three_way(raw.get("price_passthrough"), ("linked_within_1q",), ("lag_2q_plus",))


def _x5(raw: dict) -> int | None:
    return _lower_is_better(
        raw.get("top_country_share"), w.COUNTRY_SHARE_GOOD_MAX, w.COUNTRY_SHARE_BAD_MIN
    )


RUBRIC: dict[str, RubricFunction] = {
    "G1": _g1, "G2": _g2, "G3": _g3, "G4": _g4,
    "C1": _c1, "C2": _c2, "C3": _c3, "C4": _c4, "C5": _c5,
    "D1": _d1, "D2": _d2, "D3": _d3, "D4": _d4, "D5": _d5, "D6": _d6,
    "P1": _p1, "P2": _p2, "P3": _p3, "P4": _p4, "P5": _p5,
    "I1": _i1, "I2": _i2, "I3": _i3, "I4": _i4, "I5": _i5, "I6": _i6,
    "X1": _x1, "X2": _x2, "X3": _x3, "X4": _x4, "X5": _x5,
}


def score_raw(item_code: str, raw: dict | None) -> int | None:
    if raw is None or item_code not in RUBRIC:
        return None
    return RUBRIC[item_code](raw)


# --- 결격 (1-5) ---
def veto_reasons_for_governance(raw: dict | None) -> list[str]:
    """G5 raw에서 결격 사유 코드를 뽑는다. 표현 계층이 한국어로 바꾼다."""
    if raw is None:
        return []
    reasons: list[str] = []
    if raw.get("spinoff_relisting"):
        reasons.append("G5_SPINOFF_RELISTING")
    if raw.get("executive_fraud_5y"):
        reasons.append("G5_EXECUTIVE_FRAUD")
    if raw.get("unfair_merger_ratio"):
        reasons.append("G5_UNFAIR_MERGER")
    return reasons


def is_survival_veto(raw: dict | None) -> bool:
    return raw is not None and raw.get("survival_10y") == "extinction_path"
