"""QIP3 5요인 점수 파이프라인 — compute_scores() 마지막 단계에서 호출된다.

기존 종합점수(Vscore/Mscore/…)와 독립된 새 컬럼 패밀리(QIP3 *)만 추가한다.
동작:
1. 재수집 이전 옛 run 스냅샷에 없을 수 있는 신규 원천 팩터 컬럼을 보장(없으면 NaN).
2. 신규 팩터(QIP3_SCORED_FACTORS)를 통화권 전체(퍼센타일·스탠다드) + 섹터/산업
   모집단에 채점한다. 기존에 이미 채점된 팩터(PER·GPTOA 등)는 그 점수를 재사용한다.
3. 6계열(S/SS × 전체/Sec/Ind)로 5요인 + 종합점수를 부착하고 모집단별 평균을 낸다.
4. 안정성 하드 필터값(시장·섹터 블렌드)을 계산한다.

컬럼 네이밍은 기존 규칙을 그대로 따른다 (score_pipeline.py 참고):
- 요인:  QIP3 Value{PS|SS|""} / QIP3 ValueSec{PS|SS|""} / QIP3 ValueInd{PS|SS|""} …
- 종합:  QIP3 Score{…}
"""

import numpy as np
import pandas as pd

import analysis.qip3_weights as w
from analysis.percentile import calculating_percentile
from analysis.qip3_composites import (
    compute_qip3_growth,
    compute_qip3_health,
    compute_qip3_momentum,
    compute_qip3_stability,
    compute_qip3_total,
    compute_qip3_value,
)
from analysis.qip3_factors import QIP3_RAW_FACTOR_NAMES, QIP3_SCORED_FACTORS
from analysis.score_pipeline import GROUP_POPULATIONS, _score_group_population
from analysis.standard_score import calculating_standard

# 5요인 이름과 계산 함수. 종합점수(QIP3 Score)는 이 다섯에서 파생한다.
_FACTOR_COMPUTERS = {
    "QIP3 Value": compute_qip3_value,
    "QIP3 Growth": compute_qip3_growth,
    "QIP3 Momentum": compute_qip3_momentum,
    "QIP3 Stability": compute_qip3_stability,
    "QIP3 Health": compute_qip3_health,
}
QIP3_COMPOSITE_NAMES: list[str] = list(_FACTOR_COMPUTERS) + ["QIP3 Score"]

# 안정성 하드 필터 컬럼 (시장 전체 + 섹터 내 블렌드)
QIP3_STABILITY_FILTER: str = "QIP3 Stability Filter"

# (팩터 점수 접미사, 종합점수 출력 접미사) — 전체/섹터/산업 × 퍼센타일/스탠다드
_SERIES_MAP: list[tuple[str, str]] = [
    ("S", "PS"),
    ("SS", "SS"),
    ("SecS", "SecPS"),
    ("SecSS", "SecSS"),
    ("IndS", "IndPS"),
    ("IndSS", "IndSS"),
]
_POPULATION_TAGS: list[str] = ["", "Sec", "Ind"]


def compute_qip3_scores(scored: pd.DataFrame) -> pd.DataFrame:
    """기존 점수가 붙은 표에 QIP3 5요인·종합점수·안정성 필터 컬럼을 추가한다."""
    scored = _ensure_raw_factor_columns(scored)

    # 신규 팩터만 통화권 전체 두 계열로 채점 (기존 팩터는 이미 점수 컬럼 보유)
    for factor in QIP3_SCORED_FACTORS:
        scored = calculating_percentile(scored, factor.name, factor.direction)
        scored = calculating_standard(scored, factor.name, factor.direction)

    # 신규 팩터를 섹터/산업 모집단에도 채점 (기존 _score_group_population 재사용)
    for tag, group_column in GROUP_POPULATIONS:
        scored = _score_group_population(
            scored, tag, group_column, factors=QIP3_SCORED_FACTORS
        )

    for factor_suffix, out_suffix in _SERIES_MAP:
        _attach_qip3_composite_set(scored, factor_suffix, out_suffix)
    for pop_tag in _POPULATION_TAGS:
        _attach_qip3_averages(scored, pop_tag)

    scored[QIP3_STABILITY_FILTER] = (
        scored["QIP3 Stability"] * w.STABILITY_FILTER_MARKET_WEIGHT
        + scored["QIP3 StabilitySec"] * w.STABILITY_FILTER_SECTOR_WEIGHT
    )
    return scored


def _ensure_raw_factor_columns(scored: pd.DataFrame) -> pd.DataFrame:
    """QIP3가 참조하는 신규 원천 팩터 컬럼이 없으면 NaN으로 만들어 둔다.

    재수집 이전 옛 스냅샷에는 이 컬럼들이 아예 없어 채점 엔진이 KeyError로 죽는다.
    NaN이면 엔진 규칙대로 중립 50점이 되어 재수집 전까지 자연스럽게 완충된다.
    """
    scored = scored.copy()
    for name in QIP3_RAW_FACTOR_NAMES:
        if name not in scored.columns:
            scored[name] = np.nan
    return scored


def _attach_qip3_composite_set(
    df: pd.DataFrame, factor_suffix: str, out_suffix: str
) -> None:
    """한 계열(팩터 접미사)로 5요인 + 종합점수를 계산해 {이름}{out_suffix}로 붙인다."""
    factor_scores = {
        name: computer(df, factor_suffix)
        for name, computer in _FACTOR_COMPUTERS.items()
    }
    for name, series in factor_scores.items():
        df[f"{name}{out_suffix}"] = series
    df[f"QIP3 Score{out_suffix}"] = compute_qip3_total(
        factor_scores["QIP3 Value"],
        factor_scores["QIP3 Growth"],
        factor_scores["QIP3 Momentum"],
        factor_scores["QIP3 Health"],
    )


def _attach_qip3_averages(df: pd.DataFrame, pop_tag: str) -> None:
    """모집단 하나의 최종 요인·종합점수 = (퍼센타일 + 스탠다드) / 2."""
    for name in QIP3_COMPOSITE_NAMES:
        df[f"{name}{pop_tag}"] = (
            df[f"{name}{pop_tag}PS"] + df[f"{name}{pop_tag}SS"]
        ) / 2
