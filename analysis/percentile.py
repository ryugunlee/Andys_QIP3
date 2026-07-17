"""단일 컬럼에 대한 percentile 스코어링 핵심 엔진."""

import pandas as pd

from analysis.factors import Direction


def calculating_percentile(
    df: pd.DataFrame,
    column: str,
    direction: Direction = Direction.HIGHER_IS_BETTER,
    score_column: str | None = None,
) -> pd.DataFrame:
    """주어진 컬럼의 값을 백분위(0~100) 점수로 변환해 `score_column`
    (기본 `{column}S`) 컬럼으로 추가한다.

    데이터 존재 여부는 `{column}TF` 컬럼(0/1)에 별도로 기록한다.
    (TF는 모집단과 무관한 "데이터 유무"라 score_column과 상관없이 같은 이름이다.)
    결측치는 점수 50(중립)으로 처리한다.
    섹터/산업 등 부분 모집단 점수는 부분집합 df와 별도 score_column으로 호출한다.
    """
    df = df.copy()
    target = score_column if score_column is not None else f"{column}S"
    df[column] = df[column].apply(lambda x: None if isinstance(x, str) else x)
    df[target] = df[column].apply(lambda x: 50 if x is None or pd.isna(x) else 0)
    df[f"{column}TF"] = df[column].apply(lambda x: 0 if pd.isna(x) or x is None else 1)

    df_non_na = df.dropna(subset=[column])
    if direction == Direction.LOWER_IS_BETTER_RECIPROCAL:
        df_non_na = df_non_na[df_non_na[column] != 0]
        df_non_na.loc[:, target] = (
            (1 / df_non_na[column]).rank(pct=True).apply(lambda x: round(x * 100))
        )
    elif direction == Direction.HIGHER_IS_BETTER:
        df_non_na.loc[:, target] = (
            df_non_na[column].rank(pct=True).apply(lambda x: round(x * 100))
        )
    elif direction == Direction.LOWER_IS_BETTER_NEGATED:
        df_non_na.loc[:, target] = (
            (-df_non_na[column]).rank(pct=True).apply(lambda x: round(x * 100))
        )
    df.update(df_non_na)
    return df


def attach_presence_flag(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """방향성 점수 없이 `{column}TF`(데이터 존재 0/1)만 추가한다.

    다른 점수 계산의 입력으로 쓰이지 않아 방향(direction)을 정할 필요가 없는
    팩터(예: 신뢰도 판단에만 쓰이는 팩터)에 calculating_percentile 대신 쓴다.
    """
    df = df.copy()
    cleaned = df[column].apply(lambda x: None if isinstance(x, str) else x)
    df[f"{column}TF"] = cleaned.apply(lambda x: 0 if x is None or pd.isna(x) else 1)
    return df
