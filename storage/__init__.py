"""수집/분석 결과를 DuckDB에 저장하고 조회하는 계층.

CSV/txt 산출물을 대체한다. 스키마는 `database.py`에 정의되어 있다.
"""

from storage.database import (
    KR_STOCK_DB_PATH,
    MACRO_DB_PATH,
    US_STOCK_DB_PATH,
    connect,
    stock_db_path_for_market,
)
from storage.consensus_repository import get_consensus_revisions, upsert_consensus_history
from storage.financial_repository import get_financial_statements, upsert_financial_statements
from storage.group_index_builder import build_group_indices
from storage.index_repository import get_group_index, get_index_returns
from storage.group_summary_repository import get_group_summary, upsert_group_summary
from storage.macro_repository import (
    get_latest_macro_pairs,
    get_macro_history,
    upsert_macro_values,
)
from storage.news_repository import get_latest_news, prune_news, upsert_news
from storage.price_repository import get_price_history, upsert_price_history
from storage.qip4_inputs import attach_qip4_inputs
from storage.qualitative_repository import (
    get_latest_qualitative_grade,
    get_latest_qualitative_grades,
    upsert_qualitative_grade,
)
from storage.raw_repository import get_raw_latest, upsert_raw_latest
from storage.qip3_selection import get_goodstock2
from storage.qip4_selection import get_goodstock3
from storage.report_export import (
    get_goodstock,
    get_latest_snapshots,
)
from storage.snapshot_repository import (
    record_collection_run,
    save_snapshot_factors,
    save_standard_cutlines,
    update_snapshot_scores,
)

__all__ = [
    "KR_STOCK_DB_PATH",
    "US_STOCK_DB_PATH",
    "MACRO_DB_PATH",
    "stock_db_path_for_market",
    "connect",
    "upsert_price_history",
    "get_price_history",
    "upsert_macro_values",
    "get_macro_history",
    "get_latest_macro_pairs",
    "upsert_financial_statements",
    "get_financial_statements",
    "upsert_consensus_history",
    "get_consensus_revisions",
    "build_group_indices",
    "attach_qip4_inputs",
    "get_group_index",
    "get_index_returns",
    "upsert_raw_latest",
    "get_raw_latest",
    "record_collection_run",
    "save_snapshot_factors",
    "save_standard_cutlines",
    "update_snapshot_scores",
    "get_latest_snapshots",
    "upsert_group_summary",
    "get_group_summary",
    "get_goodstock",
    "get_goodstock2",
    "get_goodstock3",
    "upsert_news",
    "prune_news",
    "get_latest_news",
    "upsert_qualitative_grade",
    "get_latest_qualitative_grades",
    "get_latest_qualitative_grade",
]
