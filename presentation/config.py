"""표현 계층 전반에서 쓰는 상수 정의.

시장 목록, 기본 경로, 화면에 노출하는 종목 개수 등 매직 넘버를 한곳에 모은다.
"""

from pathlib import Path

# 파이프라인(Andys_QIP2.py)이 시장 단위로 CSV를 만들기 때문에, 사이트는 이 목록을
# 순회하며 존재하는 시장 데이터만 통합한다.
MARKETS: tuple[str, ...] = ("KOSPI", "KOSDAQ", "NASDAQ", "NYSE")
KR_MARKETS: tuple[str, ...] = ("KOSPI", "KOSDAQ")
US_MARKETS: tuple[str, ...] = ("NASDAQ", "NYSE")

# 한국/미국 구분자. 통화 포맷(₩/$)과 시총 단위(조/T) 선택에 쓰인다.
REGION_KR: str = "KR"
REGION_US: str = "US"


def is_korean_market_name(market: str | None) -> bool:
    """시장명이 한국 시장(K로 시작: KRX/KOSPI/KOSDAQ/KONEX)인지 판별한다.

    collection.tickers.is_korean_market과 같은 규칙이지만, 표현 계층이
    수집 계층에 의존하지 않도록 여기서 별도로 정의한다.
    """
    return bool(market) and market[0] == "K"

DEFAULT_DATA_DIR: Path = Path("./qipinfos")
DEFAULT_OUTPUT_DIR: Path = Path("./docs")

SITE_TITLE: str = "Andy's QIP"
SITE_DESCRIPTION: str = "투자자가 스스로 판단할 수 있도록 정보를 제공하는 정량 분석 리포트"
DISCLAIMER: str = (
    "본 사이트의 모든 정보는 투자 판단을 돕기 위한 자료이며, "
    "매수·매도를 권유하지 않습니다."
)

# --- PWA (홈 화면 설치) ---
# 별도의 모바일 앱을 만들지 않고 이 정적 사이트 자체를 설치형 앱으로 쓴다
# (.claude/DECISIONS.md 2026-07-17 "모바일 앱 = PWA" 참고).
# 홈 화면 아이콘 아래에 표시되는 이름이라 짧아야 한다(안드로이드 권장 12자 이내).
APP_SHORT_NAME: str = "QIP"
# 안드로이드 상태 표시줄 색. 헤더 배경(흰색)과 맞춰 이어져 보이게 한다.
APP_THEME_COLOR: str = "#ffffff"
# 앱 시작 시 스플래시 배경. style.css의 --page-bg와 같은 값이어야 깜빡임이 없다.
APP_BACKGROUND_COLOR: str = "#ffffff"

# 목록 화면에 노출하는 종목 개수
TOP_MARKET_CAP_LIMIT: int = 10  # 시가총액 상위 표
RECOMMENDED_DISPLAY_LIMIT: int = 12  # 주식 분석 페이지의 추천 종목 카드
INDEX_RECOMMENDED_PREVIEW_LIMIT: int = 6  # 메인 페이지의 추천 종목 미리보기
