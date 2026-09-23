"""시장 수집 실행(run)의 단계별 조립 — 진입점들이 공유하는 파이프라인 계층.

`Andys_QIP2.py`(전체 실행), `collect_chunk.py`(조각 수집), `finalize_run.py`(확정·채점)가
모두 이 패키지의 같은 함수를 쓴다. 단계를 한 곳에만 두어 진입점이 늘어도 순서·규칙이
갈라지지 않게 하는 것이 목적이다.
"""

from pipeline.market_run import (
    collect_market,
    curated_columns_only,
    PartialRunError,
    finalize_run,
    persist_ticker_data,
    record_snapshot,
    report_run,
    run_market,
    source_for_market,
)

__all__ = [
    "collect_market",
    "curated_columns_only",
    "PartialRunError",
    "finalize_run",
    "persist_ticker_data",
    "record_snapshot",
    "report_run",
    "run_market",
    "source_for_market",
]
