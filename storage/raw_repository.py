"""raw_latest 테이블 upsert. yfinance info / 네이버 basic·integration 같은 원본 응답을
종목당 최신본만 덮어써서 보관한다 (재수집 가능한 데이터라 이력 보존이 불필요하다)."""

import json

import duckdb


def upsert_raw_latest(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    source: str,
    payload: dict,
) -> None:
    """종목의 원본 응답을 최신본으로 덮어쓴다."""
    conn.execute(
        """
        INSERT INTO raw_latest (ticker, source, payload, updated_at)
        VALUES (?, ?, ?, now())
        ON CONFLICT (ticker) DO UPDATE SET
            source = excluded.source,
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        [ticker, source, json.dumps(payload, default=str)],
    )


def get_raw_latest(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    """종목의 최신 raw payload를 dict로 반환한다. 없으면 None."""
    row = conn.execute(
        "SELECT payload FROM raw_latest WHERE ticker = ?", [ticker]
    ).fetchone()
    return json.loads(row[0]) if row else None
