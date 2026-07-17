"""주식 시장별 티커 목록 조회.

원래 Andys_QIP2.py에 있었으나 데이터 수집 계층을 완전히 분리하기 위해 이 파일로
옮겼다 (.claude/PROBLEMS.md #7 해결).
"""

import re

import pandas as pd
import FinanceDataReader as fdr

# 한국 상장 종목 티커 패턴: 6자리 숫자 코드 + 선택적 .KS(코스피)/.KQ(코스닥) 접미사.
# 한국 ADR(미국 상장, 예: PKX/KB/SHG/LPL)은 알파벳 심볼이라 매칭되지 않는다.
# 방어 가드이므로 접미사 대소문자는 구분하지 않는다(.KS/.ks 모두 차단).
_KOREAN_LISTED_TICKER_PATTERN = re.compile(r"^\d{6}(\.(KS|KQ))?$", re.IGNORECASE)

_DOW_30_TICKERS: list[str] = [
    "AAPL",
    "MSFT",
    "V",
    "GS",
    "JPM",
    "AXP",
    "BA",
    "CAT",
    "CSCO",
    "CVX",
    "DIS",
    "DOW",
    "GS",
    "HD",
    "HON",
    "IBM",
    "INTC",
    "JNJ",
    "KO",
    "MCD",
    "MMM",
    "MRK",
    "NKE",
    "PFE",
    "PG",
    "TRV",
    "UNH",
    "VZ",
    "WBA",
    "WMT",
]


def is_korean_market(stockmarket: str) -> bool:
    """이 시장의 티커를 네이버증권 경로(collection.naver)로 수집해야 하는지 여부.
    KRX/KOSPI/KOSDAQ/KONEX가 모두 "K"로 시작하는 것을 이용한다."""
    return stockmarket[0] == "K"


def is_korean_listed_ticker(ticker: str) -> bool:
    """이 티커가 한국거래소 상장 종목(6자리 코드, .KS/.KQ 접미사 허용)인지 여부.

    한국 상장 종목은 오직 네이버증권 경로로만 수집한다 — yfinance 경로가 이 티커를
    받으면 접미사 붙은 영문명 데이터가 섞여 들어오므로(.claude/PROBLEMS.md #24) 진입점에서
    차단하는 방어 가드에 쓰인다. 한국 ADR(미국 상장 알파벳 심볼)은 여기에 걸리지 않아
    정상적으로 yfinance로 수집된다."""
    return bool(_KOREAN_LISTED_TICKER_PATTERN.match(ticker.strip()))


def get_tickers(stockmarket: str) -> list[str]:
    """
    param: stockmarket: str, "KRX" or "KOSPI" or "KOSDAQ" or "KONEX" or "NASDAQ" or "NYSE" or "AMEX" or "S&P500"
    return: tickers: list of stock tickers

    주어진 시장에 대한 주식 티커를 문자열 리스트로 구해오는 함수입니다.
    한국 시장(KRX/KOSPI/KOSDAQ/KONEX)은 네이버증권이 쓰는 6자리 종목 코드를
    접미사 없이 그대로 반환합니다 (수집은 collection.naver가 담당).
    """
    if stockmarket == "AMERICAN":
        tickers = (
            fdr.StockListing("AMEX")["Symbol"].tolist()
            + fdr.StockListing("NASDAQ")["Symbol"].tolist()
            + fdr.StockListing("NYSE")["Symbol"].tolist()
        )
        tickers = list(set(tickers))
        return [ticker.replace(".", "-") for ticker in tickers if " " not in ticker]
    elif is_korean_market(stockmarket):
        tickers = fdr.StockListing(stockmarket)["Code"].tolist()
        return [ticker for ticker in tickers if not pd.isna(ticker)]
    elif stockmarket == "TMP":
        return ["AMZN", "QFIN", "GGAL", "STNE", "ALK"]
    elif stockmarket == "DJI" or stockmarket == "DOW":
        return _DOW_30_TICKERS
    else:
        return fdr.StockListing(stockmarket)["Symbol"].tolist()
