"""QIP4 축 점수 수식. 이미 0~100으로 채점된 팩터 점수 컬럼만 조합한다.

`analysis/qip3_composites.py`와 같은 방식으로 접미사(suffix)를 파라미터로 받아
6계열(전체/섹터/산업 × 퍼센타일/스탠다드)에 같은 수식을 재사용한다.

두 채점 엔진이 NaN을 내보내지 않으므로(결측 → 중립 50) 여기에 fillna가 없다.
부작용으로 결측 팩터는 조용히 "가중치 × 50"을 기여하는데, 하류의 `reliability`
문턱이 그 위장 진입을 막는다 — QIP3와 같은 구조다.

가치 축만 다른 축과 다르다: **섹터군마다 4지표의 가중치가 다르다.** 은행에
FCF Yield를 묻는 것은 무의미하고 소프트웨어에 PBR을 묻는 것도 마찬가지이기 때문이다.
"""

import pandas as pd

import analysis.qip4_weights as w
from analysis.qip4_gate import (
    EFFICIENCY_MULTIPLIER_COLUMN,
    VALUE_TRAP_MULTIPLIER_COLUMN,
)
from collection.sector_groups import GROUP_GENERAL

_SECTOR_GROUP_COLUMN = "QIP4 Sector Group"

# 가치 4지표 → 점수 컬럼 이름(접미사 제외). PBR은 기존 파이프라인이 이미 채점한다.
_VALUE_COMPONENT_COLUMNS: dict[str, str] = {
    "fcf_yield": "QIP4 FCF Yield",
    "ev_to_ebit": "QIP4 EV to EBIT",
    "pbr": "PBR",
    "shareholder_yield": "QIP4 Shareholder Yield",
}


def _col(df: pd.DataFrame, factor: str, suffix: str) -> pd.Series:
    return df[f"{factor}{suffix}"]


def compute_qip4_value(df: pd.DataFrame, suffix: str) -> pd.Series:
    """가치 점수. 섹터군별 가중치를 행마다 골라 적용하고 밸류 트랩 승수를 곱한다."""
    groups = (
        df[_SECTOR_GROUP_COLUMN]
        if _SECTOR_GROUP_COLUMN in df.columns
        else pd.Series(GROUP_GENERAL, index=df.index)
    )
    # 분류되지 않은 종목은 '일반' 가중치로 떨어뜨린다 — 분류 실패로 점수를 잃는 것보다 낫다.
    groups = groups.fillna(GROUP_GENERAL)

    score = pd.Series(0.0, index=df.index)
    for component, column in _VALUE_COMPONENT_COLUMNS.items():
        # 섹터군마다 다른 가중치를 행 단위 시리즈로 만든다.
        weights = groups.map(
            lambda group: w.VALUE_WEIGHTS_BY_GROUP.get(
                group, w.VALUE_WEIGHTS_BY_GROUP[GROUP_GENERAL]
            )[component]
        )
        score = score + _col(df, column, suffix) * weights

    if VALUE_TRAP_MULTIPLIER_COLUMN in df.columns:
        score = score * df[VALUE_TRAP_MULTIPLIER_COLUMN]
    return score


def compute_qip4_growth(df: pd.DataFrame, suffix: str) -> pd.Series:
    """성장 점수. 변동계수·자본집약도는 팩터 등록 단계에서 이미 방향이 뒤집혀 있어
    (NEGATED) 여기서는 그대로 더하면 된다."""
    return (
        _col(df, "QIP4 Growth Continuity", suffix) * w.GROWTH_CONTINUITY_WEIGHT
        + _col(df, "QIP4 Revenue Growth Volatility", suffix) * w.GROWTH_STABILITY_WEIGHT
        + _col(df, "QIP4 Growth Self Funding", suffix) * w.GROWTH_SELF_FUNDING_WEIGHT
        + _col(df, "QIP4 Capital Intensity", suffix) * w.GROWTH_CAPITAL_INTENSITY_WEIGHT
        + _col(df, "QIP4 Relative Revenue Growth", suffix) * w.GROWTH_RELATIVE_WEIGHT
    )


def compute_qip4_momentum(df: pd.DataFrame, suffix: str) -> pd.Series:
    """모멘텀 점수. **선정에 관여하지 않고 집행률만 정한다.**

    12-1 가격 모멘텀은 기존 파이프라인이 이미 채점한 컬럼을 재사용한다.
    """
    return (
        _col(df, "12-1Y Ratio", suffix) * w.MOMENTUM_PRICE_12_1_WEIGHT
        + _col(df, "QIP4 Relative Strength", suffix) * w.MOMENTUM_RELATIVE_STRENGTH_WEIGHT
        + _col(df, "QIP4 Earnings Revision", suffix) * w.MOMENTUM_EARNINGS_REVISION_WEIGHT
    )


def compute_qip4_total(
    df: pd.DataFrame, value: pd.Series, growth: pd.Series
) -> pd.Series:
    """종합점수 = (가치·성장 가중합) × 효율성 승수.

    모멘텀은 들어가지 않는다 — "무엇을 살지"가 아니라 "얼마나 살지"를 정하는 축이라
    선정 점수에 섞으면 그 구분이 무너진다.

    효율성 탈락은 승수 0.0이라 종합점수가 0이 되어 순위에서 자연히 밀려난다.
    이 저장소의 분석 계층은 연속값만 다루므로 불리언 탈락 개념을 새로 만들지 않는다.
    """
    total = value * w.TOTAL_VALUE_WEIGHT + growth * w.TOTAL_GROWTH_WEIGHT
    if EFFICIENCY_MULTIPLIER_COLUMN in df.columns:
        total = total * df[EFFICIENCY_MULTIPLIER_COLUMN]
    return total


def compute_execution_rate(momentum: pd.Series) -> pd.Series:
    """모멘텀 점수 → 집행률(%). 이미 고른 종목을 얼마나 담을지에만 관여한다.

    절대 비중(5%/3%/1.5%)은 포트폴리오 크기에 종속되므로 산출하지 않는다 —
    이 프로그램은 매수/매도를 강요하지 않고 판단 재료만 제공한다.
    """
    rate = pd.Series(w.EXECUTION_RATE_BANDS[-1][1], index=momentum.index)
    # 낮은 구간부터 덮어써서 높은 구간이 이기게 한다.
    for threshold, value in sorted(w.EXECUTION_RATE_BANDS):
        rate = rate.where(momentum < threshold, value)
    return rate
