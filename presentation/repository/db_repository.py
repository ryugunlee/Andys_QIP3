"""StockRepository의 DuckDB 구현체 (현재 파이프라인의 기본 데이터 소스).

주식 DB는 통화권별로 2개(KR/US)로 나뉘어 있다 (storage/database.py 참고).
각 DB에서 시장별 **최신 run**의 스냅샷(snapshot_factors)을 읽어 통합한다.
행→모델 변환은 row_mapping에 위임한다.

- 추천 종목은 storage.report_export.get_goodstock을 재사용해 파이프라인과
  동일한 선별 기준(run 단위 Finalscore 상위 10% 등)을 유지한다.
- DB 파일이 없으면 경고 후 그 DB만 건너뛴다 (CSV 구현체의 결측 시장 처리와 동일한 태도).
- 사이트 생성은 읽기 전용이므로 read_only로 연결한다.
"""

from pathlib import Path
from typing import Callable, Iterator, Sequence

import duckdb
import pandas as pd

from presentation import config
from presentation.models import (
    GroupScore,
    PricePoint,
    SearchEntry,
    StockCharts,
    StockDetail,
    StockSummary,
)
from presentation.repository import row_mapping as rows
from presentation.repository.financial_series import annual_financials_from_df
from storage.database import KR_STOCK_DB_PATH, US_STOCK_DB_PATH
from storage.financial_repository import get_financial_statements
from storage.group_summary_repository import get_group_summary
from storage.price_repository import get_price_history
from storage.report_export import get_goodstock, get_run_snapshot

DEFAULT_STOCK_DB_PATHS: tuple[str, ...] = (KR_STOCK_DB_PATH, US_STOCK_DB_PATH)

# 그룹 요약(long format)에서 상대 점수·종합 중앙값의 기준이 되는 팩터
_GROUP_SCORE_FACTOR = "Finalscore"

_LATEST_RUNS_QUERY = """
    SELECT market, max(run_id) AS run_id, max(run_at) AS run_at
    FROM collection_runs
    GROUP BY market
    ORDER BY max(run_at) DESC
"""


