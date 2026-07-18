"""데이터 수집에 쓰이는 이름 있는 상수 (기간, 임계값 등)."""

# yfinance 요청 사이 대기 시간 (레이트리밋 방지)
REQUEST_THROTTLE_SECONDS: float = 0.5
TOO_MANY_REQUESTS_WAIT_SECONDS: int = 300

# yfinance/네이버에 요청할 일봉 조회 기간 (년)
HISTORY_PERIOD_YEARS: int = 5
HISTORY_PERIOD: str = f"{HISTORY_PERIOD_YEARS}y"  # yfinance period 파라미터 형식

# 최소 1년치 거래일 수 (이보다 적으면 기술적 지표 계산 불가로 판단)
MIN_HISTORY_TRADING_DAYS: int = 130

# 이동평균선 기간
MA_WINDOWS: list[int] = [5, 20, 60, 120, 200]

# MACD 파라미터
MACD_SHORT_SPAN: int = 12
MACD_LONG_SPAN: int = 26
MACD_SIGNAL_SPAN: int = 9

# RSI 파라미터
RSI_SPAN: int = 14
RSI_SIGNAL_WINDOW: int = 9
RSI_OVERHEAT_THRESHOLD: float = 70
RSI_UNDERHEAT_THRESHOLD: float = 30

# 기간 수익률/거래대금 조회 구간 (거래일 기준)
RATIO_LOOKBACK_1Y_DAYS: int = 252
RATIO_LOOKBACK_6M_DAYS: int = 126
RATIO_LOOKBACK_3M_DAYS: int = 63
VOLUME_LOOKBACK_10D_DAYS: int = 10

# EPS가 0일 때 0으로 나누기를 피하기 위한 대체값
EPS_ZERO_SUBSTITUTE: float = 0.0001

# yfinance의 earningsGrowth/revenueGrowth는 비율(0.1)로 오므로 %로 환산
GROWTH_RATE_PERCENT_SCALE: float = 100

# --- 네이버증권(collection/naver) 전용 상수 ---
NAVER_USER_AGENT: str = "Mozilla/5.0"
NAVER_MAX_RETRIES: int = 3

# 네이버 ROE/부채비율 등은 이미 %(예: 10.85)로 오지만, yfinance의 returnOnEquity는
# 비율(예: 0.1085)이다. 두 소스의 ROE 스케일을 맞추기 위한 환산 상수.
NAVER_ROE_PERCENT_TO_FRACTION: float = 100

# 네이버 재무제표의 매출액/영업이익/당기순이익은 "억원" 단위 숫자로 온다 (1억 = 1e8원).
NAVER_EOK_TO_WON: float = 1e8

# --- WiseFn(navercomp.wisereport.co.kr) 재무제표 API 전용 상수 ---
# 네이버 coinfo 페이지의 "재무분석" 탭이 iframe으로 불러오는 실제 소스. 손익계산서/
# 재무상태표/현금흐름표(현금흐름표 포함)를 여기서 얻는다. cF3002.aspx 호출 파라미터.
NAVER_WISE_RPT_INCOME_STATEMENT: int = 0
NAVER_WISE_RPT_BALANCE_SHEET: int = 1
NAVER_WISE_RPT_CASH_FLOW: int = 2
NAVER_WISE_FRQ_ANNUAL: int = 0  # frq/frqTyp 공통: 0=연간, 1=분기
NAVER_WISE_FRQ_QUARTER: int = 1

# WiseFn 계정과목 코드(ACCODE). 삼성전자(005930)와 SK하이닉스(000660) 두 종목으로
# 교차 검증해 종목·기간과 무관하게 고정된 값임을 확인했다 (표준 IFRS 계정 코드 체계로 보임).
NAVER_WISE_ACCODE_REVENUE: str = "200000"  # 매출액(수익)
NAVER_WISE_ACCODE_GROSS_PROFIT: str = "200810"  # 매출총이익
NAVER_WISE_ACCODE_OPERATING_INCOME: str = "201370"  # 영업이익
NAVER_WISE_ACCODE_INTEREST_EXPENSE: str = "202560"  # 이자비용 (금융원가 하위)
NAVER_WISE_ACCODE_NET_INCOME: str = "203170"  # 당기순이익
NAVER_WISE_ACCODE_TOTAL_ASSETS: str = "110000"  # 자산총계
NAVER_WISE_ACCODE_CURRENT_ASSETS: str = "112830"  # 유동자산
NAVER_WISE_ACCODE_CASH_AND_EQUIVALENTS: str = "190650"  # 현금및현금성자산
NAVER_WISE_ACCODE_TOTAL_LIABILITIES: str = "130000"  # 부채총계
NAVER_WISE_ACCODE_CURRENT_LIABILITIES: str = "131580"  # 유동부채
NAVER_WISE_ACCODE_TOTAL_DEBT: str = "190980"  # *이자발생부채 (Yahoo의 Total Debt에 해당)
NAVER_WISE_ACCODE_CAPEX: str = "191000"  # *CAPEX (양수, Yahoo의 Capital Expenditure는 음수라 부호 반대)
NAVER_WISE_ACCODE_TOTAL_EQUITY: str = "120000"  # 자본총계
NAVER_WISE_ACCODE_OPERATING_CASH_FLOW: str = "400000"  # 영업활동으로인한현금흐름
NAVER_WISE_ACCODE_DEPRECIATION: str = "400140"  # 유형자산감가상각비 (영업CF 가산 항목)
NAVER_WISE_ACCODE_TREASURY_STOCK_DISPOSAL: str = "403890"  # 자기주식의처분 (재무활동 현금유입)
NAVER_WISE_ACCODE_TREASURY_STOCK_ACQUISITION: str = "404220"  # 자기주식의취득 (재무활동 현금유출)
# 신규 팩터(수익성/재무건전성/효율성)용 계정. 삼성전자(005930)·SK하이닉스(000660)로 교차 검증.
NAVER_WISE_ACCODE_COGS: str = "200360"  # 매출원가 (손익계산서)
NAVER_WISE_ACCODE_PRETAX_INCOME: str = "203120"  # 법인세비용차감전계속사업이익 (세전이익)
NAVER_WISE_ACCODE_INCOME_TAX: str = "203130"  # 법인세비용
NAVER_WISE_ACCODE_INVENTORY: str = "112840"  # 재고자산 (유동자산 하위)
NAVER_WISE_ACCODE_TRADE_RECEIVABLES: str = "190560"  # 매출채권 (19xxxx 정규화 계열)

# --- 경제지표(매크로, collection/macro) 전용 상수 ---
# 히스토리 적재 기간은 주식 일봉(HISTORY_PERIOD)과 동일한 5년을 쓴다.

# 금 1트로이온스 = 31.1034768g (국제 금 USD/oz ↔ KRX 금 원/g 환산에 사용)
TROY_OUNCE_GRAMS: float = 31.1034768

# FRED 공식 API(api.stlouisfed.org) 요청 타임아웃. 실패해도 다른 지표 수집은
# 계속한다 (collection/macro/fred_source.py).
FRED_REQUEST_TIMEOUT_SECONDS: int = 30

# 한국은행 ECOS Open API 요청 타임아웃 (collection/macro/ecos_source.py).
ECOS_REQUEST_TIMEOUT_SECONDS: int = 30

# 네이버 marketindex(금현물) 페이지네이션. pageSize는 60까지만 허용됨(2026-07-16 검증,
# 100은 400 응답). 60개 × 21페이지 = 1,260행 ≈ 거래일 5년 커버.
NAVER_GOLD_PAGE_SIZE: int = 60
NAVER_GOLD_MAX_PAGES: int = 21
