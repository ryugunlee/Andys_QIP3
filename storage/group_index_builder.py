"""시가총액 가중 지수를 `price_daily` + `snapshot_factors`로부터 산출한다.

왜 직접 만드는가: 상대강도(종목 6개월 − 업종 6개월)에는 업종 기준점이 필요한데
외부 업종지수를 받아오는 경로가 없다. 반면 전 종목의 일봉과 수집 run별 시가총액은
이미 가지고 있으므로 지수를 우리가 만들 수 있다.

산출 순서:
1. 수집 run마다 `주식수 = Market Cap / Close`를 역산한다.
2. 각 거래일에 **그 날짜 이전 가장 최근 run의 주식수**를 붙인다(ASOF JOIN).
   미래 시가총액을 과거에 적용하지 않으므로 look-ahead가 없다.
   첫 run 이전 구간은 최초 run의 주식수를 소급 적용한다(그 이전은 알 방법이 없다).
3. 그룹(시장/섹터/산업)별로 `Σ(주식수 × 종가)`를 더하고 최초일을 1000으로 정규화한다.

전 종목 × 5년 일봉이면 수백만 행이라 파이썬 루프로는 감당이 안 된다 —
DuckDB 집계 쿼리 하나로 끝낸다.
"""

import duckdb
import pandas as pd

from storage.index_repository import (
    INDEX_BASE_VALUE,
    MIN_INDEX_MEMBERS,
    upsert_group_indices,
)

# (group_type, snapshot_factors의 컬럼명). market은 collection_runs에서 온다.
_GROUP_LEVELS: list[tuple[str, str]] = [
    ("market", "market"),
    ("sector", "Sector"),
    ("industry", "Industry"),
]

# 첫 run 이전 구간에 최초 run의 주식수를 소급 적용하기 위한 하한 날짜.
# ASOF JOIN이 항상 매칭되도록 최초 run의 유효 시작일을 이 값으로 낮춘다.
_EPOCH_DATE = "1900-01-01"


def _shares_by_run_sql() -> str:
    """수집 run별 주식수·그룹 라벨을 만드는 CTE.

    같은 run_date에 같은 종목이 두 번 들어오는 경우(재수집)는 최신 run_id만 남긴다.
    """
    return f"""
    runs AS (
        SELECT
            s.ticker,
            CAST(r.run_at AS DATE) AS run_date,
            r.run_id,
            s."Market Cap" / s."Close" AS shares,
            r.market AS market,
            s."Sector" AS sector,
            s."Industry" AS industry,
            ROW_NUMBER() OVER (
                PARTITION BY s.ticker, CAST(r.run_at AS DATE) ORDER BY r.run_id DESC
            ) AS run_rank
        FROM snapshot_factors s
        JOIN collection_runs r USING (run_id)
        WHERE s."Market Cap" > 0 AND s."Close" > 0
    ),
    deduped AS (
        SELECT * FROM runs WHERE run_rank = 1
    ),
    effective AS (
        SELECT
            ticker, shares, market, sector, industry,
            CASE
                WHEN ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY run_date) = 1
                THEN DATE '{_EPOCH_DATE}'
                ELSE run_date
            END AS effective_from
        FROM deduped
    )
    """


def _build_level(
    conn: duckdb.DuckDBPyConnection, group_type: str, group_column: str
) -> pd.DataFrame:
    """그룹 한 단계(market/sector/industry)의 지수 시계열을 만든다."""
    return conn.execute(
        f"""
        WITH {_shares_by_run_sql()},
        valued AS (
            SELECT
                e.{group_column} AS group_value,
                p.date AS date,
                SUM(e.shares * p.close) AS market_value,
                COUNT(*) AS member_count
            FROM price_daily p
            ASOF JOIN effective e
              ON p.ticker = e.ticker
             AND p.date >= e.effective_from
            WHERE e.{group_column} IS NOT NULL
              AND p.close > 0
            GROUP BY group_value, p.date
        ),
        sized AS (
            SELECT *,
                   MIN(member_count) OVER (PARTITION BY group_value) AS min_members
            FROM valued
        )
        SELECT
            '{group_type}' AS group_type,
            group_value,
            date,
            market_value
                / FIRST_VALUE(market_value) OVER (
                      PARTITION BY group_value ORDER BY date
                  )
                * {INDEX_BASE_VALUE} AS index_value,
            member_count
        FROM sized
        WHERE min_members >= {MIN_INDEX_MEMBERS}
        ORDER BY group_value, date
        """
    ).fetchdf()


def build_group_indices(conn: duckdb.DuckDBPyConnection) -> int:
    """시장/섹터/산업 지수를 모두 산출해 저장하고, 저장한 행 수를 반환한다.

    입력 데이터가 없으면(첫 실행 등) 조용히 0을 반환한다 — 지수는 부가 데이터라
    없다고 해서 수집·채점 전체를 실패시키지 않는다.
    """
    saved = 0
    for group_type, group_column in _GROUP_LEVELS:
        indices = _build_level(conn, group_type, group_column)
        if indices.empty:
            continue
        upsert_group_indices(conn, indices)
        saved += len(indices)
    return saved
