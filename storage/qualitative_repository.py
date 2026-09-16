"""qualitative_grades 테이블 upsert/조회 (정성 등급 결과).

관측값(점수·근거·증거 인용)은 DB가 아니라 `qualitative/observations/<티커>.json`에 git으로
추적한다 — 사람이 검토·수정한 이력이 diff로 남아야 하기 때문이다. 여기에는 판정 결과만
들어가고, 표현 계층이 상세 페이지에 쓴다.
(ticker, graded_on) 기준 upsert라 같은 날 재판정하면 덮어쓰고, 다른 날이면 이력이 쌓인다.
"""

import duckdb
import pandas as pd

_GRADE_COLUMNS: list[str] = [
    "ticker", "graded_on", "observed_asof", "sector_group", "item_scores", "composite", "score",
    "multiplier", "decision", "veto_reasons", "cap_reasons", "watch_items", "valid_items",
    "trend_flag", "tier", "model", "valid_until", "observations_path",
]


def upsert_qualitative_grade(conn: duckdb.DuckDBPyConnection, row: dict) -> None:
    """등급 결과 한 행을 upsert한다. row는 _GRADE_COLUMNS 키를 모두 가져야 한다."""
    columns_clause = ", ".join(_GRADE_COLUMNS)
    placeholders = ", ".join("?" for _ in _GRADE_COLUMNS)
    updates = ", ".join(
        f"{column}=excluded.{column}" for column in _GRADE_COLUMNS if column not in ("ticker", "graded_on")
    )
    conn.execute(
        f"""
        INSERT INTO qualitative_grades ({columns_clause})
        VALUES ({placeholders})
        ON CONFLICT (ticker, graded_on) DO UPDATE SET {updates}
        """,
        [row[column] for column in _GRADE_COLUMNS],
    )


def get_latest_qualitative_grades(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """종목별 가장 최근 판정 한 행씩. 유효기간 판단은 표현 계층이 valid_until로 한다."""
    return conn.execute(
        """
        SELECT * FROM (
            SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY graded_on DESC) AS recency
            FROM qualitative_grades
        )
        WHERE recency = 1
        """
    ).fetchdf().drop(columns=["recency"])


def get_latest_qualitative_grade(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    """한 종목의 가장 최근 판정 행을 dict로. 없으면 None. 상세 페이지 등급카드용."""
    frame = conn.execute(
        "SELECT * FROM qualitative_grades WHERE ticker = ? ORDER BY graded_on DESC LIMIT 1", [ticker]
    ).fetchdf()
    if frame.empty:
        return None
    record = frame.iloc[0].to_dict()
    return {key: (None if pd.isna(value) else value) for key, value in record.items()}
