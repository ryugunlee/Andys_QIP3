"""세계 경제 뉴스 수집에 쓰이는 상수.

Google News RSS는 이용약관상 "개인용 피드리더, 비상업적 용도"로 제한하고 있으나,
헤드라인+링크(+짧은 요약)만 노출하고 본문은 저장하지 않는 애그리게이터 방식으로
사용하기로 결정했다 (.claude/DECISIONS.md 참고).
"""

import urllib.parse

NEWS_REQUEST_TIMEOUT: int = 10  # seconds
NEWS_USER_AGENT: str = "Mozilla/5.0 (compatible; AndysQIP/1.0)"

_GOOGLE_NEWS_QUERY: str = "세계 경제"
GOOGLE_NEWS_RSS_URL: str = (
    "https://news.google.com/rss/search?q="
    + urllib.parse.quote(_GOOGLE_NEWS_QUERY)
    + "&hl=ko&gl=KR&ceid=KR:ko"
)
YONHAP_ECONOMY_RSS_URL: str = "https://www.yna.co.kr/rss/economy.xml"

GOOGLE_NEWS_FETCH_LIMIT: int = 30  # 소스 1개당 이번 수집에서 가져올 최대 기사 수
YONHAP_FETCH_LIMIT: int = 30

NEWS_KEEP_LIMIT: int = 100  # DB에 유지할 최신 기사 수 (피드에서 밀려난 오래된 기사 정리 기준)

# 표현 계층이 "세계 경제 핵심"(Google News 검색 결과)을 연합뉴스의 국내 경제 일반 기사보다
# 우선 노출하기 위해 구분하는 출처 태그 (news_provider.py 참고)
ORIGIN_GOOGLE_NEWS: str = "google_news"
ORIGIN_YONHAP: str = "yonhap"
