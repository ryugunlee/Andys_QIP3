"""QIP4 관문·경보 코드 → 한국어 표시 문구.

분석 계층(`analysis/qip4_gate.py`)은 사유를 **코드**로만 남긴다("S1_OCF|REPAYMENT_YEARS").
언어는 표현 계층의 책임이라, 코드→한국어 변환은 이 파일 한 곳에만 둔다
(`presentation/korean_names.py`가 종목명을 맡는 것과 같은 층위).
"""

from dataclasses import dataclass

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

# 관문 탈락 사유
_GATE_REASON_LABELS: dict[str, str] = {
    REASON_S1: "영업활동현금흐름이 3년 중 2년 이상 음수",
    REASON_S2: "누적 현금전환율이 0.7 미만 (이익이 현금으로 들어오지 않음)",
    REASON_S3: "이자보상배율이 2년 연속 1 미만 (영업이익으로 이자를 못 냄)",
    REASON_REPAYMENT: "상환연수 초과 (영업현금흐름으로 순부채를 감당하기 어려움)",
    # 자산형(은행·보험·증권·지주) 전용
    REASON_F1: "최근 3년 중 당기순손실이 2년 이상",
    REASON_F2: "자기자본비율이 4% 미만 (자본적정성 미달)",
}

# 자산 품질 경고 (탈락이 아니라 주의)
_WARNING_LABELS: dict[str, str] = {
    WARN_TANGIBLE: "장부 자기자본의 25% 이상이 영업권·이연법인세자산",
    WARN_GOODWILL: "영업권이 총자산의 20%를 넘음",
}

# 효율성 경보
_ALARM_LABELS: dict[str, str] = {
    ALARM_INVENTORY: "재고가 매출보다 빠르게 증가 (수요 둔화·밀어내기 의심)",
    ALARM_RECEIVABLES: "매출채권이 매출보다 빠르게 증가 (회수 부실 의심)",
    ALARM_ACCRUAL: "이익과 현금의 괴리가 업종 상위 10%",
    ALARM_CCC: "현금전환주기가 연속 악화 (운전자본 관리 실패)",
}


@dataclass(frozen=True)
class GateView:
    """상세 페이지의 안정성 관문 블록에 필요한 표시 정보."""

    passed: bool
    verdict_label: str
    gate_reasons: list[str]
    warnings: list[str]
    alarm_count: int | None
    alarm_reasons: list[str]
    efficiency_multiplier: float | None
    execution_rate: float | None


def _split_codes(raw: object) -> list[str]:
    """"S1_OCF|REPAYMENT_YEARS" → ["S1_OCF", "REPAYMENT_YEARS"]."""
    if raw is None or not isinstance(raw, str) or not raw.strip():
        return []
    return [code for code in raw.split(REASON_SEPARATOR) if code]


def _labels(raw: object, table: dict[str, str]) -> list[str]:
    """코드 문자열을 한국어 문구 목록으로 바꾼다. 모르는 코드는 그대로 남긴다."""
    return [table.get(code, code) for code in _split_codes(raw)]


def build_gate_view(values: dict) -> GateView | None:
    """상세 페이지 값 dict에서 관문 표시 정보를 만든다.

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
        gate_reasons=_labels(values.get("QIP4 Gate Reasons"), _GATE_REASON_LABELS),
        warnings=_labels(values.get("QIP4 Warnings"), _WARNING_LABELS),
        alarm_count=int(alarm_count) if alarm_count is not None else None,
        alarm_reasons=_labels(values.get("QIP4 Efficiency Reasons"), _ALARM_LABELS),
        efficiency_multiplier=(
            float(multiplier) if multiplier is not None else None
        ),
        execution_rate=(
            float(values["QIP4 Execution Rate"])
            if values.get("QIP4 Execution Rate") is not None
            else None
        ),
    )
