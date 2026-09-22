"""시장 하나를 조각으로 나눠 그중 한 조각만 수집하는 진입점 (분할 수집).

KOSDAQ 1,820종목은 종목당 약 16초로 8시간이 넘어 GitHub 호스팅 러너의 작업 시간 상한
6시간을 넘는다. 그래서 워크플로가 조각을 **순차 job**으로 나눠 이 스크립트를 부르고,
마지막에 `finalize_run.py`가 조각을 합쳐 하나의 run으로 확정한다
(`.claude/PROBLEMS.md` #42).

이 스크립트는 **`collection_runs`에 행을 만들지 않는다.** 종목별 일봉/재무제표/원본만
DuckDB에 적재(티커 키 upsert)하고, curated 표는 조각 파일로 남긴다. 중간 조각이 실패해도
점수 없는 반쪽 run이 DB에 생기지 않게 하려는 의도적 분리다.

사용법:
    python collect_chunk.py KOSDAQ --chunk 2/4 [--chunk-dir qipinfos/chunks]
"""

import argparse
from pathlib import Path

import storage
from collection import chunk_tickers, get_tickers, parse_chunk_spec
from pipeline import collect_market
from pipeline.chunk_store import write_chunk

DEFAULT_CHUNK_DIR = Path("qipinfos/chunks")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="시장의 티커 목록을 조각내 그중 한 조각만 수집한다 (결과는 조각 파일로 남긴다)."
    )
    parser.add_argument("market", help="시장 이름 (예: KOSDAQ)")
    parser.add_argument(
        "--chunk",
        required=True,
        metavar="번호/전체",
        help="맡을 조각 (예: 2/4 — 4조각 중 두 번째)",
    )
    parser.add_argument(
        "--chunk-dir",
        type=Path,
        default=DEFAULT_CHUNK_DIR,
        help=f"조각 결과를 쓸 폴더 (기본값: {DEFAULT_CHUNK_DIR})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    market = args.market.upper()
    index, total = parse_chunk_spec(args.chunk)

    tickers = get_tickers(market)
    chunk = chunk_tickers(tickers, index, total)
    print(
        f"[collect_chunk] {market} 조각 {index}/{total} — 전체 {len(tickers)}종목 중 {len(chunk)}종목"
    )
    if not chunk:
        print("[collect_chunk] 이 조각에 배정된 종목이 없습니다 — 빈 조각으로 넘어갑니다.")

    conn = storage.connect(storage.stock_db_path_for_market(market))
    try:
        stockdata, error_tickers = collect_market(conn, market, chunk)
    finally:
        conn.close()

    path = write_chunk(
        args.chunk_dir, market, index, total, stockdata, error_tickers
    )
    print(f"[collect_chunk] 조각 결과 저장: {path} ({len(stockdata)}종목)")


if __name__ == "__main__":
    main()
