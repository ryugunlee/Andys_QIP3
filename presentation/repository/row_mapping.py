"""분석 산출물의 한 행(row)을 표현용 모델로 바꾸는 공용 변환기.

CSV·DuckDB 등 저장 방식이 달라도 행의 컬럼 구성(분석 산출물 스키마)은 같으므로,
컬럼명 상수와 행→모델 변환은 이 파일에서만 정의한다. 각 구현체(csv_repository,
db_repository)는 데이터를 DataFrame으로 읽는 방법만 다르고 변환은 여기에 위임한다.
"""

import pandas as pd

from presentation.korean_names import display_name
from presentation.metrics import DETAIL_VALUE_COLUMNS
from presentation.models import SearchEntry, StockDetail, StockSummary

# 분석 산출물의 원문 컬럼명
COL_TICKER = "Ticker"
COL_NAME = "Company Name"
COL_SECTOR = "Sector"
COL_INDUSTRY = "Industry"
COL_COUNTRY = "Country"
COL_MARKET_CAP = "Market Cap"
COL_CLOSE = "Close"
COL_RATIO_3M = "3M Ratio"
COL_FINALSCORE = "Finalscore"
COL_RELIABILITY = "reliablity"  # 분석 영역의 원문 표기(오탈자 포함)를 그대로 따른다

# 시장 통합 시 구현체가 덧붙이는 컬럼 (산출물 원본에는 없음)
COL_MARKET = "Market"


def to_none(value: object) -> object:
    """pandas의 NaN/NaT를 None으로 바꾼다. 그 외 값은 그대로."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    return value


def to_float(value: object) -> float | None:
    value = to_none(value)
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def to_str(value: object) -> str | None:
    value = to_none(value)
    return None if value is None else str(value)


def row_value(row: pd.Series, column: str) -> object:
    return to_none(row[column]) if column in row.index else None


def _display_name(row: pd.Series) -> str | None:
    """한국 종목은 한글 보정명, 그 외는 원문 종목명을 반환한다."""
    return display_name(str(row[COL_TICKER]), to_str(row_value(row, COL_NAME)))


def summary_from_row(row: pd.Series) -> StockSummary:
    return StockSummary(
        ticker=str(row[COL_TICKER]),
        name=_display_name(row),
        market=str(row[COL_MARKET]),
        sector=to_str(row_value(row, COL_SECTOR)),
        close=to_float(row_value(row, COL_CLOSE)),
        market_cap=to_float(row_value(row, COL_MARKET_CAP)),
        ratio_3m=to_float(row_value(row, COL_RATIO_3M)),
        final_score=to_float(row_value(row, COL_FINALSCORE)),
        reliability=to_float(row_value(row, COL_RELIABILITY)),
    )


def detail_from_row(row: pd.Series) -> StockDetail:
    values = {column: row_value(row, column) for column in DETAIL_VALUE_COLUMNS}
    return StockDetail(
        ticker=str(row[COL_TICKER]),
        name=_display_name(row),
        market=str(row[COL_MARKET]),
        sector=to_str(row_value(row, COL_SECTOR)),
        industry=to_str(row_value(row, COL_INDUSTRY)),
        country=to_str(row_value(row, COL_COUNTRY)),
        close=to_float(row_value(row, COL_CLOSE)),
        market_cap=to_float(row_value(row, COL_MARKET_CAP)),
        values=values,
        qualitative=None,  # 정성 평가는 아직 분석 영역에 미구현
    )


def search_entry_from_row(row: pd.Series) -> SearchEntry:
    return SearchEntry(
        ticker=str(row[COL_TICKER]),
        name=_display_name(row),
        market=str(row[COL_MARKET]),
        sector=to_str(row_value(row, COL_SECTOR)),
        final_score=to_float(row_value(row, COL_FINALSCORE)),
        market_cap=to_float(row_value(row, COL_MARKET_CAP)),
    )
