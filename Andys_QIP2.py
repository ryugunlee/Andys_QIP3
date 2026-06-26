# Andy`s Quantitative Investment Program II

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from tqdm import tqdm
import FinanceDataReader as fdr
import json
import schedule
import time
import os
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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


def get_stock_basic_infomation(tickers):
    """
    param: tickers: list of stock tickers

    return: stockdata: list of stock data
            infos: list of stock information

    이 함수는 기업의 저평가 여부 및, 시장 전체의 개별 주식 재무상태 분석을 위한 자료 수집 함수이다. (재무건전성은 다음에 만드는 함수에서 구하는 걸로..)
    여기서 구하는 자료는
    회사명, 섹터, 산업, 국가, 시가총액, 종가,
    PER, PBR, PSR, PCR, EV/EBITDA, 배당수익률, 자사주매입수익률,
    ROE, ROA, 영업이익률, 순이익률, 이익성장률, 매출액증가율, 이자보상비율
    3개월, 6개월, 1년 수익률, 과열지수, 변동성, 내부자 매수 비율 등이다.
    추가로 macd, williamsR, rsi, stochastic, disparity, divergence, bollinger, Volumema 등 시장 전반의 지표도 구하고 활용한다.
    """

    def ma(ohlcv):
        ohlcv = ohlcv.copy()
        ohlcv["ma5"] = ohlcv["Close"].rolling(window=5).mean()
        ohlcv["ma20"] = ohlcv["Close"].rolling(window=20).mean()
        ohlcv["ma60"] = ohlcv["Close"].rolling(window=60).mean()
        ohlcv["ma120"] = ohlcv["Close"].rolling(window=120).mean()
        ohlcv["ma200"] = ohlcv["Close"].rolling(window=200).mean()
        return ohlcv

    def macd(ohlcv):
        ohlcv = ohlcv.copy()
        ohlcv["ema12"] = ohlcv["Close"].ewm(span=12).mean()
        ohlcv["ema26"] = ohlcv["Close"].ewm(span=26).mean()
        ohlcv["macd"] = ohlcv["ema12"] - ohlcv["ema26"]
        ohlcv["signal"] = ohlcv["macd"].ewm(span=9).mean()
        ohlcv["stdmacd"] = ohlcv["macd"] / ohlcv["ma20"] * 100
        return ohlcv

    def rsi(ohlcv):
        ohlcv = ohlcv.copy()
        ohlcv["diff"] = ohlcv["Close"].diff()
        ohlcv["AU"] = ohlcv["diff"].apply(lambda x: x if x > 0 else 0)
        ohlcv["AD"] = ohlcv["diff"].apply(lambda x: -x if x < 0 else 0)
        ohlcv["AU"] = ohlcv["AU"].ewm(span=14).mean()
        ohlcv["AD"] = ohlcv["AD"].ewm(span=14).mean()
        ohlcv["RSI"] = ohlcv["AU"] / (ohlcv["AU"] + ohlcv["AD"]) * 100
        ohlcv["RSI_signal"] = ohlcv["RSI"].rolling(window=9).mean()
        return ohlcv

    data = []
    errortickers = []
    for ticker in tqdm(tickers, desc="Downloading stock data", unit="Ticker"):
        while True:
            try:
                stock = yf.Ticker(ticker)
                time.sleep(0.5)
                info = stock.info
                company_name = info.get("shortName", None)
                sector = info.get("sector", None)
                industry = info.get("industry", None)
                country = info.get("country", None)
                marketcap = info.get("marketCap", None)
                close = info.get("previousClose", None)
                if close == None or marketcap == None:
                    break

                dividend_yield = info.get("dividendYield", 0)
                evtoebitda = info.get("enterpriseToEbitda", None)
                pbr = info.get("priceToBook", None)
                psr = info.get("priceToSalesTrailing12Months", None)
                cashflow = info.get("operatingCashflow", None)
                pcr = marketcap / cashflow if cashflow != None else None
                evtorevenue = info.get("enterpriseToRevenue", None)
                netincome = info.get("netIncomeToCommon", None)
                revenue = info.get("totalRevenue", None)
                roe = info.get("returnOnEquity", None)
                roa = info.get("returnOnAssets", None)
                eps = info.get("trailingEps", None)
                if eps == 0:
                    eps = 0.0001
                if eps != None:
                    per = close / eps
                else:
                    per = None
                epsgrowth = info.get("earningsGrowth", 0) * 100
                revenuegrowth = info.get("revenueGrowth", 0) * 100
                insider_ratio = info.get("heldPercentInsiders", 0)
                institution = info.get("heldPercentInstitutions", 0)
                pegr = info.get("trailingPegRatio", None)
                opcashflow = info.get("operatingCashflow", None)
                debttoequity = info.get("debtToEquity", None)
                dividendtoincome = (dividend_yield * close / eps) / 100

                history = stock.history(period="1y")
                if len(history) < 130:
                    break
                history = ma(history)
                history = macd(history)
                history = rsi(history)
                if history["macd"].iloc[-1] > history["signal"].iloc[-1]:
                    macd_signal = "Heating"
                    if history["macd"].iloc[-2] < history["signal"].iloc[-2]:
                        macd_signal = "Heat Timing"
                else:
                    macd_signal = "Cooling"
                    if history["macd"].iloc[-2] > history["signal"].iloc[-2]:
                        macd_signal = "Sell Timing"
                if (
                    rsi_signal := history["RSI"].iloc[-1]
                    > history["RSI_signal"].iloc[-1]
                ):
                    rsi_signal = "Heating"
                    if history["RSI"].iloc[-2] < history["RSI_signal"].iloc[-2]:
                        rsi_signal = "Heat Timing"
                else:
                    rsi_signal = 0
                    if history["RSI"].iloc[-2] > history["RSI_signal"].iloc[-2]:
                        rsi_signal = -1
                if history["RSI"].iloc[-1] > 70:
                    rsir = "OVERHEAT"
                elif history["RSI"].iloc[-1] < 30:
                    rsir = "UNDERHEAT"
                else:
                    rsir = "NORMAL"

                ma5 = (
                    "Hit"
                    if history["Close"].iloc[-1] > history["ma5"].iloc[-1]
                    else "Miss"
                )
                ma20 = (
                    "Hit"
                    if history["Close"].iloc[-1] > history["ma20"].iloc[-1]
                    else "Miss"
                )
                ma60 = (
                    "Hit"
                    if history["Close"].iloc[-1] > history["ma60"].iloc[-1]
                    else "Miss"
                )
                ma120 = (
                    "Hit"
                    if history["Close"].iloc[-1] > history["ma120"].iloc[-1]
                    else "Miss"
                )
                ma200 = (
                    "Hit"
                    if history["Close"].iloc[-1] > history["ma200"].iloc[-1]
                    else "Miss"
                )
                ratio1r = (
                    history["Close"].iloc[-1] / history["Close"].iloc[0]
                ) * 100 - 100  # 기간 수익률
                ratio6m = (
                    history["Close"].iloc[-1] / history["Close"].iloc[-126]
                ) * 100 - 100
                ratio3m = (
                    history["Close"].iloc[-1] / history["Close"].iloc[-63]
                ) * 100 - 100
                avgvol1y = history["Volume"][-252:].mean()
                avgvol3m = history["Volume"][-63:].mean()
                avgvol10d = history["Volume"][-10:].mean()
                money10d = avgvol10d * history["Close"].iloc[-1]
                money3m = avgvol3m * history["Close"].iloc[-1]
                money1y = avgvol1y * history["Close"].iloc[-1]
                turnover1y = money1y / marketcap
                turnover3m = money3m / marketcap
                turnover10d = money10d / marketcap
                overheatratio_10d = turnover10d / turnover3m
                overheatratio_3m = turnover3m / turnover1y  # 과열 지수
                volatility3m = history["Close"][-63:].pct_change().abs().mean()
                volatility1y = history["Close"][-252:].pct_change().abs().mean()
                # 과열 지수, 기간 수익률, 변동폭 변동성 구함.

                cashflowq = stock.cashflow

                if "Repurchase Of Capital Stock" in cashflowq.index:
                    repurchase_of_capital_stock = cashflowq.loc[
                        "Repurchase Of Capital Stock"
                    ].iloc[0]
                else:
                    repurchase_of_capital_stock = 0
                if "Issuance Of Capital Stock" in cashflowq.index:
                    issuance_of_capital_stock = cashflowq.loc[
                        "Issuance Of Capital Stock"
                    ].iloc[0]
                else:
                    issuance_of_capital_stock = 0
                if "Capital Expenditure" in cashflowq.index:
                    capex = cashflowq.loc["Capital Expenditure"].iloc[0]
                else:
                    capex = None
                buyback_yield = (
                    -(
                        (repurchase_of_capital_stock + issuance_of_capital_stock)
                        / marketcap
                    )
                    * 100
                )

                financials = stock.financials

                if "Interest Expense" in financials.index:
                    interest_expense = financials.loc["Interest Expense"].iloc[0]
                else:
                    interest_expense = None

                if "Operating Income" in financials.index:
                    operating_income = financials.loc["Operating Income"].iloc[0]
                else:
                    operating_income = None

                if "Net Income" in financials.index and netincome is None:
                    netincome = financials.loc["Net Income"].iloc[0]

                if "Gross Profit" in financials.index:
                    gross_profit = financials.loc["Gross Profit"].iloc[0]
                else:
                    gross_profit = None

                if "EBIT" in financials.index:
                    ebit = financials.loc["EBIT"].iloc[0]
                else:
                    ebit = None

                if "Reconciled Depreciation" in financials.index:
                    depreciation = financials.loc["Reconciled Depreciation"].iloc[0]
                else:
                    depreciation = None
                if interest_expense is not None and operating_income is not None:
                    interest_ratio = operating_income / interest_expense
                else:
                    interest_ratio = None

                if netincome is not None and opcashflow is not None:
                    arp = (netincome - opcashflow) / marketcap * 100
                else:
                    arp = None

                balance_sheet = stock.balance_sheet

                if capex is not None and depreciation is not None:
                    decapexratio = -(depreciation / capex)
                else:
                    decapexratio = None

                if "Total Debt" in balance_sheet.index:
                    debt = balance_sheet.loc["Total Debt"].iloc[0]
                else:
                    debt = None

                if (
                    "Total Debt" in balance_sheet.index
                    and len(balance_sheet.loc["Total Debt"]) > 1
                ):
                    debt1yage = balance_sheet.loc["Total Debt"].iloc[1]
                else:
                    debt1yage = None

                if debt is not None and debt1yage is not None:
                    debt_growth = (debt - debt1yage) / debt1yage * 100
                else:
                    debt_growth = None

                if "Total Assets" in balance_sheet.index:
                    asset = balance_sheet.loc["Total Assets"].iloc[0]
                else:
                    asset = None

                if "Stockholders Equity" in balance_sheet.index:
                    equity = balance_sheet.loc["Stockholders Equity"].iloc[0]
                else:
                    equity = None

                if "Current Assets" in balance_sheet.index:
                    current_assets = balance_sheet.loc["Current Assets"].iloc[0]
                else:
                    current_assets = None

                if "Current Liabilities" in balance_sheet.index:
                    current_liabilities = balance_sheet.loc["Current Liabilities"].iloc[
                        0
                    ]
                else:
                    current_liabilities = None

                if "Total Liabilities Net Minority Interest" in balance_sheet.index:
                    liabilities = balance_sheet.loc[
                        "Total Liabilities Net Minority Interest"
                    ].iloc[0]
                else:
                    liabilities = None
                if equity is not None and asset is not None:
                    assettoequity = asset / equity
                else:
                    assettoequity = (
                        None  # 자기자본 비율 15점 이상이면 좋음 그 후부터는 비슷함.
                    )

                if debt is not None and opcashflow is not None:
                    coverageratio = opcashflow / debt
                else:
                    coverageratio = None  # 현금흐름/부채 25점 이상이면 좋음

                if current_assets is not None and current_liabilities is not None:
                    ncav = (current_assets - current_liabilities) / marketcap
                else:
                    ncav = None

                if current_assets is not None and current_liabilities is not None:
                    currentratio = current_assets / current_liabilities
                else:
                    currentratio = None

                if ebit is not None and liabilities is not None and asset is not None:
                    roc = ebit / (asset - liabilities)
                else:
                    roc = None

                if gross_profit is not None and asset is not None:
                    gptoa = gross_profit / asset
                else:
                    gptoa = None

                if revenue is not None and asset is not None:
                    assetturnover = revenue / asset
                else:
                    assetturnover = None

                if opcashflow is not None and capex is not None:
                    pfcr = marketcap / (opcashflow - capex)
                else:
                    pfcr = None

                insiderinfo = stock.insider_purchases
                if insiderinfo.empty != True:
                    netsharespurchased = insiderinfo.loc[2]["Shares"]
                    insiderbuyratio = (
                        (
                            netsharespurchased
                            * history["Close"].iloc[0]
                            / marketcap
                            * 100
                        )
                        if netsharespurchased != None
                        else None
                    )
                    # 내부자 매수 비율(음수면 매도, 양수면 매수)
                else:
                    insiderbuyratio = None

                buybacktoincome = ((buyback_yield * close) / eps) / 100

                data.append(
                    [
                        ticker,
                        company_name,
                        sector,
                        industry,
                        country,
                        marketcap,
                        close,
                        per,
                        pbr,
                        psr,
                        pcr,
                        evtorevenue,
                        evtoebitda,
                        dividend_yield,
                        roe,
                        roa,
                        epsgrowth,
                        revenuegrowth,
                        insider_ratio,
                        institution,
                        pegr,
                        opcashflow,
                        revenue,
                        debttoequity,
                        eps,
                        netincome,
                        dividendtoincome,
                        ratio3m,
                        ratio6m,
                        ratio1r,
                        turnover3m,
                        turnover1y,
                        turnover10d,
                        overheatratio_3m,
                        overheatratio_10d,
                        volatility3m,
                        volatility1y,
                        buyback_yield,
                        interest_ratio,
                        debt_growth,
                        insiderbuyratio,
                        arp,
                        decapexratio,
                        assettoequity,
                        coverageratio,
                        macd_signal,
                        rsi_signal,
                        rsir,
                        ma5,
                        ma20,
                        ma60,
                        ma120,
                        ma200,
                        ncav,
                        currentratio,
                        roc,
                        gptoa,
                        assetturnover,
                        pfcr,
                        buybacktoincome,
                    ]
                )
                break
            except Exception as e:
                if "Too Many Requests." in str(e):
                    print(f"Too Many Requests for {ticker}. waiting 5 minutes.")
                    time.sleep(300)
                else:
                    print(f"Error for {ticker}: {e}")
                    errortickers.append(ticker)
                    traceback.print_exc()
                    break
    return (
        pd.DataFrame(
            data,
            columns=[
                "Ticker",
                "Company Name",
                "Sector",
                "Industry",
                "Country",
                "Market Cap",
                "Close",
                "PER",
                "PBR",
                "PSR",
                "PCR",
                "EV/Revenue",
                "EV/EBITDA",
                "Dividend Yield",
                "ROE",
                "ROA",
                "EPSgrowth",
                "Revenuegrowth",
                "Insiderpercent",
                "Institutionpercent",
                "PEGR",
                "Operating Cashflow",
                "Revenue",
                "Debt to Equity",
                "EPS",
                "Net Income",
                "Dividend to Income",
                "3M Ratio",
                "6M Ratio",
                "1Y Ratio",
                "3M Turnover",
                "1Y Turnover",
                "10D Turnover",
                "3M Overheat",
                "10D Overheat",
                "3M Volatility",
                "1Y Volatility",
                "Buyback Yield",
                "Interest Ratio",
                "Debt Growth",
                "Insider Buy Ratio",
                "ARP",
                "Depreciation Capex Ratio",
                "Asset to Equity",
                "Coverage Ratio",
                "MACD Signal",
                "RSI Signal",
                "RSI",
                "MA5",
                "MA20",
                "MA60",
                "MA120",
                "MA200",
                "NCAV",
                "Current Ratio",
                "ROC",
                "GPTOA",
                "Asset Turnover",
                "PFCR",
                "Buyback to Income",
            ],
        ),
        errortickers,
    )


