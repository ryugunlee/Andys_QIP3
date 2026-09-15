"""수치 재계산 루브릭 — raw 수치가 있는 항목(Q1·Q6·Q8·Q9)의 점수를 앵커 보간으로 다시 낸다.

`.claude/정성 평가 규칙.md` 2절: 이 네 항목은 raw가 채워져 있으면 코드가 채점자 점수를
덮어쓴다. 같은 사실이면 같은 점수가 나오게 하려는 것이다. 나머지 항목(Q2~Q5·Q7)은 채점자의
점수를 그대로 쓴다 — 여기 함수가 None을 돌려주면 판정기가 채점자 점수를 유지한다.

임계값은 전부 `weights.py`에서 가져온다.
"""

from collections.abc import Callable

import analysis.qualitative.weights as w
from collection.qualitative.items import PIPELINE_STAGE_MAX, PIPELINE_STAGE_MIN

RecomputeFunction = Callable[[dict], float | None]


def interpolate(value: float, points: tuple[tuple[float, float], ...]) -> float:
    """(x, score) 꺾은선에서 x=value의 점수. 범위 밖은 양끝 값으로 고정한다."""
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return points[-1][1]


def _q1(raw: dict) -> float | None:
    ratio = raw.get("committed_to_revenue")
    if ratio is None:
        return None
    score = interpolate(float(ratio), w.COMMITTED_REVENUE_POINTS)
    if raw.get("binding_contracts") is False:
        score = min(score, w.SCORE_BELOW_F)
    return score


def _q6(raw: dict) -> float | None:
    ratio = raw.get("related_party_ratio")
    if ratio is None:
        return None
    score = interpolate(float(ratio), w.RELATED_PARTY_POINTS)
    if raw.get("related_party_trend_3y") == "increasing":
        score = min(score, w.SCORE_BELOW_F)
    outside, total = raw.get("outside_directors"), raw.get("total_directors")
    if outside is not None and total and outside * 2 <= total:
        score = min(score, w.BOARD_MINORITY_CAP)
    return score


def _q8(raw: dict) -> float | None:
    scores: list[float] = []
    customer = raw.get("top_customer_sales_share")
    if customer is not None:
        scores.append(interpolate(float(customer), w.CUSTOMER_SHARE_POINTS))
    segment = raw.get("top_segment_op_income_share")
    if segment is not None:
        scores.append(interpolate(float(segment), w.SEGMENT_SHARE_POINTS))
    return min(scores) if scores else None


def _q9(raw: dict) -> float | None:
    share = raw.get("top_country_share")
    if share is None:
        return None
    score = interpolate(float(share), w.COUNTRY_SHARE_POINTS)
    if raw.get("fx_hedged") is False:
        score = min(score, w.UNHEDGED_CAP)
    return score


RECOMPUTE: dict[str, RecomputeFunction] = {"Q1": _q1, "Q6": _q6, "Q8": _q8, "Q9": _q9}


def recompute_score(item_code: str, raw: dict | None) -> float | None:
    """raw 수치로 다시 낸 점수. 재계산 대상이 아니거나 수치가 없으면 None."""
    if raw is None or item_code not in RECOMPUTE:
        return None
    return RECOMPUTE[item_code](raw)


def pipeline_ratio(pipelines: list[dict] | None) -> float | None:
    """Σ(확실성 계수 × 규모/현매출). Q5 근거 표시용 — 점수는 채점자가 낸다."""
    if pipelines is None:
        return None
    total = 0.0
    for entry in pipelines:
        stage = min(max(int(entry["stage"]), PIPELINE_STAGE_MIN), PIPELINE_STAGE_MAX)
        total += w.PIPELINE_STAGE_COEFFICIENTS[stage] * float(entry["revenue_ratio"])
    return total


# --- 결격 (문서 3절) ---
VETO_FIELDS: dict[str, str] = {
    "spinoff_relisting": "VETO_SPINOFF_RELISTING",
    "executive_fraud_5y": "VETO_EXECUTIVE_FRAUD",
    "unfair_merger_ratio": "VETO_UNFAIR_MERGER",
}


def veto_reasons_for_governance(raw: dict | None) -> list[str]:
    """Q6 raw에서 결격 사유 코드를 뽑는다. 표현 계층이 한국어로 바꾼다."""
    if raw is None:
        return []
    return [code for field, code in VETO_FIELDS.items() if raw.get(field)]
