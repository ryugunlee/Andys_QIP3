"""정적 자산 배치: static/ 복사와 GitHub Pages용 .nojekyll 생성."""

import shutil
from pathlib import Path

STATIC_DIR: Path = Path(__file__).resolve().parent.parent / "static"


def copy_static(output_dir: Path) -> None:
    """presentation/static/ 을 출력 폴더의 static/ 으로 복사한다."""
    shutil.copytree(STATIC_DIR, output_dir / "static", dirs_exist_ok=True)


def write_nojekyll(output_dir: Path) -> None:
    """GitHub Pages의 Jekyll 빌드를 끈다 (수천 개 HTML을 그대로 서빙)."""
    (output_dir / ".nojekyll").write_text("")