def calculating_percentile(df, column, s=0):
    """
    param: data: pd.DataFrame
                column: str
                s: int, -1 or 0 or 1
    return: data: pd.DataFrame

    주어진 데이터프레임의 특정 열에 대해 백분위수를 계산하여 새로운 열을 추가하는 함수이다.
    """
    df = df.copy()
    df[column] = df[column].apply(lambda x: None if isinstance(x, str) else x)
    df[f"{column}S"] = df[column].apply(lambda x: 50 if x == None or pd.isna(x) else 0)
    df[f"{column}TF"] = df[column].apply(lambda x: 0 if pd.isna(x) or x is None else 1)

    df_non_na = df.dropna(subset=[column])
    if s == 1:
        df_non_na = df_non_na[df_non_na[column] != 0]
        df_non_na.loc[:, f"{column}S"] = (
            (1 / df_non_na[column]).rank(pct=True).apply(lambda x: round(x * 100))
        )
    elif s == 0:
        df_non_na.loc[:, f"{column}S"] = (
            df_non_na[column].rank(pct=True).apply(lambda x: round(x * 100))
        )
    elif s == -1:
        df_non_na.loc[:, f"{column}S"] = (
            (-df_non_na[column]).rank(pct=True).apply(lambda x: round(x * 100))
        )
    df.update(df_non_na)
    return df


