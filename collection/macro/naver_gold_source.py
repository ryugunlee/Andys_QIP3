"""KRX 금현물(원/g) 시세를 네이버 marketindex에서 수집한다.

네이버 클라이언트(collection/naver/client.py)의 스로틀/재시도를 재사용하고,
페이지네이션(최신부터)을 따라가며 히스토리를 모은다. 국제 금과의 괴리율 계산은
derived.py가 담당한다.
"""

import pandas as pd

from collection.constants import NAVER_GOLD_MAX_PAGES, NAVER_GOLD_PAGE_SIZE
from collection.macro.indicators import MacroSource, specs_by_source
from collection.naver.client import fetch_market_index_prices
from collection.naver.parsers import parse_number

_MACRO_COLUMNS: list[str] = ["indicator", "date", "value"]
_METALS_CATEGORY: str = "metals"


def _parse_rows(rows: list[dict], indicator_id: str) -> pd.DataFrame:
    records: list[dict] = []
    for row in rows:
        traded_at = row.get("localTradedAt")
        close_price = parse_number(row.get("closePrice"))
        if traded_at is None or close_price is None:
            continue
        records.append(
            {
                "indicator": indicator_id,
                "date": pd.Timestamp(traded_at).date(),
                "value": close_price,
            }
        )
    return pd.DataFrame(records, columns=_MACRO_COLUMNS)


def fetch_naver_gold_macro(max_pages: int = NAVER_GOLD_MAX_PAGES) -> pd.DataFrame:
    """NAVER_GOLD 소스 지표(KRX 금현물)의 일별 종가를 long DataFrame으로 반환한다."""
    frames: list[pd.DataFrame] = []
    for spec in specs_by_source(MacroSource.NAVER_GOLD):
        if spec.symbol is None:
            continue
        pages: list[pd.DataFrame] = []
        for page in range(1, max_pages + 1):
            rows = fetch_market_index_prices(
                _METALS_CATEGORY, spec.symbol, page, NAVER_GOLD_PAGE_SIZE
            )
            if rows is None:
                print(f"[macro] 경고: 네이버 금현물({spec.id}) {page}페이지 응답 실패 — 중단")
                break
            if not rows:
                break  # 히스토리 끝
            pages.append(_parse_rows(rows, spec.id))
            if len(rows) < NAVER_GOLD_PAGE_SIZE:
                break  # 마지막 페이지
        if pages:
            frames.append(pd.concat(pages, ignore_index=True))
        else:
            print(f"[macro] 경고: 네이버 금현물({spec.id}) 데이터 없음 — 건너뜀")
    if not frames:
        return pd.DataFrame(columns=_MACRO_COLUMNS)
    merged = pd.concat(frames, ignore_index=True)
    return merged.drop_duplicates(subset=["indicator", "date"], keep="first")
