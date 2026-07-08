"""1차 스코어링: 밸류에이션 팩터의 백분위 점수와 VC1 지표."""

import pandas as pd

from analysis.factors import (
    BASIC_ORIGINAL_FACTORS,
    BASIC_REVERSE_FACTORS,
    BASIC_SHARE_FACTORS,
    VC1_FACTOR_COLUMNS,
)
from analysis.percentile import calculating_percentile
from analysis.weights import VC1_DIVISOR


def get_sorting_and_basicscore(stockdata: pd.DataFrame) -> pd.DataFrame:
    """기본 팩터들에 대해 percentile 점수를 매기고 VC1을 계산한다."""
    for factor in BASIC_SHARE_FACTORS:
        stockdata = calculating_percentile(stockdata, factor.name, factor.direction)
    for factor in BASIC_ORIGINAL_FACTORS:
        stockdata = calculating_percentile(stockdata, factor.name, factor.direction)
    for factor in BASIC_REVERSE_FACTORS:
        stockdata = calculating_percentile(stockdata, factor.name, factor.direction)

    stockdata["VC1"] = stockdata[VC1_FACTOR_COLUMNS].sum(axis=1) / VC1_DIVISOR

    return stockdata
