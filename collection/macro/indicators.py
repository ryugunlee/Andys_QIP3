"""경제지표(매크로) 정의의 단일 소스.

어떤 지표를 어떤 소스에서 어떤 심볼로 수집하고, 어떤 한국어 이름/단위로
보여줄지 여기서만 정의한다 (analysis/factors.py의 FactorSpec,
presentation/metrics.py의 MetricSpec과 같은 패턴).

- 새 지표 추가 = 이 파일에 스펙 한 줄 추가 (소스가 기존 4종이면 수집기 수정 불필요).
- 선언 순서 = 메인 페이지 카드 표시 순서.
- ECOS 소스는 API 키 확보 전까지 수집기가 없어 자리만 잡아둔 상태다
  (프로젝트 루트 API_REQUESTS.txt 참고).
"""

from dataclasses import dataclass
from enum import Enum


class MacroSource(Enum):
    YAHOO = "yahoo"  # yfinance (지수/환율/원자재/미 국채 지수)
    FRED = "fred"  # fredgraph.csv (키 불필요, 네트워크에 따라 차단 가능)
    NAVER_GOLD = "naver_gold"  # 네이버 marketindex 금현물 (KRX)
    DERIVED = "derived"  # 수집된 다른 지표로부터 계산
    ECOS = "ecos"  # 한국은행 ECOS — API 키 필요, 수집 보류


class MacroCategory(Enum):
    """카드 묶음. 값 = 한국어 표시명. 선언 순서 = 표시 순서."""

    INDEX = "시장 지수"
    FX = "환율"
    COMMODITY = "원자재·금"
    RATE = "금리·물가"


@dataclass(frozen=True)
class MacroIndicatorSpec:
    id: str  # macro_daily.indicator 값 (영문 스네이크)
    name_ko: str  # 카드에 보여줄 한국어 이름
    unit: str  # 카드에 보여줄 단위
    source: MacroSource
    symbol: str | None  # yfinance 티커 / FRED 시리즈 / 네이버 reutersCode. DERIVED는 None
    category: MacroCategory
    scale: float = 1.0  # 수집 원값에 곱하는 배율 (예: 엔/원은 100엔 기준 표시)
    show_card: bool = True  # False면 수집만 하고 메인 페이지 카드에는 노출하지 않음


MACRO_INDICATORS: list[MacroIndicatorSpec] = [
    # --- 시장 지수 ---
    MacroIndicatorSpec("kospi", "코스피", "pt", MacroSource.YAHOO, "^KS11", MacroCategory.INDEX),
    MacroIndicatorSpec("kosdaq", "코스닥", "pt", MacroSource.YAHOO, "^KQ11", MacroCategory.INDEX),
    MacroIndicatorSpec("nasdaq", "나스닥", "pt", MacroSource.YAHOO, "^IXIC", MacroCategory.INDEX),
    MacroIndicatorSpec("sp500", "S&P 500", "pt", MacroSource.YAHOO, "^GSPC", MacroCategory.INDEX),
    MacroIndicatorSpec("vix", "VIX (공포지수)", "pt", MacroSource.YAHOO, "^VIX", MacroCategory.INDEX),
    # --- 환율 ---
    MacroIndicatorSpec("usd_krw", "달러/원", "원", MacroSource.YAHOO, "KRW=X", MacroCategory.FX),
    MacroIndicatorSpec(
        "jpy100_krw", "엔/원 (100엔)", "원", MacroSource.YAHOO, "JPYKRW=X", MacroCategory.FX, scale=100.0
    ),
    # 위안/원: yfinance의 CNYKRW=X는 히스토리가 1일뿐이라(2026-07-16 확인) 달러원÷달러위안으로 파생 계산
    MacroIndicatorSpec("cny_krw", "위안/원", "원", MacroSource.DERIVED, None, MacroCategory.FX),
    MacroIndicatorSpec(
        "usd_cny", "달러/위안", "위안", MacroSource.YAHOO, "CNY=X", MacroCategory.FX, show_card=False
    ),
    MacroIndicatorSpec("dollar_index", "달러인덱스", "pt", MacroSource.YAHOO, "DX-Y.NYB", MacroCategory.FX),
    # --- 원자재·금 ---
    MacroIndicatorSpec("wti", "WTI 유가", "달러/배럴", MacroSource.YAHOO, "CL=F", MacroCategory.COMMODITY),
    MacroIndicatorSpec("brent", "브렌트유", "달러/배럴", MacroSource.YAHOO, "BZ=F", MacroCategory.COMMODITY),
    MacroIndicatorSpec("gold_intl", "국제 금", "달러/온스", MacroSource.YAHOO, "GC=F", MacroCategory.COMMODITY),
    MacroIndicatorSpec(
        "gold_krx", "KRX 금현물", "원/g", MacroSource.NAVER_GOLD, "M04020000", MacroCategory.COMMODITY
    ),
    MacroIndicatorSpec(
        "gold_gap_pct", "금 괴리율 (KRX/국제)", "%", MacroSource.DERIVED, None, MacroCategory.COMMODITY
    ),
    # --- 금리·물가 ---
    MacroIndicatorSpec("us_base_rate", "미국 기준금리", "%", MacroSource.FRED, "DFF", MacroCategory.RATE),
    MacroIndicatorSpec("us_2y", "미 2년 국채금리", "%", MacroSource.FRED, "DGS2", MacroCategory.RATE),
    MacroIndicatorSpec("us_10y", "미 10년 국채금리", "%", MacroSource.YAHOO, "^TNX", MacroCategory.RATE),
    MacroIndicatorSpec("us_30y", "미 30년 국채금리", "%", MacroSource.YAHOO, "^TYX", MacroCategory.RATE),
    MacroIndicatorSpec("us_3m", "미 3개월 국채금리", "%", MacroSource.YAHOO, "^IRX", MacroCategory.RATE),
    MacroIndicatorSpec(
        "yield_spread_10y_3m", "미 장단기 금리차 (10Y−3M)", "%p", MacroSource.DERIVED, None, MacroCategory.RATE
    ),
    MacroIndicatorSpec(
        "us_cpi_yoy", "미국 인플레이션 (CPI YoY)", "%", MacroSource.FRED, "CPIAUCSL", MacroCategory.RATE
    ),
    # --- 수집 보류 (ECOS API 키 필요 — API_REQUESTS.txt 참고) ---
    MacroIndicatorSpec("kr_base_rate", "한국 기준금리", "%", MacroSource.ECOS, "722Y001", MacroCategory.RATE),
    MacroIndicatorSpec("kr_cpi_yoy", "한국 인플레이션 (CPI YoY)", "%", MacroSource.ECOS, "901Y009", MacroCategory.RATE),
]


def specs_by_source(source: MacroSource) -> list[MacroIndicatorSpec]:
    return [spec for spec in MACRO_INDICATORS if spec.source is source]


def spec_by_id(indicator_id: str) -> MacroIndicatorSpec | None:
    for spec in MACRO_INDICATORS:
        if spec.id == indicator_id:
            return spec
    return None
