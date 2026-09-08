"""안정성 관문(Pass/Fail)과 효율성 승수 판정.

수집 계층은 원시 숫자만 낸다. 임계값 비교는 전부 여기서 한다 — 그래야 규칙이 바뀌어도
몇 시간짜리 재수집 없이 재채점만으로 반영된다.

**이 코드베이스에는 컴포지트에 곱셈을 적용하는 개념이 없었다.** 그래서 "탈락"을
불리언이 아니라 **승수 0.0**으로 표현한다 — 그러면 종합점수가 자동으로 0이 되어
순위에서 자연히 밀려나고, 분석 계층은 여전히 "연속값의 곱"만 하게 된다.

**자산형(은행·보험·증권·지주)은 현금흐름 기반 4개 조건 대신 전용 조건 2개를 쓴다.**
은행에게 이자비용은 예금 조달원가라 이자보상배율이 1 미만인 것이 정상이고, 영업현금흐름도
대출 잔액 변동에 따라 크게 흔들려 부실 신호로 읽을 수 없다. 그대로 두면 금융 섹터 전체가
구조적으로 탈락한다(실측: 은행·증권 5종목 전부 S3 탈락).

다만 **면제만 하면 자산형에 관문이 비어버리므로**, 금융사에도 의미가 살아있는 두 조건으로
대체한다:

    F1  최근 3년 중 당기순손실 2년 이상        (S1의 대응물)
    F2  자기자본비율(자본총계÷자산총계) < 4%   (자본적정성 하한)

자산 품질 경고(실질 자기자본·영업권)는 자산형에도 그대로 적용한다 — 현금흐름이 아니라
자산의 실체를 묻는 지표라 업종과 무관하게 유효하다.

관문 결과와 사유는 문자열 컬럼으로 낸다. `analysis/detail_score.py`가 이미
`Value risk`를 "O"/"X"로 내보내고 있어 새 규약이 아니다. 사유는 **코드**로만 남기고
한국어 변환은 표현 계층이 맡는다(`presentation/`이 언어를 담당하는 기존 분업).
"""

import numpy as np
import pandas as pd

import analysis.qip4_weights as w
from analysis.score_pipeline import MIN_GROUP_POPULATION
from collection.sector_groups import GROUP_ASSET

# 관문 결과값.
_SECTOR_GROUP_COLUMN: str = "QIP4 Sector Group"

GATE_PASS: str = "PASS"
GATE_FAIL: str = "FAIL"

# 출력 컬럼 이름.
GATE_COLUMN: str = "QIP4 Stability Gate"
GATE_REASONS_COLUMN: str = "QIP4 Gate Reasons"
WARNINGS_COLUMN: str = "QIP4 Warnings"
ALARM_COUNT_COLUMN: str = "QIP4 Efficiency Alarms"
ALARM_REASONS_COLUMN: str = "QIP4 Efficiency Reasons"
EFFICIENCY_MULTIPLIER_COLUMN: str = "QIP4 Efficiency Multiplier"
VALUE_TRAP_MULTIPLIER_COLUMN: str = "QIP4 Value Trap Multiplier"

# 사유 코드. 표현 계층이 한국어로 바꾼다.
REASON_SEPARATOR: str = "|"
REASON_S1: str = "S1_OCF"
REASON_S2: str = "S2_CASH_CONVERSION"
REASON_S3: str = "S3_INTEREST"
REASON_REPAYMENT: str = "REPAYMENT_YEARS"
REASON_F1: str = "F1_NET_LOSS"
REASON_F2: str = "F2_EQUITY_RATIO"
WARN_TANGIBLE: str = "TANGIBLE_EQUITY"
WARN_GOODWILL: str = "GOODWILL"
ALARM_INVENTORY: str = "INVENTORY"
ALARM_RECEIVABLES: str = "RECEIVABLES"
ALARM_ACCRUAL: str = "ACCRUAL"
ALARM_CCC: str = "CCC"


