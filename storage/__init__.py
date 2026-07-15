"""수집/분석 결과를 DuckDB에 저장하고 조회하는 계층.

CSV/txt 산출물을 대체한다. 스키마는 `database.py`에 정의되어 있다.
"""

from storage.database import DEFAULT_DB_PATH, connect
from storage.financial_repository import get_financial_statements, upsert_financial_statements
from storage.price_repository import get_price_history, upsert_price_history
from storage.raw_repository import get_raw_latest, upsert_raw_latest
from storage.report_export import export_run_summary, get_goodstock, get_market_cutlines
from storage.snapshot_repository import (
    record_collection_run,
    save_snapshot_factors,
    save_standard_cutlines,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "connect",
    "upsert_price_history",
    "get_price_history",
    "upsert_financial_statements",
    "get_financial_statements",
    "upsert_raw_latest",
    "get_raw_latest",
    "record_collection_run",
    "save_snapshot_factors",
    "save_standard_cutlines",
    "export_run_summary",
    "get_goodstock",
    "get_market_cutlines",
]
