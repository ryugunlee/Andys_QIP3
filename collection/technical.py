"""OHLCV(시가/고가/저가/종가/거래량) DataFrame에서 기술적 지표를 계산하는 공용 함수.

Close/Volume 컬럼만 있으면 계산 가능하므로 야후/네이버 등 데이터 소스와 무관하게
재사용한다 (`collection/stock_base.py`의 `BaseStock._compute_technical_factors`가 호출).
"""

import pandas as pd

from collection.constants import (
    MA_WINDOWS,
    MACD_LONG_SPAN,
    MACD_SHORT_SPAN,
    MACD_SIGNAL_SPAN,
    RSI_SIGNAL_WINDOW,
    RSI_SPAN,
)


def add_moving_averages(ohlcv: pd.DataFrame) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    for window in MA_WINDOWS:
        ohlcv[f"ma{window}"] = ohlcv["Close"].rolling(window=window).mean()
    return ohlcv


def add_macd(ohlcv: pd.DataFrame) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    ohlcv["ema12"] = ohlcv["Close"].ewm(span=MACD_SHORT_SPAN).mean()
    ohlcv["ema26"] = ohlcv["Close"].ewm(span=MACD_LONG_SPAN).mean()
    ohlcv["macd"] = ohlcv["ema12"] - ohlcv["ema26"]
    ohlcv["signal"] = ohlcv["macd"].ewm(span=MACD_SIGNAL_SPAN).mean()
    ohlcv["stdmacd"] = ohlcv["macd"] / ohlcv["ma20"] * 100
    return ohlcv


def add_rsi(ohlcv: pd.DataFrame) -> pd.DataFrame:
    ohlcv = ohlcv.copy()
    ohlcv["diff"] = ohlcv["Close"].diff()
    ohlcv["AU"] = ohlcv["diff"].apply(lambda x: x if x > 0 else 0)
    ohlcv["AD"] = ohlcv["diff"].apply(lambda x: -x if x < 0 else 0)
    ohlcv["AU"] = ohlcv["AU"].ewm(span=RSI_SPAN).mean()
    ohlcv["AD"] = ohlcv["AD"].ewm(span=RSI_SPAN).mean()
    ohlcv["RSI"] = ohlcv["AU"] / (ohlcv["AU"] + ohlcv["AD"]) * 100
    ohlcv["RSI_signal"] = ohlcv["RSI"].rolling(window=RSI_SIGNAL_WINDOW).mean()
    return ohlcv


def lookback_index(history: pd.DataFrame, lookback_days: int) -> int:
    """`lookback_days` 거래일 전 위치를 iloc 인덱스로 반환한다.

    history 조회 기간이 5년으로 늘어난 뒤에도 "1년 전 종가"처럼 고정된 기간 전
    값을 가리키려면 `iloc[0]`(히스토리 시작일)이 아니라 이 인덱스를 써야 한다.
    history가 `lookback_days`보다 짧으면 첫 번째 행(0)으로 대체한다.
    """
    return -lookback_days if len(history) >= lookback_days else 0
