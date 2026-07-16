"""DuckDB 연결과 스키마 생성.

DB 파일은 용도별로 3개로 나뉜다 (점수 모집단 = 통화권 단위이므로 주식 DB를 시장권별로 분리):
- KR_STOCK_DB_PATH: 한국 시장(KRX/KOSPI/KOSDAQ/KONEX) 상장 종목
- US_STOCK_DB_PATH: 미국 시장(NASDAQ/NYSE/AMEX 등) 상장 종목 — ADR도 미국 시장 상장이므로 여기
- MACRO_DB_PATH: 경제지표(매크로) — 시장 구분이 없는 세계 지표

세 DB 모두 같은 스키마로 생성한다 (스키마 분기로 얻는 이득보다 단순함이 크다).

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
- group_summary: 섹터/산업 자체 평가 — 그룹별 팩터 중앙값과 그룹 간 상대 점수
  (analysis/group_summary.py가 계산, 재계산 시 (group_type, group_value, factor) upsert).
- macro_daily: 경제지표(매크로) 일별값. (indicator, date) 기준 upsert — 지표 정의는
  collection/macro/indicators.py, 저장/조회는 macro_repository.py 참고.
"""

import os

import duckdb

KR_STOCK_DB_PATH: str = "./qipinfos/andys_qip_kr.duckdb"
US_STOCK_DB_PATH: str = "./qipinfos/andys_qip_us.duckdb"
MACRO_DB_PATH: str = "./qipinfos/andys_qip_macro.duckdb"


def stock_db_path_for_market(market: str) -> str:
    """시장명으로 주식 DB 파일을 고른다. 한국 시장(K로 시작)은 KR, 그 외는 US.

    collection.tickers.is_korean_market과 같은 규칙이지만, 저장 계층이
    수집 계층에 의존하지 않도록 여기서 별도로 정의한다.
    """
    return KR_STOCK_DB_PATH if market and market[0] == "K" else US_STOCK_DB_PATH

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
    """
    CREATE TABLE IF NOT EXISTS group_summary (
        group_type TEXT,
        group_value TEXT,
        ticker_count INTEGER,
        factor TEXT,
        median_value DOUBLE,
        score_s DOUBLE,
        score_ss DOUBLE,
        PRIMARY KEY (group_type, group_value, factor)
    )
    """,
]


def connect(db_path: str) -> duckdb.DuckDBPyConnection:
    """DuckDB 파일에 연결하고 스키마가 없으면 생성한다.

    db_path는 KR_STOCK_DB_PATH / US_STOCK_DB_PATH / MACRO_DB_PATH 중 하나를
    (또는 stock_db_path_for_market 결과를) 명시적으로 받는다.
    """
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    conn = duckdb.connect(db_path)
    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)
    return conn
