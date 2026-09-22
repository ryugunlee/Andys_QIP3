"""시장 수집 실행(run)의 단계를 함수로 분리한다.

원래 `Andys_QIP2.py`의 `main()` 하나가 "수집 → 스냅샷 저장 → 지수 → 채점 → 커트라인 →
그룹요약"을 전부 했다. KOSDAQ처럼 한 job에 담기지 않는 시장을 조각내 수집하려면
**수집 단계와 확정 단계를 따로 부를 수 있어야** 해서 여기로 옮겼다
(`.claude/PROBLEMS.md` #42).

단계 구분과 호출 순서:

1. `collect_market(conn, market, tickers)` — 티커를 수집하고 종목별 일봉/재무제표/원본을
   DuckDB에 적재한다. **`collection_runs` 행을 만들지 않는다** — 조각 수집이 실패해도
   반쪽짜리 run이 DB에 남지 않게 하려는 의도적 분리다.
2. `record_snapshot(conn, market, source, stockdata, error_tickers)` — 이 시점에 비로소
   run 1건을 기록하고 curated 팩터를 스냅샷으로 저장한다. 조각 수집에서는 마지막
   확정 job이 조각들을 합친 표로 **한 번만** 부른다.
3. `finalize_run(conn, run_id)` — 시총가중 지수 → 채점 → 커트라인 → 그룹요약.

`run_market(market)`은 1~3을 이어 부르는 기존 동작(전체 수집)이다.
"""

import time
from datetime import date, datetime

import duckdb
import pandas as pd

import storage
from analysis import (
    compute_group_summary,
    compute_scores,
    get_standard_data,
    score_output_columns,
)
from collection import (
    get_naver_stock_information,
    get_stock_basic_infomation,
    get_tickers,
    is_korean_market,
    split_raw_and_curated,
)
from collection.stock_base import BaseStock

# 이 값을 넘는 종목만 "신뢰할 수 있는 데이터"로 세어 보고한다 (기존 main()의 기준).
RELIABILITY_REPORT_THRESHOLD: int = 50
# 리포트에 나열하는 추천 종목 티커 수 (기존 main()의 기준).
GOODSTOCK_PREVIEW_COUNT: int = 30

_RAW_COLUMN_PREFIX = "raw_"


def source_for_market(market: str) -> str:
    """시장 이름 → 수집 소스 이름 (`snapshot_factors`/`raw_latest`의 source 컬럼 값)."""
    return "naver" if is_korean_market(market) else "yahoo"


def persist_ticker_data(
    conn: duckdb.DuckDBPyConnection, stock: BaseStock, source: str
) -> None:
    """수집된 종목의 5년 일봉/재무제표/원본 데이터를 DuckDB에 저장한다.

    수집(collection)과 저장(storage) 계층을 분리하기 위해 basic_information의
    `on_ticker_collected` 콜백으로 전달된다.

    여기서 쓰는 테이블은 모두 **티커 키 upsert**라 run과 무관하다 — 그래서 조각 수집이
    여러 job으로 나뉘어도 그대로 누적되고, 확정 job이 run을 하나로 묶을 수 있다.
    """
    storage.upsert_price_history(conn, stock.ticker, source, stock.history)
    storage.upsert_financial_statements(conn, stock.to_financial_statement_rows())
    # 컨센서스는 재수집 때마다 값이 바뀌므로 관측일과 함께 따로 쌓는다
    # (financial_statements에 넣으면 덮어써져 과거 추정치가 사라진다).
    storage.upsert_consensus_history(conn, stock.to_consensus_rows(date.today()))
    raw_payload, _ = split_raw_and_curated(stock.to_row())
    storage.upsert_raw_latest(conn, stock.ticker, source, raw_payload)


def curated_columns_only(stockdata: pd.DataFrame) -> pd.DataFrame:
    """수집 결과에서 `raw_` 접두사 컬럼을 뺀 표.

    raw 원본은 `persist_ticker_data`가 이미 `raw_latest`에 넣었으므로 스냅샷에는
    curated 팩터만 들어간다.
    """
    columns = [
        column
        for column in stockdata.columns
        if not column.startswith(_RAW_COLUMN_PREFIX)
    ]
    return stockdata[columns]


def collect_market(
    conn: duckdb.DuckDBPyConnection, market: str, tickers: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    """티커 목록을 수집해 (수집 표, 실패 티커) 를 반환한다.

    한국 시장(KRX/KOSPI/KOSDAQ/KONEX)은 네이버증권, 그 외는 yfinance로 수집한다.
    """
    source = source_for_market(market)
    persist = lambda stock: persist_ticker_data(conn, stock, source)

    start_time = time.time()
    if is_korean_market(market):
        stockdata, error_tickers = get_naver_stock_information(
            tickers, on_ticker_collected=persist
        )
    else:
        stockdata, error_tickers = get_stock_basic_infomation(
            tickers, on_ticker_collected=persist
        )
    elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))

    print(f"Time taken to execute collection ({source}): {elapsed}")
    print("Basic stock information has been downloaded.")
    print("The number of searched stock: ", len(stockdata))
    return stockdata, error_tickers


