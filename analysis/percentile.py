"""단일 컬럼에 대한 percentile 스코어링 핵심 엔진."""

import pandas as pd

from analysis.factors import Direction


def calculating_percentile(
    df: pd.DataFrame, column: str, direction: Direction = Direction.HIGHER_IS_BETTER
) -> pd.DataFrame:
    """주어진 컬럼의 값을 백분위(0~100) 점수로 변환해 `{column}S` 컬럼으로 추가한다.

    데이터 존재 여부는 `{column}TF` 컬럼(0/1)에 별도로 기록한다.
    결측치는 점수 50(중립)으로 처리한다.
    """
    df = df.copy()
    df[column] = df[column].apply(lambda x: None if isinstance(x, str) else x)
    df[f"{column}S"] = df[column].apply(lambda x: 50 if x is None or pd.isna(x) else 0)
    df[f"{column}TF"] = df[column].apply(lambda x: 0 if pd.isna(x) or x is None else 1)

    df_non_na = df.dropna(subset=[column])
    if direction == Direction.LOWER_IS_BETTER_RECIPROCAL:
        df_non_na = df_non_na[df_non_na[column] != 0]
        df_non_na.loc[:, f"{column}S"] = (
            (1 / df_non_na[column]).rank(pct=True).apply(lambda x: round(x * 100))
        )
    elif direction == Direction.HIGHER_IS_BETTER:
        df_non_na.loc[:, f"{column}S"] = (
            df_non_na[column].rank(pct=True).apply(lambda x: round(x * 100))
        )
    elif direction == Direction.LOWER_IS_BETTER_NEGATED:
        df_non_na.loc[:, f"{column}S"] = (
            (-df_non_na[column]).rank(pct=True).apply(lambda x: round(x * 100))
        )
    df.update(df_non_na)
    return df