def _column(df: pd.DataFrame, name: str) -> pd.Series:
    """없을 수 있는 컬럼을 NaN 시리즈로 안전하게 읽는다."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def _join_reasons(flags: dict[str, pd.Series]) -> pd.Series:
    """조건별 불리언 시리즈를 "CODE|CODE" 문자열로 합친다."""
    joined = pd.Series("", index=next(iter(flags.values())).index)
    for code, flag in flags.items():
        addition = flag.map({True: code, False: ""}).fillna("")
        joined = joined.str.cat(addition, sep=REASON_SEPARATOR).str.strip(REASON_SEPARATOR)
        # 연속된 구분자(빈 코드가 사이에 낀 경우)를 정리한다.
        joined = joined.str.replace(
            f"{REASON_SEPARATOR}{REASON_SEPARATOR}", REASON_SEPARATOR, regex=False
        )
    return joined


def _repayment_limit(df: pd.DataFrame) -> pd.Series:
    """종목별 상환연수 임계값. 유틸리티·리츠·인프라는 완화 임계를 쓴다."""
    tolerant = _column(df, "QIP4 Leverage Tolerant").fillna(0) > 0
    return pd.Series(
        np.where(
            tolerant,
            w.GATE_MAX_REPAYMENT_YEARS_TOLERANT,
            w.GATE_MAX_REPAYMENT_YEARS,
        ),
        index=df.index,
    )


def _accrual_alarm(df: pd.DataFrame) -> pd.Series:
    """발생액이 **업종 내** 상위 분위수를 넘는가 — 유일하게 횡단면인 경보.

    업종 정보가 없거나 표본이 너무 적으면 경보를 켜지 않는다(무죄 추정).
    """
    accrual = _column(df, "QIP4 Accrual Ratio")
    if "Industry" not in df.columns:
        return pd.Series(False, index=df.index)

    labels = df["Industry"]
    # 표본이 적은 업종에서는 상위 10% 컷라인이 개별 종목 한두 개로 정해져 의미가 없다.
    # 다른 모집단 계산과 같은 문턱(MIN_GROUP_POPULATION)을 써서 경보를 끈다.
    group_sizes = labels.groupby(labels).transform("size")
    large_enough = labels.notna() & (group_sizes >= MIN_GROUP_POPULATION)

    cutoff = accrual.groupby(labels).transform(
        lambda values: values.quantile(w.ACCRUAL_ALARM_QUANTILE)
    )
    return (accrual > cutoff) & accrual.notna() & cutoff.notna() & large_enough


def _is_asset_type(df: pd.DataFrame) -> pd.Series:
    """자산형(은행·보험·증권·지주)인가.

    이 종목들은 현금흐름 기반 조건(S1~S3·상환연수) 대신 자산형 전용 조건(F1·F2)을 쓴다.
    이자비용이 조달원가라 이자보상배율이 1 미만인 것이 정상이고, 영업현금흐름도
    대출·투자자산 잔액 변동에 따라 흔들려 부실 신호로 읽을 수 없기 때문이다.
    """
    if _SECTOR_GROUP_COLUMN not in df.columns:
        return pd.Series(False, index=df.index)
    return df[_SECTOR_GROUP_COLUMN] == GROUP_ASSET


def attach_gate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """관문 결과·경고·효율성 승수·밸류트랩 승수를 df에 붙인다(in-place)."""
    # --- 안정성 관문 ---
    # 각 조건은 "확실히 위반"일 때만 True다. 값이 없으면(None/NaN) 판정을 유보해
    # 통과시킨다 — 데이터 부족만으로 종목을 죽이지 않는다.
    fail_flags = {
        REASON_S1: _column(df, "QIP4 OCF Negative Years") >= w.GATE_MAX_NEGATIVE_OCF_YEARS,
        REASON_S2: _column(df, "QIP4 Cash Conversion 3Y") < w.GATE_MIN_CASH_CONVERSION,
        REASON_S3: _column(df, "QIP4 Interest Coverage Fail Years")
        >= w.GATE_MAX_INTEREST_FAIL_YEARS,
        REASON_REPAYMENT: _column(df, "QIP4 Debt Repayment Years") > _repayment_limit(df),
    }
    fail_flags = {code: flag.fillna(False) for code, flag in fail_flags.items()}

    # 자산형은 현금흐름 기반 조건을 끄고 전용 조건(F1·F2)으로 대체한다.
    asset_type = _is_asset_type(df)
    fail_flags = {code: flag & ~asset_type for code, flag in fail_flags.items()}
    fail_flags[REASON_F1] = (
        _column(df, "QIP4 Net Loss Years") >= w.GATE_MAX_NET_LOSS_YEARS
    ).fillna(False) & asset_type
    fail_flags[REASON_F2] = (
        _column(df, "QIP4 Equity Ratio") < w.GATE_MIN_EQUITY_RATIO
    ).fillna(False) & asset_type

    failed = pd.Series(False, index=df.index)
    for flag in fail_flags.values():
        failed = failed | flag

    df[GATE_COLUMN] = np.where(failed, GATE_FAIL, GATE_PASS)
    df[GATE_REASONS_COLUMN] = _join_reasons(fail_flags)

    # --- 안정성 3단계: 경고 (탈락 아님) ---
    warn_flags = {
        WARN_TANGIBLE: (
            _column(df, "QIP4 Tangible Equity Ratio") < w.WARN_MIN_TANGIBLE_EQUITY_RATIO
        ).fillna(False),
        WARN_GOODWILL: (
            _column(df, "QIP4 Goodwill to Assets") > w.WARN_MAX_GOODWILL_TO_ASSETS
        ).fillna(False),
    }
    df[WARNINGS_COLUMN] = _join_reasons(warn_flags)

    # --- 효율성 감사 ---
    inventory_alarm = _column(df, "QIP4 Inventory Alarm").fillna(0) > 0
    # 재고 경보는 선수금이 늘고 있으면 해제한다 — 선제 확보와 재고 적체를 가르는
    # 관측 가능한 신호다(원 규칙의 수주잔고는 정기 공시가 아니라 수집 불가).
    advances_growing = _column(df, "QIP4 Advances Growing").fillna(0) > 0
    inventory_alarm = inventory_alarm & ~advances_growing

    alarm_flags = {
        ALARM_INVENTORY: inventory_alarm,
        ALARM_RECEIVABLES: _column(df, "QIP4 Receivables Alarm").fillna(0) > 0,
        ALARM_ACCRUAL: _accrual_alarm(df),
        ALARM_CCC: _column(df, "QIP4 CCC Deteriorating").fillna(0) > 0,
    }
    alarm_count = sum(flag.astype(int) for flag in alarm_flags.values())
    df[ALARM_COUNT_COLUMN] = alarm_count
    df[ALARM_REASONS_COLUMN] = _join_reasons(alarm_flags)
    df[EFFICIENCY_MULTIPLIER_COLUMN] = alarm_count.map(w.EFFICIENCY_MULTIPLIERS).fillna(
        w.EFFICIENCY_FAIL_MULTIPLIER
    )

    # --- 밸류 트랩 보정 ---
    trap = pd.Series(1.0, index=df.index)
    shrinking = (_column(df, "QIP4 Revenue CAGR") < 0).fillna(False)
    trap = trap.where(~shrinking, trap * w.VALUE_TRAP_SHRINKING_REVENUE_MULTIPLIER)

    no_payout = (
        (_column(df, "QIP4 Dividend Payout Yield").fillna(0) <= 0)
        & (_column(df, "Buyback Yield").fillna(0) <= 0)
        & (_column(df, "QIP4 Net Cash Years").fillna(0) >= w.VALUE_TRAP_NET_CASH_YEARS)
    )
    trap = trap.where(~no_payout, trap * w.VALUE_TRAP_IDLE_NET_CASH_MULTIPLIER)
    df[VALUE_TRAP_MULTIPLIER_COLUMN] = trap

    return df
