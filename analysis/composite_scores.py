"""종합점수(VC1/Vscore/Mscore/Fscore/EQC/Quant score/Finalscore) 수식의 단일 소스.

같은 수식을 팩터 점수 컬럼의 접미사만 바꿔 여러 계열에 재사용한다:
- suffix="S"    : 퍼센타일 계열 (통화권 모집단) — detail_score.py가 사용
- suffix="SS"   : 스탠다드 계열 (통화권 모집단)
- suffix="SecS"/"SecSS"/"IndS"/"IndSS" : 섹터/산업 모집단 계열 — score_pipeline.py가 사용

가중치는 weights.py의 기존 값을 그대로 쓴다 (수치 무변경).
"""

import pandas as pd

import analysis.weights as w

# VC1을 구성하는 팩터 (접미사 없는 원본 이름)
VC1_FACTORS: list[str] = ["PER", "PBR", "PSR", "PCR", "EV/EBITDA"]


def _col(df: pd.DataFrame, factor: str, suffix: str) -> pd.Series:
    return df[f"{factor}{suffix}"]


def compute_vc1(df: pd.DataFrame, suffix: str) -> pd.Series:
    columns = [f"{factor}{suffix}" for factor in VC1_FACTORS]
    return df[columns].sum(axis=1) / w.VC1_DIVISOR


def compute_vscore(df: pd.DataFrame, suffix: str) -> pd.Series:
    return (
        _col(df, "PER", suffix)
        + _col(df, "EV/EBITDA", suffix) * w.VSCORE_EV_EBITDA_WEIGHT
        + _col(df, "PCR", suffix) * w.VSCORE_PCR_WEIGHT
        + _col(df, "PSR", suffix) * w.VSCORE_PSR_WEIGHT
        + _col(df, "Buyback Yield", suffix) * w.VSCORE_BUYBACK_YIELD_WEIGHT
        + _col(df, "Dividend Yield", suffix) * w.VSCORE_DIVIDEND_YIELD_WEIGHT
    ) / w.VSCORE_DIVISOR


def compute_mscore(df: pd.DataFrame, suffix: str) -> pd.Series:
    return (
        _col(df, "3M Ratio", suffix) * w.MSCORE_3M_WEIGHT
        + _col(df, "6M Ratio", suffix) * w.MSCORE_6M_WEIGHT
        + _col(df, "1Y Ratio", suffix)
    ) / w.MSCORE_DIVISOR


def compute_fscore(df: pd.DataFrame, suffix: str) -> pd.Series:
    return (
        _col(df, "Insider Buy Ratio", suffix) * w.FSCORE_INSIDER_BUY_WEIGHT
        + _col(df, "EPSgrowth", suffix) * w.FSCORE_EPSGROWTH_WEIGHT
        + _col(df, "Revenuegrowth", suffix) * w.FSCORE_REVENUEGROWTH_WEIGHT
        + _col(df, "PEGR", suffix)
    ) / w.FSCORE_DIVISOR


def compute_finalscore(vscore: pd.Series, mscore: pd.Series) -> pd.Series:
    return vscore * w.FINALSCORE_VSCORE_WEIGHT + mscore * w.FINALSCORE_MSCORE_WEIGHT


def compute_eqc(df: pd.DataFrame, suffix: str) -> pd.Series:
    return (
        _col(df, "Depreciation Capex Ratio", suffix)
        + _col(df, "ARP", suffix) * w.EQC_ARP_WEIGHT
        + _col(df, "Coverage Ratio", suffix) * w.EQC_COVERAGE_RATIO_WEIGHT
    )


def compute_quant_score(df: pd.DataFrame, suffix: str) -> pd.Series:
    return (
        _col(df, "NCAV", suffix)
        + _col(df, "GPTOA", suffix)
        + _col(df, "Asset Turnover", suffix)
        + _col(df, "PFCR", suffix)
    ) / w.QUANT_SCORE_DIVISOR
