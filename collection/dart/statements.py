"""종목 하나의 DART 재무제표를 여러 회계연도·주기로 모아 long format으로 낸다.

**호출 수 설계** (일일 한도 20,000):
- 사업보고서 한 번의 응답이 당기·전기·전전기 **3개년**을 준다 → 6개년을 2콜로 확보한다.
- 분기는 1분기·반기·3분기 보고서 각각이 당기 3개월분을 주므로 최근 연도 3콜 + 사업보고서
  (연간 4분기 대용)로 시계열을 만든다.
- 종목당 연간 2 + 분기 3 = **5콜**. KOSPI 942종목 → 4,710콜, KOSDAQ 1,820종목 → 9,100콜.
  시장별 수집이 요일마다 나뉘어 있어 하루 최대치는 KOSDAQ의 9,100콜이다(한도의 46%).

`fs_div`는 연결(CFS) 우선, 없으면 별도(OFS) 폴백이다 — WiseFn이 연결(MAIN) 기준이었으므로
같은 성격을 유지한다. 지주·소규모 회사는 연결재무제표를 작성하지 않는다.
"""

from datetime import date

import pandas as pd

from collection.dart import client
from collection.dart.parsers import (
    LONG_FORMAT_COLUMNS,
    REPORT_PERIOD_MONTH,
    parse_statements,
)

_FINANCIAL_STATEMENT_API: str = "fnlttSinglAcntAll.json"

# 보고서 코드.
REPORT_ANNUAL: str = "11011"
REPORT_Q1: str = "11013"
REPORT_HALF: str = "11012"
REPORT_Q3: str = "11014"

# 연결 우선, 별도 폴백.
FS_CONSOLIDATED: str = "CFS"
FS_SEPARATE: str = "OFS"

# statement_type 이름 — WiseFn 경로("wise_*")와 구분되게 둔다. 소스가 섞여 저장되는
# financial_statements 테이블에서 어느 경로로 받은 값인지 구분하는 근거가 된다.
ANNUAL_STATEMENT_TYPE: str = "dart_annual"
QUARTERLY_STATEMENT_TYPE: str = "dart_quarterly"

# 사업보고서 응답이 주는 3개년의 (금액 필드, 기준연도로부터의 차이).
_ANNUAL_PERIOD_FIELDS: tuple[tuple[str, int], ...] = (
    ("thstrm_amount", 0),
    ("frmtrm_amount", -1),
    ("bfefrmtrm_amount", -2),
)
# 한 응답이 커버하는 연수 (3개년) — 6개년을 원하면 2콜.
YEARS_PER_ANNUAL_CALL: int = len(_ANNUAL_PERIOD_FIELDS)

_EMPTY = pd.DataFrame(columns=LONG_FORMAT_COLUMNS)


# 사업보고서 제출 기한은 사업연도 종료 후 90일이라, 이 달 이전에는 전전년도가 최신이다.
ANNUAL_REPORT_AVAILABLE_MONTH: int = 4


def latest_annual_year(today: date) -> int:
    """오늘 기준으로 사업보고서가 확실히 나와 있는 가장 최근 회계연도.

    12월 결산 회사의 사업보고서는 이듬해 3월 말까지 제출된다. 4월 이전에 전년도를
    요청하면 아직 없는 보고서를 묻게 되므로 한 해 더 내려간다.
    """
    return today.year - (1 if today.month >= ANNUAL_REPORT_AVAILABLE_MONTH else 2)


def fetch_payload(corp_code: str, year: int, report_code: str) -> dict | None:
    """전체 재무제표 응답 한 건(원본). 연결 → 별도 순으로 시도하고 데이터가 없으면 None.

    `verify_dart_mapping.py`가 계정 덤프를 만들 때도 쓴다 — 매핑을 고치려면 원본이 필요하다."""
    for fs_div in (FS_CONSOLIDATED, FS_SEPARATE):
        response = client.get(
            _FINANCIAL_STATEMENT_API,
            corp_code=corp_code,
            bsns_year=str(year),
            reprt_code=report_code,
            fs_div=fs_div,
        )
        payload = response.json()
        if payload.get("status") == client.STATUS_OK and payload.get("list"):
            return payload
    return None


def _annual_period_fields(year: int) -> dict[str, str]:
    """사업보고서 응답의 {회계기간 라벨: 금액 필드} — 당기/전기/전전기."""
    month = REPORT_PERIOD_MONTH[REPORT_ANNUAL]
    return {f"{year + offset}{month}": field for field, offset in _ANNUAL_PERIOD_FIELDS}


def fetch_annual(corp_code: str, latest_year: int, years: int) -> pd.DataFrame:
    """최근 `years`개년 연간 재무제표. 한 응답이 3개년을 주므로 필요한 만큼만 호출한다."""
    frames: list[pd.DataFrame] = []
    collected = 0
    year = latest_year
    while collected < years:
        payload = fetch_payload(corp_code, year, REPORT_ANNUAL)
        if payload is not None:
            frames.append(
                parse_statements(
                    payload, ANNUAL_STATEMENT_TYPE, _annual_period_fields(year)
                )
            )
        # 응답이 없어도 다음 구간으로 내려간다 — 신규 상장사는 과거 보고서가 아예 없다.
        collected += YEARS_PER_ANNUAL_CALL
        year -= YEARS_PER_ANNUAL_CALL

    if not frames:
        return _EMPTY.copy()
    merged = pd.concat(frames, ignore_index=True)
    # 구간이 겹쳐 같은 (기간, 항목)이 두 번 오면 최신 보고서의 값을 남긴다
    # (정정 공시가 반영된 쪽이 앞선 호출이므로 keep="first").
    merged = merged.drop_duplicates(subset=["period", "item"], keep="first")
    return _trim_to_recent_periods(merged, years)


def fetch_quarterly(corp_code: str, latest_year: int) -> pd.DataFrame:
    """최근 연도의 분기 재무제표(1분기·반기·3분기). 실적 시계열 표시용이다.

    재무 팩터(curated factors)는 연간만 쓴다 — WiseFn 경로와 같은 원칙이다.
    """
    frames: list[pd.DataFrame] = []
    for report_code in (REPORT_Q1, REPORT_HALF, REPORT_Q3):
        payload = fetch_payload(corp_code, latest_year, report_code)
        if payload is None:
            continue
        period = f"{latest_year}{REPORT_PERIOD_MONTH[report_code]}"
        frames.append(
            parse_statements(
                payload, QUARTERLY_STATEMENT_TYPE, {period: "thstrm_amount"}
            )
        )
    if not frames:
        return _EMPTY.copy()
    return pd.concat(frames, ignore_index=True)


def _trim_to_recent_periods(statements: pd.DataFrame, years: int) -> pd.DataFrame:
    """가장 최근 `years`개 회계기간만 남긴다 (기간 라벨이 YYYYMM이라 문자열 정렬로 충분)."""
    if statements.empty:
        return statements
    recent = sorted(statements["period"].unique())[-years:]
    return statements[statements["period"].isin(recent)].reset_index(drop=True)