def get_sorting_and_basicscore(stockdata):
    """
    param: stockdata: pd.DataFrame
    return: stockdata: pd.DataFrame

    기본 주식 정보들에 대해서 주식 정보를 스코어링하는 함수이다. VC1을 구할 수 있다.
    """

    sharefactor = ["PER", "PBR", "PSR", "PCR", "PEGR", "EV/EBITDA", "EV/Revenue"]
    originalfactor = [
        "ROE",
        "ROA",
        "Dividend Yield",
        "Market Cap",
        "EPSgrowth",
        "Revenuegrowth",
        "Insiderpercent",
        "Institutionpercent",
        "Debt to Equity",
        "EPS",
        "Net Income",
        "Dividend to Income",
    ]
    reversefactor = []

    for factor in sharefactor:
        stockdata = calculating_percentile(stockdata, factor, s=1)
    for factor in originalfactor:
        stockdata = calculating_percentile(stockdata, factor)
    for factor in reversefactor:
        stockdata = calculating_percentile(stockdata, factor, s=-1)

    # stockdata["reliablity"] = (
    #     stockdata["PERTF"]
    #     + stockdata["PBRTF"]
    #     + stockdata["PSRTF"]
    #     + stockdata["PCRTF"]
    #     + stockdata["EV/EBITDATF"]
    # )

    vc1factors = ["PERS", "PBRS", "PSRS", "PCRS", "EV/EBITDAS"]
    stockdata["VC1"] = stockdata[vc1factors].sum(axis=1) / 5

    return stockdata


