"""price_daily 테이블 upsert/조회. 야후·네이버 양쪽에서 공용으로 쓴다."""

import duckdb
import pandas as pd

_PRICE_COLUMNS: list[str] = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "foreign_rate",
    "source",
]


def upsert_price_history(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    source: str,
    ohlcv: pd.DataFrame,
) -> None:
    """일봉 DataFrame을 (ticker, date) 기준으로 upsert한다.

    ohlcv는 DatetimeIndex를 가지며 Open/High/Low/Close/Volume 컬럼(대문자 시작)을
    포함해야 한다. foreign_rate 컬럼은 있으면 사용하고 없으면 NULL로 채운다.
    """
    if ohlcv.empty:
        return

    rows = pd.DataFrame(
        {
            "ticker": ticker,
            "date": pd.to_datetime(ohlcv.index).date,
            "open": ohlcv["Open"].to_numpy(),
            "high": ohlcv["High"].to_numpy(),
            "low": ohlcv["Low"].to_numpy(),
            "close": ohlcv["Close"].to_numpy(),
            "volume": ohlcv["Volume"].to_numpy(),
            "foreign_rate": ohlcv["foreign_rate"].to_numpy()
            if "foreign_rate" in ohlcv.columns
            else None,
            "source": source,
        }
    )

    conn.register("price_rows_view", rows)
    try:
        columns_clause = ", ".join(_PRICE_COLUMNS)
        update_clause = ", ".join(
            f"{column}=excluded.{column}" for column in _PRICE_COLUMNS if column not in ("ticker", "date")
        )
        conn.execute(
            f"""
            INSERT INTO price_daily ({columns_clause})
            SELECT {columns_clause} FROM price_rows_view
            ON CONFLICT (ticker, date) DO UPDATE SET {update_clause}
            """
        )
    finally:
        conn.unregister("price_rows_view")


def get_price_history(conn: duckdb.DuckDBPyConnection, ticker: str) -> pd.DataFrame:
    """저장된 종목 일봉을 날짜 오름차순 DataFrame으로 반환한다."""
    return conn.execute(
        "SELECT * FROM price_daily WHERE ticker = ? ORDER BY date", [ticker]
    ).fetchdf()
