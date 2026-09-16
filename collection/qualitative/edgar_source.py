"""SEC EDGAR에서 최신 10-K 본문을 받아 텍스트로 만든다. 키는 없고 User-Agent(연락처)만 요구한다.

흐름: 티커 → CIK(company_tickers.json) → 제출 목록(submissions) → 최신 10-K의 본문 HTML → 텍스트.
10-K는 사업보고서보다 작아 섹션을 자르지 않는다.

주의: SEC는 클라우드 IP 대역(Codespaces·Actions 러너 포함)을 403으로 막는 경우가 있어 이 로더는
로컬 PC에서 도는 것을 전제로 한다(`.claude/PROBLEMS.md` #36). 우회는 하지 않는다.
User-Agent는 개인 연락처가 들어가므로 코드에 박지 않고 EDGAR_USER_AGENT 환경변수로 받는다.
"""

import os

import requests

from collection.qualitative.sources import SourceDocument, html_to_text

TICKERS_URL: str = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL: str = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL: str = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
REQUEST_TIMEOUT_SECONDS: int = 60
FORM_10K: str = "10-K"


class EdgarError(RuntimeError):
    """SEC EDGAR에서 원문을 받지 못했다."""


def _headers() -> dict[str, str]:
    user_agent = os.getenv("EDGAR_USER_AGENT")
    if not user_agent:
        raise EdgarError('EDGAR_USER_AGENT 미설정 — SEC 요구 형식 "이름 이메일"을 .env에 넣어라')
    return {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}


def _get(url: str) -> requests.Response:
    response = requests.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code == requests.codes.forbidden:
        raise EdgarError("SEC가 403으로 거부했다 — 클라우드 IP 차단일 수 있다. 로컬 PC에서 실행하거나 파일로 넣어라")
    response.raise_for_status()
    return response


def cik_for(ticker: str, tickers_payload: dict | None = None) -> int:
    payload = tickers_payload if tickers_payload is not None else _get(TICKERS_URL).json()
    wanted = ticker.upper()
    for entry in payload.values():
        if entry.get("ticker", "").upper() == wanted:
            return int(entry["cik_str"])
    raise EdgarError(f"SEC 티커 목록에 {ticker}가 없다")


def pick_latest_10k(submissions: dict) -> dict:
    """submissions JSON의 filings.recent(열 단위 병렬 배열)에서 가장 최근 10-K."""
    recent = submissions["filings"]["recent"]
    for index, form in enumerate(recent["form"]):
        if form == FORM_10K:
            return {
                "accession": recent["accessionNumber"][index].replace("-", ""),
                "document": recent["primaryDocument"][index],
                "filing_date": recent["filingDate"][index],
                "report_date": recent["reportDate"][index],
            }
    raise EdgarError("최근 제출 목록에 10-K가 없다")


def fetch_edgar_10k(ticker: str) -> tuple[SourceDocument, dict]:
    cik = cik_for(ticker)
    filing = pick_latest_10k(_get(SUBMISSIONS_URL.format(cik=cik)).json())
    html = _get(ARCHIVE_URL.format(cik=cik, accession=filing["accession"], document=filing["document"])).text
    text = html_to_text(html)
    title = f"10-K (report {filing['report_date']}, filed {filing['filing_date']})"
    return SourceDocument(title=title, text=text), {**filing, "cik": cik, "chars": len(text)}
