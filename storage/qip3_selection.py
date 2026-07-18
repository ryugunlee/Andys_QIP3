"""QIP3 5요인 점수 체계의 추천 종목 선별 (get_goodstock2).

기존 get_goodstock(report_export.py)과 병행하는 두 번째 선별기다. run 하나가 곧
시장 하나(KOSPI/KOSDAQ/NASDAQ/NYSE)이므로 "시장별 선별"이 run 단위로 자연히 구현된다.

선별 규칙 (QUANT2.md 6절):
1. 안정성(시장·섹터 블렌드) 하위 20%는 무조건 제외 — 생존 리스크 하드 필터.
2. 데이터 신뢰도 하한 통과 — 결측 중립 50점 누적으로 위장 진입하는 것 방지.
3. 남은 종목을 QIP3 종합점수로 정렬해 "시장 전체 종목 수"의 약 10%를 선별한다.
"""

import duckdb
import pandas as pd

import analysis.qip3_weights as w
from analysis.qip3_pipeline import QIP3_STABILITY_FILTER
from storage.report_export import get_run_snapshot

_QIP3_SCORE_COLUMN = "QIP3 Score"
_RELIABILITY_COLUMN = "reliability"


def get_goodstock2(conn: duckdb.DuckDBPyConnection, run_id: int) -> pd.DataFrame:
    """QIP3 선별 결과를 QIP3 종합점수 내림차순으로 반환한다.

    QIP3 점수가 아직 계산되지 않은(재점수 이전) DB면 빈 DataFrame을 돌려준다 —
    사이트는 해당 섹션을 우아하게 숨긴다.
    """
    df = get_run_snapshot(conn, run_id)
    if df.empty or _QIP3_SCORE_COLUMN not in df.columns:
        return pd.DataFrame()

    stability_cut = df[QIP3_STABILITY_FILTER].quantile(w.STABILITY_CUT_QUANTILE)
    survivors = df[
        (df[QIP3_STABILITY_FILTER] > stability_cut)
        & (df[_RELIABILITY_COLUMN] > w.RELIABILITY_THRESHOLD)
    ]

    pick_count = max(1, round(len(df) * w.SELECTION_RATIO))
    selected = survivors.nlargest(pick_count, _QIP3_SCORE_COLUMN)
    return selected.reset_index(drop=True)
