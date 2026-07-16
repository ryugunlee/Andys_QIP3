"""FRED(세인트루이스 연준) 공식 API에서 매크로 시리즈를 내려받는다. FRED_API_KEY 필요.

과거에는 fredgraph.csv를 키 없이 크롤링했으나, 일부 네트워크(GitHub Codespaces
포함)에서 fred.stlouisfed.org가 응답하지 않는 문제가 있어(.claude/PROBLEMS.md #16
해결) 공식 REST API(api.stlouisfed.org)로 전환했다. 키는 .env의 FRED_API_KEY를
python-dotenv(collect_macro.py)로 읽는다.

CPIAUCSL(미 CPI 지수)은 원지수 대신 전년동월비(YoY %)로 변환해 저장한다
(us_cpi_yoy 지표의 정의가 인플레이션율이기 때문).
"""

import os
from datetime import date

import pandas as pd
import requests

from collection.constants import FRED_REQUEST_TIMEOUT_SECONDS, HISTORY_PERIOD_YEARS
from collection.macro.indicators import MacroSource, specs_by_source

FRED_OBSERVATIONS_URL: str = "https://api.stlouisfed.org/fred/series/observations"

# CPI YoY 계산용: 월별 시리즈에서 12개월 전 대비 변화율
_MONTHS_PER_YEAR: int = 12
_CPI_SERIES_INDICATOR_ID: str = "us_cpi_yoy"

_MACRO_COLUMNS: list[str] = ["indicator", "date", "value"]


def _fetch_fred_series(series_id: str, api_key: str, start: date) -> pd.Series | None:
    """시리즈 하나를 날짜 인덱스 Series로 반환한다. 실패하면 None."""
    try:
        response = requests.get(
            FRED_OBSERVATIONS_URL,
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": start.isoformat(),
            },
            timeout=FRED_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"[macro] 경고: FRED {series_id} 요청 실패({type(error).__name__}) — 건너뜀")
        return None

    observations = response.json().get("observations", [])
    if not observations:
        print(f"[macro] 경고: FRED {series_id} 응답이 비어 있음 — 건너뜀")
        return None

    frame = pd.DataFrame(observations)
    values = pd.to_numeric(frame["value"], errors="coerce")  # 결측치는 "."로 옴
    series = pd.Series(values.to_numpy(dtype=float), index=pd.to_datetime(frame["date"]), name=series_id)
    return series.dropna()


def fetch_fred_macro() -> pd.DataFrame:
    """FRED 소스 지표 전체를 (indicator, date, value) long DataFrame으로 반환한다."""
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        print("[macro] 경고: FRED_API_KEY 미설정 — FRED 지표 전체 건너뜀")
        return pd.DataFrame(columns=_MACRO_COLUMNS)

    today = date.today()
    # CPI YoY는 12개월 전 값이 필요하므로 1년 여유를 더 둔다
    start = today.replace(year=today.year - HISTORY_PERIOD_YEARS - 1)

    frames: list[pd.DataFrame] = []
    for spec in specs_by_source(MacroSource.FRED):
        if spec.symbol is None:
            continue
        series = _fetch_fred_series(spec.symbol, api_key, start)
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
