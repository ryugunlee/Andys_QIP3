"""2차 스코어링: 세부 팩터 percentile, Vscore/Mscore/Fscore/Finalscore,
품질/리스크 지표(EQC, Value risk, Growth risk, Quant score, reliablity)를 계산한다.

종합점수 수식은 composite_scores.py(단일 소스)에 위임한다 — 이 파일은
퍼센타일 계열(suffix "S")로 호출하는 기존 경로다. 리스크 플래그와 신뢰도는
계열과 무관한 단일 지표라 여기에 남긴다.
"""

import numpy as np
import pandas as pd

import analysis.weights as w
from analysis.composite_scores import (
    compute_eqc,
    compute_finalscore,
    compute_fscore,
    compute_mscore,
    compute_quant_score,
    compute_vscore,
)
from analysis.factors import (
    DETAIL_ORIGINAL_FACTORS,
    DETAIL_REVERSE_FACTORS,
    DETAIL_SHARE_FACTORS,
    RELIABILITY_TF_COLUMNS,
)
from analysis.percentile import calculating_percentile

_PERCENTILE_SUFFIX = "S"


def get_detailscore_and_finalrank(stockinfo: pd.DataFrame) -> pd.DataFrame:
    """세부 팩터 percentile을 적용한 뒤 파생 스코어 컬럼들을 모두 붙인다."""
    stockinfo = _apply_detail_percentiles(stockinfo.copy())

    stockinfo["Vscore"] = compute_vscore(stockinfo, _PERCENTILE_SUFFIX)
    stockinfo["Mscore"] = compute_mscore(stockinfo, _PERCENTILE_SUFFIX)
    stockinfo["Fscore"] = compute_fscore(stockinfo, _PERCENTILE_SUFFIX)
    stockinfo["Finalscore"] = compute_finalscore(stockinfo["Vscore"], stockinfo["Mscore"])
    stockinfo["EQC"] = compute_eqc(stockinfo, _PERCENTILE_SUFFIX)
    stockinfo["Value risk"] = compute_value_risk(stockinfo)
    stockinfo["Growth risk"] = compute_growth_risk(stockinfo)
    stockinfo["Quant score"] = compute_quant_score(stockinfo, _PERCENTILE_SUFFIX)
    stockinfo["reliablity"] = compute_reliability(stockinfo)

    return stockinfo


def _apply_detail_percentiles(stockinfo: pd.DataFrame) -> pd.DataFrame:
    # 이 순서(share -> original -> reverse)가 "Buyback to Income"이 두 리스트에
    # 모두 들어있을 때 어느 계산이 최종값으로 남는지를 결정하므로 그대로 유지한다.
    for factor in DETAIL_SHARE_FACTORS:
        stockinfo = calculating_percentile(stockinfo, factor.name, factor.direction)
    for factor in DETAIL_ORIGINAL_FACTORS:
        stockinfo = calculating_percentile(stockinfo, factor.name, factor.direction)
    for factor in DETAIL_REVERSE_FACTORS:
        stockinfo = calculating_percentile(stockinfo, factor.name, factor.direction)
    return stockinfo


def compute_value_risk(stockinfo: pd.DataFrame) -> np.ndarray:
    """가치 리스크 플래그(O/X). 퍼센타일 컬럼 기준 — 계열과 무관한 단일 지표."""
    return np.where(
        (stockinfo["Debt GrowthS"] < w.VALUE_RISK_DEBT_GROWTH_THRESHOLD)
        | (stockinfo["PBRS"] < w.VALUE_RISK_PBR_THRESHOLD),
        "O",
        "X",
    )


def compute_growth_risk(stockinfo: pd.DataFrame) -> np.ndarray:
    """성장 리스크 플래그(O/X). 퍼센타일 컬럼 기준 — 계열과 무관한 단일 지표."""
    return np.where(
        (stockinfo["Net Income"] > 0)
        & (stockinfo["EPSgrowthS"] > w.GROWTH_RISK_EPSGROWTH_THRESHOLD)
        & (stockinfo["RevenuegrowthS"] > w.GROWTH_RISK_REVENUEGROWTH_THRESHOLD),
        "X",
        "O",
    )


def compute_reliability(stockinfo: pd.DataFrame) -> pd.Series:
    """데이터 신뢰도(0~100). TF 컬럼 기반 — 계열과 무관한 단일 지표."""
    tf_columns = [f"{name}TF" for name in RELIABILITY_TF_COLUMNS]
    return stockinfo[tf_columns].sum(axis=1) * w.RELIABILITY_SCALE / len(RELIABILITY_TF_COLUMNS)
