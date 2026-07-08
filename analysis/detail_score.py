"""2차 스코어링: 세부 팩터 percentile, Vscore/Mscore/Fscore/Finalscore,
품질/리스크 지표(EQC, Value risk, Growth risk, Quant score, reliablity)를 계산한다.
"""

import numpy as np
import pandas as pd

import analysis.weights as w
from analysis.factors import (
    DETAIL_ORIGINAL_FACTORS,
    DETAIL_REVERSE_FACTORS,
    DETAIL_SHARE_FACTORS,
    RELIABILITY_TF_COLUMNS,
)
from analysis.percentile import calculating_percentile


def get_detailscore_and_finalrank(stockinfo: pd.DataFrame) -> pd.DataFrame:
    """세부 팩터 percentile을 적용한 뒤 파생 스코어 컬럼들을 모두 붙인다."""
    stockinfo = _apply_detail_percentiles(stockinfo.copy())

    stockinfo["Vscore"] = _compute_vscore(stockinfo)
    stockinfo["Mscore"] = _compute_mscore(stockinfo)
    stockinfo["Fscore"] = _compute_fscore(stockinfo)
    stockinfo["Finalscore"] = _compute_finalscore(stockinfo)
    stockinfo["EQC"] = _compute_eqc(stockinfo)
    stockinfo["Value risk"] = _compute_value_risk(stockinfo)
    stockinfo["Growth risk"] = _compute_growth_risk(stockinfo)
    stockinfo["Quant score"] = _compute_quant_score(stockinfo)
    stockinfo["reliablity"] = _compute_reliability(stockinfo)

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


def _compute_vscore(stockinfo: pd.DataFrame) -> pd.Series:
    return (
        stockinfo["PERS"]
        + stockinfo["EV/EBITDAS"] * w.VSCORE_EV_EBITDA_WEIGHT
        + stockinfo["PCRS"] * w.VSCORE_PCR_WEIGHT
        + stockinfo["PSRS"] * w.VSCORE_PSR_WEIGHT
        + stockinfo["Buyback YieldS"] * w.VSCORE_BUYBACK_YIELD_WEIGHT
        + stockinfo["Dividend YieldS"] * w.VSCORE_DIVIDEND_YIELD_WEIGHT
    ) / w.VSCORE_DIVISOR


def _compute_mscore(stockinfo: pd.DataFrame) -> pd.Series:
    return (
        stockinfo["3M RatioS"] * w.MSCORE_3M_WEIGHT
        + stockinfo["6M RatioS"] * w.MSCORE_6M_WEIGHT
        + stockinfo["1Y RatioS"]
    ) / w.MSCORE_DIVISOR


def _compute_fscore(stockinfo: pd.DataFrame) -> pd.Series:
    return (
        stockinfo["Insider Buy RatioS"] * w.FSCORE_INSIDER_BUY_WEIGHT
        + stockinfo["EPSgrowthS"] * w.FSCORE_EPSGROWTH_WEIGHT
        + stockinfo["RevenuegrowthS"] * w.FSCORE_REVENUEGROWTH_WEIGHT
        + stockinfo["PEGRS"]
    ) / w.FSCORE_DIVISOR


def _compute_finalscore(stockinfo: pd.DataFrame) -> pd.Series:
    return (
        stockinfo["Vscore"] * w.FINALSCORE_VSCORE_WEIGHT
        + stockinfo["Mscore"] * w.FINALSCORE_MSCORE_WEIGHT
    )


def _compute_eqc(stockinfo: pd.DataFrame) -> pd.Series:
    return (
        stockinfo["Depreciation Capex RatioS"]
        + stockinfo["ARPS"] * w.EQC_ARP_WEIGHT
        + stockinfo["Coverage RatioS"] * w.EQC_COVERAGE_RATIO_WEIGHT
    )


def _compute_value_risk(stockinfo: pd.DataFrame) -> np.ndarray:
    return np.where(
        (stockinfo["Debt GrowthS"] < w.VALUE_RISK_DEBT_GROWTH_THRESHOLD)
        | (stockinfo["PBRS"] < w.VALUE_RISK_PBR_THRESHOLD),
        "O",
        "X",
    )


def _compute_growth_risk(stockinfo: pd.DataFrame) -> np.ndarray:
    return np.where(
        (stockinfo["Net Income"] > 0)
        & (stockinfo["EPSgrowthS"] > w.GROWTH_RISK_EPSGROWTH_THRESHOLD)
        & (stockinfo["RevenuegrowthS"] > w.GROWTH_RISK_REVENUEGROWTH_THRESHOLD),
        "X",
        "O",
    )


def _compute_quant_score(stockinfo: pd.DataFrame) -> pd.Series:
    return (
        stockinfo["NCAVS"]
        + stockinfo["GPTOAS"]
        + stockinfo["Asset TurnoverS"]
        + stockinfo["PFCRS"]
    ) / w.QUANT_SCORE_DIVISOR


def _compute_reliability(stockinfo: pd.DataFrame) -> pd.Series:
    tf_columns = [f"{name}TF" for name in RELIABILITY_TF_COLUMNS]
    return stockinfo[tf_columns].sum(axis=1) * w.RELIABILITY_SCALE / len(RELIABILITY_TF_COLUMNS)
