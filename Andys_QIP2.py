# Andy`s Quantitative Investment Program II

import pandas as pd
from datetime import datetime
import schedule
import sys
import time

import duckdb

import storage
from collection import (
    get_naver_stock_information,
    get_stock_basic_infomation,
    get_tickers,
    is_korean_market,
    split_raw_and_curated,
)
from collection.stock_base import BaseStock
from analysis import (
    compute_group_summary,
    compute_scores,
    get_standard_data,
    score_output_columns,
)

# 현재 KRX, KOSPI, KOSDAQ, KONEX, NASDAQ, NYSE, AMEX, S&P500, DJI 중 하나를 선택할 수 있습니다.
# AMERICAN을 선택하면 AMEX, NASDAQ, NYSE의 종목을 모두 가져옵니다.(ETF 제외)
# pd.set_option("future.no_silent_downcasting", True)


def _persist_ticker_data(conn: duckdb.DuckDBPyConnection, stock: BaseStock, source: str) -> None:
    """수집된 종목의 5년 일봉/재무제표/원본 데이터를 DuckDB에 저장한다.

    수집(collection)과 저장(storage) 계층을 분리하기 위해 basic_information의
    `on_ticker_collected` 콜백으로 전달된다."""
    storage.upsert_price_history(conn, stock.ticker, source, stock.history)
    storage.upsert_financial_statements(conn, stock.to_financial_statement_rows())
    raw_payload, _ = split_raw_and_curated(stock.to_row())
    storage.upsert_raw_latest(conn, stock.ticker, source, raw_payload)


def main(stockmarket):
    """
    이 함수는 전체적인 프로그램을 실행하는 함수이다.

    한국 시장(KRX/KOSPI/KOSDAQ/KONEX)은 네이버증권, 그 외는 yfinance로 수집한다.
    산출물은 통화권별 DuckDB(qipinfos/andys_qip_kr.duckdb / andys_qip_us.duckdb)에 저장한다.
    점수는 수집 직후 해당 통화권 DB의 시장별 최신 run 전체를 모집단으로 계산한다.
    """
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"Date: {today}")

    conn = storage.connect(storage.stock_db_path_for_market(stockmarket))
    source = "naver" if is_korean_market(stockmarket) else "yahoo"

    tickers = get_tickers(stockmarket)
    persist_ticker = lambda stock: _persist_ticker_data(conn, stock, source)

    start_time = time.time()
    if is_korean_market(stockmarket):
        stockdata, errortickers = get_naver_stock_information(
            tickers, on_ticker_collected=persist_ticker
        )
    else:
        stockdata, errortickers = get_stock_basic_infomation(
            tickers, on_ticker_collected=persist_ticker
        )
    end_time = time.time()
    elapsed_time = end_time - start_time
    elapsed_time = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
    print(f"Time taken to execute collection ({source}): {elapsed_time}")

    print("Basic stock information has been downloaded.")
    print("The number of searched stock: ", len(stockdata))

    run_id = storage.record_collection_run(conn, stockmarket, source, len(stockdata), errortickers)
    curated_columns = [column for column in stockdata.columns if not column.startswith("raw_")]
    storage.save_snapshot_factors(conn, run_id, stockdata[curated_columns])

    # 점수는 이 DB(통화권)의 시장별 최신 run 전체를 모집단으로 계산한다.
    # (예: KOSPI 수집 직후라도 KOSDAQ 최신 run과 합쳐 한국 전체에서 점수를 냄)
    population = storage.get_latest_snapshots(conn)
    scored = compute_scores(population)
    new_score_columns = score_output_columns(scored, population.columns)
    storage.update_snapshot_scores(conn, scored[["run_id", "Ticker"] + new_score_columns])
    this_run = scored[scored["run_id"] == run_id]
    print(
        "The number of reliable stock: ", int((this_run["reliability"] > 50).sum())
    )

    standard_data, sector_standard_data, country_standard_data = get_standard_data(
        scored
    )
    storage.save_standard_cutlines(conn, run_id, standard_data, sector_standard_data, country_standard_data)

    # 섹터/산업 자체 평가 (그룹별 팩터 중앙값 + 그룹 간 상대 점수)
    for group_type, group_column in (("sector", "Sector"), ("industry", "Industry")):
        storage.upsert_group_summary(
            conn, group_type, compute_group_summary(scored, group_column)
        )

    goodstock = storage.get_goodstock(conn, run_id)

    text = f"Date: {today}\n"
    text += f"Number of searched stocks: {len(stockdata)}\n"
    text += (
        f"Number of reliable stocks: {int((this_run['reliability'] > 50).sum())}\n"
    )
    text += f"Number of good stocks: {len(goodstock)}\n"
    text += f"Time taken to load stock data: {elapsed_time}\n"
    text += f"good stock tickerlist: \n{goodstock['Ticker'].tolist()[:30]}\n"

    print(text)

    conn.close()


pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.max_colwidth", None)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 명령줄 인자로 시장을 넘기면 (GitHub Actions 등 비대화형 실행) 1회만 실행하고 종료한다.
        main(sys.argv[1].upper())
    else:
        stockmarket = input(
            "Enter the stock market (e.g., NASDAQ, NYSE, KRX, AMERICAN): "
        ).upper()
        main(stockmarket)
        # Schedule the main function to run every day at 9:00 AM
        schedule.every().day.at("09:00").do(main, stockmarket)
        # Keep the script running to execute the scheduled task
        while True:
            schedule.run_pending()
            time.sleep(1)
