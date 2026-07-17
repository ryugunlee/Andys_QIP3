"""네이버증권 API HTTP 클라이언트. User-Agent 헤더, 요청 간 스로틀,
429(요청 과다)/일시적 오류 재시도를 담당한다.

404/409(잘못된 티커 코드)는 예외가 아니라 None으로 반환해 fetch() 쪽에서
yfinance의 "필수 필드 없음 → is_valid=False" 패턴과 동일하게 다룰 수 있게 한다.
"""

import re
import time

import requests

from collection.constants import (
    NAVER_MAX_RETRIES,
    NAVER_USER_AGENT,
    NAVER_WISE_FRQ_ANNUAL,
    REQUEST_THROTTLE_SECONDS,
    TOO_MANY_REQUESTS_WAIT_SECONDS,
)
from collection.naver.endpoints import (
    BASIC_URL_TEMPLATE,
    FINANCE_ANNUAL_URL_TEMPLATE,
    INTEGRATION_URL_TEMPLATE,
    MARKET_INDEX_PRICES_URL,
    SISE_JSON_URL,
    WISE_COMPANY_PAGE_URL_TEMPLATE,
    WISE_FINANCIAL_STATEMENT_URL,
)

_HEADERS = {"User-Agent": NAVER_USER_AGENT}
_REQUEST_TIMEOUT_SECONDS: float = 10
_INVALID_TICKER_STATUS_CODES: tuple[int, ...] = (404, 409)
_WISE_ENCPARAM_PATTERN = re.compile(r"encparam:\s*'([^']+)'")


def _get(
    url: str, params: dict | None = None, extra_headers: dict | None = None
) -> requests.Response | None:
    """잘못된 티커(404/409)는 None, 성공은 Response, 그 외에는 재시도 후 예외를 던진다."""
    headers = {**_HEADERS, **extra_headers} if extra_headers else _HEADERS
    response = None
    for _ in range(NAVER_MAX_RETRIES):
        time.sleep(REQUEST_THROTTLE_SECONDS)
        response = requests.get(url, params=params, headers=headers, timeout=_REQUEST_TIMEOUT_SECONDS)
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


def fetch_market_index_prices(
    category: str, reuters_code: str, page: int, page_size: int
) -> list[dict] | None:
    """시장지표(금현물 등) 일별 시세 한 페이지를 가져온다 (최신 날짜부터).

    page_size는 60까지만 허용된다 (collection/constants.py의 NAVER_GOLD_PAGE_SIZE 참고).
    응답이 없거나 실패하면 None.
    """
    params = {
        "category": category,
        "reutersCode": reuters_code,
        "page": page,
        "pageSize": page_size,
    }
    response = _get(MARKET_INDEX_PRICES_URL, params=params)
    if response is None:
        return None
    payload = response.json()
    if not payload.get("isSuccess"):
        return None
    return payload.get("result") or []


def fetch_wise_encparam(code: str) -> str | None:
    """WiseFn 재무제표 페이지(HTML)에서 cF3002.aspx 호출에 필요한 encparam 토큰을 추출한다.
    이 토큰은 cmp_cd별로 다르므로(교차 검증함) 종목마다 새로 가져와야 한다."""
    response = _get(WISE_COMPANY_PAGE_URL_TEMPLATE.format(code=code))
    if response is None:
        return None
    match = _WISE_ENCPARAM_PATTERN.search(response.text)
    return match.group(1) if match else None


def fetch_wise_financial_statement(
    code: str, encparam: str, rpt: int, frq: int = NAVER_WISE_FRQ_ANNUAL
) -> dict | None:
    """WiseFn 손익계산서(rpt=0)/재무상태표(rpt=1)/현금흐름표(rpt=2) JSON을 가져온다.
    frq=0(연간, 기본)/1(분기). Referer 헤더가 없으면 빈 응답을 주므로 반드시 함께 보낸다.

    frq와 무관하게 응답 형태(YYMM 6개 = 실적 5개 기간 + 컨센서스 1개 기간)는 동일함을
    확인했다(2026-07-17, 005930으로 검증) — parsers.parse_wise_financial_statement가
    그대로 재사용된다."""
    params = {
        "cmp_cd": code,
        "frq": frq,
        "rpt": rpt,
        "finGubun": "MAIN",
        "frqTyp": frq,
        "cn": "",
        "encparam": encparam,
    }
    referer = {"Referer": WISE_COMPANY_PAGE_URL_TEMPLATE.format(code=code)}
    response = _get(WISE_FINANCIAL_STATEMENT_URL, params=params, extra_headers=referer)
    if response is None or not response.text:
        return None
    return response.json()
