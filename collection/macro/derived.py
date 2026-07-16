"""수집된 지표들로부터 파생 지표를 계산한다.

- gold_gap_pct: KRX 금현물(원/g)과 국제 금(USD/oz→원/g 환산)의 괴리율(%).
  괴리가 벌어지면 투자 기회가 될 수 있어 히스토리로 저장한다.
- yield_spread_10y_3m: 미 10년물 − 3개월물 금리차(%p). 역전(음수)은 침체 신호.

입력/출력 모두 (indicator, date, value) long DataFrame이라 수집 결과에 concat해서
그대로 macro_daily에 upsert하면 된다.
"""

import pandas as pd

from collection.constants import TROY_OUNCE_GRAMS

_MACRO_COLUMNS: list[str] = ["indicator", "date", "value"]


def _to_long(series: pd.Series, indicator_id: str) -> pd.DataFrame:
    series = series.dropna()
    return pd.DataFrame(
        {
            "indicator": indicator_id,
            "date": series.index,
            "value": series.to_numpy(dtype=float),
        }
    )


def compute_derived_indicators(collected: pd.DataFrame) -> pd.DataFrame:
    """수집된 long DataFrame에서 파생 지표를 계산해 같은 형식으로 반환한다.

    필요한 원천 지표가 없는 파생 지표는 조용히 건너뛴다 (예: FRED 차단으로
    일부 결측이어도 나머지 파생은 계산).
    """
    if collected.empty:
        return pd.DataFrame(columns=_MACRO_COLUMNS)
    wide = collected.pivot_table(index="date", columns="indicator", values="value")

    frames: list[pd.DataFrame] = []

    # 위안/원 = 달러/원 ÷ 달러/위안 (yfinance CNYKRW=X는 히스토리가 없어 파생 계산)
    if {"usd_krw", "usd_cny"}.issubset(wide.columns):
        frames.append(_to_long(wide["usd_krw"] / wide["usd_cny"], "cny_krw"))
    else:
        print("[macro] 경고: 위안/원 계산에 필요한 지표 부족 — 건너뜀")

    # 금 괴리율: (KRX 원/g − 국제 금 원/g 환산) / 환산가 × 100
    if {"gold_krx", "gold_intl", "usd_krw"}.issubset(wide.columns):
        intl_krw_per_gram = wide["gold_intl"] / TROY_OUNCE_GRAMS * wide["usd_krw"]
        gap_pct = (wide["gold_krx"] - intl_krw_per_gram) / intl_krw_per_gram * 100
        frames.append(_to_long(gap_pct, "gold_gap_pct"))
    else:
        print("[macro] 경고: 금 괴리율 계산에 필요한 지표 부족 — 건너뜀")

    # 미 장단기 금리차 (10Y − 3M)
    if {"us_10y", "us_3m"}.issubset(wide.columns):
        frames.append(_to_long(wide["us_10y"] - wide["us_3m"], "yield_spread_10y_3m"))
    else:
        print("[macro] 경고: 장단기 금리차 계산에 필요한 지표 부족 — 건너뜀")

    if not frames:
        return pd.DataFrame(columns=_MACRO_COLUMNS)
    return pd.concat(frames, ignore_index=True)
