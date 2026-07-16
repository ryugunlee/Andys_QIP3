"""섹터/산업 자체의 상대 평가: 그룹별 팩터 중앙값 + 그룹 간 점수.

각 섹터(산업)의 주요 팩터 **중앙값**을 집계한 뒤, "섹터가 행"인 표를 모집단으로
같은 점수 엔진(퍼센타일 + 스탠다드)을 적용한다. 결과로 어느 섹터/산업이 다른
섹터/산업 대비 우위·열위인지 0~100 점수로 비교할 수 있다.

금액 팩터(시총·매출 등)는 통화·규모 집계의 의미가 약해 제외하고,
종합점수(Finalscore 등)의 중앙값은 그룹의 전반적 우위를 보여주므로 포함한다.
"""

import pandas as pd

from analysis.factors import STANDARD_DATA_FACTORS, FactorSpec
from analysis.percentile import calculating_percentile
from analysis.score_pipeline import MIN_GROUP_POPULATION
from analysis.standard_score import calculating_standard, numeric_values

# 그룹 집계에서 제외하는 절대 금액 팩터
_EXCLUDED_MONEY_FACTORS: set[str] = {
    "Market Cap",
    "Revenue",
    "Operating Cashflow",
    "Net Income",
    "EPS",
}

GROUP_SUMMARY_FACTORS: list[FactorSpec] = [
    spec for spec in STANDARD_DATA_FACTORS if spec.name not in _EXCLUDED_MONEY_FACTORS
]

_GROUP_VALUE_COLUMN = "group_value"


def compute_group_summary(scored: pd.DataFrame, group_column: str) -> pd.DataFrame:
    """그룹(섹터/산업)별 팩터 중앙값과 그룹 간 상대 점수를 long format으로 반환한다.

    반환 컬럼: group_value, ticker_count, factor, median_value, score_s, score_ss
    표본이 MIN_GROUP_POPULATION 미만인 그룹은 순위 왜곡을 막기 위해 제외한다.
    """
    if group_column not in scored.columns or scored.empty:
        return _empty_summary()

    valid = scored[scored[group_column].notna()]
    counts = valid.groupby(group_column).size()
    large_groups = counts[counts >= MIN_GROUP_POPULATION].index
    valid = valid[valid[group_column].isin(large_groups)]
    if valid.empty:
        return _empty_summary()

    # 그룹별 중앙값 표 ("그룹이 행"인 모집단)
    factor_names = [spec.name for spec in GROUP_SUMMARY_FACTORS if spec.name in valid.columns]
    numeric = valid[factor_names].apply(numeric_values)
    numeric[_GROUP_VALUE_COLUMN] = valid[group_column].astype(str)
    table = numeric.groupby(_GROUP_VALUE_COLUMN).median().reset_index()
    table["ticker_count"] = table[_GROUP_VALUE_COLUMN].map(counts).astype(int)

    # 그룹들 자체를 모집단으로 두 계열 점수 적용
    for spec in GROUP_SUMMARY_FACTORS:
        if spec.name not in table.columns:
            continue
        table = calculating_percentile(
            table, spec.name, spec.direction, score_column=f"{spec.name}__score_s"
        )
        table = calculating_standard(
            table, spec.name, spec.direction, score_column=f"{spec.name}__score_ss"
        )

    rows: list[dict[str, object]] = []
    for record in table.to_dict("records"):  # 컬럼명에 공백/특수문자가 있어 itertuples 부적합
        for name in factor_names:
            rows.append(
                {
                    "group_value": record[_GROUP_VALUE_COLUMN],
                    "ticker_count": record["ticker_count"],
                    "factor": name,
                    "median_value": record.get(name),
                    "score_s": record.get(f"{name}__score_s"),
                    "score_ss": record.get(f"{name}__score_ss"),
                }
            )
    return pd.DataFrame(rows)


def _empty_summary() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["group_value", "ticker_count", "factor", "median_value", "score_s", "score_ss"]
    )
