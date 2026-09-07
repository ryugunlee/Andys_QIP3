"""QIP4 파이프라인 — `compute_scores()` 마지막 단계에서 QIP3 다음으로 호출된다.

기존 점수(Vscore/QIP3 …)와 독립된 새 컬럼 패밀리(QIP4 *)만 추가한다. QIP3는 건드리지 않는다.

동작 순서:
1. 옛 스냅샷에 없을 수 있는 원천 컬럼을 보장(없으면 NaN) — KeyError로 사이트 빌드가
   통째로 죽는 것을 막는다.
2. 횡단면으로만 만들 수 있는 파생 원천 컬럼을 만든다(업종 대비 상대 성장률, 주주환원수익률).
3. 관문·경고·효율성 승수·밸류트랩 승수를 판정한다(`qip4_gate`).
4. 신규 팩터를 통화권 전체(퍼센타일·스탠다드) + 섹터/산업 모집단에 채점한다.
5. 6계열로 축 점수와 종합점수를 부착하고 모집단별 평균을 낸다.
6. 모멘텀 점수에서 집행률을 낸다.

컬럼 네이밍은 기존 규칙 그대로다 (`analysis/qip3_pipeline.py` 참고).
"""

import numpy as np
import pandas as pd

from analysis.percentile import calculating_percentile
from analysis.qip4_composites import (
    compute_execution_rate,
    compute_qip4_growth,
    compute_qip4_momentum,
    compute_qip4_total,
    compute_qip4_value,
)
from analysis.qip4_factors import (
    QIP4_RAW_FACTOR_NAMES,
    QIP4_SCORED_FACTORS,
    QIP4_TEXT_COLUMNS,
)
from analysis.qip4_gate import attach_gate_columns
from analysis.score_pipeline import GROUP_POPULATIONS, _score_group_population
from analysis.standard_score import calculating_standard

# 축 이름과 계산 함수. 종합점수는 가치·성장에서 파생한다.
_AXIS_COMPUTERS = {
    "QIP4 Value": compute_qip4_value,
    "QIP4 Growth": compute_qip4_growth,
    "QIP4 Momentum": compute_qip4_momentum,
}
QIP4_COMPOSITE_NAMES: list[str] = list(_AXIS_COMPUTERS) + ["QIP4 Score"]

# 집행률 컬럼 (모멘텀에서 파생, 선정 점수와 별개)
QIP4_EXECUTION_RATE: str = "QIP4 Execution Rate"

# (팩터 점수 접미사, 종합점수 출력 접미사) — QIP3와 동일한 규약.
_SERIES_MAP: list[tuple[str, str]] = [
    ("S", "PS"),
    ("SS", "SS"),
    ("SecS", "SecPS"),
    ("SecSS", "SecSS"),
    ("IndS", "IndPS"),
    ("IndSS", "IndSS"),
]
_POPULATION_TAGS: list[str] = ["", "Sec", "Ind"]


def _ensure_raw_factor_columns(df: pd.DataFrame) -> pd.DataFrame:
    """재수집 이전 스냅샷에 없는 원천 컬럼을 NaN으로 만들어 둔다."""
    df = df.copy()
    for name in QIP4_RAW_FACTOR_NAMES:
        if name not in df.columns:
            df[name] = np.nan
    for name in QIP4_TEXT_COLUMNS:
        if name not in df.columns:
            df[name] = None
    return df


def _attach_derived_factors(df: pd.DataFrame) -> None:
    """횡단면으로만 만들 수 있는 원천 팩터를 만든다(채점 이전에 있어야 한다)."""
    # 상대 성장률 = 자사 매출 성장률 − 업종 중앙값. 업종 정보가 없으면 0(중립).
    if "Revenuegrowth" in df.columns and "Industry" in df.columns:
        growth = pd.to_numeric(df["Revenuegrowth"], errors="coerce")
        industry_median = growth.groupby(df["Industry"]).transform("median")
        df["QIP4 Relative Revenue Growth"] = growth - industry_median
    else:
        df["QIP4 Relative Revenue Growth"] = np.nan

    # 주주환원수익률 = 배당 + 순자사주매입. 원 규칙의 "자사주 소각"은 취득과 구분되지
    # 않아 순매입 기준으로 바꿨다(기존 Buyback Yield가 이미 발행분을 차감한다).
    dividend = pd.to_numeric(
        df.get("QIP4 Dividend Payout Yield", np.nan), errors="coerce"
    ).fillna(0)
    # Buyback Yield는 이미 %(퍼센트) 단위라 비율인 배당수익률과 자릿수를 맞춘다.
    buyback = pd.to_numeric(df.get("Buyback Yield", np.nan), errors="coerce").fillna(0) / 100
    df["QIP4 Shareholder Yield"] = dividend + buyback


def _attach_composite_set(df: pd.DataFrame, factor_suffix: str, out_suffix: str) -> None:
    """한 계열(예: 섹터 퍼센타일)의 축 점수와 종합점수를 부착한다."""
    axis_scores = {
        name: computer(df, factor_suffix) for name, computer in _AXIS_COMPUTERS.items()
    }
    for name, series in axis_scores.items():
        df[f"{name}{out_suffix}"] = series
    df[f"QIP4 Score{out_suffix}"] = compute_qip4_total(
        df, axis_scores["QIP4 Value"], axis_scores["QIP4 Growth"]
    )


def _attach_averages(df: pd.DataFrame, pop_tag: str) -> None:
    """퍼센타일 계열과 스탠다드 계열의 평균을 접미사 없는 컬럼으로 만든다."""
    for name in QIP4_COMPOSITE_NAMES:
        df[f"{name}{pop_tag}"] = (
            df[f"{name}{pop_tag}PS"] + df[f"{name}{pop_tag}SS"]
        ) / 2


def compute_qip4_scores(scored: pd.DataFrame) -> pd.DataFrame:
    """QIP4 컬럼 패밀리를 붙인 DataFrame을 반환한다."""
    scored = _ensure_raw_factor_columns(scored)
    _attach_derived_factors(scored)
    attach_gate_columns(scored)

    for factor in QIP4_SCORED_FACTORS:
        scored = calculating_percentile(scored, factor.name, factor.direction)
        scored = calculating_standard(scored, factor.name, factor.direction)

    for tag, group_column in GROUP_POPULATIONS:
        scored = _score_group_population(
            scored, tag, group_column, factors=QIP4_SCORED_FACTORS
        )

    for factor_suffix, out_suffix in _SERIES_MAP:
        _attach_composite_set(scored, factor_suffix, out_suffix)
    for pop_tag in _POPULATION_TAGS:
        _attach_averages(scored, pop_tag)

    scored[QIP4_EXECUTION_RATE] = compute_execution_rate(scored["QIP4 Momentum"])
    return scored
