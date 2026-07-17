#!/usr/bin/env bash
# build_site.py로 docs/를 다시 만들고, 변경이 있으면 main에 바로 커밋·푸시한다.
# GitHub Pages가 main/docs를 소스로 쓰므로 이 커밋만으로 사이트가 갱신된다.
set -euo pipefail

# 데이터 복원에 실패한 실행은 build_site.py가 빈 사이트를 만드는 대신 0이 아닌 코드로
# 끝난다. set -e가 여기서 스크립트를 중단시켜 커밋에 도달하지 못하게 하는 것이 핵심이다 —
# 이 가드가 없으면 데이터 없는 실행이 배포된 사이트를 빈 껍데기로 덮어쓴다.
python build_site.py

if [ -z "$(git status --porcelain docs)" ]; then
    echo "[build_and_commit_site] docs/ 변경 없음 — 커밋 생략"
    exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add docs
git commit -m "chore: 사이트 데이터 자동 갱신 ($(date -u +'%Y-%m-%d'))"

# 같은 시간대에 다른 워크플로가 먼저 push했을 경우를 대비해 rebase 후 재시도
git pull --rebase origin "${GITHUB_REF_NAME:-main}"
git push
