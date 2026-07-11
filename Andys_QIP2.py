# Andy`s Quantitative Investment Program II

import pandas as pd
from datetime import datetime
import FinanceDataReader as fdr
import json
import schedule
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from collection import get_stock_basic_infomation
from analysis import (
    get_sorting_and_basicscore,
    get_detailscore_and_finalrank,
    get_standard_data,
)

# 현재 KRX, KOSPI, KOSDAQ, KONEX, NASDAQ, NYSE, AMEX, S&P500, DJI 중 하나를 선택할 수 있습니다.
# AMERICAN을 선택하면 AMEX, NASDAQ, NYSE의 종목을 모두 가져옵니다.(ETF 제외)
# pd.set_option("future.no_silent_downcasting", True)


def get_tickers(stockmarket):
    """
    param: stockmarket: str, "KRX" or "KOSPI" or "KOSDAQ" or "KONEX" or "NASDAQ" or "NYSE" or "AMEX" or "S&P500"
    return: tickers: list of stock tickers

    주어진 시장에 대한 주식 티커를 문자열 리스트로 구해오는 함수입니다.
    """
    if stockmarket == "AMERICAN":
        tickers = (
            fdr.StockListing("AMEX")["Symbol"].tolist()
            + fdr.StockListing("NASDAQ")["Symbol"].tolist()
            + fdr.StockListing("NYSE")["Symbol"].tolist()
        )
        tickers = list(set(tickers))
        return [ticker.replace(".", "-") for ticker in tickers if " " not in ticker]
    elif stockmarket[0] == "K":
        tickers = fdr.StockListing(stockmarket)["Code"].tolist()
        return [ticker + ".KS" for ticker in tickers if not pd.isna(ticker)]
    elif stockmarket == "TMP":
        return ["AMZN", "QFIN", "GGAL", "STNE", "ALK"]
    elif stockmarket == "DJI" or stockmarket == "DOW":
        return [
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
    else:
        return fdr.StockListing(stockmarket)["Symbol"].tolist()


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
    """
    today = datetime.today().strftime("%Y-%m-%d")
    print(f"Date: {today}")
    # Create a folder named "stockdata2_[날짜]" inside "qipinfos" if it doesn't exist

    folder_name = f"{stockmarket}stockdata2"
    folder_path = os.path.join("./qipinfos", folder_name)
    os.makedirs(folder_path, exist_ok=True)
    tickers = get_tickers(stockmarket)
    # tickers = tickers[:30]
    start_time = time.time()
    stockdata, errortickers = get_stock_basic_infomation(tickers)
    end_time = time.time()
    elapsed_time = end_time - start_time
    elapsed_time = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
    print(f"Time taken to execute get_stock_basic_infomation: {elapsed_time}")
    stockdata.to_csv(
        f"./qipinfos/{stockmarket}stockdata2/{stockmarket}stockdata.csv",
        index=False,
    )
    stockdata = get_sorting_and_basicscore(stockdata)
    stockdata = get_detailscore_and_finalrank(stockdata)
    print("Basic stock information has been downloaded.")
    print("The number of searched stock: ", len(stockdata))
    print(
        "The number of reliable stock: ", len(stockdata[stockdata["reliablity"] > 50])
    )

    text = f"Date: {today}\n"
    text += f"Number of searched stocks: {len(stockdata)}\n"
    text += (
        f"Number of reliable stocks: {len(stockdata[stockdata['reliablity'] > 50])}\n"
    )
    # text += f"Number of good stocks: {len(goodstock)}\n"
    text += f"Time taken to load stock data: {elapsed_time}\n"

    title = f"{stockmarket} Stock Data Summary - {today}"

    stockdata.to_csv(
        f"./qipinfos/{stockmarket}stockdata2/{stockmarket}stockdata.csv",
        index=False,
    )
    standard_data, sector_standard_data, country_standard_data = get_standard_data(
        stockdata
    )
    standard_data.to_csv(
        f"./qipinfos/{stockmarket}stockdata2/{stockmarket}standarddata.csv",
        index=False,
    )
    stockdata = stockdata.sort_values(by="Finalscore", ascending=False)
    stockdata = stockdata.reset_index(drop=True)
    goodstock = stockdata[
        (stockdata["Finalscore"] > stockdata["Finalscore"].quantile(0.9))
        & (stockdata["reliablity"] > 80)
        & (stockdata["Quant score"] > 50)
        & (stockdata["Fscore"] > 50)
    ]
    goodstock = goodstock.sort_values(by="Finalscore", ascending=False)
    goodstock = goodstock.reset_index(drop=True)
    goodstock.to_csv(
        f"./qipinfos/{stockmarket}stockdata2/{stockmarket}goodstock.csv",
        index=False,
    )
    file_path = f"./qipinfos/{stockmarket}stockdata2/{stockmarket}stockinfo.txt"
    with open(file_path, "w") as file:
        file.write(f"Date: {today}\n")
        file.write(f"stockdata, {len(stockdata)} tickers, {elapsed_time} Loading\n")
        file.write(stockdata.to_string())
        file.write("\n\n")
        file.write(f"standard data:\n")
        file.write(standard_data.to_string())
        file.write("\n\n")
        file.write(f"sector standard data:\n")
        for sector, data in sector_standard_data.items():
            file.write(
                f"{sector}: {len(stockdata[stockdata['Sector'] == sector])} tickers\n"
            )
            file.write(data.to_string())
            file.write("\n\n")
        file.write(f"country standard data:\n")
        for country, data in country_standard_data.items():
            file.write(
                f"{country}: {len(stockdata[stockdata['Country'] == country])} tickers\n"
            )
            file.write(data.to_string())
            file.write("\n\n")
        file.write(f"good stock:\n")
        file.write(
            goodstock.to_string(
                columns=[
                    "Ticker",
                    "Sector",
                    "Country",
                    "Finalscore",
                    "Vscore",
                    "Mscore",
                    "EQC",
                    "Quant score",
                    "Fscore",
                    "reliablity",
                    "Current RatioS",
                    "Debt to EquityS",
                    "Debt GrowthS",
                    "Interest RatioS",
                    "Insider Buy RatioS",
                    "3M TurnoverS",
                    "Asset to EquityS",
                    "Asset TurnoverS",
                    "PFCRS",
                    "PEGRS",
                ]
            )
        )
    print("The stock information has been downloaded.")
    text += f"good stock tickerlist: \n{goodstock['Ticker'].tolist()[:30]}\n"
    email_report(title, text, folder_path)
    print("Email report has been sent.")


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
