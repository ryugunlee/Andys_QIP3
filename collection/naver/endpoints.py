"""네이버증권 API 엔드포인트 URL 템플릿 (2026-07-11, 005930/247540/000660으로 검증됨)."""

SISE_JSON_URL: str = "https://api.finance.naver.com/siseJson.naver"
BASIC_URL_TEMPLATE: str = "https://m.stock.naver.com/api/stock/{code}/basic"
INTEGRATION_URL_TEMPLATE: str = "https://m.stock.naver.com/api/stock/{code}/integration"
FINANCE_ANNUAL_URL_TEMPLATE: str = "https://m.stock.naver.com/api/stock/{code}/finance/annual"

# 네이버 코인포(coinfo) 페이지의 "재무분석" 탭이 iframe으로 불러오는 실제 소스(WiseFn).
# 손익계산서/재무상태표/현금흐름표 원본(현금흐름표 포함)을 여기서 얻는다.
# cF3002.aspx 호출에는 이 페이지에서 추출한 encparam 토큰과 Referer 헤더가 필요하다.
WISE_COMPANY_PAGE_URL_TEMPLATE: str = "https://navercomp.wisereport.co.kr/v2/company/c1030001.aspx?cmp_cd={code}"
WISE_FINANCIAL_STATEMENT_URL: str = "https://navercomp.wisereport.co.kr/company/cF3002.aspx"

# 시장지표(marketIndex) 일별 시세. KRX 금현물(category=metals, reutersCode=M04020000) 등
# 종목이 아닌 시장지표의 일별 히스토리를 페이지네이션으로 제공한다 (2026-07-16 검증).
MARKET_INDEX_PRICES_URL: str = "https://m.stock.naver.com/front-api/marketIndex/prices"

# 업종(upjong) 목록 페이지. 종목 API가 업종을 숫자 코드로만 주기 때문에(PROBLEMS #20)
# 코드→한글 업종명 매핑을 얻으려면 이 페이지가 유일한 공개 경로다.
# euc-kr 인코딩이고, 한 번의 요청으로 전체 업종 목록을 준다 (2026-09-07 79개 확인).
INDUSTRY_LIST_URL: str = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
