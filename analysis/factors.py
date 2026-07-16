"""분석 스코어링에 쓰이는 팩터(컬럼) 목록과 방향성을 정의하는 단일 소스.

'방향성'은 원래 코드의 s 파라미터(1/0/-1)를 의미가 드러나는 이름으로 바꾼 것이다.
"""

from dataclasses import dataclass
from enum import IntEnum


class Direction(IntEnum):
    """percentile 랭킹 방향. 원본 calculating_percentile/get_data의 s 값과 동일하다."""

    HIGHER_IS_BETTER = 0
    LOWER_IS_BETTER_RECIPROCAL = 1
    LOWER_IS_BETTER_NEGATED = -1


@dataclass(frozen=True)
class FactorSpec:
    name: str
    direction: Direction


# --- get_sorting_and_basicscore (VC1) ---
BASIC_SHARE_FACTORS: list[FactorSpec] = [
    FactorSpec(name, Direction.LOWER_IS_BETTER_RECIPROCAL)
    for name in ["PER", "PBR", "PSR", "PCR", "PEGR", "EV/EBITDA", "EV/Revenue"]
]
BASIC_ORIGINAL_FACTORS: list[FactorSpec] = [
    FactorSpec(name, Direction.HIGHER_IS_BETTER)
    for name in [
        "ROE",
        "ROA",
        "Dividend Yield",
        "Market Cap",
        "EPSgrowth",
        "Revenuegrowth",
        "Insiderpercent",
        "Institutionpercent",
        "Debt to Equity",
        "EPS",
        "Net Income",
        "Dividend to Income",
    ]
]
BASIC_REVERSE_FACTORS: list[FactorSpec] = []

# VC1 구성 팩터 목록은 analysis/composite_scores.py의 VC1_FACTORS(접미사 없는
# 원본 이름)로 이동했다 — 여러 점수 계열(S/SS 등)에서 재사용하기 위함.


# --- get_detailscore_and_finalrank ---
# "Buyback to Income"가 아래 두 리스트에 모두 들어있는 것은 원본 코드의 의도치 않은
# 중복으로 보이지만, 두 번째 계산(originalfactor, s=0)이 값을 덮어써서 현재 결과값이
# 정해지는 방식이라 그대로 보존한다. 자세한 내용은 .claude/PROBLEMS.md 참고.
DETAIL_SHARE_FACTORS: list[FactorSpec] = [
    FactorSpec(name, Direction.LOWER_IS_BETTER_RECIPROCAL)
    for name in ["PFCR", "Buyback to Income", "Dividend to Income"]
]
DETAIL_ORIGINAL_FACTORS: list[FactorSpec] = [
    FactorSpec(name, Direction.HIGHER_IS_BETTER)
    for name in [
        "3M Ratio",
        "6M Ratio",
        "1Y Ratio",
        "3M Turnover",
        "1Y Turnover",
        "10D Turnover",
        "3M Overheat",
        "10D Overheat",
        "3M Volatility",
        "1Y Volatility",
        "Buyback Yield",
        "Interest Ratio",
        "Insider Buy Ratio",
        "Asset to Equity",
        "Coverage Ratio",
        "NCAV",
        "Current Ratio",
        "ROC",
        "GPTOA",
        "Asset Turnover",
        "Buyback to Income",
        "Depreciation Capex Ratio",
    ]
]
DETAIL_REVERSE_FACTORS: list[FactorSpec] = [
    FactorSpec(name, Direction.LOWER_IS_BETTER_NEGATED) for name in ["Debt Growth", "ARP"]
]

RELIABILITY_TF_COLUMNS: list[str] = [
    "PER",
    "PBR",
    "PSR",
    "PCR",
    "EV/EBITDA",
    "Debt Growth",
    "ARP",
    "Insider Buy Ratio",
    "Coverage Ratio",
    "Asset to Equity",
    "NCAV",
    "Current Ratio",
    "ROC",
    "GPTOA",
    "Asset Turnover",
    "PFCR",
    "Buyback to Income",
    "Depreciation Capex Ratio",
]


