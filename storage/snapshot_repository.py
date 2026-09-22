"""수집 실행(run) 기록과 run별 스냅샷(팩터·점수, percentile 커트라인) 저장.

snapshot_factors는 analysis 파이프라인이 만드는 컬럼(팩터마다 `{name}S`/`{name}TF`가
동적으로 생김)을 그대로 저장해야 하므로, 고정 DDL 대신 저장 시점에 컬럼을 발견해
`ALTER TABLE ADD COLUMN`으로 스키마를 넓혀간다. analysis/factors.py의 팩터 목록을
여기서 다시 나열하지 않기 위한 선택이다.
"""

import duckdb
import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

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


def _drop_imaginary_parts(df: pd.DataFrame) -> pd.DataFrame:
    """복소수 컬럼을 실수 컬럼으로 되돌린 복사본을 반환한다 (필요할 때만 복사).

    DuckDB는 complex128을 모르기 때문에 `conn.register()`가
    `NotImplementedException`을 던지고, 몇 시간짜리 수집 실행이 **마지막 저장
    단계에서** 통째로 죽는다. 실제로 QIP4 매출 CAGR이 음수 매출에서 복소수를
    만들어 9월 미국 수집 2회를 전부 날렸다 (`.claude/PROBLEMS.md` #40).

    중복 티커 방어선(save_snapshot_factors)과 같은 성격의 안전망이다 — 계산 쪽
    버그는 계산 쪽에서 고치되, 저장 경계가 실행 전체를 죽이지는 않게 한다.
    허수부가 있는 값은 그 팩터의 계산이 정의되지 않은 자리라 결측으로 남기고,
    허수부가 0인 값은 실수부를 그대로 쓴다.
    """
    complex_columns = [
        column for column in df.columns if is_complex_dtype(df[column])
    ]
    if not complex_columns:
        return df

    df = df.copy()
    for column in complex_columns:
        values = df[column].to_numpy()
        real = np.real(values).astype(float)
        df[column] = np.where(np.imag(values) != 0, np.nan, real)
    print(
        "[storage] 복소수 컬럼을 실수로 정규화했습니다 (허수부 있는 값은 결측 처리): "
        f"{complex_columns}"
    )
    return df


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

    rows = _drop_imaginary_parts(stockdata).rename(columns={"Ticker": "ticker"}).copy()

    # 티커 목록 오염 등으로 같은 티커가 두 번 수집돼도 (run_id, ticker) PK 위반으로
    # 1시간짜리 수집 실행 전체가 마지막 저장 단계에서 죽지 않도록 하는 방어선.
    duplicated = rows["ticker"].duplicated(keep="first")
    if duplicated.any():
        duplicate_tickers = rows.loc[duplicated, "ticker"].unique().tolist()
        print(f"[storage] snapshot 중복 티커 {duplicate_tickers} — 첫 행만 저장합니다.")
        rows = rows[~duplicated]

    rows.insert(0, "run_id", run_id)

    _ensure_snapshot_columns(conn, rows)

    conn.register("snapshot_rows_view", rows)
    try:
        conn.execute(f"INSERT INTO {_SNAPSHOT_TABLE} BY NAME SELECT * FROM snapshot_rows_view")
    finally:
        conn.unregister("snapshot_rows_view")


def update_snapshot_scores(
    conn: duckdb.DuckDBPyConnection, scores: pd.DataFrame
) -> None:
    """점수 파이프라인(analysis.compute_scores) 결과로 스냅샷 행들을 갱신한다.

    scores는 run_id·Ticker(또는 ticker)와 점수 컬럼들을 담는다. 점수 모집단이
    통화권 전체(여러 run)라서 INSERT가 아닌 (run_id, ticker) 기준 UPDATE를 쓴다.
    새 점수 컬럼은 _ensure_snapshot_columns가 동적으로 추가한다.
    """
    if scores.empty:
        return

    rows = _drop_imaginary_parts(scores).rename(columns={"Ticker": "ticker"}).copy()
    _ensure_snapshot_columns(conn, rows)

    score_columns = [
        column for column in rows.columns if column not in _FIXED_SNAPSHOT_COLUMNS
    ]
    if not score_columns:
        return
    set_clause = ", ".join(f'"{column}" = v."{column}"' for column in score_columns)

    conn.register("score_rows_view", rows)
    try:
        conn.execute(
            f"""
            UPDATE {_SNAPSHOT_TABLE} SET {set_clause}
            FROM score_rows_view v
            WHERE {_SNAPSHOT_TABLE}.run_id = v.run_id
              AND {_SNAPSHOT_TABLE}.ticker = v.ticker
            """
        )
    finally:
        conn.unregister("score_rows_view")


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
