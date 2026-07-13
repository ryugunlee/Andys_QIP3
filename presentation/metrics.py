"""화면에 보여줄 지표 메타데이터의 단일 소스.

분석 영역(collection/analysis)이 만드는 CSV 컬럼을 "어떤 한국어 라벨로,
어떤 포맷으로, 어떤 그룹에" 보여줄지 여기서만 정의한다.
(analysis/factors.py의 FactorSpec 패턴을 표현 계층에 맞게 재현한 것)

분석 영역에서 새 지표가 추가되면 이 파일에 MetricSpec 한 줄을 추가하는 것으로
상세 페이지 반영이 끝난다. 템플릿과 빌더는 수정할 필요가 없다.

단위 판별 근거는 collection/stock.py의 계산식이다.
예: ROE는 yfinance의 소수(0.15)라 FRACTION_PERCENT(×100 후 %),
3M Ratio는 이미 %로 계산되어 PERCENT(그대로 %).
"""

from dataclasses import dataclass
from enum import Enum


class MetricFormat(Enum):
    """값을 화면 문자열로 바꿀 때 쓰는 포맷 종류. formatters.py가 해석한다."""

    TEXT = "text"  # 문자열 그대로 (Hit/Miss, Heating 등)
    MONEY = "money"  # 큰 금액: KR 조/억, US $T/$B
    PRICE = "price"  # 주가/주당 금액: ₩71,200 / $189.34
    MULTIPLE = "multiple"  # 배수: 12.4배
    PERCENT = "percent"  # 이미 % 단위인 값: 12.4%
    FRACTION_PERCENT = "fraction_percent"  # 소수(0.124)를 ×100 해서 12.4%
    NUMBER = "number"  # 단순 숫자 (소수 2자리)
    SCORE = "score"  # 0~100 점수 (소수 1자리, 게이지 표시 가능)


class MetricGroup(Enum):
    """상세 페이지의 지표 그룹. 선언 순서 = 화면 표시 순서. 값 = 한국어 제목."""

    VALUATION = "밸류에이션"
    PROFITABILITY = "수익성"
    GROWTH = "성장성"
    STABILITY = "재무 건전성"
    SHAREHOLDER = "주주환원·지분"
    MOMENTUM = "수급·모멘텀"
    TECHNICAL = "기술적 신호"
    SCORES = "종합 점수"


@dataclass(frozen=True)
class MetricSpec:
    column: str  # 분석 산출물(CSV)의 컬럼명
    label: str  # 화면에 보여줄 한국어 라벨
    format: MetricFormat
    group: MetricGroup


