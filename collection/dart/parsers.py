"""OpenDART `fnlttSinglAcntAll` 응답 → 정규화 long format.

출력 형태는 WiseFn 경로와 **같은 계약**이다 (statement_type, period, item, value,
is_consensus) — 그래야 `BaseStock.to_financial_statement_rows()` 하류가 그대로 돌아간다.
`item`은 `"<지표>:<한글 계정명>"`으로, WiseFn의 `"ACCODE:계정명"`과 같은 모양이라
읽는 쪽(`series_adapter`, `presentation/financial_series`)이 접두사 매칭을 재사용한다.

`is_consensus`는 항상 False다 — DART는 공시(실적)만 주고 추정치를 주지 않는다.
컨센서스는 계속 네이버 모바일 API(`finance/annual`)에서 온다.

**금액 단위는 원(KRW)이다.** WiseFn이 억원이었던 것과 다르므로, 이 경로에는
`NAVER_EOK_TO_WON` 환산을 적용하지 않는다 (`collection/qip4/series_adapter.py` 참고).
"""

import pandas as pd

from collection.dart.accounts import (
    ACCOUNT_SPECS,
    AGGREGATED_LABEL,
    AGGREGATE_SUM,
    item_key,
)

LONG_FORMAT_COLUMNS: list[str] = [
    "statement_type",
    "period",
    "item",
    "value",
    "is_consensus",
]

# `account_id`가 이 값이면 표준계정코드가 없다는 뜻 — 한글 계정명 폴백으로 넘어간다.
NO_STANDARD_ACCOUNT_ID: str = "-표준계정코드 미사용-"

# reprt_code → 회계기간 라벨의 월. WiseFn이 "YYYYMM"(기간 말월)을 썼으므로 같은 규약을 쓴다.
# **12월 결산을 가정한다** — 3월 결산 회사도 같은 라벨 체계를 쓰므로 문자열 정렬(=시간 정렬)은
# 보존되지만 월 자체는 실제 결산월과 다를 수 있다. 하류에서 월을 쓰는 곳은 분기 라벨
# (Q1~Q4) 뿐이다.
REPORT_PERIOD_MONTH: dict[str, str] = {
    "11013": "03",  # 1분기보고서
    "11012": "06",  # 반기보고서
    "11014": "09",  # 3분기보고서
    "11011": "12",  # 사업보고서
}


