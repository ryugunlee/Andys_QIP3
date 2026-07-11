"""네이버증권 응답(문자열/JSON)을 숫자·DataFrame으로 변환하는 순수 함수 모음."""

import ast

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
