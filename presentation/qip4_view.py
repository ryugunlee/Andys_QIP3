"""QIP4 관문·경보 코드 → 한국어 표시 문구와 평가기준 카드.

분석 계층(`analysis/qip4_gate.py`)은 사유를 **코드**로만 남긴다("S1_OCF|REPAYMENT_YEARS").
언어는 표현 계층의 책임이라, 코드→한국어 변환은 이 파일 한 곳에만 둔다
(`presentation/korean_names.py`가 종목명을 맡는 것과 같은 층위).

여기에는 "무엇에 걸렸는가"(사유 목록)뿐 아니라 **"어떤 기준으로 봤는가"**(평가기준
카드)도 함께 산다. 임계값 문구는 `analysis/qip4_weights.py`의 상수를 그대로 끼워
만들기 때문에, 규칙이 바뀌면 화면 문구도 따라 바뀐다.
"""

from dataclasses import dataclass

import analysis.qip4_weights as w
from analysis.qip4_gate import (
    ALARM_ACCRUAL,
    ALARM_CCC,
    ALARM_INVENTORY,
    ALARM_RECEIVABLES,
    GATE_FAIL,
    REASON_F1,
    REASON_F2,
    REASON_REPAYMENT,
    REASON_S1,
    REASON_S2,
    REASON_S3,
    REASON_SEPARATOR,
    WARN_GOODWILL,
    WARN_TANGIBLE,
)
from collection.sector_groups import GROUP_ASSET
from presentation.formatters import format_metric
from presentation.metrics import MetricFormat

_SECTOR_GROUP_VALUE = "QIP4 Sector Group"

# 평가기준 판정 상태. 화면 클래스명(gate-status-*)과 같은 값을 쓴다.
_STATUS_FAIL = "fail"
_STATUS_WARN = "warn"
_STATUS_PASS = "pass"
_STATUS_UNKNOWN = "unknown"

# 상태 라벨은 기준의 성격에 따라 다르다 — 관문은 "탈락/통과", 경고·경보는 "경고/이상 없음".
_KIND_GATE = "gate"
_KIND_WARNING = "warning"
_KIND_ALARM = "alarm"

_STATUS_LABELS: dict[tuple[str, str], str] = {
    (_KIND_GATE, _STATUS_FAIL): "탈락",
    (_KIND_GATE, _STATUS_PASS): "통과",
    (_KIND_WARNING, _STATUS_WARN): "경고",
    (_KIND_WARNING, _STATUS_PASS): "해당 없음",
    (_KIND_ALARM, _STATUS_WARN): "경보",
    (_KIND_ALARM, _STATUS_PASS): "이상 없음",
}
_UNKNOWN_LABEL = "판정 불가"

# 기준이 걸렸을 때 켜지는 상태 (관문은 탈락, 나머지는 경고)
_FIRED_STATUS: dict[str, str] = {
    _KIND_GATE: _STATUS_FAIL,
    _KIND_WARNING: _STATUS_WARN,
    _KIND_ALARM: _STATUS_WARN,
}


@dataclass(frozen=True)
class _CriterionSpec:
    """평가기준 한 줄의 정의. 사유 문구와 설명을 한곳에서 관리한다."""

    code: str
    name: str  # 카드 제목 ("S1 · 영업활동현금흐름")
    reason: str  # 걸렸을 때 요약 목록에 쓰는 한 줄
    rule: str  # 임계값 — "무엇을 넘으면 걸리는가"
    description: str  # 왜 이 기준을 보는가
    value_column: str | None  # 판정 근거 컬럼 (없으면 데이터 유무를 묻지 않는다)
    value_format: MetricFormat = MetricFormat.NUMBER
    value_label: str = "측정값"
    # 0/1 플래그 컬럼은 "0.00" 같은 숫자를 보여줘봐야 읽을 것이 없다.
    # 데이터가 있는지만 확인하고 측정값 줄은 내보내지 않는다.
    show_value: bool = True


@dataclass(frozen=True)
class _GroupSpec:
    """평가기준 묶음. 자산형/비자산형에 따라 어떤 묶음을 쓸지 갈린다."""

    title: str
    note: str | None
    kind: str
    specs: tuple[_CriterionSpec, ...]