def parse_amount(raw: object) -> float | None:
    """DART 금액 문자열("1,234,567" / "-1,234" / "" / "-")을 float으로. 못 읽으면 None."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace(" ", "")
    if text in ("", "-", "--"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _entries_for(spec, candidates: list[dict]) -> list[dict]:
    """spec이 가리키는 계정들. 단일 지표는 **우선순위대로** 하나만, 합산 지표는 전부 모은다.

    우선순위가 중요하다. 예를 들어 이자비용은 `이자비용`과 그 상위 계정 `금융원가`가 같은
    손익계산서에 함께 나오는데, 우선순위 없이 "아무거나 먼저 매칭된 것"을 쓰면 회사에 따라
    상위 계정이 잡혀 값이 부풀려진다. 그래서 `account_ids`와 `name_patterns`의 **나열 순서가
    곧 선호 순서**이고, 앞선 후보가 하나라도 맞으면 뒤는 보지 않는다.
    """
    if spec.aggregate == AGGREGATE_SUM:
        # 합산 지표는 선호 순서가 아니라 **합집합**이다 — 이자발생부채는 차입금·사채·리스부채를
        # 모두 더해야 하고, CAPEX는 표준ID로 잡힌 것과 계정명으로만 잡히는 것이 섞일 수 있다.
        chosen: dict[int, dict] = {}
        for index, entry in enumerate(candidates):
            account_id = (entry.get("account_id") or "").strip()
            account_name = (entry.get("account_nm") or "").strip()
            if account_id in spec.account_ids or spec.matches_name(account_name):
                chosen[index] = entry
        return list(chosen.values())

    # 1층: XBRL 표준계정ID — 나열 순서가 선호 순서다.
    for account_id in spec.account_ids:
        matched = [
            entry for entry in candidates if (entry.get("account_id") or "").strip() == account_id
        ]
        if matched:
            return matched
    # 2층: 한글 계정명 — 표준ID가 없거나 매칭되지 않은 회사를 위한 폴백. 여기도 나열 순서대로.
    for pattern in spec.compiled:
        matched = [
            entry
            for entry in candidates
            if spec.matches_name((entry.get("account_nm") or "").strip())
            and pattern.search((entry.get("account_nm") or "").strip())
        ]
        if matched:
            return matched
    return []


def _resolve_metric(entries: list[dict], metric: str) -> tuple[float, str] | None:
    """한 지표의 (값, 계정명 라벨). 못 찾으면 None(결측)."""
    spec = ACCOUNT_SPECS[metric]
    candidates = [
        entry for entry in entries if (entry.get("sj_div") or "") in spec.statements
    ]
    if not candidates:
        return None

    matched = _entries_for(spec, candidates)
    if not matched:
        return None

    if spec.aggregate == AGGREGATE_SUM:
        values = [
            amount
            for amount in (parse_amount(entry.get("_amount")) for entry in matched)
            if amount is not None
        ]
        if not values:
            return None
        label = (
            (matched[0].get("account_nm") or "").strip()
            if len(values) == 1
            else AGGREGATED_LABEL
        )
        return sum(values), label

    # 같은 계정이 여러 번 나오면(연결/별도 혼재 등) 첫 행을 쓴다 — DART는 ord 순으로 준다.
    for entry in matched:
        amount = parse_amount(entry.get("_amount"))
        if amount is not None:
            return amount, (entry.get("account_nm") or "").strip()
    return None


def parse_statements(
    payload: dict, statement_type: str, period_amount_fields: dict[str, str]
) -> pd.DataFrame:
    """응답 하나를 long format으로 바꾼다.

    `period_amount_fields`는 {회계기간 라벨: 금액 필드명} 이다 — 사업보고서 한 번의 응답이
    당기/전기/전전기 3개년을 주므로, 호출부가 어느 필드를 어느 기간으로 볼지 정해 넘긴다
    (예: {"202512": "thstrm_amount", "202412": "frmtrm_amount", "202312": "bfefrmtrm_amount"}).
    """
    entries = payload.get("list") or []
    rows: list[dict] = []
    for period, amount_field in period_amount_fields.items():
        # 기간마다 같은 계정 목록을 다른 금액 필드로 읽는다. `_amount`는 이 함수 안에서만
        # 쓰는 임시 키로, _resolve_metric이 어느 기간을 보는지 한 군데서 정하게 한다.
        period_entries = [{**entry, "_amount": entry.get(amount_field)} for entry in entries]
        for metric in ACCOUNT_SPECS:
            resolved = _resolve_metric(period_entries, metric)
            if resolved is None:
                continue
            value, account_name = resolved
            rows.append(
                {
                    "statement_type": statement_type,
                    "period": period,
                    "item": item_key(metric, account_name or AGGREGATED_LABEL),
                    "value": value,
                    "is_consensus": False,
                }
            )
    return pd.DataFrame(rows, columns=LONG_FORMAT_COLUMNS)


def account_inventory(payload: dict) -> pd.DataFrame:
    """응답에 실제로 들어온 (sj_div, account_id, account_nm)을 전부 덤프한다.

    매핑을 고치려면 "DART가 무슨 계정을 주는가"를 먼저 봐야 한다. `verify_dart_mapping.py`가
    이걸 찍어 표준계정ID·계정명 후보를 확인하는 근거로 쓴다 (`.claude/PROBLEMS.md` #44).
    """
    entries = payload.get("list") or []
    rows = [
        {
            "sj_div": entry.get("sj_div"),
            "account_id": entry.get("account_id"),
            "account_nm": (entry.get("account_nm") or "").strip(),
            "thstrm_amount": parse_amount(entry.get("thstrm_amount")),
        }
        for entry in entries
    ]
    return pd.DataFrame(
        rows, columns=["sj_div", "account_id", "account_nm", "thstrm_amount"]
    )
