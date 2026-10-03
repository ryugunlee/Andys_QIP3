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
4. 남은 종목(생존 종목)을 QIP4 종합점수로 정렬해 **생존 종목 수의** 10%를 선별한다.

4번의 분모가 시장 전체가 아니라 생존 종목인 이유: 보유 판단 구간(생존 종목 상위 20%,
`presentation/holding_ranks.py`)과 같은 모집단을 써야 "선별 ⊂ 보유 구간"이 보장된다.
시장 전체 10%로 뽑으면 생존 종목이 시장의 30~40%뿐이라 선별이 생존의 약 30%까지 내려가,
"사라"면서 "보유할 위치가 아니다"라고 말하는 종목이 생긴다(2026-10-03, DECISIONS 참고).
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


def qip4_survivor_mask(df: pd.DataFrame) -> pd.Series:
    """선별 규칙 1~3(관문·효율성·신뢰도)을 통과한 행이면 True.

    선별(`get_goodstock3`)과 사이트의 보유 판단 목록(`presentation/holding_ranks.py`)이
    "생존 종목"을 같은 기준으로 세도록 이 한 곳에서만 정의한다.
    """
    return (
        (df[GATE_COLUMN] == GATE_PASS)
        & (pd.to_numeric(df[EFFICIENCY_MULTIPLIER_COLUMN], errors="coerce") > 0)
        & (pd.to_numeric(df[_RELIABILITY_COLUMN], errors="coerce") > w.RELIABILITY_THRESHOLD)
    )


def get_goodstock3(conn: duckdb.DuckDBPyConnection, run_id: int) -> pd.DataFrame:
    """QIP4 선별 결과를 종합점수 내림차순으로 반환한다.

    QIP4 점수가 아직 계산되지 않은(재점수 이전) DB면 빈 DataFrame을 돌려준다 —
    사이트는 해당 섹션을 우아하게 숨긴다.
    """
    df = get_run_snapshot(conn, run_id)
    if df.empty or _QIP4_SCORE_COLUMN not in df.columns:
        return pd.DataFrame()

    survivors = df[qip4_survivor_mask(df)]

    pick_count = max(1, round(len(survivors) * w.SELECTION_RATIO))
    selected = survivors.nlargest(pick_count, _QIP4_SCORE_COLUMN)
    return selected.reset_index(drop=True)
