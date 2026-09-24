#!/usr/bin/env bash
# build_site.py로 docs/를 다시 만들고, 변경이 있으면 main에 바로 커밋·푸시한다.
# GitHub Pages가 main/docs를 소스로 쓰므로 이 커밋만으로 사이트가 갱신된다.
#
# **rebase를 쓰지 않는다.** 원래는 `git commit` 후 `git pull --rebase`로 경합을 풀었는데,
# docs/는 전량 생성물이라 같은 파일이 양쪽에서 통째로 바뀌어 rebase가 거의 항상 충돌했다.
# 수집은 성공하고 DB도 저장됐는데 마지막 커밋에서만 깨지는 실행이 반복됐다
# (2026-09-10 NASDAQ, 09-11 NYSE, 09-15·09-23 KOSPI, 09-23 NASDAQ — `.claude/PROBLEMS.md` #45).
#
# 대신 **origin 위에 다시 얹는다**: `git reset --mixed origin/<브랜치>`로 HEAD와 인덱스만
# 최신 origin으로 옮기고(작업 트리의 생성된 docs/는 그대로 둔다) docs/만 다시 스테이징한다.
# 그러면 커밋이 항상 origin 최신 위에 한 개 올라가고 충돌이 생길 수 없다.
# docs/는 생성물이라 "방금 만든 쪽이 항상 옳다" — 병합할 내용이 애초에 없다.
#
# push 직전에 다른 워크플로가 끼어들면 push가 거부되므로, 그때는 fetch부터 다시 돈다.
set -euo pipefail

BRANCH="${GITHUB_REF_NAME:-main}"
# push 경합 재시도 횟수. 같은 시간대에 도는 워크플로가 3개를 넘지 않아 이 정도면 충분하다.
MAX_PUSH_ATTEMPTS=5

# 데이터 복원에 실패한 실행은 build_site.py가 빈 사이트를 만드는 대신 0이 아닌 코드로
# 끝난다. set -e가 여기서 스크립트를 중단시켜 커밋에 도달하지 못하게 하는 것이 핵심이다 —
# 이 가드가 없으면 데이터 없는 실행이 배포된 사이트를 빈 껍데기로 덮어쓴다.
python build_site.py

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

for attempt in $(seq 1 "$MAX_PUSH_ATTEMPTS"); do
    git fetch --quiet origin "$BRANCH"

    # HEAD·인덱스만 origin 최신으로. 작업 트리(방금 생성한 docs/)는 건드리지 않는다.
    git reset --quiet --mixed "origin/$BRANCH"

    # `--ignore-removal`: 추가·수정만 스테이징하고 **삭제는 하지 않는다.**
    # reset으로 기준이 origin 최신이 됐으므로, 우리가 체크아웃한 뒤 다른 워크플로가 새로
    # 만든 docs/ 파일은 우리 작업 트리에 없다. 그것을 "삭제"로 올리면 방금 생긴 페이지가
    # 사라진다(실측: 동시 빌드가 추가한 페이지가 지워졌다). build_site.py는 낡은 산출물을
    # 지우지 않으므로(PROBLEMS #27) 진짜 삭제할 것도 없다 — 없애야 할 파일이 생기는 날에는
    # 그 정리를 build_site.py 쪽에서 명시적으로 해야 한다.
    git add --ignore-removal docs

    if git diff --cached --quiet; then
        echo "[build_and_commit_site] origin/$BRANCH 대비 docs/ 변경 없음 — 커밋 생략"
        exit 0
    fi

    git commit --quiet -m "chore: 사이트 데이터 자동 갱신 ($(date -u +'%Y-%m-%d'))"

    if git push --quiet origin "HEAD:$BRANCH"; then
        echo "[build_and_commit_site] docs/ 커밋·푸시 완료 (시도 ${attempt}회)"
        exit 0
    fi

    # 푸시 거부 = 그 사이 누군가 먼저 올렸다. 다음 바퀴의 reset이 이 커밋을 물리고
    # 새 origin 위에 다시 얹는다.
    echo "[build_and_commit_site] 푸시 경합 — origin이 갱신됐습니다. 다시 시도합니다 (${attempt}/${MAX_PUSH_ATTEMPTS})"
    sleep "$((attempt * 5))"
done

echo "[build_and_commit_site] 오류: ${MAX_PUSH_ATTEMPTS}회 시도 후에도 푸시하지 못했습니다." >&2
exit 1
