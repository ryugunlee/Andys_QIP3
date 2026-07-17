"""표현 계층이 다루는 데이터 모델 정의.

repository가 분석 산출물(CSV, 추후 DB)을 이 모델들로 변환해 넘기고,
builders/templates는 이 모델만 알면 된다. 즉 저장 방식이 바뀌어도
이 파일 아래(빌더·템플릿)는 수정할 필요가 없다.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StockSummary:
    """목록/카드 화면에 쓰는 종목 요약."""

    ticker: str
    name: str | None
    market: str  # KOSPI | KOSDAQ | NASDAQ | NYSE
    sector: str | None
    close: float | None
    market_cap: float | None
    ratio_3m: float | None  # 최근 3개월 수익률 (%)
    final_score: float | None
    reliability: float | None


@dataclass(frozen=True)
class StockDetail:
    """종목 상세 페이지 하나를 그리는 데 필요한 전체 정보.

    values는 "CSV 컬럼명 -> 값" 매핑이며, 어떤 컬럼을 어떤 라벨/포맷/그룹으로
    보여줄지는 metrics.METRIC_SPECS가 결정한다. 분석 영역에서 지표가 추가되면
    metrics.py에 스펙 한 줄만 추가하면 상세 페이지에 자동 반영된다.
    """

    ticker: str
    name: str | None
    market: str
    sector: str | None
    industry: str | None
    country: str | None
    close: float | None
    market_cap: float | None
    values: dict[str, object] = field(default_factory=dict)
    qualitative: str | None = None  # 정성 평가 (없으면 상세 페이지에서 미표시)


@dataclass(frozen=True)
class PricePoint:
    """일봉 한 점 (주가 차트용)."""

    date: str  # "YYYY-MM-DD"
    close: float
    volume: float | None = None
    foreign_rate: float | None = None  # 외국인소진율(%) — 한국 종목만, 미국은 None


@dataclass(frozen=True)
class AnnualFinancials:
    """실적 한 기간 (매출·영업이익·순이익 막대그래프용). 연간·분기 겸용.

    항목명은 수집 소스마다 다르므로(repository/financial_series.py) 변환을 거쳐
    여기서는 이미 계열별로 정리된 값만 담는다. 없는 값은 None.
    """

    period: str  # 표시용 기간 라벨. 연간 "2023", 분기 "2025 Q3"
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None


@dataclass(frozen=True)
class StockCharts:
    """종목 상세 페이지의 시계열 시각화 묶음.

    데이터가 없는 계열은 빈 리스트 — 템플릿에서 해당 섹션을 숨긴다.
    quarterly는 현재 네이버(WiseFn 분기) 수집만 채워진다 — 미국 종목은 항상 빈 리스트
    (.claude/PROBLEMS.md #10 참고).
    """

    prices: list[PricePoint] = field(default_factory=list)
    annual: list[AnnualFinancials] = field(default_factory=list)
    quarterly: list[AnnualFinancials] = field(default_factory=list)


@dataclass(frozen=True)
class SearchEntry:
    """검색 인덱스(JSON)에 들어가는 경량 항목."""

    ticker: str
    name: str | None
    market: str
    sector: str | None
    final_score: float | None
    market_cap: float | None


@dataclass(frozen=True)
class GroupScore:
    """섹터/산업 자체 평가 한 행 (그룹 간 상대 점수 + 대표 지표 중앙값)."""

    name: str  # 섹터/산업명
    region: str  # KR | US
    ticker_count: int
    relative_score: float | None  # 그룹 간 상대 점수 (Finalscore의 퍼센타일·스탠다드 평균)
    median_finalscore: float | None  # 그룹 내 종목 종합 점수 중앙값
    median_per: float | None
    median_roe: float | None  # 소수(0.15 = 15%)
    median_ratio_3m: float | None  # %


@dataclass(frozen=True)
class EconomicIndicator:
    """세계 경제 지표(금값, 유가, 금리, 환율 등) 한 개.

    수집 영역에 지표 수집이 구현되면 repository/indicators_provider.py가
    이 모델의 리스트를 반환하는 것으로 연결이 끝난다.
    """

    name: str  # 예: "금", "WTI 유가", "미 10년물 금리"
    value: float
    unit: str  # 예: "USD/oz", "%", "원/달러"
    change_pct: float | None  # 전일 대비 변화율 (%)
    as_of: str  # 기준일 "YYYY-MM-DD"
    category: str = ""  # MacroCategory.value (한국어 카테고리명) — 우측 추이 사이드바 그룹핑용
    history: list[float] = field(default_factory=list)  # 최근 6개월 일별값 (추이 스파크라인용, 오래된→최신 순)


@dataclass(frozen=True)
class NewsItem:
    """뉴스 기사 한 건.

    수집 영역에 뉴스 수집이 구현되면 repository/news_provider.py가
    이 모델의 리스트를 반환하는 것으로 연결이 끝난다.
    """

    title: str
    source: str
    url: str
    published_at: str  # "YYYY-MM-DD" 또는 "YYYY-MM-DD HH:MM"
    summary: str | None = None
