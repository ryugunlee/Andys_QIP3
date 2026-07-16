"""macro_daily 테이블 upsert/조회 (경제지표 일별값).

price_repository의 register → INSERT ON CONFLICT → unregister 패턴을 따른다.
지표 정의(어떤 indicator id가 있는지)는 collection/macro/indicators.py가 단일 소스다.
"""

import duckdb
import pandas as pd

_MACRO_COLUMNS: list[str] = ["indicator", "date", "value"]


def upsert_macro_values(conn: duckdb.DuckDBPyConnection, values: pd.DataFrame) -> None:
    """(indicator, date, value) long format DataFrame을 upsert한다.

    values는 _MACRO_COLUMNS 컬럼을 포함해야 하며, value가 NaN인 행은 저장하지 않는다.
    """
    if values.empty:
        return
    rows = values[_MACRO_COLUMNS].dropna(subset=["value"]).copy()
    if rows.empty:
        return
    rows["date"] = pd.to_datetime(rows["date"]).dt.date

    conn.register("macro_rows_view", rows)
    try:
        columns_clause = ", ".join(_MACRO_COLUMNS)
        conn.execute(
            f"""
            INSERT INTO macro_daily ({columns_clause})
            SELECT {columns_clause} FROM macro_rows_view
            ON CONFLICT (indicator, date) DO UPDATE SET value=excluded.value
            """
        )
    finally:
        conn.unregister("macro_rows_view")


def get_macro_history(conn: duckdb.DuckDBPyConnection, indicator: str) -> pd.DataFrame:
    """지표 하나의 일별값을 날짜 오름차순으로 반환한다."""
    return conn.execute(
        "SELECT * FROM macro_daily WHERE indicator = ? ORDER BY date", [indicator]
    ).fetchdf()


def get_latest_macro_pairs(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """지표별 (최신 날짜, 최신값, 직전값)을 반환한다.

    표현 계층이 전일 대비 변화율을 계산하는 데 쓴다.
    컬럼: indicator, date, value, prev_value
    """
    return conn.execute(
        """
        SELECT indicator, date, value, prev_value FROM (
            SELECT
                indicator,
                date,
                value,
                lag(value) OVER (PARTITION BY indicator ORDER BY date) AS prev_value,
                row_number() OVER (PARTITION BY indicator ORDER BY date DESC) AS recency
            FROM macro_daily
        )
        WHERE recency = 1
        """
    ).fetchdf()