class DuckDbStockRepository:
    """통화권별 주식 DB들에서 시장별 최신 run을 읽는 StockRepository 구현체."""

    def __init__(self, db_paths: Sequence[str | Path] = DEFAULT_STOCK_DB_PATHS):
        self._db_paths = [Path(path) for path in db_paths]
        self._warned_missing: set[Path] = set()
        self._all_stocks: pd.DataFrame | None = None
        self._good_stocks: pd.DataFrame | None = None
        # 차트용 종목별 시계열 조회는 종목 수만큼 반복되므로 DB 연결을 캐시한다.
        self._chart_conns: dict[Path, duckdb.DuckDBPyConnection] = {}

    # --- 내부: DB 접근 ---

    def _existing_paths(self) -> list[Path]:
        paths = []
        for path in self._db_paths:
            if path.exists():
                paths.append(path)
            elif path not in self._warned_missing:
                print(f"[presentation] 경고: DuckDB 없음 — {path}")
                self._warned_missing.add(path)
        return paths

    def _load_runs(
        self, loader: Callable[[duckdb.DuckDBPyConnection, int], pd.DataFrame]
    ) -> pd.DataFrame:
        """모든 주식 DB의 시장별 최신 run에 loader(conn, run_id)를 적용해 통합한다.

        같은 티커가 여러 시장 run에 있으면(예: KRX와 KOSPI를 둘 다 실행)
        최신 run의 행이 남는다 (run_at 내림차순 순회 + keep="first").
        """
        frames: list[pd.DataFrame] = []
        for path in self._existing_paths():
            conn = duckdb.connect(str(path), read_only=True)
            try:
                runs = conn.execute(_LATEST_RUNS_QUERY).fetchdf()
                for run in runs.itertuples():
                    frame = loader(conn, int(run.run_id))
                    if frame.empty:
                        continue
                    frame = frame.drop(columns=["run_id"], errors="ignore")
                    frame[rows.COL_MARKET] = run.market
                    frames.append(frame)
            finally:
                conn.close()
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

    def chart_bundle(self, ticker: str, market: str) -> StockCharts | None:
        path = Path(
            KR_STOCK_DB_PATH
            if config.is_korean_market_name(market)
            else US_STOCK_DB_PATH
        )
        if not path.exists():
            return None
        source = "naver" if config.is_korean_market_name(market) else "yahoo"
        conn = self._chart_conn(path)
        prices = self._price_points(get_price_history(conn, ticker))
        annual = annual_financials_from_df(
            get_financial_statements(conn, ticker, source), source
        )
        if not prices and not annual:
            return None
        return StockCharts(prices=prices, annual=annual)

    def _chart_conn(self, path: Path) -> duckdb.DuckDBPyConnection:
        conn = self._chart_conns.get(path)
        if conn is None:
            conn = duckdb.connect(str(path), read_only=True)
            self._chart_conns[path] = conn
        return conn

    @staticmethod
    def _price_points(prices: pd.DataFrame) -> list[PricePoint]:
        if prices.empty:
            return []
        points: list[PricePoint] = []
        for row in prices.itertuples(index=False):
            close = rows.to_float(row.close)
            if close is None:
                continue
            points.append(
                PricePoint(
                    date=pd.Timestamp(row.date).strftime("%Y-%m-%d"),
                    close=close,
                    volume=rows.to_float(getattr(row, "volume", None)),
                    foreign_rate=rows.to_float(getattr(row, "foreign_rate", None)),
                )
            )
        return points

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

    def group_scores(self, group_type: str) -> list[GroupScore]:
        scores: list[GroupScore] = []
        for path in self._existing_paths():
            region = self._region_for_path(path)
            conn = duckdb.connect(str(path), read_only=True)
            try:
                summary = get_group_summary(conn, group_type)
            finally:
                conn.close()
            if summary.empty:
                continue
            for group_value, rows_of_group in summary.groupby("group_value"):
                by_factor = rows_of_group.set_index("factor")
                scores.append(
                    GroupScore(
                        name=str(group_value),
                        region=region,
                        ticker_count=int(rows_of_group["ticker_count"].iloc[0]),
                        relative_score=self._relative_score(by_factor),
                        median_finalscore=self._median_of(by_factor, _GROUP_SCORE_FACTOR),
                        median_per=self._median_of(by_factor, "PER"),
                        median_roe=self._median_of(by_factor, "ROE"),
                        median_ratio_3m=self._median_of(by_factor, "3M Ratio"),
                    )
                )
        scores.sort(
            key=lambda score: score.relative_score if score.relative_score is not None else -1,
            reverse=True,
        )
        return scores

    @staticmethod
    def _region_for_path(path: Path) -> str:
        if path == Path(KR_STOCK_DB_PATH):
            return config.REGION_KR
        if path == Path(US_STOCK_DB_PATH):
            return config.REGION_US
        return path.stem  # 기본 경로가 아니면 파일명으로 표시

    @staticmethod
    def _median_of(by_factor: pd.DataFrame, factor: str) -> float | None:
        if factor not in by_factor.index:
            return None
        value = by_factor.loc[factor, "median_value"]
        return None if pd.isna(value) else float(value)

    @staticmethod
    def _relative_score(by_factor: pd.DataFrame) -> float | None:
        """그룹 간 상대 점수 = Finalscore 중앙값의 (퍼센타일 + 스탠다드) / 2."""
        if _GROUP_SCORE_FACTOR not in by_factor.index:
            return None
        row = by_factor.loc[_GROUP_SCORE_FACTOR]
        if pd.isna(row["score_s"]) or pd.isna(row["score_ss"]):
            return None
        return (float(row["score_s"]) + float(row["score_ss"])) / 2

    def updated_date(self) -> str | None:
        latest: pd.Timestamp | None = None
        for path in self._existing_paths():
            conn = duckdb.connect(str(path), read_only=True)
            try:
                value = conn.execute("SELECT max(run_at) FROM collection_runs").fetchone()[0]
            finally:
                conn.close()
            if value is not None:
                stamp = pd.Timestamp(value)
                latest = stamp if latest is None or stamp > latest else latest
        return latest.strftime("%Y-%m-%d") if latest is not None else None
