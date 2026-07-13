"""뉴스 연결 지점.

아직 수집 영역에 뉴스 수집이 구현되지 않아 None을 반환한다.
수집이 구현되면 이 함수 본문만 산출물을 읽어 NewsItem 리스트를 반환하도록
교체하면 된다 — 템플릿·빌더·모델은 수정할 필요가 없다.
반환 타입이 계약이다: None = "준비 중" 표시, 리스트 = 뉴스 목록 렌더링.

ticker=None이면 시장 전체 뉴스(메인/주식 분석 페이지),
ticker를 지정하면 해당 종목 뉴스(종목 상세 페이지)를 뜻한다.
"""

from presentation.models import NewsItem


def load_news(ticker: str | None = None) -> list[NewsItem] | None:
    return None