def get_detailscore_and_finalrank(stockinfo):
    """
    param: stockinfo: pd.DataFrame
    return: stockinfo: pd.DataFrame

    주식의 상세 정보를 스코어링하는 함수이다. VC2를 구할 수 있다.
    최후 스코어는 기간 모멘텀과 기본 스코어를 합한 것과 비슷하다.
    """
    stockinfo = stockinfo.copy()
    sharefactor = [
        "PFCR",
        "Buyback to Income",
        "Dividend to Income",
    ]
    originalfactor = [
        "3M Ratio",
        "6M Ratio",
        "1Y Ratio",
        "3M Turnover",
        "1Y Turnover",
        "10D Turnover",
        "3M Overheat",
        "10D Overheat",
        "3M Volatility",
        "1Y Volatility",
        "Buyback Yield",
        "Interest Ratio",
        "Insider Buy Ratio",
        "Asset to Equity",
        "Coverage Ratio",
        "NCAV",
        "Current Ratio",
        "ROC",
        "GPTOA",
        "Asset Turnover",
        "Buyback to Income",
        "Depreciation Capex Ratio",
    ]
    reversefactor = ["Debt Growth", "ARP"]

    for factor in sharefactor:
        stockinfo = calculating_percentile(stockinfo, factor, s=1)
    for factor in originalfactor:
        stockinfo = calculating_percentile(stockinfo, factor)
    for factor in reversefactor:
        stockinfo = calculating_percentile(stockinfo, factor, s=-1)

    stockinfo["Vscore"] = (
        stockinfo["PERS"]
        + stockinfo["EV/EBITDAS"] * 1.2
        + stockinfo["PCRS"] * 1.1
        + stockinfo["PSRS"] * 0.9
        + stockinfo["Buyback YieldS"] * 0.9
        + stockinfo["Dividend YieldS"] * 0.4
    ) / 5.5
    stockinfo["Mscore"] = (
        stockinfo["3M RatioS"] * 1.2
        + stockinfo["6M RatioS"] * 1.6
        + stockinfo["1Y RatioS"]
    ) / 3.8
    stockinfo["Fscore"] = (
        stockinfo["Insider Buy RatioS"] * 0.6
        + stockinfo["EPSgrowthS"] * 1.4
        + stockinfo["RevenuegrowthS"] * 1.2
        + stockinfo["PEGRS"]
    ) / 4.2
    stockinfo["Finalscore"] = stockinfo["Vscore"] * 0.63 + stockinfo["Mscore"] * 0.37
    stockinfo["EQC"] = (
        stockinfo["Depreciation Capex RatioS"]
        + stockinfo["ARPS"] * 1.7
        + stockinfo["Coverage RatioS"] * 1.3
    )
    stockinfo["Value risk"] = np.where(
        (stockinfo["Debt GrowthS"] < 15) | (stockinfo["PBRS"] < 40), "O", "X"
    )
    stockinfo["Growth risk"] = np.where(
        (stockinfo["Net Income"] > 0)
        & (stockinfo["EPSgrowthS"] > 30)
        & (stockinfo["RevenuegrowthS"] > 30),
        "X",
        "O",
    )
    stockinfo["Quant score"] = (
        stockinfo["NCAVS"]
        + stockinfo["GPTOAS"]
        + stockinfo["Asset TurnoverS"]
        + stockinfo["PFCRS"]
    ) / 4
    stockinfo["reliablity"] = (
        (
            stockinfo["PERTF"]
            + stockinfo["PBRTF"]
            + stockinfo["PSRTF"]
            + stockinfo["PCRTF"]
            + stockinfo["EV/EBITDATF"]
            + stockinfo["Debt GrowthTF"]
            + stockinfo["ARPTF"]
            + stockinfo["Insider Buy RatioTF"]
            + stockinfo["Coverage RatioTF"]
            + stockinfo["Asset to EquityTF"]
            + stockinfo["NCAVTF"]
            + stockinfo["Current RatioTF"]
            + stockinfo["ROCTF"]
            + stockinfo["GPTOATF"]
            + stockinfo["Asset TurnoverTF"]
            + stockinfo["PFCRTF"]
            + stockinfo["Buyback to IncomeTF"]
            + stockinfo["Depreciation Capex RatioTF"]
        )
        * 100
        / 18
    )
    return stockinfo


