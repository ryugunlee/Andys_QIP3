"""StockRepository의 DuckDB 구현체 (현재 파이프라인의 기본 데이터 소스).

Andys_QIP2.py가 storage 패키지로 저장한 DuckDB에서 시장별 **최신 run**의
스냅샷(snapshot_factors)을 읽어 통합한다. 행→모델 변환은 row_mapping에 위임한다.

- 추천 종목은 storage.report_export.get_goodstock을 재사용해 파이프라인과
  동일한 선별 기준(run 단위 Finalscore 상위 10% 등)을 유지한다.
- DB 파일이 없으면 경고 후 빈 데이터로 동작한다 (CSV 구현체의 결측 시장 처리와 동일한 태도).
- 사이트 생성은 읽기 전용이므로 read_only로 연결한다.
"""

from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd

from presentation import config
from presentation.models import SearchEntry, StockDetail, StockSummary
from presentation.repository import row_mapping as rows
from storage.database import DEFAULT_DB_PATH
from storage.report_export import get_goodstock, get_run_snapshot


class DuckDbStockRepository:
    """qipinfos/andys_qip.duckdb에서 시장별 최신 run을 읽는 StockRepository 구현체."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._missing_warned = False
        self._latest_runs: pd.DataFrame | None = None
        self._all_stocks: pd.DataFrame | None = None
        self._good_stocks: pd.DataFrame | None = None

    # --- 내부: DB 접근 ---

    def _connect(self) -> duckdb.DuckDBPyConnection | None:
        if self._conn is None:
            if not self._db_path.exists():
                if not self._missing_warned:
                    print(f"[presentation] 경고: DuckDB 없음 — {self._db_path}")
                    self._missing_warned = True
                return None
            self._conn = duckdb.connect(str(self._db_path), read_only=True)
        return self._conn

    def _runs(self) -> pd.DataFrame:
        """시장별 최신 run (컬럼: market, run_id, run_at). 최신 실행 순으로 정렬."""
        if self._latest_runs is None:
            conn = self._connect()
            if conn is None:
                self._latest_runs = pd.DataFrame(columns=["market", "run_id", "run_at"])
            else:
                self._latest_runs = conn.execute(
                    """
                    SELECT market, max(run_id) AS run_id, max(run_at) AS run_at
                    FROM collection_runs
                    GROUP BY market
                    ORDER BY max(run_at) DESC
                    """
                ).fetchdf()
        return self._latest_runs

    def _load_runs(self, loader) -> pd.DataFrame:
        """시장별 최신 run에 loader(conn, run_id)를 적용해 통합한다.

        같은 티커가 여러 시장 run에 있으면(예: KRX와 KOSPI를 둘 다 실행)
        최신 run의 행이 남는다 (_runs()가 최신 순 정렬이므로 keep="first").
        """
        conn = self._connect()
        if conn is None:
            return pd.DataFrame(columns=[rows.COL_TICKER, rows.COL_MARKET])
        frames: list[pd.DataFrame] = []
        for run in self._runs().itertuples():
            frame = loader(conn, int(run.run_id))
            if frame.empty:
                continue
            frame = frame.drop(columns=["run_id"], errors="ignore")
            frame[rows.COL_MARKET] = run.market
            frames.append(frame)
        if not frames:
            return pd.DataFrame(columns=[rows.COL_TICKER, rows.COL_MARKET])
        merged = pd.concat(frames, ignore_index=True)
        return merged.drop_duplicates(subset=rows.COL_TICKER, keep="first")

    def _all(self) -> pd.DataFrame:
        if self._all_stocks is None:
            self._all_stocks = self._load_runs(get_run_snapshot)
        return self._all_stocks

    def _good(self) -> pd.DataFrame:
        if self._good_stocks is None:
            good = self._load_runs(get_goodstock)
            if rows.COL_FINALSCORE in good.columns:
                good = good.sort_values(by=rows.COL_FINALSCORE, ascending=False)
            self._good_stocks = good.reset_index(drop=True)
        return self._good_stocks

    # --- StockRepository 계약 구현 ---

    def good_stocks(self, limit: int | None = None) -> list[StockSummary]:
        good = self._good()
        if limit is not None:
            good = good.head(limit)
        return [rows.summary_from_row(row) for _, row in good.iterrows()]

    def top_by_market_cap(self, region: str, limit: int) -> list[StockSummary]:
        stocks = self._all()
        if stocks.empty or rows.COL_MARKET_CAP not in stocks.columns:
            return []
        is_kr = stocks[rows.COL_MARKET].map(config.is_korean_market_name)
        stocks = stocks[is_kr if region == config.REGION_KR else ~is_kr]
        stocks = stocks.sort_values(by=rows.COL_MARKET_CAP, ascending=False).head(limit)
        return [rows.summary_from_row(row) for _, row in stocks.iterrows()]

    def iter_stock_details(self) -> Iterator[StockDetail]:
        for _, row in self._all().iterrows():
            yield rows.detail_from_row(row)

    def search_entries(self) -> list[SearchEntry]:
        return [
            rows.search_entry_from_row(row) for _, row in self._all().iterrows()
        ]

    def market_counts(self) -> dict[str, int]:
        stocks = self._all()
        if stocks.empty:
            return {}
        counts = stocks[rows.COL_MARKET].value_counts()
        return {str(market): int(count) for market, count in counts.items()}

    def updated_date(self) -> str | None:
        runs = self._runs()
        if runs.empty:
            return None
        return pd.Timestamp(runs["run_at"].max()).strftime("%Y-%m-%d")
