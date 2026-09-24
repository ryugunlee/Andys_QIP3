"""DART 계정 → 정규화 지표 매핑의 단일 소스.

WiseFn은 자기가 만든 **정규화 계정**을 줬다. ACCODE `19xxxx` 계열이 그것이다 —
`190980`(이자발생부채), `191000`(CAPEX), `190560`(매출채권)처럼 회사별 계정 이름 차이를
FnGuide가 미리 흡수해 준 항목이다. **DART는 회사가 공시한 계정을 그대로 준다.**
그래서 매핑이 1:1이 아니라 "여러 계정의 합산 + 이름 변형 흡수"가 된다.

세 층으로 해결한다. 위에서 찾으면 아래는 보지 않는다.

1. **XBRL 표준계정ID**(`account_id`) — 가장 안정적. 회사·연도와 무관하게 같다.
2. **한글 계정명**(`account_nm`) 정규식 — `account_id`가 `"-표준계정코드 미사용-"`인
   회사(적지 않다)를 위한 폴백.
3. **합산 규칙** — `aggregate="sum"`인 지표는 매칭된 계정을 전부 더한다
   (이자발생부채·CAPEX처럼 DART에 단일 계정이 없는 항목).

**`account_ids`와 `name_patterns`의 나열 순서가 곧 선호 순서다.** 앞선 후보가 하나라도 맞으면
뒤는 보지 않는다 — 이자비용과 상위 계정 금융원가처럼 둘 다 존재할 때 어느 쪽을 쓸지는 순서로만
정해진다. 단 `aggregate="sum"`은 선호가 아니라 **합집합**이다(차입금·사채·리스부채를 다 더해야 한다).

찾지 못하면 예외가 아니라 **결측**으로 남긴다 — WiseFn 실패 때와 같은 태도다.
계정 하나 못 찾은 것으로 종목을 잃는 것보다 그 팩터만 비우는 편이 낫다.

> **표준계정ID는 잠정값이다.** IFRS 택사노미 기준으로 채웠으나 실제 공시에서 어떤 ID가
> 오는지는 키가 있는 환경에서 확인해야 한다. `verify_dart_mapping.py`가 표본 종목의
> (sj_div, account_id, account_nm)을 전부 덤프하고 WiseFn 값과 나란히 비교하도록 만든
> 이유가 이것이다. **검증 전에 수집 경로를 바꾸지 않는다** (`.claude/PROBLEMS.md` #44).
"""

import re
from dataclasses import dataclass, field

# 재무제표 구분(sj_div) — DART 응답 값.
BS: str = "BS"  # 재무상태표
IS: str = "IS"  # 손익계산서
CIS: str = "CIS"  # 포괄손익계산서
CF: str = "CF"  # 현금흐름표

# 손익 항목은 회사에 따라 IS 대신 CIS에만 있을 수 있어 둘 다 본다.
_PROFIT_STATEMENTS: tuple[str, ...] = (IS, CIS)

AGGREGATE_FIRST: str = "first"
AGGREGATE_SUM: str = "sum"


@dataclass(frozen=True)
class AccountSpec:
    """정규화 지표 하나를 DART 계정에서 찾아내는 규칙."""

    statements: tuple[str, ...]
    account_ids: tuple[str, ...] = ()
    name_patterns: tuple[str, ...] = ()
    aggregate: str = AGGREGATE_FIRST
    # 합산 지표에서 제외할 계정명 조각 (예: 차입금 합산에서 "상환"·"증가" 같은 현금흐름 항목)
    name_excludes: tuple[str, ...] = ()
    compiled: tuple[re.Pattern, ...] = field(default=(), repr=False, compare=False)

    def matches_name(self, account_name: str) -> bool:
        if any(token in account_name for token in self.name_excludes):
            return False
        return any(pattern.search(account_name) for pattern in self.compiled)


def _spec(
    statements: tuple[str, ...],
    account_ids: tuple[str, ...] = (),
    name_patterns: tuple[str, ...] = (),
    aggregate: str = AGGREGATE_FIRST,
    name_excludes: tuple[str, ...] = (),
) -> AccountSpec:
    return AccountSpec(
        statements=statements,
        account_ids=account_ids,
        name_patterns=name_patterns,
        aggregate=aggregate,
        name_excludes=name_excludes,
        compiled=tuple(re.compile(pattern) for pattern in name_patterns),
    )


