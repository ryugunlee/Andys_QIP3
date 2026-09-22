"""티커 목록을 조각으로 나눈다 (분할 수집용 순수 함수).

KOSDAQ 1,820종목은 네이버 수집 속도(종목당 약 16초)로 8시간이 넘어 GitHub 호스팅
러너의 작업 시간 상한 6시간을 넘는다. 그래서 워크플로가 조각을 순차 job으로 나눠
수집하고, 마지막 job이 조각들을 합쳐 **하나의 run**으로 확정한다
(`.claude/PROBLEMS.md` #42 / `pipeline/market_run.py`).

분할은 **결정적**이어야 한다 — 조각 job이 재실행되어도 같은 몫을 받아야 하고,
조각들의 합집합이 정확히 원래 목록이어야 한다.
"""


def chunk_tickers(tickers: list[str], index: int, total: int) -> list[str]:
    """`tickers`를 `total`조각으로 나눈 뒤 `index`번째(1부터) 조각을 반환한다.

    나머지는 앞 조각들에 하나씩 더 얹어 조각 크기 차이를 1 이내로 유지한다.
    목록 순서를 바꾸지 않으므로 조각들을 순서대로 이으면 원래 목록이 된다.
    """
    if total < 1:
        raise ValueError(f"조각 수는 1 이상이어야 한다: {total}")
    if not 1 <= index <= total:
        raise ValueError(f"조각 번호는 1~{total} 범위여야 한다: {index}")

    base_size, remainder = divmod(len(tickers), total)
    # 앞쪽 `remainder`개 조각이 1개씩 더 맡는다.
    start = base_size * (index - 1) + min(index - 1, remainder)
    size = base_size + (1 if index <= remainder else 0)
    return tickers[start : start + size]


def parse_chunk_spec(spec: str) -> tuple[int, int]:
    """"2/4" 형식의 조각 지정을 (index, total)로 바꾼다."""
    parts = spec.split("/")
    if len(parts) != 2:
        raise ValueError(f'조각 지정은 "번호/전체" 형식이어야 한다 (예: 2/4): {spec}')
    try:
        index, total = int(parts[0]), int(parts[1])
    except ValueError as error:
        raise ValueError(f"조각 지정에 숫자가 아닌 값이 있다: {spec}") from error
    if not 1 <= index <= total:
        raise ValueError(f"조각 번호는 1~{total} 범위여야 한다: {spec}")
    return index, total
