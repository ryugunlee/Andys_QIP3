"""티커 목록을 받아 종목별 Stock 데이터를 모아 하나의 표(DataFrame)로 만든다."""

import time
import traceback
from typing import Callable, Optional

import pandas as pd
from tqdm import tqdm

from collection.constants import TOO_MANY_REQUESTS_WAIT_SECONDS
from collection.stock import Stock, YahooStock
from collection.tickers import is_korean_listed_ticker


def get_stock_basic_infomation(
    tickers: list[str],
    on_ticker_collected: Optional[Callable[[YahooStock], None]] = None,
) -> tuple[pd.DataFrame, list[str]]:
    """티커마다 Stock을 만들어 raw+curated 데이터를 모두 담은 표를 반환한다.

    티커별로 존재하는 raw 필드가 달라도(예: 시장마다 info 키가 다름) pandas가
    합집합 컬럼을 자동으로 만들고 없는 값은 NaN으로 채운다.

    `on_ticker_collected`가 주어지면 팩터 계산이 끝난 직후 Stock 인스턴스로 호출한다
    (예: 일봉/재무제표를 DuckDB에 저장). 이 모듈은 저장 계층을 모르므로 콜백으로
    위임한다 — 데이터 수집과 저장의 책임을 분리하기 위함이다.
    """
    rows: list[dict] = []
    errortickers: list[str] = []

    for ticker in tqdm(tickers, desc="Downloading stock data", unit="Ticker"):
        # 한국 상장 종목(6자리 코드/.KS/.KQ)은 네이버 경로 전용이다 — yfinance로는 절대
        # 수집하지 않는다(.claude/PROBLEMS.md #24). 정상 라우팅(Andys_QIP2.main의
        # is_korean_market 분기)에서는 걸릴 일이 없지만, 잘못 호출돼도 오염 데이터가
        # 섞이지 않도록 진입점에서 차단하는 방어 가드다.
        if is_korean_listed_ticker(ticker):
            print(
                f"[collection] 한국 상장 종목 {ticker}는 yfinance로 수집하지 않습니다 "
                "(네이버 경로 전용). 건너뜁니다."
            )
            continue
        while True:
            try:
                stock = Stock(ticker)
                stock.fetch()
                if not stock.is_valid:
                    break
                stock.compute_curated_factors()
                if on_ticker_collected is not None:
                    on_ticker_collected(stock)
                rows.append(stock.to_row())
                break
            except Exception as e:
                if "Too Many Requests." in str(e):
                    print(f"Too Many Requests for {ticker}. waiting 5 minutes.")
                    time.sleep(TOO_MANY_REQUESTS_WAIT_SECONDS)
                else:
                    print(f"Error for {ticker}: {e}")
                    errortickers.append(ticker)
                    traceback.print_exc()
                    break

    return pd.DataFrame(rows), errortickers
