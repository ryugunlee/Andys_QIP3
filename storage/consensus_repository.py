"""애널리스트 컨센서스 추정치의 **관측일 이력**(`consensus_history`) 저장·조회.

왜 별도 테이블인가: `financial_statements`는 PK가
`(ticker, source, statement_type, period, item)`이라 같은 회계기간을 다시 수집하면
값을 **덮어쓴다**. 실적은 확정치라 덮어써도 무방하지만, 컨센서스는 시간에 따라
바뀌는 값이라 덮어쓰면 "3개월 전 추정치"가 영원히 사라진다 — 이익 모멘텀
(추정치 변화율)이 바로 그 사라진 값을 필요로 한다.

그래서 PK에 `observed_on`(관측일)을 넣어 append-only로 쌓는다. 하루에 여러 번
수집해도 같은 날짜면 덮어쓰므로 무한히 늘지 않는다.

미국(yfinance)은 `eps_trend`가 90일 전 추정치를 직접 주므로 이 테이블 없이도
이익 모멘텀이 계산된다. 한국은 현재 시점 추정치만 주기 때문에 이 테이블에
쌓기 시작한 뒤 3개월이 지나야 첫 값이 나온다.
"""

import duckdb
import pandas as pd

_CONSENSUS_TABLE = "consensus_history"
_CONSENSUS_COLUMNS: list[str] = [
    "ticker",
    "source",
    "observed_on",
    "fiscal_period",
    "item",
    "value",
]


def upsert_consensus_history(conn: duckdb.DuckDBPyConnection, rows: pd.DataFrame) -> None:
    """컨센서스 관측치를 upsert한다. 비어 있으면 아무 것도 하지 않는다."""
    if rows.empty:
        return

    payload = rows[_CONSENSUS_COLUMNS]
    conn.register("consensus_rows_view", payload)
    try:
        columns_clause = ", ".join(_CONSENSUS_COLUMNS)
        conn.execute(
            f"""
            INSERT INTO {_CONSENSUS_TABLE} ({columns_clause})
            SELECT {columns_clause} FROM consensus_rows_view
            ON CONFLICT (ticker, source, observed_on, fiscal_period, item)
            DO UPDATE SET value = excluded.value
            """
        )
    finally:
        conn.unregister("consensus_rows_view")


def get_consensus_revisions(
    conn: duckdb.DuckDBPyConnection, item: str, lookback_days: int
) -> pd.DataFrame:
    """전 종목의 `lookback_days`일 전 대비 컨센서스 변화율(%)을 한 번에 계산한다.

    각 종목의 **가장 먼 미래 회계기간**(= 다음 연도 추정치)을 기준으로,
    최신 관측치와 `lookback_days`일 이전의 가장 가까운 관측치를 비교한다.

    반환: (ticker, consensus_revision). 비교할 과거 관측치가 없거나 기준 추정치가
    0 이하인 종목은 제외된다 — 적자 기업은 분모가 작은 음수라 변화율이 폭주해
    신호가 아니라 잡음이 되기 때문이다.
    """
    return conn.execute(
        f"""
        WITH target AS (
            SELECT ticker, MAX(fiscal_period) AS fiscal_period
            FROM {_CONSENSUS_TABLE}
            WHERE item = ?
            GROUP BY ticker
        ),
        observations AS (
            SELECT c.ticker, c.observed_on, c.value
            FROM {_CONSENSUS_TABLE} c
            JOIN target t
              ON c.ticker = t.ticker AND c.fiscal_period = t.fiscal_period
            WHERE c.item = ?
        ),
        latest AS (
            SELECT ticker, observed_on, value,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY observed_on DESC) AS rn
            FROM observations
        ),
        past AS (
            SELECT o.ticker, o.value,
                   ROW_NUMBER() OVER (PARTITION BY o.ticker ORDER BY o.observed_on DESC) AS rn
            FROM observations o
            JOIN latest l ON o.ticker = l.ticker AND l.rn = 1
            WHERE o.observed_on <= l.observed_on - INTERVAL '{lookback_days}' DAY
        )
        SELECT latest.ticker,
               (latest.value - past.value) / abs(past.value) * 100 AS consensus_revision
        FROM latest
        JOIN past ON latest.ticker = past.ticker AND past.rn = 1
        WHERE latest.rn = 1
          AND past.value > 0
        """,
        [item, item],
    ).fetchdf()
