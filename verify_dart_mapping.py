"""DART 계정 매핑을 실제 응답으로 검증한다 (전환 전 필수 단계).

`collection/dart/accounts.py`의 표준계정ID·계정명 패턴은 IFRS 택사노미 기준의 **잠정값**이다.
실제 공시에서 어떤 `account_id`/`account_nm`이 오는지 확인하지 않고 수집 경로를 바꾸면,
매핑이 틀린 팩터가 조용히 잘못된 값으로 채워진다. 종목 수 급감 가드(PROBLEMS #43)는
**개수만** 보므로 값의 오류는 잡지 못한다.

이 스크립트가 하는 일 — 업종이 다른 표본 종목마다:

1. **계정 덤프**: DART가 실제로 준 (sj_div, account_id, account_nm, 금액)을 전부 CSV로 남긴다.
   매핑을 고칠 때 봐야 하는 유일한 근거다.
2. **매핑 결과**: 32개 정규화 지표 중 무엇이 풀렸고 무엇이 결측인지.
3. **WiseFn 대조**: 같은 종목·같은 회계기간의 WiseFn 값과 나란히 놓고 상대오차를 낸다.

`DART_API_KEY`가 필요하다. 로컬 `.env` 또는 Actions Secrets에 있어야 한다
(`.github/workflows/verify-dart.yml`이 Actions에서 돌리는 통로다).

사용법:
    python verify_dart_mapping.py                       # 기본 표본
    python verify_dart_mapping.py 005930 055550         # 종목 지정
    python verify_dart_mapping.py --out-dir qipinfos/dart_verify
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from collection.dart import client, statements as dart_statements
from collection.dart.accounts import ACCOUNT_SPECS, metric_of
from collection.constants import NAVER_EOK_TO_WON
from collection.dart.parsers import account_inventory

# 업종 구조가 서로 다른 표본 — 매핑이 제조업에만 맞는 것을 잡아내기 위한 구성이다.
# 금융지주·은행은 손익 계정 트리가 아예 다르고, 유틸리티는 유형자산·차입금 비중이 크다.
DEFAULT_SAMPLE_TICKERS: tuple[str, ...] = (
    "005930",  # 삼성전자 — 제조 대형주 (WiseFn 실측 기준값이 있는 종목)
    "055550",  # 신한지주 — 금융지주 (당기순이익 계정이 다른 대표 사례)
    "015760",  # 한국전력 — 유틸리티 (차입금·CAPEX 비중 큼)
    "068270",  # 셀트리온 — 바이오 (무형자산·연구개발)
    "005380",  # 현대차 — 자동차 (금융 자회사 연결)
    "035420",  # NAVER — 인터넷 (매출원가 구조가 다름)
)

# 상대오차가 이 값을 넘으면 매핑을 의심해야 한다.
MISMATCH_TOLERANCE: float = 0.01

# WiseFn 연간 재무제표의 statement_type (collection/naver/naver_stock.py 규약).
_WISE_ANNUAL_STATEMENTS: tuple[str, ...] = (
    "wise_income_statement",
    "wise_balance_sheet",
    "wise_cash_flow",
)

DEFAULT_OUT_DIR = Path("qipinfos/dart_verify")
# 검증은 최근 3개년만 본다 — 매핑이 맞는지 보는 데는 충분하고 호출을 아낀다.
VERIFY_YEARS: int = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DART 계정 매핑을 실제 응답으로 검증하고 WiseFn 값과 대조한다."
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        default=list(DEFAULT_SAMPLE_TICKERS),
        help=f"검증할 종목코드 (기본값: {' '.join(DEFAULT_SAMPLE_TICKERS)})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"계정 덤프·대조표를 쓸 폴더 (기본값: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--skip-wise",
        action="store_true",
        help="WiseFn 대조를 건너뛴다 (DART 계정 덤프와 매핑 결과만 본다)",
    )
    return parser.parse_args()


def dart_metrics(rows: pd.DataFrame) -> dict[str, dict[str, float]]:
    """DART long format → {지표: {회계기간: 값}}."""
    if rows.empty:
        return {}
    result: dict[str, dict[str, float]] = {}
    for row in rows.itertuples():
        result.setdefault(metric_of(row.item), {})[row.period] = float(row.value)
    return result


# 정규화 지표 → WiseFn ACCODE. `collection/qip4/series_adapter.py`의 표는 23개 지표만 담고
# 있어서(하류 계산에 쓰는 것만) 32개 전부를 대조하려면 여기서 직접 매핑해야 한다.
# 값은 `collection/constants.py`의 NAVER_WISE_ACCODE_* 와 같다.
_WISE_ACCODES: dict[str, str] = {
    "revenue": "200000", "cogs": "200360", "gross_profit": "200810",
    "operating_income": "201370", "interest_expense": "202560",
    "pretax_income": "203120", "income_tax": "203130", "net_income": "203170",
    "total_assets": "110000", "current_assets": "112830",
    "total_liabilities": "130000", "current_liabilities": "131580",
    "total_equity": "120000", "cash": "190650", "inventory": "112840",
    "receivables": "190560", "payables": "132010", "goodwill": "190170",
    "deferred_tax_assets": "112340", "employee_benefit_obligation": "130880",
    "pension_plan_assets": "190400", "lease_liability": "190780",
    "lease_liability_current": "131850", "total_debt": "190980",
    "operating_cash_flow": "400000", "depreciation": "400140", "capex": "191000",
    "dividends_paid": "404320", "interest_paid": "402100",
    "advances_received": "401820", "treasury_stock_acquisition": "404220",
    "treasury_stock_disposal": "403890",
}


def wise_metrics(ticker: str) -> dict[str, dict[str, float]]:
    """WiseFn 경로의 같은 지표 시계열. 억원 → 원으로 환산해 DART와 단위를 맞춘다."""
    # 지연 import — WiseFn 대조를 건너뛸 때 네이버 모듈을 불러오지 않는다.
    from collection.naver.naver_stock import NaverStock

    stock = NaverStock(ticker)
    stock.fetch()
    if not stock.is_valid:
        return {}
    rows = stock.to_financial_statement_rows()
    if rows.empty:
        return {}
    annual = rows[
        rows["statement_type"].isin(_WISE_ANNUAL_STATEMENTS) & ~rows["is_consensus"]
    ]
    result: dict[str, dict[str, float]] = {}
    for metric, accode in _WISE_ACCODES.items():
        matched = annual[annual["item"].str.startswith(f"{accode}:")]
        if matched.empty:
            continue
        result[metric] = {
            str(row.period): float(row.value) * NAVER_EOK_TO_WON
            for row in matched.itertuples()
        }
    return result


def compare(
    ticker: str,
    dart: dict[str, dict[str, float]],
    wise: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """지표×회계기간 대조표. 두 소스에 모두 있는 기간만 비교한다."""
    records: list[dict] = []
    for metric in ACCOUNT_SPECS:
        dart_periods = dart.get(metric) or {}
        wise_periods = wise.get(metric) or {}
        shared = sorted(set(dart_periods) & set(wise_periods), reverse=True)
        if not shared:
            records.append(
                {
                    "ticker": ticker,
                    "metric": metric,
                    "period": "",
                    "dart": dart_periods.get(max(dart_periods)) if dart_periods else None,
                    "wise": wise_periods.get(max(wise_periods)) if wise_periods else None,
                    "relative_error": None,
                    "verdict": "겹치는 기간 없음",
                }
            )
            continue
        for period in shared:
            dart_value, wise_value = dart_periods[period], wise_periods[period]
            scale = max(abs(dart_value), abs(wise_value))
            error = abs(dart_value - wise_value) / scale if scale else 0.0
            records.append(
                {
                    "ticker": ticker,
                    "metric": metric,
                    "period": period,
                    "dart": dart_value,
                    "wise": wise_value,
                    "relative_error": error,
                    "verdict": "일치" if error <= MISMATCH_TOLERANCE else "불일치",
                }
            )
    return pd.DataFrame(records)


def _report_one(ticker: str, out_dir: Path, skip_wise: bool) -> pd.DataFrame:
    print(f"\n{'=' * 70}\n{ticker}\n{'=' * 70}")
    corp_code = client.corp_code_for(ticker)
    latest_year = dart_statements.latest_annual_year(date.today())

    # 1) 계정 덤프 — 매핑을 고칠 때 보는 근거.
    payload = dart_statements.fetch_payload(corp_code, latest_year, dart_statements.REPORT_ANNUAL)
    if payload is None:
        print(f"  DART 응답 없음 (corp_code={corp_code}, {latest_year} 사업보고서)")
        return pd.DataFrame()
    inventory = account_inventory(payload)
    inventory_path = out_dir / f"{ticker}-accounts-{latest_year}.csv"
    inventory.to_csv(inventory_path, index=False, encoding="utf-8-sig")
    print(f"  계정 {len(inventory)}개 덤프 → {inventory_path}")
    print(
        "  표준계정ID 있는 계정: "
        f"{int((inventory['account_id'] != '-표준계정코드 미사용-').sum())} / {len(inventory)}"
    )

    # 2) 매핑 결과.
    rows = dart_statements.fetch_annual(corp_code, latest_year, VERIFY_YEARS)
    dart = dart_metrics(rows)
    missing = [metric for metric in ACCOUNT_SPECS if metric not in dart]
    print(f"  매핑 성공 {len(dart)}/{len(ACCOUNT_SPECS)} 지표")
    if missing:
        print(f"  결측 지표: {', '.join(missing)}")

    if skip_wise:
        return pd.DataFrame()

    # 3) WiseFn 대조.
    try:
        wise = wise_metrics(ticker)
    except Exception as error:  # 네이버가 막혀 있어도 DART 덤프는 살린다
        print(f"  WiseFn 대조 건너뜀 — {type(error).__name__}: {error}")
        return pd.DataFrame()
    if not wise:
        print("  WiseFn 데이터를 받지 못해 대조 생략")
        return pd.DataFrame()

    table = compare(ticker, dart, wise)
    mismatched = table[table["verdict"] == "불일치"]
    print(
        f"  대조: 일치 {int((table['verdict'] == '일치').sum())}건 /"
        f" 불일치 {len(mismatched)}건 / 비교불가 {int((table['verdict'] == '겹치는 기간 없음').sum())}건"
    )
    if not mismatched.empty:
        print("  --- 불일치 상위 ---")
        worst = mismatched.nlargest(8, "relative_error")
        for row in worst.itertuples():
            print(
                f"    {row.metric:28} {row.period}  DART={row.dart:>18,.0f}"
                f"  WiseFn={row.wise:>18,.0f}  오차={row.relative_error:.1%}"
            )
    return table


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    try:
        client.load_corp_codes()
    except client.DartError as error:
        sys.exit(f"[verify_dart] {error}")

    tables = [
        _report_one(ticker, args.out_dir, args.skip_wise) for ticker in args.tickers
    ]
    tables = [table for table in tables if not table.empty]
    if not tables:
        print("\n대조표가 비었습니다 (WiseFn 대조를 건너뛰었거나 데이터를 받지 못했습니다).")
        return

    merged = pd.concat(tables, ignore_index=True)
    comparison_path = args.out_dir / "comparison.csv"
    merged.to_csv(comparison_path, index=False, encoding="utf-8-sig")

    print(f"\n{'=' * 70}\n전체 요약\n{'=' * 70}")
    summary = (
        merged.groupby("metric")["verdict"]
        .value_counts()
        .unstack(fill_value=0)
        .reindex(columns=["일치", "불일치", "겹치는 기간 없음"], fill_value=0)
    )
    # 손볼 지표를 위로 올린다.
    summary = summary.sort_values(["불일치", "겹치는 기간 없음"], ascending=False)
    print(summary.to_string())
    print(f"\n대조표 전체 → {comparison_path}")

    suspect = summary[(summary["불일치"] > 0) | (summary["일치"] == 0)]
    if not suspect.empty:
        print(
            f"\n손봐야 할 지표 {len(suspect)}개: {', '.join(suspect.index)}\n"
            "→ 위에 덤프된 *-accounts-*.csv에서 실제 account_id/account_nm을 확인해"
            " collection/dart/accounts.py를 고치세요."
        )


if __name__ == "__main__":
    main()
