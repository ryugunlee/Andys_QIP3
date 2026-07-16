"""섹터/산업 자체 평가(group_summary) 저장·조회.

analysis/group_summary.compute_group_summary의 long format 결과를
(group_type, group_value, factor) 기준으로 upsert한다 — 재점수 때마다
같은 키가 갱신되므로 테이블 크기는 그룹×팩터 수로 고정된다.
"""

import duckdb
import pandas as pd

_TABLE = "group_summary"
_KEY_COLUMNS = ("group_type", "group_value", "factor")
_VALUE_COLUMNS = ("ticker_count", "median_value", "score_s", "score_ss")


def upsert_group_summary(
    conn: duckdb.DuckDBPyConnection, group_type: str, summary: pd.DataFrame
) -> None:
    """group_type("sector"|"industry")의 요약을 upsert한다."""
    if summary.empty:
        return
    rows = summary.copy()
    rows.insert(0, "group_type", group_type)

    update_clause = ", ".join(f"{column} = excluded.{column}" for column in _VALUE_COLUMNS)
    conn.register("group_summary_view", rows)
    try:
        conn.execute(
            f"""
            INSERT INTO {_TABLE} ({", ".join(_KEY_COLUMNS[:2])}, ticker_count, factor,
                                  median_value, score_s, score_ss)
            SELECT group_type, group_value, ticker_count, factor,
                   median_value, score_s, score_ss
            FROM group_summary_view
            ON CONFLICT ({", ".join(_KEY_COLUMNS)}) DO UPDATE SET {update_clause}
            """
        )
    finally:
        conn.unregister("group_summary_view")


def get_group_summary(
    conn: duckdb.DuckDBPyConnection, group_type: str
) -> pd.DataFrame:
    """group_type의 요약 전체를 long format으로 반환한다."""
    return conn.execute(
        f"SELECT * FROM {_TABLE} WHERE group_type = ? ORDER BY group_value, factor",
        [group_type],
    ).fetchdf()