# --- 안정성 관문: 현금흐름 기반 (일반 기업) ---
_CASHFLOW_GATE_SPECS: tuple[_CriterionSpec, ...] = (
    _CriterionSpec(
        code=REASON_S1,
        name="S1 · 영업활동현금흐름",
        reason="영업활동현금흐름이 3년 중 2년 이상 음수",
        rule=(
            f"최근 3년 중 영업활동현금흐름이 음수인 해가 "
            f"{w.GATE_MAX_NEGATIVE_OCF_YEARS}년 이상이면 탈락"
        ),
        description=(
            "장사를 해서 실제로 현금이 들어오는지 묻는 가장 기본적인 조건이다. "
            "이익은 회계 처리로 만들 수 있지만 현금은 그렇지 않다. 영업에서 현금이 "
            "계속 빠져나가는 회사는 성장 중이더라도 외부 자금에 생존을 의존한다."
        ),
        value_column="QIP4 OCF Negative Years",
        value_format=MetricFormat.COUNT,
        value_label="최근 3년 중 음수 연수",
    ),
    _CriterionSpec(
        code=REASON_S2,
        name="S2 · 현금전환율",
        reason="누적 현금전환율이 0.7 미만 (이익이 현금으로 들어오지 않음)",
        rule=(
            f"3년 누적 영업활동현금흐름 ÷ 3년 누적 순이익이 "
            f"{w.GATE_MIN_CASH_CONVERSION} 미만이면 탈락"
        ),
        description=(
            "장부에 적힌 이익이 실제 현금으로 얼마나 들어왔는지 보는 비율이다. "
            "1에 가까울수록 이익과 현금이 일치한다. 낮다면 매출채권·재고에 이익이 "
            "묶여 있거나 이익 자체가 부풀려졌을 가능성을 의심해야 한다. "
            "단년도는 운전자본 사정으로 흔들리므로 3년 누적으로 본다."
        ),
        value_column="QIP4 Cash Conversion 3Y",
    ),
    _CriterionSpec(
        code=REASON_S3,
        name="S3 · 이자보상배율",
        reason="이자보상배율이 2년 연속 1 미만 (영업이익으로 이자를 못 냄)",
        rule=(
            f"이자보상배율이 1 미만인 해가 "
            f"{w.GATE_MAX_INTEREST_FAIL_YEARS}년 연속이면 탈락"
        ),
        description=(
            "영업이익으로 이자비용을 감당하는지 본다. 1 미만은 번 돈으로 이자도 "
            "못 낸다는 뜻이라, 빚으로 빚을 갚는 구간에 들어섰다는 신호다. "
            "한 해는 업황 탓일 수 있어 2년 연속일 때만 탈락시킨다."
        ),
        value_column="QIP4 Interest Coverage Fail Years",
        value_format=MetricFormat.COUNT,
        value_label="이자 미충당 연수",
    ),
    _CriterionSpec(
        code=REASON_REPAYMENT,
        name="상환연수",
        reason="상환연수 초과 (영업현금흐름으로 순부채를 감당하기 어려움)",
        rule=(
            f"순부채 ÷ 영업활동현금흐름이 {w.GATE_MAX_REPAYMENT_YEARS:.0f}년을 넘으면 탈락 "
            f"(유틸리티·리츠·인프라는 {w.GATE_MAX_REPAYMENT_YEARS_TOLERANT:.0f}년)"
        ),
        description=(
            "지금 버는 속도로 순부채를 모두 갚는 데 몇 년이 걸리는지를 뜻한다. "
            "길수록 금리 상승이나 업황 둔화 한 번에 재무가 흔들린다. "
            "규제요금·장기계약으로 현금흐름이 예측 가능한 업종은 부채를 오래 "
            "끌고 가는 것이 정상이라 완화된 기준을 쓴다."
        ),
        value_column="QIP4 Debt Repayment Years",
        value_label="상환연수",
    ),
)

