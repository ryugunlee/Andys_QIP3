"""이메일 첨부용 표를 DB에서 뽑아 임시 CSV로 만든다.

DuckDB가 단일 진실 공급원이므로, 이메일 발송 시점에만 필요한 파일을 만들고
CSV 자체는 영속 산출물로 취급하지 않는다.
"""

import os

import duckdb
import pandas as pd

GOODSTOCK_FINALSCORE_QUANTILE: float = 0.9
GOODSTOCK_RELIABILITY_THRESHOLD: float = 80
GOODSTOCK_QUANT_SCORE_THRESHOLD: float = 50
GOODSTOCK_FSCORE_THRESHOLD: float = 50


def get_run_snapshot(conn: duckdb.DuckDBPyConnection, run_id: int) -> pd.DataFrame:
    """해당 run의 전체 스냅샷(팩터+점수)을 DataFrame으로 반환한다."""
    df = conn.execute(
        "SELECT * FROM snapshot_factors WHERE run_id = ?", [run_id]
    ).fetchdf()
    return df.rename(columns={"ticker": "Ticker"})


def get_latest_snapshots(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """이 DB(통화권)의 시장별 최신 run 스냅샷을 통합해 반환한다 (run_id 컬럼 포함).

    점수 산출의 모집단이 된다. 같은 티커가 여러 시장 run에 있으면(예: KRX와
    KOSPI를 둘 다 실행) 최신 run의 행만 남긴다.
    """
    runs = conn.execute(
        """
        SELECT market, max(run_id) AS run_id
        FROM collection_runs
        GROUP BY market
        ORDER BY max(run_at) DESC
        """
    ).fetchdf()
    frames = [
        get_run_snapshot(conn, int(run.run_id)) for run in runs.itertuples()
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["run_id", "Ticker"])
    merged = pd.concat(frames, ignore_index=True)
    return merged.drop_duplicates(subset="Ticker", keep="first").reset_index(drop=True)


def get_goodstock(conn: duckdb.DuckDBPyConnection, run_id: int) -> pd.DataFrame:
    """기존 main()의 goodstock 필터(Finalscore 상위 10% & 신뢰도>80 & Quant score>50
    & Fscore>50)를 그대로 재현한다."""
    df = get_run_snapshot(conn, run_id)
    if df.empty:
        return df

    finalscore_threshold = df["Finalscore"].quantile(GOODSTOCK_FINALSCORE_QUANTILE)
    goodstock = df[
        (df["Finalscore"] > finalscore_threshold)
        & (df["reliablity"] > GOODSTOCK_RELIABILITY_THRESHOLD)
        & (df["Quant score"] > GOODSTOCK_QUANT_SCORE_THRESHOLD)
        & (df["Fscore"] > GOODSTOCK_FSCORE_THRESHOLD)
    ]
    return goodstock.sort_values("Finalscore", ascending=False).reset_index(drop=True)


def get_market_cutlines(conn: duckdb.DuckDBPyConnection, run_id: int) -> pd.DataFrame:
    """전체 시장 percentile 커트라인 표를 wide format으로 반환한다."""
    long_form = conn.execute(
        """
        SELECT row_label, factor, value FROM standard_cutlines
        WHERE run_id = ? AND scope = 'market'
        """,
        [run_id],
    ).fetchdf()
    if long_form.empty:
        return long_form
    return long_form.pivot(index="row_label", columns="factor", values="value").reset_index()


def export_run_summary(
    conn: duckdb.DuckDBPyConnection, run_id: int, output_dir: str
) -> list[str]:
    """이메일에 첨부할 stockdata/goodstock/standarddata CSV를 output_dir에 쓰고
    생성된 파일 경로 목록을 반환한다."""
    os.makedirs(output_dir, exist_ok=True)
    file_paths = []

    stockdata_path = os.path.join(output_dir, "stockdata.csv")
    get_run_snapshot(conn, run_id).to_csv(stockdata_path, index=False)
    file_paths.append(stockdata_path)

    goodstock_path = os.path.join(output_dir, "goodstock.csv")
    get_goodstock(conn, run_id).to_csv(goodstock_path, index=False)
    file_paths.append(goodstock_path)

    standarddata_path = os.path.join(output_dir, "standarddata.csv")
    get_market_cutlines(conn, run_id).to_csv(standarddata_path, index=False)
    file_paths.append(standarddata_path)

    return file_paths
