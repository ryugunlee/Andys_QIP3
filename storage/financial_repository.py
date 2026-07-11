"""financial_statements 테이블 upsert. 재무제표를 (ticker, source, statement_type,
period, item) 기준 long format으로 저장한다 — 회계기간이 늘지 않는 한 크기가 고정된다.
"""

import duckdb
import pandas as pd

_STATEMENT_COLUMNS: list[str] = [
    "ticker",
    "source",
    "statement_type",
    "period",
    "item",
    "value",
    "is_consensus",
]


def upsert_financial_statements(
    conn: duckdb.DuckDBPyConnection,
    statements: pd.DataFrame,
) -> None:
    """long format(ticker, source, statement_type, period, item, value, is_consensus)
    DataFrame을 upsert한다. 비어 있으면 아무 것도 하지 않는다."""
    if statements.empty:
        return

    rows = statements[_STATEMENT_COLUMNS]
    conn.register("financial_rows_view", rows)
    try:
        columns_clause = ", ".join(_STATEMENT_COLUMNS)
        update_clause = ", ".join(
            f"{column}=excluded.{column}"
            for column in _STATEMENT_COLUMNS
            if column not in ("ticker", "source", "statement_type", "period", "item")
        )
        conn.execute(
            f"""
            INSERT INTO financial_statements ({columns_clause})
            SELECT {columns_clause} FROM financial_rows_view
            ON CONFLICT (ticker, source, statement_type, period, item)
            DO UPDATE SET {update_clause}
            """
        )
    finally:
        conn.unregister("financial_rows_view")


def get_financial_statements(
    conn: duckdb.DuckDBPyConnection, ticker: str, source: str
) -> pd.DataFrame:
    """종목의 저장된 재무제표를 long format DataFrame으로 반환한다."""
    return conn.execute(
        "SELECT * FROM financial_statements WHERE ticker = ? AND source = ?",
        [ticker, source],
    ).fetchdf()