METRIC_SPECS: list[MetricSpec] = [
    # --- 밸류에이션 ---
    MetricSpec("PER", "PER (주가수익비율)", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("PBR", "PBR (주가순자산비율)", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("PSR", "PSR (주가매출비율)", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("PCR", "PCR (주가현금흐름비율)", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("EV/Revenue", "EV/매출", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("EV/EBITDA", "EV/EBITDA", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("PEGR", "PEGR (PER/성장률)", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("PFCR", "PFCR (주가잉여현금흐름비율)", MetricFormat.MULTIPLE, MetricGroup.VALUATION),
    MetricSpec("NCAV", "NCAV/시가총액", MetricFormat.FRACTION_PERCENT, MetricGroup.VALUATION),
    MetricSpec("EPS", "EPS (주당순이익)", MetricFormat.PRICE, MetricGroup.VALUATION),
    # --- 수익성 ---
    MetricSpec("ROE", "ROE (자기자본이익률)", MetricFormat.FRACTION_PERCENT, MetricGroup.PROFITABILITY),
    MetricSpec("ROA", "ROA (총자산이익률)", MetricFormat.FRACTION_PERCENT, MetricGroup.PROFITABILITY),
    MetricSpec("ROC", "ROC (투하자본이익률)", MetricFormat.FRACTION_PERCENT, MetricGroup.PROFITABILITY),
    MetricSpec("GPTOA", "GP/A (매출총이익/총자산)", MetricFormat.FRACTION_PERCENT, MetricGroup.PROFITABILITY),
    MetricSpec("Asset Turnover", "자산회전율", MetricFormat.MULTIPLE, MetricGroup.PROFITABILITY),
    MetricSpec("Revenue", "매출액", MetricFormat.MONEY, MetricGroup.PROFITABILITY),
    MetricSpec("Net Income", "순이익", MetricFormat.MONEY, MetricGroup.PROFITABILITY),
    MetricSpec("Operating Cashflow", "영업현금흐름", MetricFormat.MONEY, MetricGroup.PROFITABILITY),
    # --- 성장성 ---
    MetricSpec("EPSgrowth", "EPS 성장률", MetricFormat.PERCENT, MetricGroup.GROWTH),
    MetricSpec("Revenuegrowth", "매출 성장률", MetricFormat.PERCENT, MetricGroup.GROWTH),
    # --- 재무 건전성 ---
    MetricSpec("Debt to Equity", "부채비율", MetricFormat.PERCENT, MetricGroup.STABILITY),
    MetricSpec("Debt Growth", "부채 증가율 (1년)", MetricFormat.PERCENT, MetricGroup.STABILITY),
    MetricSpec("Current Ratio", "유동비율", MetricFormat.MULTIPLE, MetricGroup.STABILITY),
    MetricSpec("Interest Ratio", "이자보상배율", MetricFormat.MULTIPLE, MetricGroup.STABILITY),
    MetricSpec("Coverage Ratio", "현금흐름/부채 비율", MetricFormat.MULTIPLE, MetricGroup.STABILITY),
    MetricSpec("Asset to Equity", "재무 레버리지 (자산/자본)", MetricFormat.MULTIPLE, MetricGroup.STABILITY),
    MetricSpec("Depreciation Capex Ratio", "감가상각/설비투자 비율", MetricFormat.MULTIPLE, MetricGroup.STABILITY),
    MetricSpec("ARP", "발생액 비율 (이익 품질)", MetricFormat.PERCENT, MetricGroup.STABILITY),
    # --- 주주환원·지분 ---
    MetricSpec("Dividend Yield", "배당수익률", MetricFormat.PERCENT, MetricGroup.SHAREHOLDER),
    MetricSpec("Buyback Yield", "자사주 매입수익률", MetricFormat.PERCENT, MetricGroup.SHAREHOLDER),
    MetricSpec("Dividend to Income", "배당성향 (배당/이익)", MetricFormat.NUMBER, MetricGroup.SHAREHOLDER),
    MetricSpec("Buyback to Income", "자사주 매입/이익", MetricFormat.NUMBER, MetricGroup.SHAREHOLDER),
    MetricSpec("Insiderpercent", "내부자 지분율", MetricFormat.FRACTION_PERCENT, MetricGroup.SHAREHOLDER),
    MetricSpec("Institutionpercent", "기관 지분율", MetricFormat.FRACTION_PERCENT, MetricGroup.SHAREHOLDER),
    MetricSpec("Insider Buy Ratio", "내부자 순매수 비율", MetricFormat.PERCENT, MetricGroup.SHAREHOLDER),
    # --- 수급·모멘텀 ---
    MetricSpec("3M Ratio", "3개월 수익률", MetricFormat.PERCENT, MetricGroup.MOMENTUM),
    MetricSpec("6M Ratio", "6개월 수익률", MetricFormat.PERCENT, MetricGroup.MOMENTUM),
    MetricSpec("1Y Ratio", "1년 수익률", MetricFormat.PERCENT, MetricGroup.MOMENTUM),
    MetricSpec("10D Turnover", "거래대금/시총 (10일)", MetricFormat.FRACTION_PERCENT, MetricGroup.MOMENTUM),
    MetricSpec("3M Turnover", "거래대금/시총 (3개월)", MetricFormat.FRACTION_PERCENT, MetricGroup.MOMENTUM),
    MetricSpec("1Y Turnover", "거래대금/시총 (1년)", MetricFormat.FRACTION_PERCENT, MetricGroup.MOMENTUM),
    MetricSpec("10D Overheat", "단기 과열도 (10일/3개월)", MetricFormat.MULTIPLE, MetricGroup.MOMENTUM),
    MetricSpec("3M Overheat", "중기 과열도 (3개월/1년)", MetricFormat.MULTIPLE, MetricGroup.MOMENTUM),
    MetricSpec("3M Volatility", "변동성 (3개월)", MetricFormat.FRACTION_PERCENT, MetricGroup.MOMENTUM),
    MetricSpec("1Y Volatility", "변동성 (1년)", MetricFormat.FRACTION_PERCENT, MetricGroup.MOMENTUM),
    # --- 기술적 신호 ---
    MetricSpec("MACD Signal", "MACD 신호", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    MetricSpec("RSI Signal", "RSI 신호", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    MetricSpec("RSI", "RSI 상태", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    MetricSpec("MA5", "5일 이동평균선", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    MetricSpec("MA20", "20일 이동평균선", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    MetricSpec("MA60", "60일 이동평균선", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    MetricSpec("MA120", "120일 이동평균선", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    MetricSpec("MA200", "200일 이동평균선", MetricFormat.TEXT, MetricGroup.TECHNICAL),
    # --- 종합 점수 (analysis/가 계산) ---
    MetricSpec("Finalscore", "종합 점수", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("Vscore", "가치 점수", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("Mscore", "모멘텀 점수", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("Fscore", "펀더멘털 점수", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("EQC", "이익 품질 점수", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("Quant score", "퀀트 점수", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("VC1", "기본 가치 점수 (VC1)", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("reliablity", "데이터 신뢰도", MetricFormat.SCORE, MetricGroup.SCORES),
    MetricSpec("Value risk", "가치 리스크", MetricFormat.TEXT, MetricGroup.SCORES),
    MetricSpec("Growth risk", "성장 리스크", MetricFormat.TEXT, MetricGroup.SCORES),
]

# 상세 페이지 상단에 게이지로 강조하는 대표 점수 (표시 순서대로)
HEADLINE_SCORE_COLUMNS: tuple[str, ...] = ("Finalscore", "Vscore", "Mscore", "Fscore")

# StockDetail.values에 담아야 하는 전체 컬럼 목록 (repository가 사용)
DETAIL_VALUE_COLUMNS: list[str] = [spec.column for spec in METRIC_SPECS]


def specs_by_group() -> dict[MetricGroup, list[MetricSpec]]:
    """그룹 -> 스펙 리스트. 그룹 순서는 MetricGroup 선언 순서를 따른다."""
    grouped: dict[MetricGroup, list[MetricSpec]] = {group: [] for group in MetricGroup}
    for spec in METRIC_SPECS:
        grouped[spec.group].append(spec)
    return {group: specs for group, specs in grouped.items() if specs}
