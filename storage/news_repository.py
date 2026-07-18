"""news 테이블 upsert/조회 (세계 경제 뉴스 헤드라인).

macro_repository와 같은 패턴(register view → INSERT ... ON CONFLICT)을 따른다.
url을 기본키로 삼아 같은 기사를 여러 번 수집해도 중복되지 않는다.
"""

import duckdb
import pandas as pd

_NEWS_COLUMNS: list[str] = ["url", "title", "source", "published_at", "summary", "origin"]


def upsert_news(conn: duckdb.DuckDBPyConnection, news: pd.DataFrame) -> None:
    """(title, source, url, published_at, summary, origin) DataFrame을 url 기준 upsert한다."""
    if news.empty:
        return
    rows = news[_NEWS_COLUMNS].dropna(subset=["url", "title"]).copy()
    if rows.empty:
        return

    conn.register("news_rows_view", rows)
    try:
        columns_clause = ", ".join(_NEWS_COLUMNS)
        conn.execute(
            f"""
            INSERT INTO news ({columns_clause})
            SELECT {columns_clause} FROM news_rows_view
            ON CONFLICT (url) DO UPDATE SET
                title=excluded.title,
                source=excluded.source,
                published_at=excluded.published_at,
                summary=excluded.summary,
                origin=excluded.origin
            """
        )
    finally:
        conn.unregister("news_rows_view")


def prune_news(conn: duckdb.DuckDBPyConnection, keep: int) -> None:
    """published_at 기준 최신 keep건만 남기고 나머지를 삭제한다 (피드에서 밀려난 오래된 기사 정리)."""
    conn.execute(
        """
        DELETE FROM news WHERE url NOT IN (
            SELECT url FROM news ORDER BY published_at DESC LIMIT ?
        )
        """,
        [keep],
    )


def get_latest_news(conn: duckdb.DuckDBPyConnection, limit: int) -> pd.DataFrame:
    """최신 기사부터 limit건 반환."""
    return conn.execute(
        "SELECT * FROM news ORDER BY published_at DESC LIMIT ?", [limit]
    ).fetchdf()
