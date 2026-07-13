"""사이트 전체 생성 오케스트레이션.

정적 자산 배치 → 메인 → 주식 분석 → 종목 상세 → 검색 인덱스 순으로
모든 빌더를 실행한다. 데이터 출처는 StockRepository 계약 뒤에 숨어 있어
CSV가 DB로 바뀌어도 이 파일은 수정할 필요가 없다.
"""

from pathlib import Path

from presentation import config
from presentation.builders.assets import copy_static, write_nojekyll
from presentation.builders.detail_pages import build_detail_pages
from presentation.builders.environment import create_environment
from presentation.builders.index_page import build_index_page
from presentation.builders.search_index import build_search_index
from presentation.builders.stocks_page import build_stocks_page
from presentation.repository.base import StockRepository


def build_site(
    repository: StockRepository, output_dir: Path = config.DEFAULT_OUTPUT_DIR
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    env = create_environment()

    copy_static(output_dir)
    write_nojekyll(output_dir)
    build_index_page(repository, env, output_dir)
    build_stocks_page(repository, env, output_dir)
    detail_count = build_detail_pages(repository, env, output_dir)
    build_search_index(repository, output_dir)

    print(f"[presentation] 사이트 생성 완료: {output_dir}")
    print(f"[presentation] 종목 상세 페이지 {detail_count:,}개")
    counts = repository.market_counts()
    if counts:
        summary = " · ".join(f"{market} {count:,}개" for market, count in counts.items())
        print(f"[presentation] 시장별 종목: {summary}")
    else:
        print("[presentation] 경고: 로드된 시장 데이터가 없어 빈 사이트가 생성되었습니다.")
