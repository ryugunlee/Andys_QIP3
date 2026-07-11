"""수집 실행(run) 기록과 run별 스냅샷(팩터·점수, percentile 커트라인) 저장.

snapshot_factors는 analysis 파이프라인이 만드는 컬럼(팩터마다 `{name}S`/`{name}TF`가
동적으로 생김)을 그대로 저장해야 하므로, 고정 DDL 대신 저장 시점에 컬럼을 발견해
`ALTER TABLE ADD COLUMN`으로 스키마를 넓혀간다. analysis/factors.py의 팩터 목록을
여기서 다시 나열하지 않기 위한 선택이다.
"""

import duckdb
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from analysis.standard_data import (
    PERCENTILE_RANGE_START,
    PERCENTILE_RANGE_STEP,
    PERCENTILE_RANGE_STOP,
)

_SNAPSHOT_TABLE = "snapshot_factors"
_FIXED_SNAPSHOT_COLUMNS = {"run_id", "ticker"}


def record_collection_run(
    conn: duckdb.DuckDBPyConnection,
    market: str,
    source: str,
    ticker_count: int,
    error_tickers: list[str],
) -> int:
    """수집 실행 1건을 기록하고 새 run_id를 반환한다."""
    run_id = conn.execute("SELECT nextval('run_id_seq')").fetchone()[0]
    conn.execute(
        """
        INSERT INTO collection_runs (run_id, run_at, market, source, ticker_count, error_tickers)
        VALUES (?, now(), ?, ?, ?, ?)
        """,
        [run_id, market, source, ticker_count, error_tickers],
    )
    return run_id


def _duckdb_type_for(series: pd.Series) -> str:
    if is_bool_dtype(series):
        return "BOOLEAN"
    if is_numeric_dtype(series):
        return "DOUBLE"
    return "VARCHAR"


def _ensure_snapshot_columns(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            [_SNAPSHOT_TABLE],
        ).fetchall()
    }
    for column in df.columns:
        if column in existing or column in _FIXED_SNAPSHOT_COLUMNS:
            continue
        duckdb_type = _duckdb_type_for(df[column])
        conn.execute(f'ALTER TABLE {_SNAPSHOT_TABLE} ADD COLUMN "{column}" {duckdb_type}')


def save_snapshot_factors(
    conn: duckdb.DuckDBPyConnection, run_id: int, stockdata: pd.DataFrame
) -> None:
    """analysis 파이프라인을 거친 전체 표(curated + percentile + 점수 컬럼)를
    run_id 스냅샷으로 저장한다."""
    if stockdata.empty:
        return

    rows = stockdata.rename(columns={"Ticker": "ticker"}).copy()
    rows.insert(0, "run_id", run_id)

    _ensure_snapshot_columns(conn, rows)

    conn.register("snapshot_rows_view", rows)
    try:
        conn.execute(f"INSERT INTO {_SNAPSHOT_TABLE} BY NAME SELECT * FROM snapshot_rows_view")
    finally:
        conn.unregister("snapshot_rows_view")


def _melt_standard_table(table: pd.DataFrame, row_labels: list[str]) -> pd.DataFrame:
    table = table.drop(columns=["Top"], errors="ignore").copy()
    table.insert(0, "row_label", row_labels[: len(table)])
    return table.melt(id_vars="row_label", var_name="factor", value_name="value")


def save_standard_cutlines(
    conn: duckdb.DuckDBPyConnection,
    run_id: int,
    standard_data: pd.DataFrame,
    sector_standard_data: dict[str, pd.DataFrame],
    country_standard_data: dict[str, pd.DataFrame],
) -> None:
    """get_standard_data()가 만든 전체/섹터/국가별 percentile 커트라인 표를 저장한다."""
    row_labels = [
        f"top{i}%"
        for i in range(PERCENTILE_RANGE_START, PERCENTILE_RANGE_STOP, PERCENTILE_RANGE_STEP)
    ]

    frames = []

    market_long = _melt_standard_table(standard_data, row_labels)
    market_long.insert(0, "scope_value", None)
    market_long.insert(0, "scope", "market")
    frames.append(market_long)

    for sector, table in sector_standard_data.items():
        sector_long = _melt_standard_table(table, row_labels)
        sector_long.insert(0, "scope_value", sector)
        sector_long.insert(0, "scope", "sector")
        frames.append(sector_long)

    for country, table in country_standard_data.items():
        country_long = _melt_standard_table(table, row_labels)
        country_long.insert(0, "scope_value", country)
        country_long.insert(0, "scope", "country")
        frames.append(country_long)

    combined = pd.concat(frames, ignore_index=True)
    combined.insert(0, "run_id", run_id)

    conn.register("cutlines_rows_view", combined)
    try:
        conn.execute(
            """
            INSERT INTO standard_cutlines (run_id, scope, scope_value, row_label, factor, value)
            SELECT run_id, scope, scope_value, row_label, factor, value FROM cutlines_rows_view
            """
        )
    finally:
        conn.unregister("cutlines_rows_view")
