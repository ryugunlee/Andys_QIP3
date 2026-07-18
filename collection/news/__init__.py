"""세계 경제 뉴스 헤드라인 수집 (Google News RSS + 연합뉴스 경제 RSS)."""

from collection.news.google_news_source import fetch_google_news_economy
from collection.news.yonhap_source import fetch_yonhap_economy

__all__ = ["fetch_google_news_economy", "fetch_yonhap_economy"]