def get_standard_data(stockdata):
    """
    param: stockdata: pd.DataFrame
    return: standard_data: pd.DataFrame

    지표 점수 십분위의 커트라인에 대해 제공하는 함수이다.

    """

    def get_data(stockdata, column, percentile, s=1):
        try:
            stockdatan = stockdata.copy()
            stockdatan = stockdatan.dropna(subset=[column])
            if s == 1:
                stockdatan = stockdatan[stockdatan[column] != 0]
                threshold = (1 / stockdatan[column]).quantile(1 - percentile / 100)
                return 1 / threshold if threshold != 0 else None
            elif s == 0:
                threshold = stockdatan[column].quantile(1 - percentile / 100)
                return threshold
            elif s == -1:
                threshold = (-stockdatan[column]).quantile(1 - percentile / 100)
                return -threshold
        except Exception as e:
            print(
                f"Error in get_data for column {column}, percentile {percentile}, s {s}: {e}"
            )
            return None

    stockdata = stockdata.copy()
    standard_data = []
    for i in range(10, 100, 10):
        standard_data.append(
            [
                f"top{i}%",
                get_data(stockdata, "PER", i, s=1),
                get_data(stockdata, "PBR", i, s=1),
                get_data(stockdata, "PSR", i, s=1),
                get_data(stockdata, "PCR", i, s=1),
                get_data(stockdata, "PEGR", i, s=1),
                get_data(stockdata, "EV/EBITDA", i, s=1),
                get_data(stockdata, "EV/Revenue", i, s=1),
                get_data(stockdata, "ROE", i, s=0),
                get_data(stockdata, "ROA", i, s=0),
                get_data(stockdata, "EPSgrowth", i, s=0),
                get_data(stockdata, "Revenuegrowth", i, s=0),
                get_data(stockdata, "Insiderpercent", i, s=0),
                get_data(stockdata, "Institutionpercent", i, s=0),
                get_data(stockdata, "Debt to Equity", i, s=0),
                get_data(stockdata, "EPS", i, s=0),
                get_data(stockdata, "Net Income", i, s=0),
                get_data(stockdata, "Dividend Yield", i, s=0),
                get_data(stockdata, "Buyback Yield", i, s=0),
                get_data(stockdata, "Operating Cashflow", i, s=0),
                get_data(stockdata, "Revenue", i, s=0),
                get_data(stockdata, "Market Cap", i, s=0),
                get_data(stockdata, "3M Ratio", i, s=0),
                get_data(stockdata, "6M Ratio", i, s=0),
                get_data(stockdata, "1Y Ratio", i, s=0),
                get_data(stockdata, "3M Turnover", i, s=0),
                get_data(stockdata, "1Y Turnover", i, s=0),
                get_data(stockdata, "10D Turnover", i, s=0),
                get_data(stockdata, "3M Overheat", i, s=0),
                get_data(stockdata, "10D Overheat", i, s=0),
                get_data(stockdata, "3M Volatility", i, s=0),
                get_data(stockdata, "1Y Volatility", i, s=0),
                get_data(stockdata, "Buyback Yield", i, s=0),
                get_data(stockdata, "Interest Ratio", i, s=0),
                get_data(stockdata, "Debt Growth", i, s=-1),
                get_data(stockdata, "Insider Buy Ratio", i, s=0),
                get_data(stockdata, "ARP", i, s=-1),
                get_data(stockdata, "Depreciation Capex Ratio", i, s=0),
                get_data(stockdata, "Asset to Equity", i, s=0),
                get_data(stockdata, "Coverage Ratio", i, s=0),
                get_data(stockdata, "NCAV", i, s=0),
                get_data(stockdata, "Current Ratio", i, s=0),
                get_data(stockdata, "ROC", i, s=0),
                get_data(stockdata, "GPTOA", i, s=0),
                get_data(stockdata, "Asset Turnover", i, s=0),
                get_data(stockdata, "PFCR", i, s=1),
                get_data(stockdata, "Buyback to Income", i, s=1),
                get_data(stockdata, "Dividend to Income", i, s=1),
                get_data(stockdata, "Finalscore", i, s=0),
                get_data(stockdata, "Vscore", i, s=0),
                get_data(stockdata, "Mscore", i, s=0),
                get_data(stockdata, "EQC", i, s=0),
                get_data(stockdata, "reliablity", i, s=0),
                get_data(stockdata, "Quant score", i, s=0),
            ]
        )
    standard_data = pd.DataFrame(
        standard_data,
        columns=[
            "Top",
            "PER",
            "PBR",
            "PSR",
            "PCR",
            "PEGR",
            "EV/EBITDA",
            "EV/Revenue",
            "ROE",
            "ROA",
            "EPSgrowth",
            "Revenuegrowth",
            "Insiderpercent",
            "Institutionpercent",
            "Debt to Equity",
            "EPS",
            "Net Income",
            "Dividend Yield",
            "Buyback Yield",
            "Operating Cashflow",
            "Revenue",
            "Market Cap",
            "3M Ratio",
            "6M Ratio",
            "1Y Ratio",
            "3M Turnover",
            "1Y Turnover",
            "10D Turnover",
            "3M Overheat",
            "10D Overheat",
            "3M Volatility",
            "1Y Volatility",
            "Buyback Yield",
            "Interest Ratio",
            "Debt Growth",
            "Insider Buy Ratio",
            "ARP",
            "Depreciation Capex Ratio",
            "Asset to Equity",
            "Coverage Ratio",
            "NCAV",
            "Current Ratio",
            "ROC",
            "GPTOA",
            "Asset Turnover",
            "PFCR",
            "Buyback to Income",
            "Dividend to Income",
            "Finalscore",
            "Vscore",
            "Mscore",
            "EQC",
            "reliablity",
            "Quant score",
        ],
    )
    sectors = stockdata["Sector"].unique()

    sector_standard_data = {}

    for sector in sectors:
        sector_data = stockdata[stockdata["Sector"] == sector]
        sector_data_list = []
        for i in range(10, 100, 10):
            sector_data_list.append(
                [
                    get_data(sector_data, "PER", i, s=1),
                    get_data(sector_data, "PBR", i, s=1),
                    get_data(sector_data, "PSR", i, s=1),
                    get_data(sector_data, "PCR", i, s=1),
                    get_data(sector_data, "PEGR", i, s=1),
                    get_data(sector_data, "EV/EBITDA", i, s=1),
                    get_data(sector_data, "EV/Revenue", i, s=1),
                    get_data(sector_data, "ROE", i, s=0),
                    get_data(sector_data, "ROA", i, s=0),
                    get_data(sector_data, "EPSgrowth", i, s=0),
                    get_data(sector_data, "Revenuegrowth", i, s=0),
                    get_data(sector_data, "Insiderpercent", i, s=0),
                    get_data(sector_data, "Institutionpercent", i, s=0),
                    get_data(sector_data, "Debt to Equity", i, s=0),
                    get_data(sector_data, "EPS", i, s=0),
                    get_data(sector_data, "Net Income", i, s=0),
                    get_data(sector_data, "Dividend Yield", i, s=0),
                    get_data(sector_data, "Buyback Yield", i, s=0),
                    get_data(sector_data, "Operating Cashflow", i, s=0),
                    get_data(sector_data, "Revenue", i, s=0),
                    get_data(sector_data, "Market Cap", i, s=0),
                    get_data(sector_data, "3M Ratio", i, s=0),
                    get_data(sector_data, "6M Ratio", i, s=0),
                    get_data(sector_data, "1Y Ratio", i, s=0),
                    get_data(sector_data, "3M Turnover", i, s=0),
                    get_data(sector_data, "1Y Turnover", i, s=0),
                    get_data(sector_data, "10D Turnover", i, s=0),
                    get_data(sector_data, "3M Overheat", i, s=0),
                    get_data(sector_data, "10D Overheat", i, s=0),
                    get_data(sector_data, "3M Volatility", i, s=0),
                    get_data(sector_data, "1Y Volatility", i, s=0),
                    get_data(sector_data, "Buyback Yield", i, s=0),
                    get_data(sector_data, "Interest Ratio", i, s=0),
                    get_data(sector_data, "Debt Growth", i, s=-1),
                    get_data(sector_data, "Insider Buy Ratio", i, s=0),
                    get_data(sector_data, "ARP", i, s=-1),
                    get_data(sector_data, "Depreciation Capex Ratio", i, s=0),
                    get_data(sector_data, "Asset to Equity", i, s=0),
                    get_data(sector_data, "Coverage Ratio", i, s=0),
                    get_data(sector_data, "NCAV", i, s=0),
                    get_data(sector_data, "Current Ratio", i, s=0),
                    get_data(sector_data, "ROC", i, s=0),
                    get_data(sector_data, "GPTOA", i, s=0),
                    get_data(sector_data, "Asset Turnover", i, s=0),
                    get_data(sector_data, "PFCR", i, s=1),
                    get_data(sector_data, "Buyback to Income", i, s=1),
                    get_data(sector_data, "Dividend to Income", i, s=1),
                    get_data(sector_data, "Finalscore", i, s=0),
                    get_data(sector_data, "Vscore", i, s=0),
                    get_data(sector_data, "Mscore", i, s=0),
                    get_data(sector_data, "EQC", i, s=0),
                    get_data(sector_data, "reliablity", i, s=0),
                    get_data(sector_data, "Quant score", i, s=0),
                ]
            )
        sector_standard_data[sector] = pd.DataFrame(
            sector_data_list,
            columns=[
                "PER",
                "PBR",
                "PSR",
                "PCR",
                "PEGR",
                "EV/EBITDA",
                "EV/Revenue",
                "ROE",
                "ROA",
                "EPSgrowth",
                "Revenuegrowth",
                "Insiderpercent",
                "Institutionpercent",
                "Debt to Equity",
                "EPS",
                "Net Income",
                "Dividend Yield",
                "Buyback Yield",
                "Operating Cashflow",
                "Revenue",
                "Market Cap",
                "3M Ratio",
                "6M Ratio",
                "1Y Ratio",
                "3M Turnover",
                "1Y Turnover",
                "10D Turnover",
                "3M Overheat",
                "10D Overheat",
                "3M Volatility",
                "1Y Volatility",
                "Buyback Yield",
                "Interest Ratio",
                "Debt Growth",
                "Insider Buy Ratio",
                "ARP",
                "Depreciation Capex Ratio",
                "Asset to Equity",
                "Coverage Ratio",
                "NCAV",
                "Current Ratio",
                "ROC",
                "GPTOA",
                "Asset Turnover",
                "PFCR",
                "Buyback to Income",
                "Dividend to Income",
                "Finalscore",
                "Vscore",
                "Mscore",
                "EQC",
                "reliablity",
                "Quant score",
            ],
        )
    countries = stockdata["Country"].unique()
    country_standard_data = {}

    for country in countries:
        country_data = stockdata[stockdata["Country"] == country]
        country_data_list = []
        for i in range(10, 100, 10):
            country_data_list.append(
                [
                    get_data(country_data, "PER", i, s=1),
                    get_data(country_data, "PBR", i, s=1),
                    get_data(country_data, "PSR", i, s=1),
                    get_data(country_data, "PCR", i, s=1),
                    get_data(country_data, "PEGR", i, s=1),
                    get_data(country_data, "EV/EBITDA", i, s=1),
                    get_data(country_data, "EV/Revenue", i, s=1),
                    get_data(country_data, "ROE", i, s=0),
                    get_data(country_data, "ROA", i, s=0),
                    get_data(country_data, "EPSgrowth", i, s=0),
                    get_data(country_data, "Revenuegrowth", i, s=0),
                    get_data(country_data, "Insiderpercent", i, s=0),
                    get_data(country_data, "Institutionpercent", i, s=0),
                    get_data(country_data, "Debt to Equity", i, s=0),
                    get_data(country_data, "EPS", i, s=0),
                    get_data(country_data, "Net Income", i, s=0),
                    get_data(country_data, "Dividend Yield", i, s=0),
                    get_data(country_data, "Buyback Yield", i, s=0),
                    get_data(country_data, "Operating Cashflow", i, s=0),
                    get_data(country_data, "Revenue", i, s=0),
                    get_data(country_data, "Market Cap", i, s=0),
                    get_data(country_data, "3M Ratio", i, s=0),
                    get_data(country_data, "6M Ratio", i, s=0),
                    get_data(country_data, "1Y Ratio", i, s=0),
                    get_data(country_data, "3M Turnover", i, s=0),
                    get_data(country_data, "1Y Turnover", i, s=0),
                    get_data(country_data, "10D Turnover", i, s=0),
                    get_data(country_data, "3M Overheat", i, s=0),
                    get_data(country_data, "10D Overheat", i, s=0),
                    get_data(country_data, "3M Volatility", i, s=0),
                    get_data(country_data, "1Y Volatility", i, s=0),
                    get_data(country_data, "Buyback Yield", i, s=0),
                    get_data(country_data, "Interest Ratio", i, s=0),
                    get_data(country_data, "Debt Growth", i, s=-1),
                    get_data(country_data, "Insider Buy Ratio", i, s=0),
                    get_data(country_data, "ARP", i, s=-1),
                    get_data(country_data, "Depreciation Capex Ratio", i, s=0),
                    get_data(country_data, "Asset to Equity", i, s=0),
                    get_data(country_data, "Coverage Ratio", i, s=0),
                    get_data(country_data, "NCAV", i, s=0),
                    get_data(country_data, "Current Ratio", i, s=0),
                    get_data(country_data, "ROC", i, s=0),
                    get_data(country_data, "GPTOA", i, s=0),
                    get_data(country_data, "Asset Turnover", i, s=0),
                    get_data(country_data, "PFCR", i, s=1),
                    get_data(country_data, "Buyback to Income", i, s=1),
                    get_data(country_data, "Dividend to Income", i, s=1),
                    get_data(country_data, "Finalscore", i, s=0),
                    get_data(country_data, "Vscore", i, s=0),
                    get_data(country_data, "Mscore", i, s=0),
                    get_data(country_data, "EQC", i, s=0),
                    get_data(country_data, "reliablity", i, s=0),
                    get_data(country_data, "Quant score", i, s=0),
                ]
            )
        country_standard_data[country] = pd.DataFrame(
            country_data_list,
            columns=[
                "PER",
                "PBR",
                "PSR",
                "PCR",
                "PEGR",
                "EV/EBITDA",
                "EV/Revenue",
                "ROE",
                "ROA",
                "EPSgrowth",
                "Revenuegrowth",
                "Insiderpercent",
                "Institutionpercent",
                "Debt to Equity",
                "EPS",
                "Net Income",
                "Dividend Yield",
                "Buyback Yield",
                "Operating Cashflow",
                "Revenue",
                "Market Cap",
                "3M Ratio",
                "6M Ratio",
                "1Y Ratio",
                "3M Turnover",
                "1Y Turnover",
                "10D Turnover",
                "3M Overheat",
                "10D Overheat",
                "3M Volatility",
                "1Y Volatility",
                "Buyback Yield",
                "Interest Ratio",
                "Debt Growth",
                "Insider Buy Ratio",
                "ARP",
                "Depreciation Capex Ratio",
                "Asset to Equity",
                "Coverage Ratio",
                "NCAV",
                "Current Ratio",
                "ROC",
                "GPTOA",
                "Asset Turnover",
                "PFCR",
                "Buyback to Income",
                "Dividend to Income",
                "Finalscore",
                "Vscore",
                "Mscore",
                "EQC",
                "reliablity",
                "Quant score",
            ],
        )

    return standard_data, sector_standard_data, country_standard_data


def email_report(title, text, folder_path):
    """
    이 함수는 이메일로 보고서를 보내는 함수이다.
    """
    # Implement email sending functionality here
    msg = MIMEMultipart()
    msg["From"] = "ryugunlee@gmail.com"
    msg["To"] = "ryugunlee@gmail.com"
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
        server.login("ryugunlee@gmail.com", "wzfa elxq pzuc xdrz")
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
