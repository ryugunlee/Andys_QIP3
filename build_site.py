"""정적 사이트 생성 진입점.

Andys_QIP2.py 파이프라인이 저장한 DuckDB(qipinfos/andys_qip.duckdb)를 읽어
docs/에 배포용 정적 사이트를 생성한다. 모든 시장 데이터를 갱신한 뒤 1회 실행한다.
DB 파일이 없으면 과거 CSV 산출물(qipinfos/{시장}stockdata2/)로 폴백한다.

사용법:
    python build_site.py [--db-path ./qipinfos/andys_qip.duckdb]
                         [--data-dir ./qipinfos] [--output ./docs]

배포: docs/를 커밋하고 GitHub Pages를 "main 브랜치 / docs 폴더"로 설정한다.
"""

import argparse
from pathlib import Path

from presentation import config
from presentation.builders.site_builder import build_site
from presentation.repository import CsvStockRepository, DuckDbStockRepository
from presentation.repository.base import StockRepository
from storage.database import DEFAULT_DB_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="분석 산출물(DuckDB/CSV)로 정적 사이트를 생성한다.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help=f"파이프라인 DuckDB 파일 (기본값: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=config.DEFAULT_DATA_DIR,
        help=f"CSV 폴백용 산출물 폴더 (기본값: {config.DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=config.DEFAULT_OUTPUT_DIR,
        help=f"사이트 출력 폴더 (기본값: {config.DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args()


def select_repository(db_path: Path, data_dir: Path) -> StockRepository:
    """DuckDB가 있으면 DB, 없으면 과거 CSV 산출물로 폴백한다."""
    if db_path.exists():
        print(f"[build_site] 데이터 소스: DuckDB ({db_path})")
        return DuckDbStockRepository(db_path=db_path)
    print(f"[build_site] DuckDB 없음({db_path}) → CSV 폴백 ({data_dir})")
    return CsvStockRepository(data_dir=data_dir)


def main() -> None:
    args = parse_args()
    repository = select_repository(args.db_path, args.data_dir)
    build_site(repository, output_dir=args.output)


if __name__ == "__main__":
    main()
