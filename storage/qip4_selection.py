"""QIP4 정량 규칙의 추천 종목 선별 (get_goodstock3).

기존 `get_goodstock`(1차)·`get_goodstock2`(QIP3)와 병행하는 세 번째 선별기다.
run 하나가 곧 시장 하나라 "시장별 선별"이 run 단위로 자연히 구현된다.

QIP3와 결정적으로 다른 점: **안정성이 분위수 컷이 아니라 절대 기준의 관문(Pass/Fail)**
이라는 것이다. 하위 20%를 자르는 게 아니라, 영업현금흐름이 계속 음수이거나 빚을
갚을 재원이 없는 기업을 **절대 기준으로** 떨어뜨린다. 시장이 전반적으로 부실해도
기준이 내려가지 않는다.

선별 규칙:
1. 안정성 관문 통과 (`QIP4 Stability Gate == "PASS"`).
2. 효율성 승수 > 0 — 경보 3개 이상이면 승수가 0이라 여기서 걸러진다.
3. 데이터 신뢰도 하한 통과 — 결측 중립 50점 누적으로 위장 진입하는 것 방지.
4. 남은 종목을 QIP4 종합점수로 정렬해 시장 전체 종목 수의 약 10%를 선별한다.
"""

import duckdb
import pandas as pd

import analysis.qip4_weights as w
from analysis.qip4_gate import (
    EFFICIENCY_MULTIPLIER_COLUMN,
    GATE_COLUMN,
    GATE_PASS,
)
from storage.report_export import get_run_snapshot

_QIP4_SCORE_COLUMN = "QIP4 Score"
_RELIABILITY_COLUMN = "reliability"


def get_goodstock3(conn: duckdb.DuckDBPyConnection, run_id: int) -> pd.DataFrame:
    """QIP4 선별 결과를 종합점수 내림차순으로 반환한다.

    QIP4 점수가 아직 계산되지 않은(재점수 이전) DB면 빈 DataFrame을 돌려준다 —
    사이트는 해당 섹션을 우아하게 숨긴다.
    """
    df = get_run_snapshot(conn, run_id)
    if df.empty or _QIP4_SCORE_COLUMN not in df.columns:
        return pd.DataFrame()

    survivors = df[
        (df[GATE_COLUMN] == GATE_PASS)
        & (pd.to_numeric(df[EFFICIENCY_MULTIPLIER_COLUMN], errors="coerce") > 0)
        & (df[_RELIABILITY_COLUMN] > w.RELIABILITY_THRESHOLD)
    ]

    pick_count = max(1, round(len(df) * w.SELECTION_RATIO))
    selected = survivors.nlargest(pick_count, _QIP4_SCORE_COLUMN)
    return selected.reset_index(drop=True)
