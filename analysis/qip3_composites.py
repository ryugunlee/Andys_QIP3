"""QIP3 5요인 점수(가치성/성장성/모멘텀/안정성/재무건전성)와 종합점수 수식.

composite_scores.py와 같은 패턴이다 — 팩터 점수 컬럼의 접미사만 바꿔 여러 계열
(S/SS/SecS/SecSS/IndS/IndSS)에 같은 수식을 재사용한다. 가중치는 qip3_weights.py.
각 요인 수식은 0~100 점수의 가중평균(가중치 합 1) 또는 동일가중 평균이라 결과도 0~100.
"""

import pandas as pd

import analysis.qip3_weights as w


def _col(df: pd.DataFrame, factor: str, suffix: str) -> pd.Series:
    return df[f"{factor}{suffix}"]


def _inverted(df: pd.DataFrame, factor: str, suffix: str) -> pd.Series:
    """'클수록 좋다'로 등록된 팩터를 '작을수록 좋다'로 뒤집는다 (100 - 점수).

    예: 1Y Volatility는 기존 파이프라인에 HIGHER_IS_BETTER로 등록돼 있어
    변동성이 클수록 점수가 높다. 안정성에는 반대가 필요하므로 반전해 쓴다.
    """
    return 100 - df[f"{factor}{suffix}"]


def compute_qip3_value(df: pd.DataFrame, suffix: str) -> pd.Series:
    """저평가성 — O'Shaughnessy Value Composite 방식(6개 컴포넌트 동일가중)."""
    shareholder_yield = (
        _col(df, "Dividend Yield", suffix) + _col(df, "Buyback Yield", suffix)
    ) / 2
    return (
        _col(df, "PER", suffix)
        + _col(df, "PBR", suffix)
        + _col(df, "PSR", suffix)
        + _col(df, "PCR", suffix)
        + _col(df, "EV/EBITDA", suffix)
        + shareholder_yield
    ) / w.VALUE_COMPONENT_COUNT


def compute_qip3_growth(df: pd.DataFrame, suffix: str) -> pd.Series:
    """성장성 — 이익·매출 성장률 + 성장의 질(GP/A)."""
    return (
        _col(df, "EPSgrowth", suffix) * w.GROWTH_EPS_WEIGHT
        + _col(df, "Revenuegrowth", suffix) * w.GROWTH_REVENUE_WEIGHT
        + _col(df, "GPTOA", suffix) * w.GROWTH_GPTOA_WEIGHT
    )


def compute_qip3_momentum(df: pd.DataFrame, suffix: str) -> pd.Series:
    """주가 흐름세 — 12-1 모멘텀 중심(Jegadeesh-Titman) + 중·단기 보조."""
    return (
        _col(df, "12-1Y Ratio", suffix) * w.MOMENTUM_12_1_WEIGHT
        + _col(df, "6M Ratio", suffix) * w.MOMENTUM_6M_WEIGHT
        + _col(df, "3M Ratio", suffix) * w.MOMENTUM_3M_WEIGHT
    )


def compute_qip3_stability(df: pd.DataFrame, suffix: str) -> pd.Series:
    """안정성(생존 리스크) — 레버리지·유동성·커버리지·저변동성. 하드 필터 전용."""
    return (
        _col(df, "Net Debt to Equity", suffix) * w.STABILITY_NET_DEBT_WEIGHT
        + _col(df, "Quick Ratio", suffix) * w.STABILITY_QUICK_WEIGHT
        + _col(df, "Interest Ratio", suffix) * w.STABILITY_INTEREST_WEIGHT
        + _col(df, "Coverage Ratio", suffix) * w.STABILITY_COVERAGE_WEIGHT
        + _inverted(df, "1Y Volatility", suffix) * w.STABILITY_LOW_VOLATILITY_WEIGHT
    )


def compute_qip3_health(df: pd.DataFrame, suffix: str) -> pd.Series:
    """재무건전성 — 수익성의 질·마진·효율성·현금완충·부채추세(Piotroski 정신)."""
    return (
        _col(df, "ROA", suffix) * w.HEALTH_ROA_WEIGHT
        + _col(df, "ARP", suffix) * w.HEALTH_ARP_WEIGHT
        + _col(df, "Gross Margin", suffix) * w.HEALTH_GROSS_MARGIN_WEIGHT
        + _col(df, "Operating Margin", suffix) * w.HEALTH_OPERATING_MARGIN_WEIGHT
        + _col(df, "Net Margin", suffix) * w.HEALTH_NET_MARGIN_WEIGHT
        + _col(df, "Asset Turnover", suffix) * w.HEALTH_ASSET_TURNOVER_WEIGHT
        + _col(df, "Inventory Turnover", suffix) * w.HEALTH_INVENTORY_TURNOVER_WEIGHT
        + _col(df, "Receivables Turnover", suffix) * w.HEALTH_RECEIVABLES_TURNOVER_WEIGHT
        + _col(df, "Debt Growth", suffix) * w.HEALTH_DEBT_GROWTH_WEIGHT
        + _col(df, "Cash Ratio", suffix) * w.HEALTH_CASH_RATIO_WEIGHT
        + _col(df, "Capex to Revenue", suffix) * w.HEALTH_CAPEX_WEIGHT
    )


def compute_qip3_total(
    value: pd.Series, growth: pd.Series, momentum: pd.Series, health: pd.Series
) -> pd.Series:
    """QIP3 종합점수. 안정성은 종합에 넣지 않고 별도 하드 필터로 쓴다(Greenblatt식 2단)."""
    return (
        value * w.TOTAL_VALUE_WEIGHT
        + growth * w.TOTAL_GROWTH_WEIGHT
        + momentum * w.TOTAL_MOMENTUM_WEIGHT
        + health * w.TOTAL_HEALTH_WEIGHT
    )
