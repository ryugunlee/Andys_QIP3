"""보유 판단 순위 — 생존 종목 중 QIP4 종합점수 상위 20%를 "보유 판단 구간"으로 본다.

`score_ranks.py`의 순위는 시장 **전체** 종목이 모집단이라 탈락 종목도 함께 센다. 보유를
판단할 때 궁금한 것은 "살아남은 종목들 중 몇 등인가"이므로 여기서는 모집단을 **생존 종목**
(`storage/qip4_selection.qip4_survivor_mask` — 관문·효율성·신뢰도 통과)으로 좁힌다.

탈락 종목도 상세 페이지에서 "점수로는 생존 종목 몇 등 사이인가"를 볼 수 있게 위치를 낸다.
효율성 탈락은 승수 0.0이라 `QIP4 Score`가 0이 되므로(`analysis/qip4_composites.py`),
그 경우만 **승수 적용 전 점수**(가치·성장 가중합)로 위치를 잡는다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

import analysis.qip4_weights as w
from analysis.qip4_gate import EFFICIENCY_MULTIPLIER_COLUMN, GATE_COLUMN, GATE_PASS
from analysis.score_pipeline import MIN_GROUP_POPULATION
from storage.qip4_selection import qip4_survivor_mask

_MARKET_COLUMN = "Market"
_SCORE_COLUMN = "QIP4 Score"
_VALUE_COLUMN = "QIP4 Value"
_GROWTH_COLUMN = "QIP4 Growth"

# 빌드 때 붙이는 컬럼 (저장 산출물에는 없다)
SURVIVOR_COLUMN = "QIP4 Survivor"  # 1.0 생존 / 0.0 탈락
EXCLUSION_COLUMN = "QIP4 Exclusion"  # 탈락 사유 코드 (생존이면 None)
PLACEMENT_SCORE_COLUMN = "QIP4 Placement Score"  # 위치를 잡은 점수
POSITION_COLUMN = "QIP4 SurvivorPosition"  # 생존: 등수 / 탈락: 이 자리 앞에 끼어든다
SURVIVOR_COUNT_COLUMN = "QIP4 SurvivorCount"
HOLDING_CUT_COLUMN = "QIP4 HoldingCut"  # 보유 판단 구간의 마지막 등수

HOLDING_VALUE_COLUMNS: list[str] = [
    SURVIVOR_COLUMN,
    EXCLUSION_COLUMN,
    PLACEMENT_SCORE_COLUMN,
    POSITION_COLUMN,
    SURVIVOR_COUNT_COLUMN,
    HOLDING_CUT_COLUMN,
]

HOLDING_TOP_PERCENT: float = w.HOLDING_RATIO * 100

# 탈락 사유 코드 → 문구. 여러 개에 걸리면 앞의 것(더 근본적인 사유)을 보인다.
_EXCLUSION_GATE = "GATE"
_EXCLUSION_EFFICIENCY = "EFFICIENCY"
_EXCLUSION_RELIABILITY = "RELIABILITY"
_EXCLUSION_LABELS: dict[str, str] = {
    _EXCLUSION_GATE: "안정성 관문 탈락",
    _EXCLUSION_EFFICIENCY: "효율성 감사 탈락",
    _EXCLUSION_RELIABILITY: "데이터 신뢰도 미달",
}


def holding_cut(survivor_count: int) -> int:
    """생존 종목 수 → 보유 판단 구간의 마지막 등수 (선별과 같은 반올림, 최소 1)."""
    return max(1, round(survivor_count * w.HOLDING_RATIO))


def _exclusion_codes(df: pd.DataFrame, survivors: pd.Series) -> pd.Series:
    multiplier = pd.to_numeric(df[EFFICIENCY_MULTIPLIER_COLUMN], errors="coerce")
    codes = pd.Series(_EXCLUSION_RELIABILITY, index=df.index, dtype=object)
    codes = codes.mask(~(multiplier > 0), _EXCLUSION_EFFICIENCY)
    codes = codes.mask(df[GATE_COLUMN] != GATE_PASS, _EXCLUSION_GATE)
    return codes.mask(survivors, None)


def _placement_scores(df: pd.DataFrame) -> pd.Series:
    """위치를 잡을 점수. 효율성 탈락(승수 0)만 승수 적용 전 가중합으로 되돌린다."""
    score = pd.to_numeric(df[_SCORE_COLUMN], errors="coerce")
    multiplier = pd.to_numeric(df[EFFICIENCY_MULTIPLIER_COLUMN], errors="coerce")
    before_multiplier = (
        pd.to_numeric(df[_VALUE_COLUMN], errors="coerce") * w.TOTAL_VALUE_WEIGHT
        + pd.to_numeric(df[_GROWTH_COLUMN], errors="coerce") * w.TOTAL_GROWTH_WEIGHT
    )
    return score.where(multiplier > 0, before_multiplier)


def _positions_in_market(scores: pd.Series, survivors: pd.Series) -> pd.Series:
    """생존 종목 중 자기보다 점수가 높은 종목 수 + 1.

    생존 종목에겐 그대로 등수(동점은 같은 등수)이고, 탈락 종목에겐 "이 등수 자리에
    끼어든다"는 뜻이 된다. 점수가 없으면 NaN.
    """
    ascending = np.sort(scores[survivors].dropna().to_numpy())
    higher = len(ascending) - np.searchsorted(ascending, scores.to_numpy(), side="right")
    return pd.Series(higher + 1, index=scores.index, dtype=float).where(scores.notna())


def attach_holding_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """보유 판단 순위 컬럼(`HOLDING_VALUE_COLUMNS`)을 붙인 사본을 돌려준다.

    QIP4가 계산되지 않은 데이터(CSV 폴백·재점수 이전 DB)면 컬럼을 비워 둔다.
    생존 종목이 `MIN_GROUP_POPULATION` 미만인 시장은 순위를 내지 않는다(`score_ranks`와 같은 문턱).
    """
    df = df.copy()
    for column in HOLDING_VALUE_COLUMNS:
        df[column] = np.nan
    df[EXCLUSION_COLUMN] = None
    required = (_SCORE_COLUMN, _VALUE_COLUMN, _GROWTH_COLUMN, GATE_COLUMN,
                EFFICIENCY_MULTIPLIER_COLUMN, "reliability", _MARKET_COLUMN)
    if df.empty or any(column not in df.columns for column in required):
        return df

    survivors = qip4_survivor_mask(df)
    scores = _placement_scores(df)
    df[SURVIVOR_COLUMN] = survivors.astype(float)
    df[EXCLUSION_COLUMN] = _exclusion_codes(df, survivors)
    df[PLACEMENT_SCORE_COLUMN] = scores
    for _, index in df.groupby(_MARKET_COLUMN).groups.items():
        market_survivors = survivors.loc[index]
        count = int(scores.loc[index][market_survivors].notna().sum())
        if count < MIN_GROUP_POPULATION:
            continue
        df.loc[index, POSITION_COLUMN] = _positions_in_market(
            scores.loc[index], market_survivors
        )
        df.loc[index, SURVIVOR_COUNT_COLUMN] = count
        df.loc[index, HOLDING_CUT_COLUMN] = holding_cut(count)
    return df


def holding_zone_mask(df: pd.DataFrame) -> pd.Series:
    """보유 판단 구간(생존 + 등수가 컷 이내)에 든 행이면 True."""
    position = pd.to_numeric(df[POSITION_COLUMN], errors="coerce")
    cut = pd.to_numeric(df[HOLDING_CUT_COLUMN], errors="coerce")
    survivor = pd.to_numeric(df[SURVIVOR_COLUMN], errors="coerce") == 1
    return survivor & (position <= cut)


# --- 상세 페이지 표시 ---


@dataclass(frozen=True)
class HoldingPositionView:
    """상세 페이지 점수 종합에 붙는 "보유 판단" 한 블록."""

    status_label: str  # "보유 판단 구간" / "구간 밖" / "안정성 관문 탈락" …
    status_class: str  # 구간 칩 CSS (score_ranks의 tier-* 재사용)
    position_text: str  # "생존 종목 812개 중 37등" / "생존 종목 812개 중 36등과 37등 사이"
    note: str


def _to_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _between_text(position: int, count: int) -> str:
    """탈락 종목이 생존 종목 사이 어디에 끼어드는지."""
    if position <= 1:
        return f"생존 종목 {count:,}개의 1등보다 위"
    if position > count:
        return f"생존 종목 {count:,}개의 최하위({count:,}등)보다 아래"
    return f"생존 종목 {count:,}개 중 {position - 1:,}등과 {position:,}등 사이"


def build_holding_position(values: dict, market: str) -> HoldingPositionView | None:
    """보유 판단 위치. 순위를 낼 수 없는 종목(QIP4 미계산·모집단 부족)이면 None."""
    position = _to_float(values.get(POSITION_COLUMN))
    count = _to_float(values.get(SURVIVOR_COUNT_COLUMN))
    cut = _to_float(values.get(HOLDING_CUT_COLUMN))
    if position is None or not count or cut is None:
        return None
    position_int, count_int, cut_int = int(position), int(count), int(cut)
    cut_text = f"{market} 보유 판단 구간은 생존 종목 상위 {HOLDING_TOP_PERCENT:.0f}%인 {cut_int:,}등까지다."

    if _to_float(values.get(SURVIVOR_COLUMN)) == 1:
        inside = position_int <= cut_int
        return HoldingPositionView(
            status_label="보유 판단 구간" if inside else "보유 판단 구간 밖",
            status_class="tier-top" if inside else "tier-low",
            position_text=f"생존 종목 {count_int:,}개 중 {position_int:,}등",
            note=cut_text,
        )

    exclusion = str(values.get(EXCLUSION_COLUMN) or "")
    note = f"탈락 종목은 순위에 들지 않고, 점수로 치면 어디쯤인지만 보여준다. {cut_text}"
    placement = _to_float(values.get(PLACEMENT_SCORE_COLUMN))
    # 관문과 효율성에 함께 걸리면 사유는 관문이지만 점수는 승수 0으로 0이 된다 —
    # 사유가 아니라 "위치를 잡은 점수가 종합점수와 다른가"로 안내 여부를 정한다.
    if placement is not None and placement != _to_float(values.get(_SCORE_COLUMN)):
        note += (
            " 효율성 감사 탈락으로 종합점수가 0이 되어, 승수 적용 전 점수"
            f"({placement:.1f})로 위치를 잡았다."
        )
    return HoldingPositionView(
        status_label=_EXCLUSION_LABELS.get(exclusion, "탈락"),
        status_class="tier-low",
        position_text=_between_text(position_int, count_int),
        note=note,
    )
