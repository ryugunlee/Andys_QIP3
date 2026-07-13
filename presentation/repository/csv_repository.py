"""StockRepository의 CSV 구현체.

Andys_QIP2.py 파이프라인이 저장한 시장별 CSV(qipinfos/{시장}stockdata2/...)를
통합해 표현용 모델로 변환한다. CSV 원문 컬럼명은 이 파일과 metrics.py만 안다.

파이프라인이 시장 단위로 실행되므로 일부 시장의 CSV가 없을 수 있다.
없는 시장은 경고만 출력하고 건너뛴다.
"""

from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

from presentation import config
from presentation.metrics import DETAIL_VALUE_COLUMNS
from presentation.models import SearchEntry, StockDetail, StockSummary

# Andys_QIP2.py의 저장 규칙과 일치해야 하는 경로 템플릿
_STOCKDATA_PATH = "{market}stockdata2/{market}stockdata.csv"
_GOODSTOCK_PATH = "{market}stockdata2/{market}goodstock.csv"

# 이 구현체가 참조하는 CSV 컬럼명 (분석 산출물의 원문 이름)
_COL_TICKER = "Ticker"
_COL_NAME = "Company Name"
_COL_SECTOR = "Sector"
_COL_INDUSTRY = "Industry"
_COL_COUNTRY = "Country"
_COL_MARKET_CAP = "Market Cap"
_COL_CLOSE = "Close"
_COL_RATIO_3M = "3M Ratio"
_COL_FINALSCORE = "Finalscore"
_COL_RELIABILITY = "reliablity"  # 분석 영역의 원문 표기(오탈자 포함)를 그대로 따른다

# 통합 시 추가하는 컬럼 (CSV에는 없고 이 구현체가 붙인다)
_COL_MARKET = "Market"


def _to_none(value: object) -> object:
    """pandas의 NaN/NaT를 None으로 바꾼다. 그 외 값은 그대로."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    return value


def _to_float(value: object) -> float | None:
    value = _to_none(value)
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_str(value: object) -> str | None:
    value = _to_none(value)
    return None if value is None else str(value)


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
            frame[_COL_MARKET] = market
            frames.append(frame)
            self._loaded_files.append(csv_path)
        if not frames:
            return pd.DataFrame(columns=[_COL_TICKER, _COL_MARKET])
        merged = pd.concat(frames, ignore_index=True)
        return merged.drop_duplicates(subset=_COL_TICKER, keep="first")

    def _all(self) -> pd.DataFrame:
        if self._all_stocks is None:
            self._all_stocks = self._load_markets(_STOCKDATA_PATH)
        return self._all_stocks

    def _good(self) -> pd.DataFrame:
        if self._good_stocks is None:
            good = self._load_markets(_GOODSTOCK_PATH)
            if _COL_FINALSCORE in good.columns:
                good = good.sort_values(by=_COL_FINALSCORE, ascending=False)
            self._good_stocks = good.reset_index(drop=True)
        return self._good_stocks

    # --- 내부: 행 -> 모델 변환 ---

    @staticmethod
    def _row_value(row: pd.Series, column: str) -> object:
        return _to_none(row[column]) if column in row.index else None

    def _to_summary(self, row: pd.Series) -> StockSummary:
        return StockSummary(
            ticker=str(row[_COL_TICKER]),
            name=_to_str(self._row_value(row, _COL_NAME)),
            market=str(row[_COL_MARKET]),
            sector=_to_str(self._row_value(row, _COL_SECTOR)),
            close=_to_float(self._row_value(row, _COL_CLOSE)),
            market_cap=_to_float(self._row_value(row, _COL_MARKET_CAP)),
            ratio_3m=_to_float(self._row_value(row, _COL_RATIO_3M)),
            final_score=_to_float(self._row_value(row, _COL_FINALSCORE)),
            reliability=_to_float(self._row_value(row, _COL_RELIABILITY)),
        )

    def _to_detail(self, row: pd.Series) -> StockDetail:
        values = {
            column: self._row_value(row, column) for column in DETAIL_VALUE_COLUMNS
        }
        return StockDetail(
            ticker=str(row[_COL_TICKER]),
            name=_to_str(self._row_value(row, _COL_NAME)),
            market=str(row[_COL_MARKET]),
            sector=_to_str(self._row_value(row, _COL_SECTOR)),
            industry=_to_str(self._row_value(row, _COL_INDUSTRY)),
            country=_to_str(self._row_value(row, _COL_COUNTRY)),
            close=_to_float(self._row_value(row, _COL_CLOSE)),
            market_cap=_to_float(self._row_value(row, _COL_MARKET_CAP)),
            values=values,
            qualitative=None,  # 정성 평가는 아직 분석 영역에 미구현
        )

    # --- StockRepository 계약 구현 ---

    def good_stocks(self, limit: int | None = None) -> list[StockSummary]:
        good = self._good()
        if limit is not None:
            good = good.head(limit)
        return [self._to_summary(row) for _, row in good.iterrows()]

    def top_by_market_cap(self, region: str, limit: int) -> list[StockSummary]:
        markets = config.KR_MARKETS if region == config.REGION_KR else config.US_MARKETS
        stocks = self._all()
        stocks = stocks[stocks[_COL_MARKET].isin(markets)]
        if _COL_MARKET_CAP not in stocks.columns:
            return []
        stocks = stocks.sort_values(by=_COL_MARKET_CAP, ascending=False).head(limit)
        return [self._to_summary(row) for _, row in stocks.iterrows()]

    def iter_stock_details(self) -> Iterator[StockDetail]:
        for _, row in self._all().iterrows():
            yield self._to_detail(row)

    def search_entries(self) -> list[SearchEntry]:
        entries: list[SearchEntry] = []
        for _, row in self._all().iterrows():
            entries.append(
                SearchEntry(
                    ticker=str(row[_COL_TICKER]),
                    name=_to_str(self._row_value(row, _COL_NAME)),
                    market=str(row[_COL_MARKET]),
                    sector=_to_str(self._row_value(row, _COL_SECTOR)),
                    final_score=_to_float(self._row_value(row, _COL_FINALSCORE)),
                    market_cap=_to_float(self._row_value(row, _COL_MARKET_CAP)),
                )
            )
        return entries

    def market_counts(self) -> dict[str, int]:
        stocks = self._all()
        if stocks.empty:
            return {}
        counts = stocks[_COL_MARKET].value_counts()
        return {market: int(counts[market]) for market in config.MARKETS if market in counts}

    def updated_date(self) -> str | None:
        self._all()  # 로드된 파일 목록 확보
        if not self._loaded_files:
            return None
        latest_mtime = max(path.stat().st_mtime for path in self._loaded_files)
        return datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d")
