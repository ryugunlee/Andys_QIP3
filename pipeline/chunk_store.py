"""조각 수집 결과를 job 사이로 넘기는 파일 저장소 (parquet + 실패 티커 JSON).

한 시장을 여러 job으로 나눠 수집할 때, 조각 job은 자기 몫의 curated 표를 여기에 쓰고
확정 job이 전부 읽어 합친다. 워크플로는 이 폴더를 artifact로 주고받는다.

**DB가 아니라 파일로 넘기는 이유**: 조각 job이 `collection_runs`에 행을 만들면 중간
job이 실패했을 때 "점수 없는 반쪽 run"이 DB에 남고, 그게 최신 run이 되어 그 시장의
점수가 사이트에서 전부 비어 보인다. 조각 결과를 DB 밖에 두면 확정 job이 성공할 때만
run이 생긴다 (`.claude/PROBLEMS.md` #42).

**parquet 입출력을 DuckDB로 하는 이유**: pandas의 `to_parquet`은 pyarrow를 요구하는데,
DuckDB는 이미 이 프로젝트의 의존성이고 parquet을 직접 읽고 쓴다. 의존성을 늘리지 않는다.
"""

import json
from pathlib import Path

import duckdb
import pandas as pd

_PARQUET_SUFFIX = ".parquet"
_ERRORS_SUFFIX = ".errors.json"


def _stem(market: str, index: int, total: int) -> str:
    """조각 파일 이름. 조각 번호가 들어가야 artifact를 합쳐도 서로 덮어쓰지 않는다."""
    return f"{market.lower()}-chunk{index}of{total}"


def _as_storable(stockdata: pd.DataFrame) -> pd.DataFrame:
    """parquet에 쓸 수 있는 형태로 정규화한 복사본.

    object 컬럼을 문자열 dtype으로 고정한다 — 값이 전부 결측인 텍스트 팩터(예: 어느 조각도
    `Revenue Trend (5Y)`를 못 채운 경우)를 DuckDB가 INTEGER로 추론해 버리면, 합본에서
    같은 컬럼의 타입이 조각마다 갈리기 때문이다.
    """
    normalized = stockdata.copy()
    for column in normalized.columns:
        if normalized[column].dtype == object:
            normalized[column] = normalized[column].astype("string")
    return normalized


def write_chunk(
    directory: Path,
    market: str,
    index: int,
    total: int,
    stockdata: pd.DataFrame,
    error_tickers: list[str],
) -> Path:
    """조각 하나의 curated 표와 실패 티커를 저장하고 parquet 경로를 반환한다."""
    directory.mkdir(parents=True, exist_ok=True)
    stem = _stem(market, index, total)

    parquet_path = directory / f"{stem}{_PARQUET_SUFFIX}"
    storable = _as_storable(stockdata)
    duckdb.sql("SELECT * FROM storable").write_parquet(str(parquet_path))

    errors_path = directory / f"{stem}{_ERRORS_SUFFIX}"
    errors_path.write_text(
        json.dumps(error_tickers, ensure_ascii=False), encoding="utf-8"
    )
    return parquet_path


def read_chunks(directory: Path, market: str) -> tuple[pd.DataFrame, list[str]]:
    """그 시장의 조각 전부를 읽어 (합친 표, 실패 티커 합집합) 을 반환한다.

    같은 티커가 두 조각에 있으면(조각 경계가 바뀐 재실행 등) 첫 조각의 행만 남긴다 —
    `snapshot_factors`의 (run_id, ticker) PK 위반으로 확정 단계가 죽지 않게 하는 방어선이다.
    """
    prefix = f"{market.lower()}-chunk"
    parquet_paths = sorted(
        path
        for path in directory.glob(f"{prefix}*{_PARQUET_SUFFIX}")
        if path.is_file()
    )
    if not parquet_paths:
        raise FileNotFoundError(
            f"{directory}에 {market} 조각 결과가 없습니다 — 조각 수집 job이 먼저 끝나야 합니다."
        )

    frames = [duckdb.read_parquet(str(path)).df() for path in parquet_paths]
    merged = pd.concat(frames, ignore_index=True)
    duplicated = merged["Ticker"].duplicated(keep="first")
    if duplicated.any():
        print(
            f"[chunk_store] 조각 간 중복 티커 {merged.loc[duplicated, 'Ticker'].tolist()}"
            " — 첫 조각의 행만 남깁니다."
        )
        merged = merged[~duplicated].reset_index(drop=True)

    error_tickers: list[str] = []
    for path in parquet_paths:
        errors_path = path.with_name(path.name.replace(_PARQUET_SUFFIX, _ERRORS_SUFFIX))
        if errors_path.exists():
            error_tickers.extend(json.loads(errors_path.read_text(encoding="utf-8")))

    print(
        f"[chunk_store] 조각 {len(parquet_paths)}개 병합 — {len(merged)}종목,"
        f" 실패 {len(error_tickers)}종목"
    )
    return merged, list(dict.fromkeys(error_tickers))
