#!/usr/bin/env bash
# qipinfos/ DuckDB 파일들을 "data-store" 릴리스(비공개 draft)에서 복원한다.
# GitHub Actions 러너는 매번 초기화되므로, 이전 실행이 쌓아둔 DB를 이 스크립트로
# 먼저 받아와야 수집이 누적(upsert)된다. 릴리스가 아직 없으면(최초 실행) 조용히 넘어간다.
#
# 사용법: restore_db.sh [gh release download --pattern에 넘길 패턴, 기본값 '*.duckdb']
#   예: restore_db.sh 'andys_qip_macro.duckdb'  # 매크로 DB만 복원
set -euo pipefail

DATA_RELEASE_TAG="${DATA_RELEASE_TAG:-data-store}"
PATTERN="${1:-*.duckdb}"

mkdir -p qipinfos

if gh release view "$DATA_RELEASE_TAG" >/dev/null 2>&1; then
    if gh release download "$DATA_RELEASE_TAG" --dir qipinfos --clobber --pattern "$PATTERN"; then
        echo "[restore_db] $DATA_RELEASE_TAG 릴리스에서 '$PATTERN'에 해당하는 DuckDB 파일을 복원했습니다."
    else
        echo "[restore_db] '$PATTERN'에 해당하는 자산이 아직 없습니다 (해당 DB의 최초 실행으로 간주)."
    fi
else
    echo "[restore_db] $DATA_RELEASE_TAG 릴리스가 아직 없습니다 (최초 실행으로 간주)."
fi
