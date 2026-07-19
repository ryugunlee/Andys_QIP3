"""연간 실적(매출·영업이익) 다년간 오름세 판정 — 소스(야후/네이버) 무관 공용 로직.

"5년 전에 비해 꾸준히 올랐는가"를 Y/N/None(데이터 부족) 세 값으로 판정한다.
1~2년 정도의 일시적 하락(허우적거림)은 허용하되, 전체적인 순증가는 요구한다.
영업이익은 적자에서 시작해도 무방하다 — 판정 기준은 절대 수준이 아니라
"오름세"이므로 첫해 값의 부호는 보지 않는다.

데이터 소스 제약(.claude/PROBLEMS.md #23): 네이버(WiseFn)는 5개년 실적을 주지만
yfinance 무료 엔드포인트는 보통 4개년만 준다. 두 경우 모두 판정 가능하도록
"가용한 연간 기간 수"에 따라 허용 하락 연수를 다르게 둔다.
"""

# 최소 4개년(=YoY 비교 3회)이 있어야 판정한다. 그 미만이면 데이터 부족(None).
MIN_YEARS_REQUIRED: int = 4

# 5개년(YoY 비교 4회) 이상일 때 허용하는 하락 연수 — "1~2년 정도는 허우적거려도 된다".
ALLOWED_DOWN_YEARS_FULL: int = 2
# 4개년(YoY 비교 3회)만 있을 때 허용하는 하락 연수 — 비교 횟수가 적어 비례로 낮춘다.
ALLOWED_DOWN_YEARS_SHORT: int = 1


def evaluate_uptrend(values_by_period: dict[str, float]) -> str | None:
    """{회계기간(예: "202312"): 값} → "Y"/"N"/None.

    판정 기준:
    1. 순증가: 가장 오래된 해보다 가장 최근 해의 값이 커야 한다.
    2. 하락 연수 제한: 전년 대비(diff) 하락한 해의 수가 허용치 이하여야 한다.
    두 조건을 모두 만족해야 "Y". 연간 데이터가 `MIN_YEARS_REQUIRED`개 미만이면
    판정을 보류하고 None을 반환한다(데이터 부족 — Y/N 어느 쪽도 단정하지 않는다).
    """
    periods = sorted(values_by_period)
    values = [values_by_period[period] for period in periods]
    if len(values) < MIN_YEARS_REQUIRED:
        return None

    diffs = [later - earlier for earlier, later in zip(values, values[1:])]
    down_years = sum(1 for diff in diffs if diff < 0)
    allowed_down = ALLOWED_DOWN_YEARS_FULL if len(values) >= 5 else ALLOWED_DOWN_YEARS_SHORT

    net_increase = values[-1] > values[0]
    return "Y" if net_increase and down_years <= allowed_down else "N"
