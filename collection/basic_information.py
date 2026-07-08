"""티커 목록을 받아 종목별 Stock 데이터를 모아 하나의 표(DataFrame)로 만든다."""

import time
import traceback

import pandas as pd
from tqdm import tqdm

from collection.constants import TOO_MANY_REQUESTS_WAIT_SECONDS
from collection.stock import Stock


def get_stock_basic_infomation(tickers: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """티커마다 Stock을 만들어 raw+curated 데이터를 모두 담은 표를 반환한다.

    티커별로 존재하는 raw 필드가 달라도(예: 시장마다 info 키가 다름) pandas가
    합집합 컬럼을 자동으로 만들고 없는 값은 NaN으로 채운다.
    """
    rows: list[dict] = []
    errortickers: list[str] = []

    for ticker in tqdm(tickers, desc="Downloading stock data", unit="Ticker"):
        while True:
            try:
                stock = Stock(ticker)
                stock.fetch()
                if not stock.is_valid:
                    break
                stock.compute_curated_factors()
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
