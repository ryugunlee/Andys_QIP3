"""단일 컬럼에 대한 스탠다드스코어(커트라인 구간 위치 점수) 엔진.

상위 1% 커트라인과 하위 1% 커트라인 사이에서 값의 선형 위치를 0~100점으로
환산한다. 예: 하위 1%가 -10%, 상위 1%가 90%일 때 값 80% → 90점.
하위 1% 커트라인 이하는 0점, 상위 1% 커트라인 이상은 100점(클램프).

방향 처리(LOWER_IS_BETTER는 1/x 또는 -x로 변환 후 계산)와 결측 50점(중립)은
percentile 엔진(analysis/percentile.py)과 대칭 구조다.
"""

import pandas as pd

from analysis.factors import Direction

UPPER_CUTLINE_QUANTILE: float = 0.99  # 상위 1% 커트라인
LOWER_CUTLINE_QUANTILE: float = 0.01  # 하위 1% 커트라인
NEUTRAL_SCORE: float = 50.0
MIN_SCORE: float = 0.0
MAX_SCORE: float = 100.0

# 스탠다드스코어 컬럼 접미사: {컬럼}SS (percentile의 {컬럼}S와 병행 저장)
STANDARD_SUFFIX: str = "SS"


def numeric_values(series: pd.Series) -> pd.Series:
    """문자열 등 숫자가 아닌 값을 결측으로 바꾼 숫자 시리즈를 반환한다.

    (score_pipeline의 그룹 모집단 벡터 연산에서도 재사용한다.)
    """
    cleaned = series.apply(lambda x: None if isinstance(x, str) else x)
    return pd.to_numeric(cleaned, errors="coerce")


def transform_by_direction(values: pd.Series, direction: Direction) -> pd.Series:
    """방향에 따라 '클수록 좋다' 공간으로 변환한다 (percentile 엔진과 동일 규칙).

    LOWER_IS_BETTER_RECIPROCAL에서 0은 역수를 만들 수 없어 제외(결측)된다.
    (score_pipeline의 그룹 모집단 벡터 연산에서도 재사용한다.)
    """
    if direction == Direction.LOWER_IS_BETTER_RECIPROCAL:
        values = values[values != 0]
        return 1 / values
    if direction == Direction.LOWER_IS_BETTER_NEGATED:
        return -values
    return values


def calculating_standard(
    df: pd.DataFrame,
    column: str,
    direction: Direction = Direction.HIGHER_IS_BETTER,
    score_column: str | None = None,
) -> pd.DataFrame:
    """주어진 컬럼의 스탠다드스코어를 `score_column`(기본 `{column}SS`)으로 추가한다.

    모집단은 전달된 df 전체다 — 섹터/산업 모집단 점수는 부분집합 df와
    별도 score_column 이름으로 호출한다. 결측·모집단 퇴화(커트라인 동일) 시 50점.
    """
    df = df.copy()
    target = score_column if score_column is not None else f"{column}{STANDARD_SUFFIX}"
    df[target] = NEUTRAL_SCORE

    values = numeric_values(df[column]).dropna()
    transformed = transform_by_direction(values, direction)
    if transformed.empty:
        return df

    upper_cutline = transformed.quantile(UPPER_CUTLINE_QUANTILE)
    lower_cutline = transformed.quantile(LOWER_CUTLINE_QUANTILE)
    if pd.isna(upper_cutline) or pd.isna(lower_cutline) or upper_cutline == lower_cutline:
        return df

    position = (transformed - lower_cutline) / (upper_cutline - lower_cutline)
    scores = (position * MAX_SCORE).clip(MIN_SCORE, MAX_SCORE)
    df.loc[scores.index, target] = scores
    return df
