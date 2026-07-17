"""수집 run의 스냅샷/추천 종목(goodstock)을 DB에서 조회한다."""

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
    df = df.rename(columns={"ticker": "Ticker"})
    # 하위호환: 오타 수정(reliablity→reliability) 이전에 수집된 DB는 옛 컬럼명을 갖는다.
    # 재수집 전까지 build_site가 크래시하지 않도록 읽기 경계에서 새 이름으로 정규화한다.
    # (재수집 후에는 새 컬럼이 이미 존재하므로 이 분기는 no-op)
    if "reliablity" in df.columns and "reliability" not in df.columns:
        df = df.rename(columns={"reliablity": "reliability"})
    return df


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
        & (df["reliability"] > GOODSTOCK_RELIABILITY_THRESHOLD)
        & (df["Quant score"] > GOODSTOCK_QUANT_SCORE_THRESHOLD)
        & (df["Fscore"] > GOODSTOCK_FSCORE_THRESHOLD)
    ]
    return goodstock.sort_values("Finalscore", ascending=False).reset_index(drop=True)