def record_snapshot(
    conn: duckdb.DuckDBPyConnection,
    market: str,
    source: str,
    stockdata: pd.DataFrame,
    error_tickers: list[str],
) -> int:
    """run 1건을 기록하고 curated 팩터를 그 run의 스냅샷으로 저장한 뒤 run_id를 반환한다.

    **수집이 전부 끝난 뒤에 한 번만 부른다.** 조각 수집에서도 확정 job이 조각을 합친
    표로 한 번 부르므로, `collection_runs`의 의미("1 run = 완성된 시장 스냅샷 1개")가
    분할 실행에서도 그대로 유지된다.
    """
    run_id = storage.record_collection_run(
        conn, market, source, len(stockdata), error_tickers
    )
    storage.save_snapshot_factors(conn, run_id, curated_columns_only(stockdata))
    return run_id


def finalize_run(conn: duckdb.DuckDBPyConnection, run_id: int) -> pd.DataFrame:
    """지수 갱신 → 채점 → 커트라인 → 그룹요약까지 마치고 채점 결과를 반환한다.

    점수는 이 DB(통화권)의 시장별 최신 run 전체를 모집단으로 계산한다.
    (예: KOSPI 수집 직후라도 KOSDAQ 최신 run과 합쳐 한국 전체에서 점수를 냄)
    """
    # 시가총액 가중 지수(시장/섹터/산업)를 갱신한다. 스냅샷이 저장된 뒤여야
    # 이번 run의 시가총액이 주식수 역산에 반영되고, 상대강도가 이 지수를 쓰므로
    # 채점(compute_scores)보다 앞서야 한다.
    index_rows = storage.build_group_indices(conn)
    print(f"Group indices updated: {index_rows} rows")

    population = storage.get_latest_snapshots(conn)
    # 저장 대상 컬럼은 "compute_scores가 새로 만든 것"을 집합 차집합으로 정한다.
    # 상대강도·이익 모멘텀을 population에 먼저 붙이면 신규 컬럼으로 인식되지 않아
    # 영구히 저장되지 않으므로, 붙이기 전에 원래 컬럼 목록을 캡처해 둔다.
    snapshot_columns = list(population.columns)
    population = storage.attach_qip4_inputs(conn, population)
    scored = compute_scores(population)
    new_score_columns = score_output_columns(scored, snapshot_columns)
    storage.update_snapshot_scores(
        conn, scored[["run_id", "Ticker"] + new_score_columns]
    )

    standard_data, sector_standard_data, country_standard_data = get_standard_data(scored)
    storage.save_standard_cutlines(
        conn, run_id, standard_data, sector_standard_data, country_standard_data
    )

    # 섹터/산업 자체 평가 (그룹별 팩터 중앙값 + 그룹 간 상대 점수)
    for group_type, group_column in (("sector", "Sector"), ("industry", "Industry")):
        storage.upsert_group_summary(
            conn, group_type, compute_group_summary(scored, group_column)
        )
    return scored


def report_run(
    conn: duckdb.DuckDBPyConnection, run_id: int, scored: pd.DataFrame, searched: int
) -> None:
    """이번 run의 요약을 표준출력에 찍는다 (기존 main()의 리포트와 동일한 내용)."""
    this_run = scored[scored["run_id"] == run_id]
    reliable = int((this_run["reliability"] > RELIABILITY_REPORT_THRESHOLD).sum())
    print("The number of reliable stock: ", reliable)

    goodstock = storage.get_goodstock(conn, run_id)
    print(
        f"Date: {datetime.today().strftime('%Y-%m-%d')}\n"
        f"Number of searched stocks: {searched}\n"
        f"Number of reliable stocks: {reliable}\n"
        f"Number of good stocks: {len(goodstock)}\n"
        f"good stock tickerlist: \n"
        f"{goodstock['Ticker'].tolist()[:GOODSTOCK_PREVIEW_COUNT]}\n"
    )


def run_market(market: str) -> None:
    """한 시장을 통째로 수집·저장·채점한다 (`Andys_QIP2.py`의 기존 동작).

    산출물은 통화권별 DuckDB(qipinfos/andys_qip_kr.duckdb / andys_qip_us.duckdb)에 저장한다.
    """
    print(f"Date: {datetime.today().strftime('%Y-%m-%d')}")

    conn = storage.connect(storage.stock_db_path_for_market(market))
    try:
        stockdata, error_tickers = collect_market(conn, market, get_tickers(market))
        run_id = record_snapshot(
            conn, market, source_for_market(market), stockdata, error_tickers
        )
        scored = finalize_run(conn, run_id)
        report_run(conn, run_id, scored, len(stockdata))
    finally:
        conn.close()
