"""데이터 수집에 쓰이는 이름 있는 상수 (기간, 임계값 등)."""

# yfinance 요청 사이 대기 시간 (레이트리밋 방지)
REQUEST_THROTTLE_SECONDS: float = 0.5
TOO_MANY_REQUESTS_WAIT_SECONDS: int = 300

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
