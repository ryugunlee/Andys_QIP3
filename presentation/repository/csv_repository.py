"""StockRepository의 CSV 구현체.

과거 파이프라인이 저장한 시장별 CSV(qipinfos/{시장}stockdata2/...)를 통합해
표현용 모델로 변환한다. 현재 파이프라인의 기본 산출물은 DuckDB이므로
(db_repository.DuckDbStockRepository 참고) 이 구현체는 CSV만 있는 환경의
폴백으로 유지한다. 행→모델 변환은 row_mapping에 위임한다.

파이프라인이 시장 단위로 실행되므로 일부 시장의 CSV가 없을 수 있다.
없는 시장은 경고만 출력하고 건너뛴다.
"""

from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

from presentation import config
from presentation.models import (
    GroupScore,
    SearchEntry,
    StockCharts,
    StockDetail,
    StockSummary,
)
from presentation.repository import row_mapping as rows

# Andys_QIP2.py의 과거 CSV 저장 규칙과 일치해야 하는 경로 템플릿
_STOCKDATA_PATH = "{market}stockdata2/{market}stockdata.csv"
_GOODSTOCK_PATH = "{market}stockdata2/{market}goodstock.csv"


class CsvStockRepository:
    """qipinfos/ 아래 시장별 CSV를 읽는 StockRepository 구현체."""

    def __init__(self, data_dir: Path = config.DEFAULT_DATA_DIR):
        self._data_dir = data_dir
        self._all_stocks: pd.DataFrame | None = None
        self._good_stocks: pd.DataFrame | None = None
        self._loaded_files: list[Path] = []

    # --- 내부: CSV 로드 ---

    def _load_markets(self, path_template: str) -> pd.DataFrame:
        """시장별 CSV를 통합한다. 없는 시장은 경고 후 건너뛴다."""
        frames: list[pd.DataFrame] = []
        for market in config.MARKETS:
            csv_path = self._data_dir / path_template.format(market=market)
            if not csv_path.exists():
                print(f"[presentation] 경고: {csv_path} 없음 — {market} 시장 건너뜀")
                continue
            frame = pd.read_csv(csv_path, low_memory=False)
            frame[rows.COL_MARKET] = market
            frames.append(frame)
            self._loaded_files.append(csv_path)
        if not frames:
            return pd.DataFrame(columns=[rows.COL_TICKER, rows.COL_MARKET])
        merged = pd.concat(frames, ignore_index=True)
        return merged.drop_duplicates(subset=rows.COL_TICKER, keep="first")

    def _all(self) -> pd.DataFrame:
        if self._all_stocks is None:
            self._all_stocks = self._load_markets(_STOCKDATA_PATH)
        return self._all_stocks

    def _good(self) -> pd.DataFrame:
        if self._good_stocks is None:
            good = self._load_markets(_GOODSTOCK_PATH)
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

    def qip3_stocks(self, limit: int | None = None) -> list[StockSummary]:
        """CSV 폴백에는 QIP3 점수 산출물이 없다 — QIP3 섹션은 표시되지 않는다."""
        return []

    def top_by_market_cap(self, region: str, limit: int) -> list[StockSummary]:
        stocks = self._all()
        if stocks.empty or rows.COL_MARKET_CAP not in stocks.columns:
            return []
        is_kr = stocks[rows.COL_MARKET].map(config.is_korean_market_name)
        stocks = stocks[is_kr if region == config.REGION_KR else ~is_kr]
        stocks = stocks.sort_values(by=rows.COL_MARKET_CAP, ascending=False).head(limit)
        return [rows.summary_from_row(row) for _, row in stocks.iterrows()]

    def chart_bundle(self, ticker: str, market: str) -> StockCharts | None:
        """CSV 폴백에는 일봉·재무제표 시계열이 없다 — 차트 섹션은 표시되지 않는다."""
        return None

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
        return {market: int(counts[market]) for market in config.MARKETS if market in counts}

    def group_scores(self, group_type: str) -> list[GroupScore]:
        """CSV 폴백에는 그룹 요약 산출물이 없다 — 섹터 페이지는 안내 카드를 보여준다."""
        return []

    def updated_date(self) -> str | None:
        self._all()  # 로드된 파일 목록 확보
        if not self._loaded_files:
            return None
        latest_mtime = max(path.stat().st_mtime for path in self._loaded_files)
        return datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d")
