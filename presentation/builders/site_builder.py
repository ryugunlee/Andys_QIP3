"""사이트 전체 생성 오케스트레이션.

정적 자산 배치 → 메인 → 주식 분석 → 종목 상세 → 검색 인덱스 → PWA 순으로
모든 빌더를 실행한다. 데이터 출처는 StockRepository 계약 뒤에 숨어 있어
CSV가 DB로 바뀌어도 이 파일은 수정할 필요가 없다.

PWA가 마지막인 이유: 서비스워커의 캐시 버전이 앞선 빌더들이 만든 산출물의
내용에서 나오므로, 모든 파일이 제자리에 있어야 한다.
"""

from pathlib import Path

from presentation import config
from presentation.builders.assets import copy_static, write_nojekyll
from presentation.builders.detail_pages import build_detail_pages
from presentation.builders.environment import create_environment
from presentation.builders.index_page import build_index_page
from presentation.builders.pwa import build_pwa
from presentation.builders.search_index import build_search_index
from presentation.builders.sectors_page import build_sectors_page
from presentation.builders.stocks_page import build_stocks_page
from presentation.repository.base import StockRepository


class EmptySiteError(RuntimeError):
    """시장 데이터가 0건이라 사이트를 만들 수 없을 때 발생한다."""


def build_site(
    repository: StockRepository, output_dir: Path = config.DEFAULT_OUTPUT_DIR
) -> None:
    """분석 산출물로 output_dir에 정적 사이트를 생성한다.

    Raises:
        EmptySiteError: 로드된 시장 데이터가 0건일 때. 빈 사이트는 정당한 산출물이
            아니므로 output_dir을 건드리기 전에 중단한다 — 데이터 공급이 끊긴 실행이
            이미 배포된 사이트를 빈 껍데기로 덮어쓰는 사고를 막기 위한 가드다.
    """
    counts = repository.market_counts()
    if not counts:
        raise EmptySiteError(
            "로드된 시장 데이터가 0건이라 사이트 생성을 중단합니다 "
            "(기존 산출물을 빈 사이트로 덮어쓰지 않기 위함). "
            "데이터 소스(qipinfos/*.duckdb 또는 data-store 릴리스)를 확인하세요."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    env = create_environment()

    copy_static(output_dir)
    write_nojekyll(output_dir)
    build_index_page(repository, env, output_dir)
    build_stocks_page(repository, env, output_dir)
    build_sectors_page(repository, env, output_dir)
    detail_count = build_detail_pages(repository, env, output_dir)
    build_search_index(repository, output_dir)
    build_pwa(repository, env, output_dir)

    print(f"[presentation] 사이트 생성 완료: {output_dir}")
    print(f"[presentation] 종목 상세 페이지 {detail_count:,}개")
    summary = " · ".join(f"{market} {count:,}개" for market, count in counts.items())
    print(f"[presentation] 시장별 종목: {summary}")
