"""네이버증권 응답(문자열/JSON)을 숫자·DataFrame으로 변환하는 순수 함수 모음."""

import ast
import re

import pandas as pd

_WON_UNIT_SUFFIXES: tuple[str, ...] = ("배", "원", "%")
_JO: float = 1e12  # 1조
_EOK: float = 1e8  # 1억

_PRICE_HISTORY_COLUMNS: tuple[str, ...] = (
    "date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "foreign_rate",
)


def parse_number(text: str | None) -> float | None:
    """콤마 구분 숫자 문자열에서 배/원/% 단위 접미사를 제거하고 float로 변환한다.
    파싱할 수 없으면 None을 반환한다 (예: "-", 빈 문자열)."""
    if text is None:
        return None
    cleaned = text.strip().replace(",", "")
    for suffix in _WON_UNIT_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_won_amount(text: str | None) -> float | None:
    """'1,666조 1,894억' 같은 조/억 결합 표기를 KRW 실수로 변환한다.
    조/억 단위가 없으면(예: "285,000") parse_number로 처리한다."""
    if text is None:
        return None
    text = text.strip()
    if "조" not in text and "억" not in text:
        return parse_number(text)

    total = 0.0
    remaining = text
    if "조" in remaining:
        jo_part, _, remaining = remaining.partition("조")
        jo_value = parse_number(jo_part)
        if jo_value is not None:
            total += jo_value * _JO
    remaining = remaining.strip()
    if "억" in remaining:
        eok_part, _, _ = remaining.partition("억")
        eok_value = parse_number(eok_part)
        if eok_value is not None:
            total += eok_value * _EOK
    return total


def parse_price_history(raw_text: str) -> pd.DataFrame:
    """siseJson.naver 응답(파이썬 리터럴 형태 유사 JSON)을 OHLCV DataFrame으로 변환한다.

    첫 행은 헤더(날짜/시가/고가/저가/종가/거래량/외국인소진율)이고, 데이터가 없는
    티커는 헤더만 있는 1행짜리 리스트가 온다 — 이 경우 빈 DataFrame을 반환한다.
    """
    parsed = ast.literal_eval(raw_text.strip())
    data_rows = parsed[1:]
    if not data_rows:
        return pd.DataFrame(columns=_PRICE_HISTORY_COLUMNS[1:])

    df = pd.DataFrame(data_rows, columns=_PRICE_HISTORY_COLUMNS)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.set_index("date")
    return df


def parse_financial_statements(payload: dict, statement_type: str) -> pd.DataFrame:
    """네이버 finance/annual(또는 finance/quarter) 응답을 long format
    (period, item, value, is_consensus) DataFrame으로 변환한다."""
    finance_info = payload["financeInfo"]
    period_is_consensus = {
        title["key"]: title["isConsensus"] == "Y" for title in finance_info["trTitleList"]
    }

    rows = []
    for row in finance_info["rowList"]:
        item = row["title"]
        for period, cell in row["columns"].items():
            value = parse_number(cell.get("value"))
            if value is None:
                continue
            rows.append(
                {
                    "period": period,
                    "item": item,
                    "value": value,
                    "is_consensus": period_is_consensus.get(period, False),
                }
            )

    columns = ["period", "item", "value", "is_consensus"]
    df = pd.DataFrame(rows, columns=columns)
    df.insert(0, "statement_type", statement_type)
    return df


def latest_actual_periods(statements: pd.DataFrame, count: int = 2) -> list[str]:
    """컨센서스(추정치)가 아닌 실제 회계기간을 최신순으로 최대 `count`개 반환한다."""
    if statements.empty:
        return []
    actual = statements.loc[~statements["is_consensus"], "period"]
    return sorted(actual.unique(), reverse=True)[:count]


def get_statement_value(statements: pd.DataFrame, period: str, item: str) -> float | None:
    """특정 회계기간·항목의 값을 반환한다. 없으면 None."""
    match = statements[(statements["period"] == period) & (statements["item"] == item)]
    return match["value"].iloc[0] if not match.empty else None


_WISE_YYMM_PATTERN = re.compile(r"(\d{4})/(\d{2})")
_WISE_ANNUAL_PERIOD_COUNT: int = 6  # DATA1~DATA6: 5개년 실적 + 1개년 컨센서스 추정치


def parse_wise_financial_statement(payload: dict, statement_type: str) -> pd.DataFrame:
    """WiseFn(navercomp.wisereport.co.kr) cF3002.aspx 응답을 long format
    (period, item, value, is_consensus) DataFrame으로 변환한다.

    item은 "ACCODE:계정명" 형태로 저장한다 — 같은 계정명(예: "이자비용")이 손익계산서
    트리의 여러 위치(매출원가/금융원가/기타영업비용 등)에 나타날 수 있어 계정명만으로는
    구분할 수 없기 때문이다. ACCODE는 종목·기간과 무관하게 고정된 값임을 확인했다
    (collection/constants.py의 NAVER_WISE_ACCODE_* 참고).
    """
    yymm_labels = payload.get("YYMM", [])[:_WISE_ANNUAL_PERIOD_COUNT]
    periods: list[str | None] = []
    is_consensus_flags: list[bool] = []
    for label in yymm_labels:
        match = _WISE_YYMM_PATTERN.search(label)
        periods.append(f"{match.group(1)}{match.group(2)}" if match else None)
        is_consensus_flags.append("(E)" in label)

    rows = []
    for entry in payload.get("DATA", []):
        item = f"{entry['ACCODE']}:{entry['ACC_NM']}"
        for index, period in enumerate(periods, start=1):
            if period is None:
                continue
            value = entry.get(f"DATA{index}")
            if value is None:
                continue
            rows.append(
                {
                    "period": period,
                    "item": item,
                    "value": float(value),
                    "is_consensus": is_consensus_flags[index - 1],
                }
            )

    columns = ["period", "item", "value", "is_consensus"]
    df = pd.DataFrame(rows, columns=columns)
    df.insert(0, "statement_type", statement_type)
    return df


def get_wise_value(statements: pd.DataFrame, period: str, accode: str) -> float | None:
    """ACCODE로 특정 회계기간의 값을 찾는다 (item 컬럼이 "ACCODE:계정명" 형태이므로
    접두사로 매칭한다)."""
    if statements.empty:
        return None
    prefix = f"{accode}:"
    match = statements[
        (statements["period"] == period) & (statements["item"].str.startswith(prefix))
    ]
    return match["value"].iloc[0] if not match.empty else None


def series_by_accode(statements: pd.DataFrame, accode: str) -> dict[str, float]:
    """ACCODE 하나의 전체 회계기간 값을 {period: value}로 반환한다 (컨센서스 제외).

    get_wise_value이 기간 하나만 조회하는 것과 달리, 다년간 추세 판정
    (collection/financial_trend.py)처럼 전체 이력이 필요할 때 쓴다.
    """
    if statements.empty:
        return {}
    prefix = f"{accode}:"
    actual = statements[~statements["is_consensus"]]
    matched = actual[actual["item"].str.startswith(prefix)]
    return dict(zip(matched["period"], matched["value"]))


def latest_period_wise_values(statements: pd.DataFrame) -> dict[str, float]:
    """가장 최근 실제(비컨센서스) 회계기간의 {item: value} 딕셔너리를 반환한다
    (raw 데이터 보관용 — 5개년 전체가 아니라 최신 한 기간만)."""
    periods = latest_actual_periods(statements, count=1)
    if not periods:
        return {}
    latest = statements[statements["period"] == periods[0]]
    return dict(zip(latest["item"], latest["value"]))
