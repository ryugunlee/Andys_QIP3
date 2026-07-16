"""yfinance로 매크로 지표(지수/환율/원자재/미 국채금리 지수)를 일괄 수집한다.

한 번의 배치 다운로드로 모든 YAHOO 소스 지표의 종가를 받아
(indicator, date, value) long DataFrame으로 변환한다. scale(예: 엔/원 100엔 기준)을
여기서 적용하므로 저장된 값이 곧 표시 값이다.
"""

import pandas as pd
import yfinance as yf

from collection.constants import HISTORY_PERIOD
from collection.macro.indicators import MacroSource, specs_by_source

_MACRO_COLUMNS: list[str] = ["indicator", "date", "value"]


def fetch_yahoo_macro(period: str = HISTORY_PERIOD) -> pd.DataFrame:
    """YAHOO 소스 지표 전체의 일별 종가를 long DataFrame으로 반환한다."""
    specs = specs_by_source(MacroSource.YAHOO)
    symbols = [spec.symbol for spec in specs if spec.symbol is not None]
    closes = yf.download(
        " ".join(symbols), period=period, interval="1d", progress=False
    )["Close"]
    if isinstance(closes, pd.Series):  # 심볼이 1개면 Series로 오므로 통일
        closes = closes.to_frame(symbols[0])

    frames: list[pd.DataFrame] = []
    for spec in specs:
        if spec.symbol not in closes.columns:
            print(f"[macro] 경고: yfinance에 {spec.symbol}({spec.id}) 데이터 없음 — 건너뜀")
            continue
        series = closes[spec.symbol].dropna() * spec.scale
        if series.empty:
            print(f"[macro] 경고: {spec.symbol}({spec.id}) 값이 비어 있음 — 건너뜀")
            continue
        frames.append(
            pd.DataFrame(
                {
                    "indicator": spec.id,
                    "date": pd.to_datetime(series.index).date,
                    "value": series.to_numpy(dtype=float),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=_MACRO_COLUMNS)
    return pd.concat(frames, ignore_index=True)
