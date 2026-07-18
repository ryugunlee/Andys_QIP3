"""Google News RSS("세계 경제" 검색)에서 헤드라인을 수집한다.

여러 언론사를 자동으로 모아주는 대신, 링크는 Google 리다이렉트 링크이고
스니펫(description)은 HTML 앵커라 정제 없이는 노출하지 않는다 — summary는 항상
비워두고 헤드라인+링크만 채운다.
"""

import feedparser
import pandas as pd
import requests

from collection.news.constants import (
    GOOGLE_NEWS_FETCH_LIMIT,
    GOOGLE_NEWS_RSS_URL,
    NEWS_REQUEST_TIMEOUT,
    NEWS_USER_AGENT,
    ORIGIN_GOOGLE_NEWS,
)
from collection.news.parsers import published_at_kst, strip_source_suffix

_NEWS_COLUMNS: list[str] = ["title", "source", "url", "published_at", "summary", "origin"]


def fetch_google_news_economy(limit: int = GOOGLE_NEWS_FETCH_LIMIT) -> pd.DataFrame:
    response = requests.get(
        GOOGLE_NEWS_RSS_URL,
        headers={"User-Agent": NEWS_USER_AGENT},
        timeout=NEWS_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)

    rows = []
    for entry in feed.entries[:limit]:
        source = getattr(entry, "source", None)
        source_name = source.get("title") if source else None
        published_at = published_at_kst(entry)
        if published_at is None:
            continue  # 발행일 없는 항목은 정렬/노출 순서를 보장할 수 없어 제외
        rows.append(
            {
                "title": strip_source_suffix(entry.title, source_name),
                "source": source_name or "Google News",
                "url": entry.link,
                "published_at": published_at,
                "summary": None,
                "origin": ORIGIN_GOOGLE_NEWS,
            }
        )
    return pd.DataFrame(rows, columns=_NEWS_COLUMNS)
