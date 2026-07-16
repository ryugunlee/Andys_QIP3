"""DuckDB 연결과 스키마 생성.

테이블 책임:
- price_daily: 종목별 일봉. (ticker, date) 기준 upsert로 5년치를 계속 유지.
- collection_runs: 수집 실행(run) 1회 = 1행. 다른 스냅샷 테이블이 run_id로 참조한다.
- snapshot_factors: run별 curated 팩터 + 분석 점수. 분석 파이프라인이 만드는 컬럼이
  가변적이므로(percentile 팩터마다 `{name}S`/`{name}TF` 컬럼이 생김) 고정 DDL로 전부
  선언하지 않고, run_id/ticker만 고정하고 나머지는 저장 시점에 동적으로 추가한다
  (snapshot_repository.save_snapshot_factors 참고). analysis/factors.py의 팩터 목록과
  중복 선언하지 않기 위한 선택이다.
- financial_statements: 재무제표. (ticker, source, statement_type, period, item) 기준
  upsert라서 회계기간이 늘지 않는 한 크기가 고정된다.
- raw_latest: yfinance info / 네이버 basic·integration 같은 원본 응답을 종목당 최신본만 보관.
- standard_cutlines: get_standard_data가 만드는 전체/섹터/국가별 percentile 커트라인 표.
- macro_daily: 경제지표(매크로) 일별값. (indicator, date) 기준 upsert — 지표 정의는
  collection/macro/indicators.py, 저장/조회는 macro_repository.py 참고.
"""

import os

import duckdb

DEFAULT_DB_PATH: str = "./qipinfos/andys_qip.duckdb"

_SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS price_daily (
        ticker TEXT,
        date DATE,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE,
        volume BIGINT,
        foreign_rate DOUBLE,
        source TEXT,
        PRIMARY KEY (ticker, date)
    )
    """,
    "CREATE SEQUENCE IF NOT EXISTS run_id_seq START 1",
    """
    CREATE TABLE IF NOT EXISTS collection_runs (
        run_id BIGINT PRIMARY KEY,
        run_at TIMESTAMP,
        market TEXT,
        source TEXT,
        ticker_count INTEGER,
        error_tickers JSON
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS snapshot_factors (
        run_id BIGINT,
        ticker TEXT,
        PRIMARY KEY (run_id, ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_statements (
        ticker TEXT,
        source TEXT,
        statement_type TEXT,
        period TEXT,
        item TEXT,
        value DOUBLE,
        is_consensus BOOLEAN,
        PRIMARY KEY (ticker, source, statement_type, period, item)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_latest (
        ticker TEXT PRIMARY KEY,
        source TEXT,
        payload JSON,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS standard_cutlines (
        run_id BIGINT,
        scope TEXT,
        scope_value TEXT,
        row_label TEXT,
        factor TEXT,
        value DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS macro_daily (
        indicator TEXT,
        date DATE,
        value DOUBLE,
        PRIMARY KEY (indicator, date)
    )
    """,
]


def connect(db_path: str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """DuckDB 파일에 연결하고 스키마가 없으면 생성한다."""
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = duckdb.connect(db_path)
    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)
    return conn
