"""연합뉴스 경제 RSS에서 헤드라인을 수집한다.

원문 링크가 직접 제공되고 description도 평문 요약이라 Google News와 달리
summary까지 채운다.
"""

import feedparser
import pandas as pd
import requests

from collection.news.constants import (
    NEWS_REQUEST_TIMEOUT,
    NEWS_USER_AGENT,
    ORIGIN_YONHAP,
    YONHAP_ECONOMY_RSS_URL,
    YONHAP_FETCH_LIMIT,
)
from collection.news.parsers import published_at_kst

_NEWS_COLUMNS: list[str] = ["title", "source", "url", "published_at", "summary", "origin"]
_SOURCE_NAME: str = "연합뉴스"


def fetch_yonhap_economy(limit: int = YONHAP_FETCH_LIMIT) -> pd.DataFrame:
    response = requests.get(
        YONHAP_ECONOMY_RSS_URL,
        headers={"User-Agent": NEWS_USER_AGENT},
        timeout=NEWS_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)

    rows = []
    for entry in feed.entries[:limit]:
        published_at = published_at_kst(entry)
        if published_at is None:
            continue  # 발행일 없는 항목은 정렬/노출 순서를 보장할 수 없어 제외
        summary = getattr(entry, "summary", None)
        rows.append(
            {
                "title": entry.title,
                "source": _SOURCE_NAME,
                "url": entry.link,
                "published_at": published_at,
                "summary": summary or None,
                "origin": ORIGIN_YONHAP,
            }
        )
    return pd.DataFrame(rows, columns=_NEWS_COLUMNS)
