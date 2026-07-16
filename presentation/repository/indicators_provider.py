"""세계 경제 지표 연결 지점: DuckDB(macro_daily)에서 최신값을 읽어 카드로 만든다.

collect_macro.py가 수집·저장한 지표를 collection/macro/indicators.py의 선언
순서대로 EconomicIndicator 리스트로 변환한다. DB 파일이 없거나 데이터가 비면
None을 반환한다 (= 메인 페이지에 "준비 중" 카드 — 기존 계약 유지).

change_pct 의미:
- 일반 지표(지수/환율/가격): 전일 대비 변화율(%)
- 단위가 %/%p인 지표(금리·괴리율·인플레이션): 전일 대비 차이(%p).
  비율 값의 상대 변화율은 오해를 부르기 때문이다 (예: 금리 4.5→4.6은 +0.1%p).
"""

import math
from pathlib import Path

import duckdb

from collection.macro.indicators import MACRO_INDICATORS
from presentation.models import EconomicIndicator
from storage.database import MACRO_DB_PATH
from storage.macro_repository import get_latest_macro_pairs

# 이 단위들은 값 자체가 비율이므로 전일 대비를 %p 차이로 계산한다
_POINT_DIFF_UNITS: tuple[str, ...] = ("%", "%p")


def _to_valid_float(value: object) -> float | None:
    if value is None:
        return None
    number = float(value)  # type: ignore[arg-type]
    return None if math.isnan(number) else number


def _change_pct(value: float, prev: float | None, unit: str) -> float | None:
    if prev is None:
        return None
    if unit in _POINT_DIFF_UNITS:
        return value - prev
    if prev == 0:
        return None
    return (value - prev) / prev * 100


def load_economic_indicators(
    db_path: str | Path = MACRO_DB_PATH,
) -> list[EconomicIndicator] | None:
    path = Path(db_path)
    if not path.exists():
        return None

    conn = duckdb.connect(str(path), read_only=True)
    try:
        pairs = get_latest_macro_pairs(conn)
    except duckdb.Error:
        return None  # macro_daily 테이블이 아직 없는 옛 DB 등
    finally:
        conn.close()
    if pairs.empty:
        return None

    latest_by_id = {str(row.indicator): row for row in pairs.itertuples()}
    cards: list[EconomicIndicator] = []
    for spec in MACRO_INDICATORS:  # 선언 순서 = 카드 표시 순서
        if not spec.show_card:
            continue  # 파생 계산용 보조 지표 (예: 달러/위안)
        row = latest_by_id.get(spec.id)
        if row is None:
            continue  # 미수집 지표(FRED 차단, ECOS 보류 등)는 카드 생략
        value = _to_valid_float(row.value)
        if value is None:
            continue
        cards.append(
            EconomicIndicator(
                name=spec.name_ko,
                value=value,
                unit=spec.unit,
                change_pct=_change_pct(value, _to_valid_float(row.prev_value), spec.unit),
                as_of=str(row.date)[:10],
            )
        )
    return cards or None
