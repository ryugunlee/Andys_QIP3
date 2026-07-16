"""점수만 재계산하는 진입점 (수집 없이).

가중치(analysis/weights.py)나 점수 방식이 바뀌었을 때, 이미 수집된 데이터로
통화권 DB의 점수를 다시 산출한다. 모집단·컬럼 규칙은 analysis/score_pipeline.py 참고.

사용법:
    python compute_scores.py [KR|US|ALL]   # 기본 ALL
"""

import sys

import storage
from analysis import (
    compute_group_summary,
    compute_scores,
    get_standard_data,
    score_output_columns,
)

_REGION_DB_PATHS: dict[str, str] = {
    "KR": storage.KR_STOCK_DB_PATH,
    "US": storage.US_STOCK_DB_PATH,
}


def rescore_db(region: str, db_path: str) -> None:
    conn = storage.connect(db_path)
    try:
        population = storage.get_latest_snapshots(conn)
        if population.empty:
            print(f"[scores] {region}: 스냅샷 데이터 없음 — 건너뜀 ({db_path})")
            return
        scored = compute_scores(population)
        new_columns = score_output_columns(scored, population.columns)
        storage.update_snapshot_scores(conn, scored[["run_id", "Ticker"] + new_columns])

        latest_run_id = int(scored["run_id"].max())
        standard_data, sector_standard_data, country_standard_data = get_standard_data(scored)
        storage.save_standard_cutlines(
            conn, latest_run_id, standard_data, sector_standard_data, country_standard_data
        )
        for group_type, group_column in (("sector", "Sector"), ("industry", "Industry")):
            storage.upsert_group_summary(
                conn, group_type, compute_group_summary(scored, group_column)
            )
        print(f"[scores] {region}: {len(scored):,}종목 재점수 완료 (점수 컬럼 {len(new_columns)}개)")
    finally:
        conn.close()


def main() -> None:
    region = (sys.argv[1] if len(sys.argv) > 1 else "ALL").upper()
    if region not in ("KR", "US", "ALL"):
        raise SystemExit(f"알 수 없는 지역: {region} (KR|US|ALL 중 하나)")
    for name, db_path in _REGION_DB_PATHS.items():
        if region in ("ALL", name):
            rescore_db(name, db_path)


if __name__ == "__main__":
    main()
