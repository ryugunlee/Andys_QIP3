"""자체 산출 시가총액 가중 지수(`group_index_daily`) 저장·조회.

상대강도(종목 6개월 − 업종 6개월)의 기준점이 필요한데 외부 업종지수를 받아오는
경로가 없다. 대신 이미 가지고 있는 것으로 직접 만든다 — `price_daily`(일봉)와
`snapshot_factors`(수집 run별 시가총액·종가·섹터·산업).

산출 방식:
    주식수_i(t) = Market Cap_i / Close_i   (t 이전 가장 최근 run 기준)
    지수(t)     = Σ_i (주식수_i × 종가_i(t))  를 최초일 1000으로 정규화

주식수를 run마다 갱신하므로 증자·자사주 소각이 주 단위로 반영되고, 미래 시점의
시가총액을 과거에 적용하는 look-ahead가 생기지 않는다. 첫 run 이전 구간만은
최초 run의 주식수를 소급 적용한다(그 이전 시가총액을 알 방법이 없다).
"""

import duckdb
import pandas as pd

_INDEX_TABLE = "group_index_daily"
_INDEX_COLUMNS: list[str] = [
    "group_type",
    "group_value",
    "date",
    "index_value",
    "member_count",
]

# 지수 기준값. 절대 수준은 의미가 없고 구간 수익률만 쓰지만, 화면에 그대로 찍히므로
# 익숙한 1000을 기준으로 둔다.
INDEX_BASE_VALUE: float = 1000.0

# 이 수보다 적은 종목으로 만든 지수는 개별 종목 움직임과 구분되지 않아 저장하지 않는다.
# analysis/score_pipeline.py의 MIN_GROUP_POPULATION과 같은 취지의 문턱이다.
MIN_INDEX_MEMBERS: int = 5


def upsert_group_indices(conn: duckdb.DuckDBPyConnection, indices: pd.DataFrame) -> None:
    """지수 시계열을 upsert한다. 비어 있으면 아무 것도 하지 않는다."""
    if indices.empty:
        return

    rows = indices[_INDEX_COLUMNS]
    conn.register("index_rows_view", rows)
    try:
        columns_clause = ", ".join(_INDEX_COLUMNS)
        update_clause = ", ".join(
            f"{column}=excluded.{column}"
            for column in _INDEX_COLUMNS
            if column not in ("group_type", "group_value", "date")
        )
        conn.execute(
            f"""
            INSERT INTO {_INDEX_TABLE} ({columns_clause})
            SELECT {columns_clause} FROM index_rows_view
            ON CONFLICT (group_type, group_value, date)
            DO UPDATE SET {update_clause}
            """
        )
    finally:
        conn.unregister("index_rows_view")


def get_group_index(
    conn: duckdb.DuckDBPyConnection, group_type: str, group_value: str
) -> pd.DataFrame:
    """지수 하나의 전체 시계열을 날짜 오름차순으로 반환한다."""
    return conn.execute(
        f"SELECT * FROM {_INDEX_TABLE} WHERE group_type = ? AND group_value = ? ORDER BY date",
        [group_type, group_value],
    ).fetchdf()


def get_index_returns(
    conn: duckdb.DuckDBPyConnection, lookback_days: int
) -> pd.DataFrame:
    """모든 지수의 최근 `lookback_days` 거래일 구간 수익률(%)을 한 번에 계산한다.

    반환: (group_type, group_value, index_return) — 관측치가 부족한 지수는 제외된다.
    상대강도 계산이 종목 수천 개를 돌기 때문에 지수별 조회 대신 한 쿼리로 끝낸다.
    """
    return conn.execute(
        f"""
        WITH ranked AS (
            SELECT group_type, group_value, index_value,
                   ROW_NUMBER() OVER (
                       PARTITION BY group_type, group_value ORDER BY date DESC
                   ) AS days_ago
            FROM {_INDEX_TABLE}
        )
        SELECT latest.group_type,
               latest.group_value,
               (latest.index_value / past.index_value - 1) * 100 AS index_return
        FROM ranked AS latest
        JOIN ranked AS past
          ON latest.group_type = past.group_type
         AND latest.group_value = past.group_value
        WHERE latest.days_ago = 1
          AND past.days_ago = ?
          AND past.index_value > 0
        """,
        [lookback_days],
    ).fetchdf()