# --- get_standard_data ---
# 원본 3곳(전체/섹터/국가)에 중복 등장하던 컬럼 목록의 단일 소스.
# "Buyback Yield"는 원본에서 두 번 등장했으나(Dividend Yield 뒤, Interest Ratio 앞)
# 두 번째는 단순 복붙 실수로 확인되어 여기서는 한 번만 남긴다.
STANDARD_DATA_FACTORS: list[FactorSpec] = [
    FactorSpec("PER", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("PBR", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("PSR", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("PCR", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("PEGR", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("EV/EBITDA", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("EV/Revenue", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("ROE", Direction.HIGHER_IS_BETTER),
    FactorSpec("ROA", Direction.HIGHER_IS_BETTER),
    FactorSpec("EPSgrowth", Direction.HIGHER_IS_BETTER),
    FactorSpec("Revenuegrowth", Direction.HIGHER_IS_BETTER),
    FactorSpec("Insiderpercent", Direction.HIGHER_IS_BETTER),
    FactorSpec("Institutionpercent", Direction.HIGHER_IS_BETTER),
    FactorSpec("Debt to Equity", Direction.HIGHER_IS_BETTER),
    FactorSpec("EPS", Direction.HIGHER_IS_BETTER),
    FactorSpec("Net Income", Direction.HIGHER_IS_BETTER),
    FactorSpec("Dividend Yield", Direction.HIGHER_IS_BETTER),
    FactorSpec("Buyback Yield", Direction.HIGHER_IS_BETTER),
    FactorSpec("Operating Cashflow", Direction.HIGHER_IS_BETTER),
    FactorSpec("Revenue", Direction.HIGHER_IS_BETTER),
    FactorSpec("Market Cap", Direction.HIGHER_IS_BETTER),
    FactorSpec("3M Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("6M Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("1Y Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("3M Turnover", Direction.HIGHER_IS_BETTER),
    FactorSpec("1Y Turnover", Direction.HIGHER_IS_BETTER),
    FactorSpec("10D Turnover", Direction.HIGHER_IS_BETTER),
    FactorSpec("3M Overheat", Direction.HIGHER_IS_BETTER),
    FactorSpec("10D Overheat", Direction.HIGHER_IS_BETTER),
    FactorSpec("3M Volatility", Direction.HIGHER_IS_BETTER),
    FactorSpec("1Y Volatility", Direction.HIGHER_IS_BETTER),
    FactorSpec("Interest Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("Debt Growth", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("Insider Buy Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("ARP", Direction.LOWER_IS_BETTER_NEGATED),
    FactorSpec("Depreciation Capex Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("Asset to Equity", Direction.HIGHER_IS_BETTER),
    FactorSpec("Coverage Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("NCAV", Direction.HIGHER_IS_BETTER),
    FactorSpec("Current Ratio", Direction.HIGHER_IS_BETTER),
    FactorSpec("ROC", Direction.HIGHER_IS_BETTER),
    FactorSpec("GPTOA", Direction.HIGHER_IS_BETTER),
    FactorSpec("Asset Turnover", Direction.HIGHER_IS_BETTER),
    FactorSpec("PFCR", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("Buyback to Income", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("Dividend to Income", Direction.LOWER_IS_BETTER_RECIPROCAL),
    FactorSpec("Finalscore", Direction.HIGHER_IS_BETTER),
    FactorSpec("Vscore", Direction.HIGHER_IS_BETTER),
    FactorSpec("Mscore", Direction.HIGHER_IS_BETTER),
    FactorSpec("EQC", Direction.HIGHER_IS_BETTER),
    FactorSpec("reliablity", Direction.HIGHER_IS_BETTER),
    FactorSpec("Quant score", Direction.HIGHER_IS_BETTER),
]
