"""네이버증권 API HTTP 클라이언트. User-Agent 헤더, 요청 간 스로틀,
429(요청 과다)/일시적 오류 재시도를 담당한다.

404/409(잘못된 티커 코드)는 예외가 아니라 None으로 반환해 fetch() 쪽에서
yfinance의 "필수 필드 없음 → is_valid=False" 패턴과 동일하게 다룰 수 있게 한다.
"""

import time

import requests

from collection.constants import (
    NAVER_MAX_RETRIES,
    NAVER_USER_AGENT,
    REQUEST_THROTTLE_SECONDS,
    TOO_MANY_REQUESTS_WAIT_SECONDS,
)
from collection.naver.endpoints import (
    BASIC_URL_TEMPLATE,
    FINANCE_ANNUAL_URL_TEMPLATE,
    INTEGRATION_URL_TEMPLATE,
    SISE_JSON_URL,
)

_HEADERS = {"User-Agent": NAVER_USER_AGENT}
_REQUEST_TIMEOUT_SECONDS: float = 10
_INVALID_TICKER_STATUS_CODES: tuple[int, ...] = (404, 409)


def _get(url: str, params: dict | None = None) -> requests.Response | None:
    """잘못된 티커(404/409)는 None, 성공은 Response, 그 외에는 재시도 후 예외를 던진다."""
    response = None
    for _ in range(NAVER_MAX_RETRIES):
        time.sleep(REQUEST_THROTTLE_SECONDS)
        response = requests.get(url, params=params, headers=_HEADERS, timeout=_REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return response
        if response.status_code in _INVALID_TICKER_STATUS_CODES:
            return None
        if response.status_code == 429:
            time.sleep(TOO_MANY_REQUESTS_WAIT_SECONDS)
            continue
        response.raise_for_status()
    return response


def fetch_basic(code: str) -> dict | None:
    """종목 기본 정보(현재가, 거래소 등)를 가져온다."""
    response = _get(BASIC_URL_TEMPLATE.format(code=code))
    return response.json() if response is not None else None


def fetch_integration(code: str) -> dict | None:
    """PER/PBR/EPS/시총/배당수익률 등 현재 스냅샷 지표를 가져온다."""
    response = _get(INTEGRATION_URL_TEMPLATE.format(code=code))
    return response.json() if response is not None else None


def fetch_finance_annual(code: str) -> dict | None:
    """연간 재무제표(매출액/영업이익/ROE/부채비율 등)를 가져온다."""
    response = _get(FINANCE_ANNUAL_URL_TEMPLATE.format(code=code))
    return response.json() if response is not None else None


def fetch_price_history(code: str, start_date: str, end_date: str) -> str | None:
    """일봉 원본 응답(문자열)을 가져온다. start_date/end_date는 'YYYYMMDD' 형식."""
    params = {
        "symbol": code,
        "requestType": 1,
        "startTime": start_date,
        "endTime": end_date,
        "timeframe": "day",
    }
    response = _get(SISE_JSON_URL, params=params)
    return response.text if response is not None else None
