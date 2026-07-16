"""한국은행 ECOS(경제통계시스템) Open API에서 매크로 시리즈를 내려받는다. BOK_API_KEY 필요.

지표별 통계표코드(spec.symbol)·조회주기(spec.ecos_cycle)·통계항목코드
(spec.ecos_item_code)는 collection/macro/indicators.py의 스펙이 단일 소스다.
키는 .env의 BOK_API_KEY를 python-dotenv(collect_macro.py)로 읽는다.

901Y009(소비자물가지수, 2020=100 원지수)는 전년동월비(YoY %)로 변환해 저장한다
(kr_cpi_yoy 지표의 정의가 인플레이션율이기 때문 — fred_source.py의 us_cpi_yoy와 동일한 처리).
"""

import os
from datetime import date

import pandas as pd
import requests

from collection.constants import ECOS_REQUEST_TIMEOUT_SECONDS, HISTORY_PERIOD_YEARS
from collection.macro.indicators import MacroSource, specs_by_source

ECOS_STATISTIC_SEARCH_URL: str = "https://ecos.bok.or.kr/api/StatisticSearch"
_MAX_RESULT_ROWS: int = 10000  # 일간 6년치(~2,200행)보다 넉넉한 응답 건수 상한

# ECOS 조회주기별 TIME 필드 날짜 형식 (D=일간 YYYYMMDD, M=월간 YYYYMM)
_DATE_FORMAT_BY_CYCLE: dict[str, str] = {"D": "%Y%m%d", "M": "%Y%m"}

# 월간 원지수를 YoY(%)로 변환해야 하는 지표 (fred_source.py의 us_cpi_yoy와 동일한 처리)
_MONTHS_PER_YEAR: int = 12
_YOY_TRANSFORM_INDICATOR_IDS: frozenset[str] = frozenset({"kr_cpi_yoy"})

_MACRO_COLUMNS: list[str] = ["indicator", "date", "value"]


def _fetch_ecos_series(
    stat_code: str, item_code: str, cycle: str, api_key: str, start: date, end: date
) -> pd.Series | None:
    """시리즈 하나를 날짜 인덱스 Series로 반환한다. 실패하면 None."""
    date_format = _DATE_FORMAT_BY_CYCLE[cycle]
    url = (
        f"{ECOS_STATISTIC_SEARCH_URL}/{api_key}/json/kr/1/{_MAX_RESULT_ROWS}/"
        f"{stat_code}/{cycle}/{start.strftime(date_format)}/{end.strftime(date_format)}/{item_code}"
    )
    try:
        response = requests.get(url, timeout=ECOS_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"[macro] 경고: ECOS {stat_code} 요청 실패({type(error).__name__}) — 건너뜀")
        return None

    payload = response.json()
    result = payload.get("StatisticSearch")
    if result is None:
        message = payload.get("RESULT", {}).get("MESSAGE", "알 수 없는 오류")
        print(f"[macro] 경고: ECOS {stat_code} 응답 오류({message}) — 건너뜀")
        return None

    rows = result.get("row", [])
    if not rows:
        print(f"[macro] 경고: ECOS {stat_code} 응답이 비어 있음 — 건너뜀")
        return None

    frame = pd.DataFrame(rows)
    values = pd.to_numeric(frame["DATA_VALUE"], errors="coerce")
    series = pd.Series(
        values.to_numpy(dtype=float),
        index=pd.to_datetime(frame["TIME"], format=date_format),
        name=stat_code,
    )
    return series.dropna()


def fetch_ecos_macro() -> pd.DataFrame:
    """ECOS 소스 지표 전체를 (indicator, date, value) long DataFrame으로 반환한다."""
    api_key = os.getenv("BOK_API_KEY")
    if not api_key:
        print("[macro] 경고: BOK_API_KEY 미설정 — ECOS 지표 전체 건너뜀")
        return pd.DataFrame(columns=_MACRO_COLUMNS)

    today = date.today()
    # CPI YoY는 12개월 전 값이 필요하므로 1년 여유를 더 둔다
    start = today.replace(year=today.year - HISTORY_PERIOD_YEARS - 1)

    frames: list[pd.DataFrame] = []
    for spec in specs_by_source(MacroSource.ECOS):
        if spec.symbol is None or spec.ecos_cycle is None or spec.ecos_item_code is None:
            continue
        series = _fetch_ecos_series(spec.symbol, spec.ecos_item_code, spec.ecos_cycle, api_key, start, today)
        if series is None or series.empty:
            continue
        if spec.id in _YOY_TRANSFORM_INDICATOR_IDS:
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
