"""네이버증권 API 엔드포인트 URL 템플릿 (2026-07-11, 005930/247540으로 검증됨)."""

SISE_JSON_URL: str = "https://api.finance.naver.com/siseJson.naver"
BASIC_URL_TEMPLATE: str = "https://m.stock.naver.com/api/stock/{code}/basic"
INTEGRATION_URL_TEMPLATE: str = "https://m.stock.naver.com/api/stock/{code}/integration"
FINANCE_ANNUAL_URL_TEMPLATE: str = "https://m.stock.naver.com/api/stock/{code}/finance/annual"
