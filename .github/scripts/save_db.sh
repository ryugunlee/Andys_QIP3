#!/usr/bin/env bash
# qipinfos/ DuckDB 파일들을 "data-store" 릴리스(비공개 draft)에 올려 다음 실행을 위해 보존한다.
# draft 릴리스는 저장소의 공개 Releases 목록에 노출되지 않지만, gh CLI(GITHUB_TOKEN)로는
# 그대로 읽고 쓸 수 있다 — 사이트(docs/)와 달리 이 데이터는 공개할 필요가 없어 draft로 둔다.
#
# 사용법: save_db.sh [올릴 qipinfos/ 상대경로 파일들...] (기본값: kr/us/macro 3종 전체)
#
# **호출부는 자기가 실제로 바꾼 DB만 인자로 넘겨야 한다.** 업로드는 --clobber라서,
# 안 바꾼 DB까지 올리면 "내가 시작할 때 복원한 낡은 사본"으로 그 사이 다른 워크플로가
# 올린 결과를 덮어쓴다. 실제로 시장 수집 4종이 전부 인자 없이 호출해, 두 시장이 겹쳐
# 돌면 나중에 끝난 쪽이 상대의 run을 통째로 지우는 상태였다 (`.claude/PROBLEMS.md` #41).
#
# 남은 제약: KOSPI·KOSDAQ은 andys_qip_kr.duckdb를, NASDAQ·NYSE는 andys_qip_us.duckdb를
# 여전히 공유한다. **같은 DB를 쓰는 두 워크플로는 동시에 돌리지 말 것** (cron은 24시간
# 간격이라 현재 겹치지 않는다). 수동 실행 시에는 앞의 실행이 끝난 뒤 다음을 시작한다.
set -euo pipefail

DATA_RELEASE_TAG="${DATA_RELEASE_TAG:-data-store}"

if [ "$#" -gt 0 ]; then
    db_files=("$@")
else
    db_files=(
        qipinfos/andys_qip_kr.duckdb
        qipinfos/andys_qip_us.duckdb
        qipinfos/andys_qip_macro.duckdb
    )
fi

if ! gh release view "$DATA_RELEASE_TAG" >/dev/null 2>&1; then
    gh release create "$DATA_RELEASE_TAG" \
        --title "데이터 저장소 (자동화 전용 — 삭제 금지)" \
        --notes "GitHub Actions 파이프라인이 qipinfos/*.duckdb를 보관하는 내부용 릴리스입니다. 사람이 보는 산출물이 아니라 실행 간 데이터 영속화 용도이므로 지우지 마세요." \
        --draft
fi

for db_file in "${db_files[@]}"; do
    if [ -f "$db_file" ]; then
        gh release upload "$DATA_RELEASE_TAG" "$db_file" --clobber
        echo "[save_db] $db_file 업로드 완료"
    fi
done
