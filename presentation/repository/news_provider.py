"""뉴스 연결 지점.

세계 경제 뉴스(ticker=None)는 collect_news.py가 DuckDB(macro DB)의 news 테이블에
채운 것을 읽어 반환한다. 종목별 뉴스(ticker 지정)는 아직 수집 영역에 구현되어 있지
않아 None을 반환한다.
반환 타입이 계약이다: None = "준비 중" 표시, 리스트 = 뉴스 목록 렌더링.
"""

from pathlib import Path

import duckdb
import pandas as pd

from presentation import config
from presentation.models import NewsItem
from storage.database import MACRO_DB_PATH
from storage.news_repository import get_latest_news

# news 테이블 전체를 넉넉히 읽어와 아래 _prioritize_google_news가 재정렬할 수 있게 한다
# (수집 계층의 보관 개수(NEWS_KEEP_LIMIT)에 표현 계층이 의존하지 않도록 별도 상수로 둔다).
_POOL_LIMIT: int = 200


def _prioritize_google_news(df: pd.DataFrame) -> pd.DataFrame:
    """상단 NEWS_FEATURED_LIMIT개는 Google News("세계 경제" 검색) 기사를 우선 채운다.

    연합뉴스 경제 RSS는 게시 빈도가 훨씬 높아, 단순 최신순 병합이면 국내 경제 일반
    기사(부동산·소송 등)가 "세계 경제" 검색 결과보다 먼저 노출돼 주요 기사 섹션의
    취지(세계 경제 핵심)를 벗어난다. 부족분은 나머지에서 최신순으로 채운다.
    그 아래 헤드라인 목록은 원래의 최신순 병합을 그대로 써서 다양성을 유지한다.
    """
    featured_limit = config.NEWS_FEATURED_LIMIT
    google_news = df[df["origin"] == "google_news"]
    featured = google_news.head(featured_limit)
    if len(featured) < featured_limit:
        backfill = df[~df.index.isin(featured.index)].head(featured_limit - len(featured))
        featured = pd.concat([featured, backfill]).sort_values("published_at", ascending=False)
    rest = df[~df.index.isin(featured.index)]
    return pd.concat([featured, rest], ignore_index=True)


def load_news(
    ticker: str | None = None, db_path: str | Path = MACRO_DB_PATH
) -> list[NewsItem] | None:
    if ticker is not None:
        return None  # 종목별 뉴스는 아직 미구현

    path = Path(db_path)
    if not path.exists():
        return None

    conn = duckdb.connect(str(path), read_only=True)
    try:
        try:
            df = get_latest_news(conn, limit=_POOL_LIMIT)
        except duckdb.Error:
            return None  # news 테이블이 아직 없는 옛 DB 등
    finally:
        conn.close()

    if df.empty:
        return None

    display_limit = config.NEWS_FEATURED_LIMIT + config.NEWS_LIST_LIMIT
    ordered = _prioritize_google_news(df).head(display_limit)
    return [
        NewsItem(
            title=str(row.title),
            source=str(row.source),
            url=str(row.url),
            published_at=str(row.published_at),
            summary=None if pd.isna(row.summary) else str(row.summary),
        )
        for row in ordered.itertuples()
    ]
