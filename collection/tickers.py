"""주식 시장별 티커 목록 조회.

원래 Andys_QIP2.py에 있었으나 데이터 수집 계층을 완전히 분리하기 위해 이 파일로
옮겼다 (.claude/PROBLEMS.md #7 해결).
"""

import pandas as pd
import FinanceDataReader as fdr

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
