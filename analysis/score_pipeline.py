"""통화권(DB) 전체 모집단에 대한 점수 산출 파이프라인.

모집단 3종 × 계열 2종의 점수를 한 번에 계산한다:

- 모집단: 통화권 전체(태그 "") / 같은 섹터 내("Sec") / 같은 산업 내("Ind")
- 계열: 퍼센타일(P, 팩터 접미사 "{모집단}S") / 스탠다드("{모집단}SS")
- 종합점수 최종값(무계열 접미사) = 두 계열의 평균.
  예: Vscore = (VscorePS + VscoreSS) / 2, VscoreSec = (VscoreSecPS + VscoreSecSS) / 2

컬럼 네이밍 규칙 (STRUCTURE.md에도 기록):
- 팩터:   {이름}S / {이름}SS / {이름}SecS / {이름}SecSS / {이름}IndS / {이름}IndSS
- 종합:   {이름}{모집단}PS / {이름}{모집단}SS / {이름}{모집단}   (모집단 = ""|Sec|Ind)
- 리스크/신뢰도(Value risk·Growth risk·reliability)는 계열 무관 단일 컬럼

새 모집단(예: 국가별)이 필요하면 GROUP_POPULATIONS에 (태그, 그룹컬럼) 한 줄을 추가한다.
"""

from typing import Iterable

import pandas as pd

from analysis.basic_score import get_sorting_and_basicscore
from analysis.composite_scores import (
    compute_eqc,
    compute_finalscore,
    compute_fscore,
    compute_mscore,
    compute_quant_score,
    compute_vc1,
    compute_vscore,
)
from analysis.detail_score import get_detailscore_and_finalrank
from analysis.factors import (
    BASIC_ORIGINAL_FACTORS,
    BASIC_REVERSE_FACTORS,
    BASIC_SHARE_FACTORS,
    DETAIL_ORIGINAL_FACTORS,
    DETAIL_REVERSE_FACTORS,
    DETAIL_SHARE_FACTORS,
    Direction,
    FactorSpec,
)
from analysis.standard_score import (
    LOWER_CUTLINE_QUANTILE,
    MAX_SCORE,
    MIN_SCORE,
    NEUTRAL_SCORE,
    UPPER_CUTLINE_QUANTILE,
    calculating_standard,
    numeric_values,
    transform_by_direction,
)

# 섹터/산업 모집단이 이 크기보다 작으면 커트라인이 무의미하므로 중립(50) 처리
MIN_GROUP_POPULATION: int = 5

# 부분 모집단 정의: (컬럼 접미사 태그, 그룹 기준 컬럼). 확장 지점.
GROUP_POPULATIONS: list[tuple[str, str]] = [("Sec", "Sector"), ("Ind", "Industry")]

# 점수화 대상 팩터 ("Buyback to Income"은 다른 종합점수의 입력이 아니라 여기서
# 제외한다 — analysis/factors.py의 PRESENCE_ONLY_FACTORS 참고)
SCORED_FACTORS: list[FactorSpec] = (
    BASIC_SHARE_FACTORS
    + BASIC_ORIGINAL_FACTORS
    + BASIC_REVERSE_FACTORS
    + DETAIL_SHARE_FACTORS
    + DETAIL_ORIGINAL_FACTORS
    + DETAIL_REVERSE_FACTORS
)

# 평균 대상 종합점수 (Finalscore는 평균화된 Vscore/Mscore에서 파생하므로 별도)
_AVERAGED_COMPOSITES: list[str] = ["VC1", "Vscore", "Mscore", "Fscore", "EQC", "Quant score"]
COMPOSITE_NAMES: list[str] = _AVERAGED_COMPOSITES + ["Finalscore"]


def compute_scores(stockdata: pd.DataFrame) -> pd.DataFrame:
    """모집단 3종 × 계열 2종의 팩터·종합 점수를 모두 붙인 DataFrame을 반환한다.

    입력은 통화권 하나의 전체 종목(curated 팩터 포함) 표다.
    """
    # 1) 통화권 전체 — 퍼센타일 계열 (기존 경로 재사용: S/TF + 리스크/신뢰도 포함)
    scored = get_sorting_and_basicscore(stockdata.copy())
    scored = get_detailscore_and_finalrank(scored)
    scored = scored.rename(columns={name: f"{name}PS" for name in COMPOSITE_NAMES})

    # 2) 통화권 전체 — 스탠다드 계열
    for factor in SCORED_FACTORS:
        scored = calculating_standard(scored, factor.name, factor.direction)

    # 3) 섹터/산업 모집단 — 두 계열
    for tag, group_column in GROUP_POPULATIONS:
        scored = _score_group_population(scored, tag, group_column)

    # 4) 종합점수: 전체는 SS·평균만(PS는 1에서 확보), 부분 모집단은 PS·SS·평균
    _attach_composite_set(scored, factor_suffix="SS", out_suffix="SS")
    for tag, _ in GROUP_POPULATIONS:
        _attach_composite_set(scored, factor_suffix=f"{tag}S", out_suffix=f"{tag}PS")
        _attach_composite_set(scored, factor_suffix=f"{tag}SS", out_suffix=f"{tag}SS")
    for tag in ["", *[tag for tag, _ in GROUP_POPULATIONS]]:
        _attach_averages(scored, tag)

    # 5) QIP3 5요인 점수 체계(안정성/재무건전성/성장성/가치성/모멘텀)를 병행 부착한다.
    #    기존 종합점수(Vscore/Mscore/…)와 독립된 새 컬럼 패밀리(QIP3 *)로만 추가하므로
    #    위 결과에는 영향이 없다. 순환 import를 피하려고 호출 시점에 지연 import한다
    #    (qip3_pipeline은 이 모듈의 _score_group_population/GROUP_POPULATIONS를 재사용).
    from analysis.qip3_pipeline import compute_qip3_scores

    scored = compute_qip3_scores(scored)

    return scored


