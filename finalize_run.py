"""조각 수집 결과를 하나의 run으로 확정하고 채점하는 진입점 (분할 수집의 마지막 단계).

`collect_chunk.py`가 남긴 조각 파일을 전부 읽어 합친 뒤, **여기서 처음으로**
`collection_runs` 행을 만들고 스냅샷을 저장한다. 그래서 조각 job이 중간에 실패하면
run 자체가 생기지 않고, 사이트는 지난주의 정상 run을 계속 쓴다
(`.claude/PROBLEMS.md` #42).

이후 단계는 전체 수집과 완전히 같다 — 지수 갱신 → 채점 → 커트라인 → 그룹요약
(`pipeline/market_run.py`의 `finalize_run`).

사용법:
    python finalize_run.py KOSDAQ [--chunk-dir qipinfos/chunks]
"""

import argparse
import sys
from pathlib import Path

import storage
from pipeline import finalize_run, record_snapshot, report_run, source_for_market
from pipeline.chunk_store import read_chunks

DEFAULT_CHUNK_DIR = Path("qipinfos/chunks")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="조각 수집 결과를 합쳐 하나의 run으로 저장하고 채점한다."
    )
    parser.add_argument("market", help="시장 이름 (예: KOSDAQ)")
    parser.add_argument(
        "--chunk-dir",
        type=Path,
        default=DEFAULT_CHUNK_DIR,
        help=f"조각 결과가 있는 폴더 (기본값: {DEFAULT_CHUNK_DIR})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    market = args.market.upper()

    try:
        stockdata, error_tickers = read_chunks(args.chunk_dir, market)
    except FileNotFoundError as error:
        # 조각이 없으면 "성공한 빈 run"을 만드는 대신 실패로 끝낸다 — 빈 run이 그 시장의
        # 최신 run이 되면 사이트에서 종목이 통째로 사라진다.
        sys.exit(f"[finalize_run] 오류: {error}")

    if stockdata.empty:
        sys.exit("[finalize_run] 오류: 조각을 합쳤지만 수집된 종목이 0건입니다.")

    conn = storage.connect(storage.stock_db_path_for_market(market))
    try:
        run_id = record_snapshot(
            conn, market, source_for_market(market), stockdata, error_tickers
        )
        print(f"[finalize_run] {market} run {run_id} 기록 — {len(stockdata)}종목")
        scored = finalize_run(conn, run_id)
        report_run(conn, run_id, scored, len(stockdata))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
