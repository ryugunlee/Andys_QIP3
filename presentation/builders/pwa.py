"""PWA(홈 화면 설치) 산출물 빌더: manifest.webmanifest · sw.js · offline.html.

별도의 모바일 앱을 만들지 않고 이 정적 사이트 자체를 설치형 앱으로 쓴다
(.claude/DECISIONS.md 2026-07-17 참고). 앱 전용 코드가 없으므로 표현 계층을 고치면
설치된 앱도 그대로 따라 바뀐다.

매니페스트와 서비스워커는 반드시 사이트 루트에 놓는다 — 매니페스트의 scope "./"와
서비스워커의 스코프가 사이트 전체를 덮어야 하기 때문이다.

서비스워커의 캐시 이름에는 빌드마다 계산한 버전을 찍는다. 버전은 "정적 자산 내용 +
데이터 기준일"의 해시라서, 내용이 그대로면 버전도 그대로다(불필요한 재다운로드 방지).
"""

import hashlib
from pathlib import Path

from jinja2 import Environment

from presentation.builders.search_index import SEARCH_INDEX_RELATIVE_PATH
from presentation.repository.base import StockRepository

MANIFEST_FILENAME = "manifest.webmanifest"
SERVICE_WORKER_FILENAME = "sw.js"
OFFLINE_FILENAME = "offline.html"

# 캐시 버전 해시 길이. 충돌 위험이 사실상 없으면서 sw.js를 읽기 쉬운 정도.
_CACHE_VERSION_LENGTH = 12

# 앱 셸: 설치 직후 오프라인으로도 열려야 하는 최소 페이지 집합.
# 종목 상세는 수천 개라 넣지 않는다 — 방문한 것만 서비스워커가 캐시한다.
_SHELL_PAGES: tuple[str, ...] = (
    "./index.html",
    f"./{OFFLINE_FILENAME}",
    "./stocks/index.html",
    "./sectors/index.html",
    f"./{MANIFEST_FILENAME}",
)


def _static_urls(output_dir: Path) -> list[str]:
    """복사가 끝난 static/ 안의 모든 파일을 매니페스트 기준 상대 URL로 만든다.

    목록을 직접 적지 않고 실제 파일에서 뽑으므로, 자산이 늘거나 줄어도
    프리캐시 목록이 어긋나지 않는다(cache.addAll은 하나만 404여도 전부 실패한다).
    """
    static_dir = output_dir / "static"
    if not static_dir.is_dir():
        return []
    return sorted(
        "./" + path.relative_to(output_dir).as_posix()
        for path in static_dir.rglob("*")
        if path.is_file()
    )


def _cache_version(output_dir: Path, updated_date: str | None, urls: list[str]) -> str:
    """프리캐시 대상들의 실제 내용과 데이터 기준일로 캐시 버전을 만든다.

    스타일 한 줄만 고쳐도 버전이 바뀌어 옛 캐시가 버려지고, 반대로 아무것도 안 바뀌면
    같은 버전이 나와 사용자가 셸을 다시 받지 않는다. 그래서 모든 산출물이 만들어진
    뒤(site_builder의 맨 끝)에 호출해야 한다.
    """
    digest = hashlib.sha256()
    digest.update((updated_date or "").encode("utf-8"))
    for url in urls:
        digest.update(url.encode("utf-8"))
        path = output_dir / url[len("./") :]
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:_CACHE_VERSION_LENGTH]


def build_pwa(
    repository: StockRepository, env: Environment, output_dir: Path
) -> None:
    """매니페스트·서비스워커·오프라인 페이지를 사이트 루트에 쓴다.

    static/ 복사가 끝난 뒤에 호출해야 한다 — 캐시 버전이 자산 내용에서 나오기 때문이다.
    """
    updated_date = repository.updated_date()

    precache_urls = list(_SHELL_PAGES)
    precache_urls.extend(_static_urls(output_dir))
    precache_urls.append("./" + SEARCH_INDEX_RELATIVE_PATH.as_posix())

    # 캐시 버전이 프리캐시 대상들의 내용에서 나오므로, 그 대상인 매니페스트와
    # 오프라인 페이지를 먼저 쓴 뒤에 서비스워커를 만든다. 순서가 뒤집히면 같은 입력으로
    # 빌드해도 버전이 달라져(첫 빌드는 파일이 없는 상태를 해싱) 캐시가 매번 버려진다.
    manifest = env.get_template(f"{MANIFEST_FILENAME}.jinja").render()
    (output_dir / MANIFEST_FILENAME).write_text(manifest, encoding="utf-8")

    offline = env.get_template(OFFLINE_FILENAME).render(
        root=".",
        active_page=None,
        updated_date=updated_date,
    )
    (output_dir / OFFLINE_FILENAME).write_text(offline, encoding="utf-8")

    service_worker = env.get_template(f"{SERVICE_WORKER_FILENAME}.jinja").render(
        cache_version=_cache_version(output_dir, updated_date, precache_urls),
        precache_urls=precache_urls,
        offline_url=f"./{OFFLINE_FILENAME}",
        manifest_url=f"./{MANIFEST_FILENAME}",
    )
    (output_dir / SERVICE_WORKER_FILENAME).write_text(service_worker, encoding="utf-8")
