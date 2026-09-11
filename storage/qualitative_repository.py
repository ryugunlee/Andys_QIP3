"""qualitative_grades 테이블 upsert/조회 (정성 등급 결과).

관측값(증거 인용 포함)은 DB가 아니라 `qualitative/observations/<티커>.json`에 git으로
추적한다 — 사람이 검토·수정한 이력이 diff로 남아야 재현성 검증이 되기 때문이다.
여기에는 판정 결과만 들어가고, 표현 계층이 상세 페이지에 쓴다.
(ticker, graded_on) 기준 upsert라 같은 날 재판정하면 덮어쓰고, 다른 날이면 이력이 쌓인다.
"""

import duckdb
import pandas as pd

_GRADE_COLUMNS: list[str] = [
    "ticker", "graded_on", "observed_asof", "sector_group", "axis_grades", "composite", "score",
    "multiplier", "decision", "veto_reasons", "cap_reasons", "watch_items",
    "not_investigated_share", "valid_until", "observations_path",
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