# --- 안정성 관문: 자산형(은행·보험·증권·지주) 전용 ---
_ASSET_GATE_SPECS: tuple[_CriterionSpec, ...] = (
    _CriterionSpec(
        code=REASON_F1,
        name="F1 · 순손실 연수",
        reason="최근 3년 중 당기순손실이 2년 이상",
        rule=f"최근 3년 중 당기순손실이 {w.GATE_MAX_NET_LOSS_YEARS}년 이상이면 탈락",
        description=(
            "자산형에서 영업활동현금흐름은 대출·투자자산 잔액 변동에 따라 크게 "
            "흔들려 부실 신호로 읽을 수 없다. 대신 손익이 반복적으로 적자인지를 "
            "본다 — S1(영업현금흐름)의 대응물이다."
        ),
        value_column="QIP4 Net Loss Years",
        value_format=MetricFormat.COUNT,
        value_label="최근 3년 중 순손실 연수",
    ),
    _CriterionSpec(
        code=REASON_F2,
        name="F2 · 자기자본비율",
        reason="자기자본비율이 4% 미만 (자본적정성 미달)",
        rule=(
            f"자본총계 ÷ 자산총계가 "
            f"{w.GATE_MIN_EQUITY_RATIO * 100:.0f}% 미만이면 탈락"
        ),
        description=(
            "자산형은 남의 돈(예금·보험료·차입)을 굴리는 사업이라 자기 자본이 "
            "손실을 받아내는 완충재 역할을 한다. 이 완충재가 얇으면 자산 가격이 "
            "조금만 흔들려도 자본이 잠식된다."
        ),
        value_column="QIP4 Equity Ratio",
        value_format=MetricFormat.FRACTION_PERCENT,
        value_label="자기자본비율",
    ),
)

# --- 자산 품질 경고 (탈락이 아니라 주의) ---
_WARNING_SPECS: tuple[_CriterionSpec, ...] = (
    _CriterionSpec(
        code=WARN_TANGIBLE,
        name="실질 자기자본",
        reason="장부 자기자본의 25% 이상이 영업권·이연법인세자산",
        rule=(
            f"(자기자본 − 영업권 − 이연법인세자산) ÷ 자기자본이 "
            f"{w.WARN_MIN_TANGIBLE_EQUITY_RATIO * 100:.0f}% 미만이면 경고"
        ),
        description=(
            "영업권과 이연법인세자산은 팔아서 현금이 되는 자산이 아니다. "
            "장부상 자본이 두꺼워 보여도 이런 항목이 큰 비중이면 실제로 손실을 "
            "흡수할 수 있는 자본은 그만큼 얇다. PBR이 낮아 보이는 착시의 흔한 원인이다."
        ),
        value_column="QIP4 Tangible Equity Ratio",
        value_format=MetricFormat.FRACTION_PERCENT,
        value_label="실질 자기자본 비율",
    ),
    _CriterionSpec(
        code=WARN_GOODWILL,
        name="영업권 비중",
        reason="영업권이 총자산의 20%를 넘음",
        rule=(
            f"영업권 ÷ 총자산이 "
            f"{w.WARN_MAX_GOODWILL_TO_ASSETS * 100:.0f}%를 넘으면 경고"
        ),
        description=(
            "영업권은 인수할 때 순자산보다 더 얹어준 금액이다. 비중이 크다는 것은 "
            "자산의 상당 부분이 과거 인수가 성공한다는 가정 위에 서 있다는 뜻이고, "
            "가정이 깨지면 손상차손으로 한 번에 사라진다."
        ),
        value_column="QIP4 Goodwill to Assets",
        value_format=MetricFormat.FRACTION_PERCENT,
        value_label="영업권 비중",
    ),
)

