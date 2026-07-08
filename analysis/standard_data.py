"""전체 시장 / 섹터별 / 국가별 percentile 커트라인(구간별 기준값) 테이블 생성.

원본 코드는 전체/섹터/국가 3곳에서 거의 동일한 ~50줄짜리 컬럼 목록을 반복 작성했다.
여기서는 `_build_standard_table` 하나로 통합해 재사용한다.
"""

import pandas as pd

from analysis.factors import STANDARD_DATA_FACTORS, Direction

PERCENTILE_RANGE_START: int = 10
PERCENTILE_RANGE_STOP: int = 100
PERCENTILE_RANGE_STEP: int = 10


def _percentile_threshold(
    df: pd.DataFrame,
    column: str,
    percentile: int,
    direction: Direction = Direction.LOWER_IS_BETTER_RECIPROCAL,
) -> float | None:
    """주어진 컬럼에서 상위 `percentile`%에 해당하는 값의 커트라인을 계산한다."""
    try:
        subset = df.copy()
        subset = subset.dropna(subset=[column])
        if direction == Direction.LOWER_IS_BETTER_RECIPROCAL:
            subset = subset[subset[column] != 0]
            threshold = (1 / subset[column]).quantile(1 - percentile / 100)
            return 1 / threshold if threshold != 0 else None
        elif direction == Direction.HIGHER_IS_BETTER:
            return subset[column].quantile(1 - percentile / 100)
        elif direction == Direction.LOWER_IS_BETTER_NEGATED:
            threshold = (-subset[column]).quantile(1 - percentile / 100)
            return -threshold
    except Exception as e:
        print(
            f"Error in _percentile_threshold for column {column}, "
            f"percentile {percentile}, direction {direction}: {e}"
        )
        return None


def _build_standard_table(df: pd.DataFrame) -> pd.DataFrame:
    """하나의 데이터프레임 부분집합(전체/특정 섹터/특정 국가)에 대해
    10~90% 구간별 커트라인 표를 만든다."""
    rows = []
    for percentile in range(PERCENTILE_RANGE_START, PERCENTILE_RANGE_STOP, PERCENTILE_RANGE_STEP):
        rows.append(
            [
                _percentile_threshold(df, factor.name, percentile, factor.direction)
                for factor in STANDARD_DATA_FACTORS
            ]
        )
    columns = [factor.name for factor in STANDARD_DATA_FACTORS]
    return pd.DataFrame(rows, columns=columns)


def get_standard_data(
    stockdata: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """전체 시장, 섹터별, 국가별 percentile 커트라인 표를 반환한다."""
    standard_data = _build_standard_table(stockdata)
    standard_data.insert(
        0,
        "Top",
        [f"top{i}%" for i in range(PERCENTILE_RANGE_START, PERCENTILE_RANGE_STOP, PERCENTILE_RANGE_STEP)],
    )

    sector_standard_data = {
        sector: _build_standard_table(stockdata[stockdata["Sector"] == sector])
        for sector in stockdata["Sector"].unique()
    }

    country_standard_data = {
        country: _build_standard_table(stockdata[stockdata["Country"] == country])
        for country in stockdata["Country"].unique()
    }

    return standard_data, sector_standard_data, country_standard_data
