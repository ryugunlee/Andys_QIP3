#!/usr/bin/env bash
# 시장 수집 워크플로들을 하나씩 실행하고 각각이 끝날 때까지 기다린다.
# `collect-all-markets.yml`이 부른다. MARKETS 환경변수(쉼표 구분)로 순서를 받는다.
#
# 동시 실행 금지 이유: KOSPI·KOSDAQ은 andys_qip_kr.duckdb를, NASDAQ·NYSE는
# andys_qip_us.duckdb를 릴리스 자산으로 주고받는다. 겹쳐 돌면 나중에 끝난 쪽이
# 상대의 run을 덮어쓴다 (`.claude/PROBLEMS.md` #41).
#
# "성공" 판정을 워크플로 결론이 아니라 **'Save DuckDB' 스텝**으로 본다: 지금까지의 실패
# 상당수가 DB 저장까지 끝낸 뒤 마지막 사이트 커밋(git rebase 충돌)에서만 깨졌고, 그걸
# 실패로 보면 몇 시간짜리 수집을 헛되이 다시 돌리게 된다.
set -uo pipefail

MARKETS="${MARKETS:-kospi,nasdaq,nyse,kosdaq}"
POLL_SECONDS="${POLL_SECONDS:-60}"
# 새 run이 목록에 나타나기를 기다리는 최대 시간 (10초 × 30 = 5분)
DISPATCH_WAIT_TRIES=30

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# $1=워크플로 파일 → 그 워크플로의 가장 최근 run id (없으면 빈 문자열)
latest_run_id() {
    gh run list --workflow="$1" --limit 1 --json databaseId \
        -q '.[0].databaseId' 2>/dev/null || echo ""
}

# $1=run id → 'Save DuckDB'로 시작하는 스텝이 하나라도 성공했으면 0
db_saved() {
    gh run view "$1" --json jobs -q \
        '[.jobs[].steps[] | select(.name | test("Save DuckDB")) | .conclusion] | index("success") != null' \
        2>/dev/null | grep -q true
}

# $1=워크플로 파일, $2=라벨 → DB 저장까지 성공하면 0
run_market_workflow() {
    local workflow="$1" label="$2" before after run_id="" conclusion
    before="$(latest_run_id "$workflow")"

    if ! gh workflow run "$workflow"; then
        log "$label: 디스패치 실패"
        return 1
    fi

    for _ in $(seq 1 "$DISPATCH_WAIT_TRIES"); do
        sleep 10
        after="$(latest_run_id "$workflow")"
        if [ -n "$after" ] && [ "$after" != "$before" ]; then
            run_id="$after"
            break
        fi
    done
    if [ -z "$run_id" ]; then
        log "$label: 새 run을 찾지 못했습니다 (동시 실행 중이거나 디스패치가 무시됐을 수 있음)"
        return 1
    fi

    log "$label: 시작 — run $run_id"
    while true; do
        if [ "$(gh run view "$run_id" --json status -q .status 2>/dev/null)" = "completed" ]; then
            break
        fi
        sleep "$POLL_SECONDS"
    done

    conclusion="$(gh run view "$run_id" --json conclusion -q .conclusion 2>/dev/null)"
    log "$label: 종료 — 결론 $conclusion (run $run_id)"
    gh run view "$run_id" --json jobs -q '.jobs[] | "    \(.conclusion // .status)  \(.name)"' 2>/dev/null

    if db_saved "$run_id"; then
        log "$label: DB 저장 성공"
        return 0
    fi
    log "$label: DB 저장에 도달하지 못했습니다"
    return 1
}

log "=== 순차 수집 시작: $MARKETS ==="
failed=""
IFS=',' read -ra requested <<< "$MARKETS"
for raw in "${requested[@]}"; do
    market="$(echo "$raw" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
    [ -z "$market" ] && continue
    workflow="collect-${market}.yml"
    if [ ! -f ".github/workflows/${workflow}" ]; then
        log "$market: ${workflow}이 없습니다 — 건너뜁니다"
        failed="${failed} ${market}(없는 시장)"
        continue
    fi
    # 한 시장이 실패해도 남은 시장은 계속한다 — 시장끼리 의존이 없고,
    # 한 소스가 막혔다고 다른 시장 갱신까지 포기할 이유가 없다.
    run_market_workflow "$workflow" "$(echo "$market" | tr '[:lower:]' '[:upper:]')" \
        || failed="${failed} ${market}"
done

if [ -n "$failed" ]; then
    log "=== 종료 — DB 저장에 실패한 시장:${failed} ==="
    exit 1
fi
log "=== 종료 — 모든 시장 DB 저장 성공 ==="