# --- 효율성 감사 (경보 개수가 점수 승수를 정한다) ---
_ALARM_SPECS: tuple[_CriterionSpec, ...] = (
    _CriterionSpec(
        code=ALARM_INVENTORY,
        name="재고",
        reason="재고가 매출보다 빠르게 증가 (수요 둔화·밀어내기 의심)",
        rule="재고 증가율이 매출 증가율을 넘으면 경보 (선수금이 함께 늘면 해제)",
        description=(
            "팔리는 속도보다 쌓이는 속도가 빠르다는 뜻이라, 수요가 꺾였거나 "
            "유통망에 물건을 밀어넣어 매출을 만든 것일 수 있다. "
            "다만 선수금이 함께 늘고 있다면 주문을 받아놓고 미리 확보한 재고이므로 "
            "경보를 해제한다."
        ),
        value_column="QIP4 Inventory Alarm",
        show_value=False,
    ),
    _CriterionSpec(
        code=ALARM_RECEIVABLES,
        name="매출채권",
        reason="매출채권이 매출보다 빠르게 증가 (회수 부실 의심)",
        rule="매출채권 증가율이 매출 증가율을 넘으면 경보",
        description=(
            "매출은 잡혔는데 돈은 아직 못 받은 몫이 커지고 있다는 뜻이다. "
            "무리한 외상 조건으로 매출을 늘렸거나 거래처 사정이 나빠지는 신호일 수 있다."
        ),
        value_column="QIP4 Receivables Alarm",
        show_value=False,
    ),
    _CriterionSpec(
        code=ALARM_ACCRUAL,
        name="발생액",
        reason="이익과 현금의 괴리가 업종 상위 10%",
        rule=(
            f"발생액 비율이 같은 업종 상위 "
            f"{(1 - w.ACCRUAL_ALARM_QUANTILE) * 100:.0f}%에 들면 경보"
        ),
        description=(
            "발생액은 순이익에서 영업활동현금흐름을 뺀 값, 즉 현금이 뒷받침하지 "
            "않는 이익이다. 회계 관행은 업종마다 다르므로 절대값이 아니라 "
            "같은 업종 안에서의 상대 위치로 판단한다."
        ),
        value_column="QIP4 Accrual Ratio",
        value_format=MetricFormat.PERCENT,
        value_label="발생액 비율",
    ),
    _CriterionSpec(
        code=ALARM_CCC,
        name="현금전환주기",
        reason="현금전환주기가 연속 악화 (운전자본 관리 실패)",
        rule="현금전환주기(재고+매출채권−매입채무 회전일)가 연속으로 길어지면 경보",
        description=(
            "재고를 사서 팔고 대금을 회수하기까지 현금이 묶여 있는 기간이다. "
            "계속 길어진다면 같은 매출을 내는 데 더 많은 운전자본이 필요해진다는 "
            "뜻이고, 그만큼 성장이 현금을 잡아먹는다."
        ),
        value_column="QIP4 CCC Deteriorating",
        show_value=False,
    ),
)

_ASSET_GATE_NOTE = (
    "은행·보험·증권·지주는 이자비용이 조달원가라 이자보상배율이 1 미만인 것이 "
    "정상이고 영업현금흐름도 잔액 변동에 흔들린다. 그래서 현금흐름 기반 4개 조건 "
    "대신 전용 조건 2개로 대체한다."
)

_ALARM_NOTE = (
    f"경보는 탈락 사유가 아니라 점수를 깎는 요소다. "
    f"{w.EFFICIENCY_FAIL_ALARM_COUNT}개 이상이면 승수가 0이 되어 사실상 탈락한다."
)

# 사유 코드 → 한 줄 문구. 위 스펙에서 파생시켜 같은 문장을 두 번 적지 않는다.
_ALL_SPECS: tuple[_CriterionSpec, ...] = (
    _CASHFLOW_GATE_SPECS + _ASSET_GATE_SPECS + _WARNING_SPECS + _ALARM_SPECS
)
_REASON_LABELS: dict[str, str] = {spec.code: spec.reason for spec in _ALL_SPECS}


@dataclass(frozen=True)
class CriterionView:
    """평가기준 한 줄의 표시 정보 (접었다 펴는 카드 하나)."""

    name: str
    status: str
    status_label: str
    rule: str
    description: str
    measured: str | None


@dataclass(frozen=True)
class CriteriaGroupView:
    """평가기준 묶음의 표시 정보."""

    title: str
    note: str | None
    items: list[CriterionView]
    # 효율성 감사 묶음만 점수 승수를 함께 보여준다. 템플릿이 제목 문자열을
    # 비교하지 않도록 여기서 플래그로 내려준다.
    shows_multiplier: bool = False


@dataclass(frozen=True)
class GateView:
    """상세 페이지의 QIP4 평가기준 블록에 필요한 표시 정보."""

    passed: bool
    verdict_label: str
    gate_reasons: list[str]
    warnings: list[str]
    alarm_count: int | None
    alarm_reasons: list[str]
    efficiency_multiplier: float | None
    execution_rate: float | None
    criteria_groups: list[CriteriaGroupView]


def _split_codes(raw: object) -> list[str]:
    """"S1_OCF|REPAYMENT_YEARS" → ["S1_OCF", "REPAYMENT_YEARS"]."""
    if raw is None or not isinstance(raw, str) or not raw.strip():
        return []
    return [code for code in raw.split(REASON_SEPARATOR) if code]


def _labels(raw: object) -> list[str]:
    """코드 문자열을 한국어 문구 목록으로 바꾼다. 모르는 코드는 그대로 남긴다."""
    return [_REASON_LABELS.get(code, code) for code in _split_codes(raw)]


