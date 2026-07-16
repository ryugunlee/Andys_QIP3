# Andy`s Quantitative Investment Program II

import pandas as pd
from datetime import datetime
import schedule
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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
    get_sorting_and_basicscore,
    get_detailscore_and_finalrank,
    get_standard_data,
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


def email_report(title, text, folder_path):
    """
    이 함수는 이메일로 보고서를 보내는 함수이다.
    발신/수신 계정 정보는 환경변수 GMAIL_ADDRESS, GMAIL_APP_PASSWORD에서 읽는다.
    """
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_address or not gmail_app_password:
        raise RuntimeError(
            "이메일 발송에 필요한 환경변수가 설정되지 않았습니다. "
            "GMAIL_ADDRESS(지메일 주소)와 GMAIL_APP_PASSWORD(지메일 앱 비밀번호)를 설정해 주세요."
        )
    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = gmail_address
    msg["Subject"] = title
    msg.attach(MIMEText(text, "plain"))
    filepaths = [
        os.path.join(folder_path, filename)
        for filename in os.listdir(folder_path)
        if filename.endswith(".csv")
        or filename.endswith(".txt")
        or filename.endswith(".json")
    ]

    for filepath in filepaths:
        try:
            with open(filepath, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())

            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {os.path.basename(filepath)}",
            )
            msg.attach(part)
        except Exception as e:
            print(f"Failed to attach file {filepath}: {e}")

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.sendmail(msg["From"], msg["To"], msg.as_string())


def main(stockmarket):
    """
    이 함수는 전체적인 프로그램을 실행하는 함수이다.

    한국 시장(KRX/KOSPI/KOSDAQ/KONEX)은 네이버증권, 그 외는 yfinance로 수집한다.
    산출물은 CSV/txt 대신 DuckDB(`storage/andys_qip.duckdb`)에 저장하며, 이메일
    첨부 파일만 발송 시점에 DB에서 임시로 뽑아낸다.
    """
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"Date: {today}")

    folder_name = f"{stockmarket}stockdata2"
    folder_path = os.path.join("./qipinfos", folder_name)
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

    stockdata = get_sorting_and_basicscore(stockdata)
    stockdata = get_detailscore_and_finalrank(stockdata)
    print("Basic stock information has been downloaded.")
    print("The number of searched stock: ", len(stockdata))
    print(
        "The number of reliable stock: ", len(stockdata[stockdata["reliablity"] > 50])
    )

    run_id = storage.record_collection_run(conn, stockmarket, source, len(stockdata), errortickers)
    curated_columns = [column for column in stockdata.columns if not column.startswith("raw_")]
    storage.save_snapshot_factors(conn, run_id, stockdata[curated_columns])

    standard_data, sector_standard_data, country_standard_data = get_standard_data(
        stockdata
    )
    storage.save_standard_cutlines(conn, run_id, standard_data, sector_standard_data, country_standard_data)

    goodstock = storage.get_goodstock(conn, run_id)

    text = f"Date: {today}\n"
    text += f"Number of searched stocks: {len(stockdata)}\n"
    text += (
        f"Number of reliable stocks: {len(stockdata[stockdata['reliablity'] > 50])}\n"
    )
    text += f"Number of good stocks: {len(goodstock)}\n"
    text += f"Time taken to load stock data: {elapsed_time}\n"
    text += f"good stock tickerlist: \n{goodstock['Ticker'].tolist()[:30]}\n"

    title = f"{stockmarket} Stock Data Summary - {today}"

    try:
        storage.export_run_summary(conn, run_id, folder_path)
        email_report(title, text, folder_path)
        print("Email report has been sent.")
    except Exception as e:
        # 이메일 발송이 실패해도 수집/분석 결과는 이미 DuckDB에 저장되어 있다.
        print(f"이메일 발송에 실패했습니다 (데이터는 DB에 저장됨): {e}")

    conn.close()


pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.max_colwidth", None)

if __name__ == "__main__":
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
