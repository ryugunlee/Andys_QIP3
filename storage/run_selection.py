""""쓸 만큼 완전한 run"을 고르는 규칙 — 기록 단계와 조회 단계가 공유한다.

수집이 소스 쪽 차단·네트워크 장애로 중간에 막히면 종목 몇백 개만 담긴 run이 만들어진다.
그 run이 그 시장의 **최신 run**이 되면 `get_latest_snapshots`와 사이트 빌드가 그것만 보고,
나머지 수천 종목이 목록·추천·검색에서 조용히 사라진다. 2026-09-22 KOSPI 수집이 실제로
942종목 중 194종목만 담은 채 최신 run이 되어 한국 종목이 사이트에서 188개로 줄었다
(`.claude/PROBLEMS.md` #43, #28이 예고한 사고).

그래서 두 곳에서 같은 기준으로 막는다.

- **기록 단계**(`pipeline.record_snapshot`): 급감한 run은 애초에 기록하지 않는다.
- **조회 단계**(`get_latest_snapshots` / 사이트 빌드): 이미 들어와 있는 급감 run은 건너뛰고
  직전 정상 run으로 폴백한다. 기록 단계 가드가 없던 시절의 run과, 가드를 우회한 run
  (`--allow-partial`)까지 덮어 준다.

기준선을 "직전 run"이 아니라 **최근 몇 개 run의 최대치**로 잡는다 — 직전 run 자체가 반쪽이면
기준선도 같이 내려가 반쪽이 정상으로 굳어 버리기 때문이다(래칫 방지). 반대로 전체 이력의
최대치를 쓰면 상장폐지로 종목이 실제로 줄었을 때 영구히 기준을 못 넘으므로 창을 둔다.
"""

import duckdb
import pandas as pd

# 기준선 대비 이 비율 미만이면 "쓸 만큼 완전하지 않다"고 본다.
# 0.7은 상장/폐지·일시적 개별 실패(직전 실측 825~828/942 ≈ 0.88)는 통과시키고,
# 소스 차단 수준의 급감(194/942 ≈ 0.21)은 잡는 위치다.
COMPLETENESS_RATIO: float = 0.7

# 기준선을 계산할 때 볼 최근 run 개수 (그 시장 기준).
RECENT_RUNS_WINDOW: int = 5

# 기준선을 세울 이력이 아직 이만큼도 없으면 가드를 적용하지 않는다
# (최초 수집·신규 시장에서 "기준이 없어서 아무것도 못 넣는" 상태를 막는다).
MIN_RUNS_FOR_BASELINE: int = 1

_RUN_ROW_COUNTS_SQL = """
    SELECT
        r.market       AS market,
        r.run_id       AS run_id,
        r.run_at       AS run_at,
        count(s.ticker) AS row_count
    FROM collection_runs r
    LEFT JOIN snapshot_factors s ON s.run_id = r.run_id
    GROUP BY r.market, r.run_id, r.run_at
"""


def run_row_counts(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """run별 (market, run_id, run_at, row_count). row_count는 실제 스냅샷 행 수다.

    `collection_runs.ticker_count`가 아니라 스냅샷 행 수를 쓴다 — 사이트가 실제로 보게 되는
    양이 그것이고, 기록이 부분 실패한 경우 둘이 어긋날 수 있다.
    """
    return conn.execute(_RUN_ROW_COUNTS_SQL).fetchdf()


def completeness_baseline(conn: duckdb.DuckDBPyConnection, market: str) -> int | None:
    """그 시장의 기준선(최근 `RECENT_RUNS_WINDOW`개 run의 최대 행 수).

    기준선을 세울 run이 `MIN_RUNS_FOR_BASELINE`개 미만이면 None — 호출부는 가드를 건너뛴다.
    """
    counts = run_row_counts(conn)
    if counts.empty:
        return None
    market_runs = counts[counts["market"] == market].sort_values(
        "run_id", ascending=False
    )
    # 행이 0인 run(기록 도중 실패)은 기준선 계산에서 무의미하므로 뺀다.
    market_runs = market_runs[market_runs["row_count"] > 0]
    if len(market_runs) < MIN_RUNS_FOR_BASELINE:
        return None
    return int(market_runs.head(RECENT_RUNS_WINDOW)["row_count"].max())


def required_minimum(baseline: int) -> int:
    """기준선에서 나오는 최소 허용 종목 수."""
    return int(baseline * COMPLETENESS_RATIO)


def latest_complete_runs(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """시장별로 "쓸 만큼 완전한" 가장 최신 run 1건씩 (market, run_id, run_at).

    최신순 정렬(run_at 내림차순)은 호출부의 중복 티커 처리(keep="first")가 최신 run을
    남기도록 하는 기존 계약이므로 그대로 유지한다.

    급감 run이 전부 걸러져 그 시장에 쓸 run이 하나도 없으면 그 시장은 결과에서 빠진다 —
    반쪽 데이터로 사이트를 덮어쓰는 것보다 그 시장을 이번에 갱신하지 않는 편이 낫다.
    """
    counts = run_row_counts(conn)
    if counts.empty:
        return pd.DataFrame(columns=["market", "run_id", "run_at"])

    selected: list[pd.Series] = []
    for market, market_runs in counts.groupby("market"):
        usable = market_runs[market_runs["row_count"] > 0]
        if usable.empty:
            continue
        ordered = usable.sort_values("run_id", ascending=False)
        # 기준선은 그 시장의 최근 창 안 최대치. 창을 벗어난 옛 run과 비교하지 않는다.
        baseline = int(ordered.head(RECENT_RUNS_WINDOW)["row_count"].max())
        minimum = required_minimum(baseline)
        complete = ordered[ordered["row_count"] >= minimum]
        chosen = complete.iloc[0] if not complete.empty else ordered.iloc[0]
        if not complete.empty and int(chosen["run_id"]) != int(ordered.iloc[0]["run_id"]):
            skipped = ordered[ordered["run_id"] > chosen["run_id"]]
            print(
                f"[run_selection] {market}: 종목 수가 급감한 run "
                f"{skipped['run_id'].tolist()}을(를) 건너뛰고 run {int(chosen['run_id'])}"
                f"({int(chosen['row_count'])}종목)을 씁니다 "
                f"(기준선 {baseline} × {COMPLETENESS_RATIO} = {minimum} 미달)."
            )
        selected.append(chosen)

    result = pd.DataFrame(selected)[["market", "run_id", "run_at"]]
    return result.sort_values("run_at", ascending=False).reset_index(drop=True)
