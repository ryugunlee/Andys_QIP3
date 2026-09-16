"""브라우저가 읽을 Supabase 접속 정보(static/config.js)를 빌드 시점에 만든다.

접속 정보를 소스코드에 적어두지 않기 위해 환경변수(.env 또는 CI 시크릿)에서 읽어 떨군다.
Andys_PFmanager의 scripts/write-config.js와 같은 역할·같은 규칙의 파이썬판이다.

여기서 쓰는 publishable(anon) 키는 브라우저에 실려 공개되는 값이다. 남의 데이터를 막는 것은
키가 아니라 Supabase의 RLS 정책이며(supabase/schema_qip3.sql), secret·service_role 키는
이 프로젝트 어디에서도 쓰지 않는다.

**환경변수가 없으면 기존 파일을 덮어쓰지 않는다.** 사이트를 다시 만드는 워크플로가 6개라
그중 하나가 시크릿 주입을 빠뜨리면, 정상 배포된 config.js가 빈 값으로 덮여 관리자 화면이
죽는다. 데이터가 없는 실행이 배포본을 빈 사이트로 덮어쓰지 못하게 막은 것과 같은 판단이다
(.claude/DECISIONS.md 2026-07-17 "빈 사이트는 산출물이 아니라 실패로 다룬다").
"""

import json
import os
from pathlib import Path

CONFIG_FILENAME: str = "config.js"

ENV_SUPABASE_URL: str = "SUPABASE_URL"
ENV_SUPABASE_ANON_KEY: str = "SUPABASE_ANON_KEY"

# Supabase 대시보드가 Project URL을 REST 경로까지 붙여 보여주는 경우가 있어 떼어낸다.
_REST_SUFFIX: str = "/rest/v1"

_HEADER: str = (
    "/* presentation/builders/site_config.py가 만든 파일. 직접 고치지 말고 환경변수를 고친다.\n"
    "   여기 담긴 publishable 키는 공개되어도 되는 값이다 — 접근 제어는 Supabase RLS가 한다. */\n"
)


def normalize_project_url(raw: str | None) -> str:
    """Project URL을 `https://<ref>.supabase.co` 형태로 정리한다. 값이 없으면 빈 문자열."""
    url = (raw or "").strip().rstrip("/")
    if url.endswith(_REST_SUFFIX):
        url = url[: -len(_REST_SUFFIX)]
    return url


def _render(url: str, anon_key: str) -> str:
    return (
        f"{_HEADER}\n"
        f"export const SUPABASE_URL = {json.dumps(url)};\n"
        f"export const SUPABASE_ANON_KEY = {json.dumps(anon_key)};\n"
    )


def write_site_config(output_dir: Path) -> None:
    """static/config.js를 쓴다. copy_static 직후, build_pwa 전에 호출해야 한다.

    build_pwa가 static/ 안의 파일 내용으로 서비스워커 캐시 버전을 계산하므로,
    이 파일이 그때 제자리에 있어야 접속 정보가 바뀔 때 캐시가 갱신된다.
    """
    config_path = output_dir / "static" / CONFIG_FILENAME
    url = normalize_project_url(os.getenv(ENV_SUPABASE_URL))
    anon_key = (os.getenv(ENV_SUPABASE_ANON_KEY) or "").strip()

    if url and anon_key:
        config_path.write_text(_render(url, anon_key), encoding="utf-8")
        print(f"[presentation] Supabase 접속 정보 기록: {url}")
        return

    if config_path.exists():
        print(
            f"[presentation] {ENV_SUPABASE_URL}/{ENV_SUPABASE_ANON_KEY}가 없어 "
            f"기존 {CONFIG_FILENAME}을 그대로 둔다 (덮어쓰지 않음)"
        )
        return

    config_path.write_text(_render("", ""), encoding="utf-8")
    print(f"[presentation] Supabase 접속 정보 없음 — 관리자 화면은 설정 안내만 표시한다")
