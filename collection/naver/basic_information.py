"""국내(네이버증권) 티커 목록을 받아 종목별 NaverStock 데이터를 모아 하나의 표로 만든다.

`collection/basic_information.py`(야후 경로)와 동일한 인터페이스·동작을 따른다:
데이터가 없는 티커는 조용히 건너뛰고, 예외가 발생한 티커만 errortickers에 남긴다.
"""

import traceback
from typing import Callable, Optional

import pandas as pd
from tqdm import tqdm

from collection.naver.naver_stock import NaverStock


def get_naver_stock_information(
    tickers: list[str],
    on_ticker_collected: Optional[Callable[[NaverStock], None]] = None,
) -> tuple[pd.DataFrame, list[str]]:
    """티커(6자리 종목 코드)마다 NaverStock을 만들어 raw+curated 데이터를 모두 담은
    표를 반환한다. 네이버 API 요청 재시도(429)는 collection.naver.client가 담당하므로
    여기서는 재시도 루프 없이 티커별로 한 번만 시도한다.

    `on_ticker_collected`가 주어지면 팩터 계산이 끝난 직후 NaverStock 인스턴스로
    호출한다 (예: 일봉/재무제표를 DuckDB에 저장)."""
    rows: list[dict] = []
    errortickers: list[str] = []

    for ticker in tqdm(tickers, desc="Downloading Naver stock data", unit="Ticker"):
        try:
            stock = NaverStock(ticker)
            stock.fetch()
            if not stock.is_valid:
                continue
            stock.compute_curated_factors()
            if on_ticker_collected is not None:
                on_ticker_collected(stock)
            rows.append(stock.to_row())
        except Exception as e:
            print(f"Error for {ticker}: {e}")
            errortickers.append(ticker)
            traceback.print_exc()

    return pd.DataFrame(rows), errortickers
