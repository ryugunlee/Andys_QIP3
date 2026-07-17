"""값을 화면 문자열로 바꾸는 포맷터와 Jinja2 필터 등록.

metrics.MetricFormat의 각 포맷을 실제 문자열로 해석하는 유일한 곳이다.
한국 종목(₩, 조/억)과 미국 종목($, $T/$B)은 시장명으로 구분한다.
"""

from jinja2 import Environment

from presentation import config
from presentation.metrics import MetricFormat

# 결측값 표시 (네이버증권 관례)
MISSING: str = "—"

# 금액 단위 경계
_KR_TRILLION = 1e12  # 1조
_KR_HUNDRED_MILLION = 1e8  # 1억
_US_TRILLION = 1e12
_US_BILLION = 1e9
_US_MILLION = 1e6

# 분석 영역이 만드는 영문 신호 값 -> 한국어 라벨
_SIGNAL_LABELS: dict[str, str] = {
    # MACD Signal (collection/stock.py)
    "Heating": "상승 흐름",
    "Heat Timing": "상승 전환",
    "Cooling": "하락 흐름",
    "Sell Timing": "하락 전환",
    # RSI Signal의 숫자 값 (0 = 하락 흐름, -1 = 하락 전환)
    "0": "하락 흐름",
    "-1": "하락 전환",
    # RSI 상태
    "OVERHEAT": "과열",
    "NORMAL": "중립",
    "UNDERHEAT": "침체",
    # 이동평균선 Hit/Miss
    "Hit": "상회",
    "Miss": "하회",
    # Value risk / Growth risk의 O/X
    "O": "있음",
    "X": "없음",
}


def is_kr_market(market: str | None) -> bool:
    return config.is_korean_market_name(market)


def format_money(value: float | None, market: str | None = None) -> str:
    """큰 금액. KR: 412.3조 / 5,032억, US: $3.2T / $45.6B / $12.3M."""
    if value is None:
        return MISSING
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if is_kr_market(market):
        if amount >= _KR_TRILLION:
            return f"{sign}{amount / _KR_TRILLION:,.1f}조"
        return f"{sign}{amount / _KR_HUNDRED_MILLION:,.0f}억"
    if amount >= _US_TRILLION:
        return f"{sign}${amount / _US_TRILLION:,.2f}T"
    if amount >= _US_BILLION:
        return f"{sign}${amount / _US_BILLION:,.1f}B"
    return f"{sign}${amount / _US_MILLION:,.1f}M"


def format_price(value: float | None, market: str | None = None) -> str:
    """주가/주당 금액. KR: ₩71,200 / US: $189.34."""
    if value is None:
        return MISSING
    if is_kr_market(market):
        return f"₩{value:,.0f}"
    return f"${value:,.2f}"


def format_percent(value: float | None) -> str:
    """이미 % 단위인 값. 12.4%"""
    if value is None:
        return MISSING
    return f"{value:,.1f}%"


def format_fraction_percent(value: float | None) -> str:
    """소수(0.124)를 %로. 12.4%"""
    if value is None:
        return MISSING
    return format_percent(value * 100)


def format_signed_percent(value: float | None) -> str:
    """부호를 항상 붙이는 %. 색과 함께 상승/하락을 이중으로 전달한다."""
    if value is None:
        return MISSING
    # 반올림 결과가 0이면 "-0.0%"처럼 음수 부호만 남는 표시를 피한다 (예: -0.03 → 0.0).
    rounded = round(value, 1) + 0.0
    return f"{rounded:+,.1f}%"


def format_multiple(value: float | None) -> str:
    if value is None:
        return MISSING
    return f"{value:,.2f}배"


def format_score(value: float | None) -> str:
    if value is None:
        return MISSING
    return f"{value:,.1f}"


def format_number(value: float | None) -> str:
    if value is None:
        return MISSING
    return f"{value:,.2f}"


def format_text(value: object) -> str:
    """신호/텍스트 값. 알려진 영문 신호는 한국어로 바꾼다."""
    if value is None:
        return MISSING
    # RSI Signal이 0.0 / -1.0 같은 float으로 저장되는 경우를 문자열 키로 정규화
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value)
    return _SIGNAL_LABELS.get(text, text)


def format_metric(value: object, metric_format: MetricFormat, market: str | None = None) -> str:
    """MetricSpec.format에 따라 값을 문자열로 변환하는 단일 진입점."""
    if metric_format is MetricFormat.TEXT:
        return format_text(value)
    if value is not None and not isinstance(value, (int, float)):
        # 숫자 포맷인데 숫자가 아닌 값이 오면 그대로 보여준다 (데이터 이상 노출)
        return str(value)
    number = float(value) if value is not None else None
    if metric_format is MetricFormat.MONEY:
        return format_money(number, market)
    if metric_format is MetricFormat.PRICE:
        return format_price(number, market)
    if metric_format is MetricFormat.MULTIPLE:
        return format_multiple(number)
    if metric_format is MetricFormat.PERCENT:
        return format_percent(number)
    if metric_format is MetricFormat.FRACTION_PERCENT:
        return format_fraction_percent(number)
    if metric_format is MetricFormat.SCORE:
        return format_score(number)
    return format_number(number)


def meter_width(value: float | None) -> float:
    """0~100 점수 미터의 채움 폭(%). 범위를 벗어난 값은 잘라낸다."""
    if value is None:
        return 0.0
    return min(max(float(value), 0.0), 100.0)


def change_class(value: float | None) -> str:
    """등락 색상용 CSS 클래스. 상승 빨강/하락 파랑은 style.css가 정의한다."""
    if value is None:
        return ""
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return ""


# 스파크라인 SVG viewBox 기본 치수 (지표 추이 사이드바 전용, 인터랙션 없는 정적 렌더)
_SPARKLINE_WIDTH = 120
_SPARKLINE_HEIGHT = 32


def sparkline_points(values: list[float], width: float = _SPARKLINE_WIDTH, height: float = _SPARKLINE_HEIGHT) -> str:
    """값 목록을 SVG `<polyline points="...">` 좌표 문자열로 변환한다.

    값이 모두 같으면(또는 1개면) 세로 중앙 수평선으로 그린다. 빌드 타임에 계산되는
    순수 정적 SVG라 차트용 JS가 필요 없다 (인터랙티브 주가 차트는 static/charts.js 참고).
    """
    if not values:
        return ""
    if len(values) == 1:
        mid = height / 2
        return f"0,{mid} {width},{mid}"
    lo, hi = min(values), max(values)
    span = hi - lo
    step = width / (len(values) - 1)
    points = []
    for i, value in enumerate(values):
        x = i * step
        y = height / 2 if span == 0 else height - (value - lo) / span * height
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def register_filters(env: Environment) -> None:
    """Jinja2 환경에 포맷터를 필터로 등록한다."""
    env.filters["money"] = format_money
    env.filters["price"] = format_price
    env.filters["percent"] = format_percent
    env.filters["signed_percent"] = format_signed_percent
    env.filters["multiple"] = format_multiple
    env.filters["score"] = format_score
    env.filters["metric"] = format_metric
    env.filters["number"] = format_number
    env.filters["meter_width"] = meter_width
    env.filters["change_class"] = change_class
    env.filters["sparkline_points"] = sparkline_points