# 정규화 지표 이름은 `collection/qip4/series_adapter.py`가 쓰는 것과 같아야 한다 —
# 그래야 소스가 바뀌어도 하류 계산이 그대로 돌아간다.
ACCOUNT_SPECS: dict[str, AccountSpec] = {
    # --- 손익계산서 ---
    "revenue": _spec(
        _PROFIT_STATEMENTS,
        ("ifrs-full_Revenue", "ifrs_Revenue", "dart_Revenue"),
        (r"^매출액$", r"^수익\(매출액\)$", r"^영업수익$", r"^매출$"),
    ),
    "cogs": _spec(
        _PROFIT_STATEMENTS,
        ("ifrs-full_CostOfSales", "ifrs_CostOfSales"),
        (r"^매출원가$", r"^영업비용$"),
    ),
    "gross_profit": _spec(
        _PROFIT_STATEMENTS,
        ("ifrs-full_GrossProfit", "ifrs_GrossProfit"),
        (r"^매출총이익",),
    ),
    "operating_income": _spec(
        _PROFIT_STATEMENTS,
        ("dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"),
        (r"^영업이익", r"^영업손익"),
    ),
    # **나열 순서가 선호 순서다.** 이자비용과 그 상위 계정 금융원가가 같은 손익계산서에 함께
    # 나오는데, WiseFn 202560이 가리킨 것은 이자비용이다. 상위 계정이 먼저 잡히면 값이 부풀려진다.
    "interest_expense": _spec(
        _PROFIT_STATEMENTS,
        ("ifrs-full_InterestExpense", "ifrs-full_FinanceCosts"),
        (r"^이자비용$", r"^금융원가$", r"^금융비용$"),
    ),
    "pretax_income": _spec(
        _PROFIT_STATEMENTS,
        ("ifrs-full_ProfitLossBeforeTax",),
        (r"법인세비용차감전", r"^세전"),
    ),
    "income_tax": _spec(
        _PROFIT_STATEMENTS,
        ("ifrs-full_IncomeTaxExpenseContinuingOperations",),
        (r"^법인세비용",),
    ),
    "net_income": _spec(
        _PROFIT_STATEMENTS,
        ("ifrs-full_ProfitLoss",),
        (r"^당기순이익", r"^당기순손익", r"^분기순이익", r"^반기순이익"),
    ),
    # --- 재무상태표 ---
    "total_assets": _spec((BS,), ("ifrs-full_Assets",), (r"^자산총계$",)),
    "current_assets": _spec((BS,), ("ifrs-full_CurrentAssets",), (r"^유동자산$",)),
    "total_liabilities": _spec((BS,), ("ifrs-full_Liabilities",), (r"^부채총계$",)),
    "current_liabilities": _spec((BS,), ("ifrs-full_CurrentLiabilities",), (r"^유동부채$",)),
    "total_equity": _spec((BS,), ("ifrs-full_Equity",), (r"^자본총계$",)),
    "cash": _spec(
        (BS,),
        ("ifrs-full_CashAndCashEquivalents",),
        (r"현금및현금성자산",),
    ),
    "inventory": _spec((BS,), ("ifrs-full_Inventories",), (r"^재고자산$",)),
    "receivables": _spec(
        (BS,),
        (
            "ifrs-full_TradeAndOtherCurrentReceivables",
            "dart_ShortTermTradeReceivable",
        ),
        (r"^매출채권", r"매출채권및기타"),
    ),
    "payables": _spec(
        (BS,),
        ("ifrs-full_TradeAndOtherCurrentPayables", "dart_ShortTermTradePayables"),
        (r"^매입채무", r"매입채무및기타"),
    ),
    "goodwill": _spec((BS,), ("ifrs-full_Goodwill",), (r"^영업권$",)),
    "deferred_tax_assets": _spec(
        (BS,), ("ifrs-full_DeferredTaxAssets",), (r"이연법인세자산",)
    ),
    "employee_benefit_obligation": _spec(
        (BS,),
        ("ifrs-full_NetDefinedBenefitLiability",),
        (r"확정급여", r"종업원급여", r"퇴직급여충당"),
        aggregate=AGGREGATE_SUM,
    ),
    "pension_plan_assets": _spec(
        (BS,),
        ("ifrs-full_DefinedBenefitPlanAssets",),
        (r"사외적립자산", r"^퇴직연금"),
        aggregate=AGGREGATE_SUM,
    ),
    # 리스부채는 유동·비유동으로 나뉘어 공시된다. WiseFn은 둘을 따로 줬으므로 그 계약을 유지한다.
    "lease_liability": _spec(
        (BS,),
        ("ifrs-full_LeaseLiabilities", "ifrs-full_NoncurrentLeaseLiabilities"),
        (r"^리스부채$", r"^비유동리스부채$"),
        aggregate=AGGREGATE_SUM,
        name_excludes=("유동성", "유동 "),
    ),
    "lease_liability_current": _spec(
        (BS,),
        ("ifrs-full_CurrentLeaseLiabilities",),
        (r"^유동리스부채$", r"^유동성리스부채$"),
        aggregate=AGGREGATE_SUM,
    ),
    # **DART에 단일 계정이 없는 지표 — 합산으로 만든다.**
    # WiseFn 190980(이자발생부채)에 대응. 차입금·사채·리스부채를 모두 더한다.
    "total_debt": _spec(
        (BS,),
        (),
        (r"차입금", r"^사채", r"리스부채"),
        aggregate=AGGREGATE_SUM,
        # 현금흐름표 문구가 재무상태표에 섞여 들어오는 것을 막는다.
        name_excludes=("상환", "증가", "감소", "차입금의", "사채의"),
    ),
    # --- 현금흐름표 ---
    "operating_cash_flow": _spec(
        (CF,),
        ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
        (r"영업활동.*현금흐름",),
    ),
    "depreciation": _spec(
        (CF,),
        ("ifrs-full_DepreciationAndAmortisationExpense",),
        (r"^감가상각비", r"유형자산감가상각"),
        aggregate=AGGREGATE_SUM,
    ),
    # WiseFn 191000(CAPEX)에 대응. 유형·무형자산 취득을 더한다.
    "capex": _spec(
        (CF,),
        (
            "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
        ),
        (r"유형자산의? ?취득", r"무형자산의? ?취득", r"유형자산의? ?증가"),
        aggregate=AGGREGATE_SUM,
        name_excludes=("처분", "감소"),
    ),
    "dividends_paid": _spec(
        (CF,),
        ("ifrs-full_DividendsPaidClassifiedAsFinancingActivities",),
        (r"배당금.*지급", r"^배당금지급"),
        aggregate=AGGREGATE_SUM,
    ),
    "interest_paid": _spec(
        (CF,),
        ("ifrs-full_InterestPaidClassifiedAsOperatingActivities",),
        (r"이자.*지급", r"^이자지급"),
        aggregate=AGGREGATE_SUM,
    ),
    "advances_received": _spec(
        (CF,),
        (),
        (r"선수금", r"계약부채"),
        aggregate=AGGREGATE_SUM,
        name_excludes=("감소",),
    ),
    "treasury_stock_acquisition": _spec(
        (CF,),
        ("ifrs-full_PaymentsToAcquireOrRedeemEntitysShares",),
        (r"자기주식의? ?취득", r"자기주식의? ?매입"),
        aggregate=AGGREGATE_SUM,
    ),
    "treasury_stock_disposal": _spec(
        (CF,),
        ("ifrs-full_ProceedsFromSaleOrIssueOfTreasuryShares",),
        (r"자기주식의? ?처분",),
        aggregate=AGGREGATE_SUM,
    ),
}

# `item` 컬럼 접두사 규약: "<지표>:<한글 계정명>".
# WiseFn이 "ACCODE:계정명"이었던 것과 같은 모양이라 읽는 쪽(series_adapter,
# presentation/financial_series)이 접두사 매칭 방식을 그대로 쓸 수 있다.
ITEM_SEPARATOR: str = ":"
# 합산으로 만든 항목의 계정명 자리 (어느 계정을 더했는지는 검증 스크립트가 보여준다).
AGGREGATED_LABEL: str = "합산"


def item_key(metric: str, account_name: str) -> str:
    """long format의 `item` 값을 만든다."""
    return f"{metric}{ITEM_SEPARATOR}{account_name}"


def metric_of(item: str) -> str:
    """`item` 값에서 정규화 지표 이름만 떼어낸다."""
    return item.split(ITEM_SEPARATOR, 1)[0]
