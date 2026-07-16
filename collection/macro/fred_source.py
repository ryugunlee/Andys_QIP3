"""FRED(fredgraph.csv)에서 매크로 시리즈를 내려받는다. API 키 불필요.

주의: fred.stlouisfed.org는 네트워크 환경(일부 클라우드 IP)에 따라 응답하지 않을 수
있다. 시리즈별로 실패를 경고로만 처리하고 나머지 수집을 계속한다 — 안정적으로
받으려면 FRED API 키 방식으로 전환할 수 있다 (API_REQUESTS.txt 참고).

CPIAUCSL(미 CPI 지수)은 원지수 대신 전년동월비(YoY %)로 변환해 저장한다
(us_cpi_yoy 지표의 정의가 인플레이션율이기 때문).
"""

import io
from datetime import date

import pandas as pd
import requests

from collection.constants import FRED_REQUEST_TIMEOUT_SECONDS, HISTORY_PERIOD_YEARS
from collection.macro.indicators import MacroSource, specs_by_source

FRED_CSV_URL: str = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_HEADERS: dict[str, str] = {"User-Agent": "Mozilla/5.0"}

# CPI YoY 계산용: 월별 시리즈에서 12개월 전 대비 변화율
_MONTHS_PER_YEAR: int = 12
_CPI_SERIES_INDICATOR_ID: str = "us_cpi_yoy"

_MACRO_COLUMNS: list[str] = ["indicator", "date", "value"]


def _fetch_fred_series(series_id: str, start: date) -> pd.Series | None:
    """시리즈 하나를 날짜 인덱스 Series로 반환한다. 실패하면 None."""
    try:
        response = requests.get(
            FRED_CSV_URL,
            params={"id": series_id, "cosd": start.isoformat()},
            headers=_HEADERS,
            timeout=FRED_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"[macro] 경고: FRED {series_id} 다운로드 실패({type(error).__name__}) — 건너뜀")
        return None
    frame = pd.read_csv(io.StringIO(response.text), na_values=".")
    if frame.empty or len(frame.columns) < 2:
        print(f"[macro] 경고: FRED {series_id} 응답이 비어 있음 — 건너뜀")
        return None
    date_column, value_column = frame.columns[0], frame.columns[1]
    series = pd.Series(
        frame[value_column].to_numpy(dtype=float),
        index=pd.to_datetime(frame[date_column]),
        name=series_id,
    )
    return series.dropna()


def fetch_fred_macro() -> pd.DataFrame:
    """FRED 소스 지표 전체를 (indicator, date, value) long DataFrame으로 반환한다."""
    today = date.today()
    # CPI YoY는 12개월 전 값이 필요하므로 1년 여유를 더 둔다
    start = today.replace(year=today.year - HISTORY_PERIOD_YEARS - 1)

    frames: list[pd.DataFrame] = []
    for spec in specs_by_source(MacroSource.FRED):
        if spec.symbol is None:
            continue
        series = _fetch_fred_series(spec.symbol, start)
        if series is None or series.empty:
            continue
        if spec.id == _CPI_SERIES_INDICATOR_ID:
            series = (series.pct_change(_MONTHS_PER_YEAR) * 100).dropna()
        frames.append(
            pd.DataFrame(
                {
                    "indicator": spec.id,
                    "date": pd.to_datetime(series.index).date,
                    "value": series.to_numpy(dtype=float),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=_MACRO_COLUMNS)
    return pd.concat(frames, ignore_index=True)
