"""검색 인덱스(data/search-index.json) 빌더.

static/search.js가 사용하는 전 종목 경량 목록. 파일 크기를 줄이기 위해
축약 키를 쓴다: t=티커, n=종목명, m=시장, s=섹터, f=종합점수, c=시가총액.
"""

import json
from pathlib import Path

from presentation.repository.base import StockRepository

SEARCH_INDEX_RELATIVE_PATH = Path("data") / "search-index.json"


def build_search_index(repository: StockRepository, output_dir: Path) -> None:
    stocks = [
        {
            "t": entry.ticker,
            "n": entry.name,
            "m": entry.market,
            "s": entry.sector,
            "f": round(entry.final_score, 1) if entry.final_score is not None else None,
            "c": int(entry.market_cap) if entry.market_cap is not None else None,
        }
        for entry in repository.search_entries()
    ]
    payload = {"updated": repository.updated_date(), "stocks": stocks}

    index_path = output_dir / SEARCH_INDEX_RELATIVE_PATH
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
