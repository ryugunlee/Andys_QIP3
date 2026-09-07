"""DB에 쌓인 이력에서 QIP4 채점 입력 컬럼을 만들어 모집단에 붙인다.

수집 시점에 종목 하나만 보고는 만들 수 없고, **누적된 이력**이 있어야 나오는 값들이다:

- 상대강도 = 종목 6개월 수익률 − 업종지수 6개월 수익률.
  업종지수는 `group_index_daily`(자체 산출 시총가중 지수)에서 온다.
- 이익 모멘텀(한국) = 영업이익 컨센서스의 3개월 변화율.
  네이버는 과거 추정치를 주지 않아 `consensus_history`에 관측일과 함께 쌓아야 하고,
  **쌓기 시작한 뒤 3개월이 지나야 첫 값이 나온다.** 그전까지는 결측(중립 50)이다.
  미국은 `eps_trend`가 90일 전 값을 직접 줘서 수집 시점에 이미 채워져 있다.

**호출 시점 주의**: `compute_scores`가 만든 컬럼만 저장하도록
`score_output_columns(scored, population.columns)`가 집합 차집합을 쓴다. 여기서 붙인
컬럼이 `population.columns`에 들어가 있으면 "신규 컬럼"으로 인식되지 않아 **영구히
저장되지 않는다.** 그래서 호출부는 이 함수를 부르기 **전에** 원래 컬럼 목록을 캡처해
그것을 `score_output_columns`에 넘겨야 한다.
"""

import duckdb
import pandas as pd

import analysis.qip4_weights as w
from storage.consensus_repository import get_consensus_revisions
from storage.index_repository import get_index_returns

# 한국 컨센서스 이력에서 이익 모멘텀에 쓸 항목.
CONSENSUS_OPERATING_INCOME_ITEM: str = "영업이익"

RELATIVE_STRENGTH_COLUMN: str = "QIP4 Relative Strength"
EARNINGS_REVISION_COLUMN: str = "QIP4 Earnings Revision"

# 종목 6개월 수익률로 쓸 기존 curated 컬럼.
_STOCK_RETURN_COLUMN = "6M Ratio"
# 업종지수를 붙일 그룹 컬럼. 산업 단위가 종목과 가장 가깝다.
_GROUP_COLUMN = "Industry"
_INDEX_GROUP_TYPE = "industry"


def attach_qip4_inputs(
    conn: duckdb.DuckDBPyConnection, population: pd.DataFrame
) -> pd.DataFrame:
    """상대강도와 (한국) 이익 모멘텀을 붙인 복사본을 반환한다.

    필요한 이력이 없으면 해당 컬럼을 결측으로 남긴다 — 채점 엔진이 결측을 중립 50으로
    다루므로 지수나 컨센서스가 아직 없어도 파이프라인 전체가 멈추지 않는다.
    """
    population = population.copy()
    _attach_relative_strength(conn, population)
    _attach_earnings_revision(conn, population)
    return population


def _attach_relative_strength(
    conn: duckdb.DuckDBPyConnection, population: pd.DataFrame
) -> None:
    stock_return = pd.to_numeric(
        population.get(_STOCK_RETURN_COLUMN, pd.Series(dtype=float)), errors="coerce"
    )
    if stock_return.empty or _GROUP_COLUMN not in population.columns:
        population[RELATIVE_STRENGTH_COLUMN] = pd.NA
        return

    index_returns = get_index_returns(conn, w.RELATIVE_STRENGTH_LOOKBACK_DAYS)
    industry_returns = index_returns[index_returns["group_type"] == _INDEX_GROUP_TYPE]
    if industry_returns.empty:
        population[RELATIVE_STRENGTH_COLUMN] = pd.NA
        return

    lookup = dict(
        zip(industry_returns["group_value"], industry_returns["index_return"])
    )
    benchmark = population[_GROUP_COLUMN].map(lookup)
    population[RELATIVE_STRENGTH_COLUMN] = stock_return - benchmark


def _attach_earnings_revision(
    conn: duckdb.DuckDBPyConnection, population: pd.DataFrame
) -> None:
    if EARNINGS_REVISION_COLUMN not in population.columns:
        population[EARNINGS_REVISION_COLUMN] = pd.NA

    revisions = get_consensus_revisions(
        conn,
        CONSENSUS_OPERATING_INCOME_ITEM,
        w.EARNINGS_REVISION_LOOKBACK_DAYS,
    )
    if revisions.empty or "Ticker" not in population.columns:
        return

    lookup = dict(zip(revisions["ticker"], revisions["consensus_revision"]))
    from_history = population["Ticker"].map(lookup)
    # 야후 경로는 수집 시점에 이미 채워져 있다. 이력에서 나온 값은 **비어 있는 자리만**
    # 채운다 — 소스가 직접 준 값을 이력 기반 근사치로 덮어쓰지 않기 위해서다.
    population[EARNINGS_REVISION_COLUMN] = pd.to_numeric(
        population[EARNINGS_REVISION_COLUMN], errors="coerce"
    ).fillna(from_history)
