"""정성 평가 주간 작업 — LLM을 부르지 않는 부분만.

    python qualitative_weekly.py [--ticker 005930] [--skip-prefetch] [--limit 30]

1. 재판정: qualitative/observations/*.json이 있는 종목(= 사람이 extract를 돌린 종목)을 전부 다시
   판정해 qualitative_grades에 저장한다. 점수는 그대로지만 ★ 플래그(6개월 수익률 vs 영업이익)가
   매주 바뀌고, 유효기한 판단의 기준일이 갱신된다. 상세 페이지 등급카드는 이 테이블을 읽는다.
2. 원문 미리 받기: QIP4 선별 종목(한국 시장) 중 종합점수 상위 N개의 사업보고서를 OpenDART에서
   받아 qualitative/sources/에 둔다. 나중에 `grade_qualitative.py extract <티커>`가 캐시를 바로 쓴다.
   미국(EDGAR)은 Actions 러너 IP가 차단돼 제외. DART_API_KEY가 없으면 이 단계만 건너뛴다.

전 종목에 정성 평가를 돌리지 않는다는 방침(DECISIONS.md 2026-09-16)에 따라, 토큰이 드는 채점은
사람이 종목을 골라 손으로 실행한다. 워크플로: .github/workflows/qualitative-weekly.yml
"""

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

import storage
from analysis.qualitative import OBSERVATIONS_DIR
from collection.qualitative.dart_source import DartError, fetch_dart_report
from collection.qualitative.sources import save_source_text
from collection.qualitative.tiers import TIER_QUICK, TIERS
from collection.tickers import is_korean_listed_ticker
from grade_qualitative import cached_source, grade_ticker

load_dotenv()

DEFAULT_PREFETCH_LIMIT: int = 30
_QIP4_SCORE_COLUMN: str = "QIP4 Score"
_TICKER_COLUMN: str = "Ticker"
_LATEST_RUNS_QUERY: str = "SELECT market, max(run_id) AS run_id FROM collection_runs GROUP BY market"


def observed_tickers() -> list[str]:
    return sorted(path.stem for path in OBSERVATIONS_DIR.glob("*.json"))


def regrade(tickers: list[str]) -> None:
    for ticker in tickers:
        print(f"\n=== {ticker} ===")
        print(grade_ticker(ticker, market=None, save=True))


def selected_korean_tickers(limit: int) -> list[str]:
    """KR DB의 시장별 최신 run에서 QIP4 선별 종목을 모아 종합점수 상위 limit개."""
    db_path = storage.KR_STOCK_DB_PATH
    if not os.path.exists(db_path):
        print(f"[weekly] KR DB 없음({db_path}) — 원문 미리 받기 생략")
        return []
    conn = storage.connect(db_path)
    try:
        runs = conn.execute(_LATEST_RUNS_QUERY).fetchdf()
        frames = [storage.get_goodstock3(conn, int(run.run_id)) for run in runs.itertuples()]
    finally:
        conn.close()
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return []
    selected = pd.concat(frames, ignore_index=True).drop_duplicates(subset=_TICKER_COLUMN)
    selected = selected.sort_values(_QIP4_SCORE_COLUMN, ascending=False).head(limit)
    return [str(ticker) for ticker in selected[_TICKER_COLUMN] if is_korean_listed_ticker(str(ticker))]


def prefetch_sources(tickers: list[str]) -> None:
    if not os.getenv("DART_API_KEY"):
        print("[weekly] DART_API_KEY 없음 — 원문 미리 받기 생략")
        return
    sections = TIERS[TIER_QUICK].sections
    for ticker in tickers:
        if cached_source(ticker) is not None:
            continue  # 사업보고서는 연 1회라 이미 받아둔 것이면 충분하다
        try:
            document, meta = fetch_dart_report(ticker, sections)
        except DartError as error:
            print(f"[weekly] {ticker} 건너뜀 — {error}")
            continue
        path = save_source_text(ticker, meta["rcept_dt"], document.text or "")
        print(f"[weekly] {ticker} {meta['report_nm']} → {path} ({meta['chars']:,}자)")


def main() -> None:
    parser = argparse.ArgumentParser(description="정성 평가 주간 작업 (LLM 미사용)")
    parser.add_argument("--ticker", default=None, help="이 종목만 재판정 (기본: 관측값이 있는 전 종목)")
    parser.add_argument("--skip-prefetch", action="store_true")
    parser.add_argument("--limit", type=int, default=DEFAULT_PREFETCH_LIMIT, help="미리 받을 종목 수")
    args = parser.parse_args()

    tickers = [args.ticker.strip()] if args.ticker and args.ticker.strip() else observed_tickers()
    if tickers:
        regrade(tickers)
    else:
        print("[weekly] 재판정할 관측값이 없다")
    if not args.skip_prefetch:
        prefetch_sources(selected_korean_tickers(args.limit))


if __name__ == "__main__":
    main()