def score_output_columns(scored: pd.DataFrame, source_columns: Iterable[str]) -> list[str]:
    """compute_scores가 새로 만든 컬럼 목록 (저장 시 UPDATE 대상)."""
    source = set(source_columns)
    return [column for column in scored.columns if column not in source]


def _score_group_population(
    df: pd.DataFrame,
    tag: str,
    group_column: str,
    factors: list[FactorSpec] | None = None,
) -> pd.DataFrame:
    """그룹(섹터/산업)별 모집단에서 두 계열 팩터 점수를 계산한다.

    그룹 수가 많아(산업은 100개 이상) 그룹×팩터마다 엔진을 호출하면 너무 느리므로,
    단일 컬럼 엔진(percentile/standard_score)과 동일한 규칙을 groupby 벡터 연산으로
    적용한다. 그룹 값이 결측이거나 표본이 MIN_GROUP_POPULATION 미만이면 중립 50점.

    `factors`를 넘기면 그 팩터 목록만 채점한다 (기본값은 기존 SCORED_FACTORS —
    호출부 무변경). QIP3 파이프라인이 자기 팩터 목록으로 재사용한다.
    """
    df = df.copy()
    scored_factors = factors if factors is not None else SCORED_FACTORS
    if group_column not in df.columns:
        for name in dict.fromkeys(spec.name for spec in scored_factors):
            df[f"{name}{tag}S"] = NEUTRAL_SCORE
            df[f"{name}{tag}SS"] = NEUTRAL_SCORE
        return df

    labels = df[group_column]
    group_sizes = labels.groupby(labels).transform("size")
    in_valid_group = labels.notna() & (group_sizes >= MIN_GROUP_POPULATION)

    for factor in scored_factors:
        values = numeric_values(df[factor.name])
        transformed = transform_by_direction(values, factor.direction)
        # 유효 그룹 소속 행만 모집단에 포함 (transform_by_direction이 0을 제외한
        # RECIPROCAL의 경우 인덱스가 줄어 있으므로 reindex로 원복)
        transformed = transformed.reindex(df.index).where(in_valid_group)
        grouped = transformed.groupby(labels)

        # 퍼센타일: 그룹 내 rank(pct) — 단일 컬럼 엔진과 동일 규칙(×100 반올림)
        percentile = grouped.rank(pct=True).mul(100).round()
        percentile_scores = percentile.fillna(NEUTRAL_SCORE)
        if factor.direction == Direction.LOWER_IS_BETTER_RECIPROCAL:
            # 단일 컬럼 엔진과 동일: 값 0은 역수 불가로 순위에서 제외되고 0점을 받는다
            zero_rows = (values == 0) & in_valid_group
            percentile_scores = percentile_scores.mask(zero_rows, 0)
        df[f"{factor.name}{tag}S"] = percentile_scores

        # 스탠다드: 그룹 내 상·하위 1% 커트라인 선형 위치 (동일 규칙: 클램프·퇴화 50)
        upper = grouped.transform(lambda s: s.quantile(UPPER_CUTLINE_QUANTILE))
        lower = grouped.transform(lambda s: s.quantile(LOWER_CUTLINE_QUANTILE))
        span = upper - lower
        standard = ((transformed - lower) / span * MAX_SCORE).clip(MIN_SCORE, MAX_SCORE)
        standard = standard.where(span != 0)  # 커트라인 동일(퇴화) → 중립
        df[f"{factor.name}{tag}SS"] = standard.fillna(NEUTRAL_SCORE)

    return df


def _attach_composite_set(df: pd.DataFrame, factor_suffix: str, out_suffix: str) -> None:
    """팩터 접미사 계열 하나로 종합점수 세트를 계산해 {이름}{out_suffix}로 붙인다."""
    df[f"VC1{out_suffix}"] = compute_vc1(df, factor_suffix)
    df[f"Vscore{out_suffix}"] = compute_vscore(df, factor_suffix)
    df[f"Mscore{out_suffix}"] = compute_mscore(df, factor_suffix)
    df[f"Fscore{out_suffix}"] = compute_fscore(df, factor_suffix)
    df[f"EQC{out_suffix}"] = compute_eqc(df, factor_suffix)
    df[f"Quant score{out_suffix}"] = compute_quant_score(df, factor_suffix)
    df[f"Finalscore{out_suffix}"] = compute_finalscore(
        df[f"Vscore{out_suffix}"], df[f"Mscore{out_suffix}"]
    )


def _attach_averages(df: pd.DataFrame, pop_tag: str) -> None:
    """모집단 하나의 최종 종합점수 = (퍼센타일 + 스탠다드) / 2. Finalscore는
    평균화된 Vscore·Mscore의 가중합으로 파생한다."""
    for name in _AVERAGED_COMPOSITES:
        df[f"{name}{pop_tag}"] = (
            df[f"{name}{pop_tag}PS"] + df[f"{name}{pop_tag}SS"]
        ) / 2
    df[f"Finalscore{pop_tag}"] = compute_finalscore(
        df[f"Vscore{pop_tag}"], df[f"Mscore{pop_tag}"]
    )
