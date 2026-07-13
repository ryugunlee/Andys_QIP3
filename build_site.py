"""정적 사이트 생성 진입점.

Andys_QIP2.py 파이프라인이 만든 qipinfos/ CSV를 읽어 docs/에 배포용
정적 사이트를 생성한다. 모든 시장 데이터를 갱신한 뒤 1회 실행한다.

사용법:
    python build_site.py [--data-dir ./qipinfos] [--output ./docs]

배포: docs/를 커밋하고 GitHub Pages를 "main 브랜치 / docs 폴더"로 설정한다.
"""

import argparse
from pathlib import Path

from presentation import config
from presentation.builders.site_builder import build_site
from presentation.repository import CsvStockRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="분석 산출물 CSV로 정적 사이트를 생성한다.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=config.DEFAULT_DATA_DIR,
        help=f"파이프라인 산출물 폴더 (기본값: {config.DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=config.DEFAULT_OUTPUT_DIR,
        help=f"사이트 출력 폴더 (기본값: {config.DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = CsvStockRepository(data_dir=args.data_dir)
    build_site(repository, output_dir=args.output)


if __name__ == "__main__":
    main()
