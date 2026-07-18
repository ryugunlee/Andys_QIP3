"""세계 경제 뉴스 헤드라인 수집 진입점.

Google News RSS("세계 경제" 검색)와 연합뉴스 경제 RSS에서 헤드라인·링크를 모아
url 기준 중복 제거 후 DuckDB(macro DB)의 news 테이블에 upsert한다. 오래된 기사는
NEWS_KEEP_LIMIT 기준으로 정리한다. 주식/매크로 파이프라인과는 독립적으로 실행한다.

의도적으로 헤드라인+링크(+가능한 경우 짧은 요약)만 저장한다 — 원문 본문은 수집하지
않는다 (Google News RSS 이용약관/각 언론사 저작권 관련 판단은 .claude/DECISIONS.md 참고).

사용법:
    python collect_news.py

기사 소스 정의: collection/news/constants.py
"""

import pandas as pd

import storage
from collection.news.constants import NEWS_KEEP_LIMIT
from collection.news.google_news_source import fetch_google_news_economy
from collection.news.yonhap_source import fetch_yonhap_economy


def collect_news() -> pd.DataFrame:
    """모든 소스를 수집하고 url 기준 중복을 제거한 DataFrame을 반환한다."""
    collected = pd.concat(
        [fetch_google_news_economy(), fetch_yonhap_economy()], ignore_index=True
    )
    return collected.drop_duplicates(subset="url", keep="first")


def main() -> None:
    news = collect_news()
    if news.empty:
        print("[news] 수집된 기사가 없습니다.")
        return

    conn = storage.connect(storage.MACRO_DB_PATH)
    try:
        storage.upsert_news(conn, news)
        storage.prune_news(conn, keep=NEWS_KEEP_LIMIT)
        print(f"[news] {len(news)}건 수집 완료. 소스별 건수:")
        print(news.groupby("source").size().sort_values(ascending=False).to_string())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