def _has_evidence(spec: _CriterionSpec, values: dict) -> bool:
    """이 기준을 판정할 원시값이 있는가. 없으면 "판정 불가"로 표시한다."""
    if spec.value_column is None:
        return True
    return values.get(spec.value_column) is not None


def _measured_text(
    spec: _CriterionSpec, values: dict, market: str | None
) -> str | None:
    """측정값 한 줄. 보여줄 값이 없으면 None."""
    if not spec.show_value or spec.value_column is None:
        return None
    value = values.get(spec.value_column)
    if value is None:
        return None
    return f"{spec.value_label} {format_metric(value, spec.value_format, market)}"


def _criterion_view(
    spec: _CriterionSpec,
    kind: str,
    fired: set[str],
    values: dict,
    market: str | None,
) -> CriterionView:
    if spec.code in fired:
        status = _FIRED_STATUS[kind]
    elif _has_evidence(spec, values):
        status = _STATUS_PASS
    else:
        status = _STATUS_UNKNOWN
    return CriterionView(
        name=spec.name,
        status=status,
        status_label=_STATUS_LABELS.get((kind, status), _UNKNOWN_LABEL),
        rule=spec.rule,
        description=spec.description,
        measured=_measured_text(spec, values, market),
    )


def _criteria_groups(values: dict, market: str | None) -> list[CriteriaGroupView]:
    """종목의 섹터군에 맞는 평가기준 묶음을 전부 만든다.

    걸린 항목만이 아니라 **전 항목**을 통과/탈락과 함께 보여준다 — 무엇을 보고
    통과시켰는지까지 드러나야 투자자가 스스로 판단할 수 있다.
    """
    is_asset_type = values.get(_SECTOR_GROUP_VALUE) == GROUP_ASSET
    gate_specs = _ASSET_GATE_SPECS if is_asset_type else _CASHFLOW_GATE_SPECS
    group_specs = (
        _GroupSpec(
            title="안정성 관문",
            note=_ASSET_GATE_NOTE if is_asset_type else None,
            kind=_KIND_GATE,
            specs=gate_specs,
        ),
        _GroupSpec(
            title="자산 품질 경고",
            note=None,
            kind=_KIND_WARNING,
            specs=_WARNING_SPECS,
        ),
        _GroupSpec(
            title="효율성 감사",
            note=_ALARM_NOTE,
            kind=_KIND_ALARM,
            specs=_ALARM_SPECS,
        ),
    )

    fired_by_kind: dict[str, set[str]] = {
        _KIND_GATE: set(_split_codes(values.get("QIP4 Gate Reasons"))),
        _KIND_WARNING: set(_split_codes(values.get("QIP4 Warnings"))),
        _KIND_ALARM: set(_split_codes(values.get("QIP4 Efficiency Reasons"))),
    }

    return [
        CriteriaGroupView(
            title=group.title,
            note=group.note,
            items=[
                _criterion_view(
                    spec, group.kind, fired_by_kind[group.kind], values, market
                )
                for spec in group.specs
            ],
            shows_multiplier=group.kind == _KIND_ALARM,
        )
        for group in group_specs
    ]


def build_gate_view(values: dict, market: str | None = None) -> GateView | None:
    """상세 페이지 값 dict에서 평가기준 블록 표시 정보를 만든다.

    QIP4가 아직 계산되지 않은 데이터면 None을 돌려주고, 화면은 블록을 통째로 숨긴다.
    """
    verdict = values.get("QIP4 Stability Gate")
    if not verdict:
        return None

    passed = verdict != GATE_FAIL
    multiplier = values.get("QIP4 Efficiency Multiplier")
    alarm_count = values.get("QIP4 Efficiency Alarms")
    return GateView(
        passed=passed,
        verdict_label="통과" if passed else "탈락",
        gate_reasons=_labels(values.get("QIP4 Gate Reasons")),
        warnings=_labels(values.get("QIP4 Warnings")),
        alarm_count=int(alarm_count) if alarm_count is not None else None,
        alarm_reasons=_labels(values.get("QIP4 Efficiency Reasons")),
        efficiency_multiplier=(
            float(multiplier) if multiplier is not None else None
        ),
        execution_rate=(
            float(values["QIP4 Execution Rate"])
            if values.get("QIP4 Execution Rate") is not None
            else None
        ),
        criteria_groups=_criteria_groups(values, market),
    )
