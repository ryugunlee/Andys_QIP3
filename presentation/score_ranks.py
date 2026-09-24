"""종합 점수의 모집단 내 순위와 3체계 비교 패널.

분석 계층은 점수(0~100)만 낸다. 그 점수가 **또래 중 어디쯤인지**는 화면이 답해야 할
질문이라 여기서 계산한다 — 사이트 빌드는 이미 시장별 최신 스냅샷 전체를 한 프레임으로
들고 있으므로(`repository._all()`), 순위는 DB 재점수 없이 한 번의 횡단면 연산으로 나온다.

순위 모집단은 **시장 내**와 **같은 시장의 같은 섹터 내** 두 가지다. 섹터만으로 묶으면
KOSPI와 NASDAQ이 섞여 의미가 없고, 시장만 보면 저PER 업종이 구조적으로 유리해 보이는
왜곡이 남는다. 둘을 나란히 두면 "시장에선 상위 12%지만 섹터 안에선 상위 3%" 같은 판단이
가능해진다.

`QIP4 Score`는 퍼센타일 계열과 스탠다드 계열의 평균이라 **그 값 자체가 상위 %는 아니다**
(`analysis/qip4_pipeline.py`의 `_attach_averages`). 그래서 점수를 그대로 백분위로 읽지 않고
같은 모집단 안에서 실제 순위를 센다.
"""

from dataclasses import dataclass

import pandas as pd

import analysis.qip4_weights as w
from analysis.score_pipeline import MIN_GROUP_POPULATION
from presentation.formatters import format_score

# --- 순위를 매기는 대상과 모집단 ---

# (모집단 태그, 묶음 기준 컬럼들). 섹터는 시장 안에서 묶는다.
_RANK_POPULATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Market", ("Market",)),
    ("Sector", ("Market", "Sector")),
)

# 순위를 매기는 종합 점수 컬럼.
_RANKED_SCORES: tuple[str, ...] = ("QIP4 Score", "QIP3 Score", "Finalscore")


def rank_column(score_column: str, population_tag: str) -> str:
    return f"{score_column} {population_tag}Rank"


def count_column(score_column: str, population_tag: str) -> str:
    return f"{score_column} {population_tag}Count"


# repository가 계산해 채우고 row_mapping이 StockDetail.values에 담는 컬럼 목록.
RANK_VALUE_COLUMNS: list[str] = [
    column
    for score in _RANKED_SCORES
    for tag, _ in _RANK_POPULATIONS
    for column in (rank_column(score, tag), count_column(score, tag))
]


def attach_score_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """종합 점수별 모집단 내 순위·모집단 크기 컬럼을 붙인 사본을 돌려준다.

    표본이 `MIN_GROUP_POPULATION` 미만인 모집단은 순위를 매기지 않는다 — 3개 중 1위는
    정보가 아니라 착시다(그룹 점수 계산이 쓰는 문턱과 같은 값).
    """
    df = df.copy()
    for score in _RANKED_SCORES:
        for tag, keys in _RANK_POPULATIONS:
            rank_name = rank_column(score, tag)
            count_name = count_column(score, tag)
            if score not in df.columns or any(key not in df.columns for key in keys):
                df[rank_name] = pd.NA
                df[count_name] = pd.NA
                continue

            values = pd.to_numeric(df[score], errors="coerce")
            groups = [df[key] for key in keys]
            ranks = values.groupby(groups).rank(ascending=False, method="min")
            counts = values.groupby(groups).transform("count")
            too_small = counts < MIN_GROUP_POPULATION
            df[rank_name] = ranks.mask(too_small)
            df[count_name] = counts.mask(too_small)
    return df


# --- 구간 분류 ---

# 상위 몇 % 이내인지로 나누는 구간. QIP4·QIP3·기존 선별이 모두 시장별 상위 10%를
# 컷으로 쓰므로(`analysis/qip4_weights.SELECTION_RATIO`), 첫 구간을 그 값에 맞춘다.
SELECTED_TOP_PERCENT: float = w.SELECTION_RATIO * 100
WATCH_TOP_PERCENT: float = 25.0
ABOVE_AVERAGE_TOP_PERCENT: float = 50.0

_TIER_BANDS: tuple[tuple[float, str, str], ...] = (
    (SELECTED_TOP_PERCENT, "최상위", "tier-top"),
    (WATCH_TOP_PERCENT, "상위권", "tier-high"),
    (ABOVE_AVERAGE_TOP_PERCENT, "평균 이상", "tier-mid"),
    (100.0, "평균 이하", "tier-low"),
)

SELECTION_NOTE: str = (
    f"세 체계 모두 시장별 상위 {SELECTED_TOP_PERCENT:.0f}%를 선별 컷으로 쓴다 — "
    "'최상위'는 그 컷 안에 든다는 뜻이다(신뢰도·관문 조건은 별도로 본다)."
)


def _tier_for(top_percent: float) -> tuple[str, str]:
    for threshold, label, css_class in _TIER_BANDS:
        if top_percent <= threshold:
            return label, css_class
    return _TIER_BANDS[-1][1], _TIER_BANDS[-1][2]


# --- 표시 모델 ---


@dataclass(frozen=True)
class RankView:
    """한 모집단에서의 위치."""

    population: str  # "NASDAQ 내", "정보기술 섹터 내"
    top_percent_text: str  # "상위 8.4%"
    rank_text: str  # "3,100개 중 261위"
    tier_label: str
    tier_class: str


@dataclass(frozen=True)
class AxisView:
    label: str
    value: float | None
    text: str


@dataclass(frozen=True)
class ScoreSystemView:
    """점수 체계 하나(QIP4 / QIP3 / 기존 종합)의 표시 정보."""

    name: str
    purpose: str  # 이 체계가 무엇을 보는가 (혼동 방지용 한 줄)
    score: float | None
    score_text: str
    # 비교표가 열 단위로 읽으므로 모집단별로 따로 들고 있는다 (목록이면 템플릿이
    # 인덱스로 뒤져야 하고, 섹터 순위가 없는 종목에서 열이 밀린다).
    market_rank: RankView | None
    sector_rank: RankView | None
    axes: list[AxisView]

    @property
    def ranks(self) -> list[RankView]:
        """있는 순위만 표시 순서대로. 헤드라인 목록이 쓴다."""
        return [rank for rank in (self.market_rank, self.sector_rank) if rank]


@dataclass(frozen=True)
class ScorePanelView:
    """상세 페이지 점수 섹션 전체."""

    headline: ScoreSystemView  # 위에 크게 세우는 체계 (QIP4)
    headline_available: bool
    systems: list[ScoreSystemView]  # 접이식 비교표 (QIP4·QIP3·기존)
    selection_note: str


_SYSTEM_SPECS: tuple[tuple[str, str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "QIP4 정량 규칙",
        "QIP4 Score",
        "안정성 관문을 통과한 종목만 가치·성장으로 채점한다. 모멘텀은 선정이 아니라 "
        "집행률에만 관여한다.",
        (
            ("가치", "QIP4 Value"),
            ("성장성", "QIP4 Growth"),
            ("모멘텀", "QIP4 Momentum"),
        ),
    ),
    (
        "QIP3 5요인",
        "QIP3 Score",
        "안정성 하위 20%를 제외하고 가치성·성장성·모멘텀·재무건전성을 종합한다. "
        "관문이 아니라 분위수 컷을 쓴다.",
        (
            ("가치성", "QIP3 Value"),
            ("성장성", "QIP3 Growth"),
            ("모멘텀", "QIP3 Momentum"),
            ("재무건전성", "QIP3 Health"),
            ("안정성", "QIP3 Stability"),
        ),
    ),
    (
        "기존 종합",
        "Finalscore",
        "이 프로그램의 첫 점수 체계. 전 팩터를 퍼센타일·스탠다드 두 계열로 채점해 "
        "평균한 값이다.",
        (
            ("가치", "Vscore"),
            ("모멘텀", "Mscore"),
            ("펀더멘털", "Fscore"),
            ("이익 품질", "EQC"),
        ),
    ),
)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _position_text(rank: float, count: float, top_percent: float) -> str:
    """위치 문구. 아래쪽 절반은 "상위 100%"가 아니라 "하위 N%"로 읽는 게 자연스럽다."""
    if top_percent <= ABOVE_AVERAGE_TOP_PERCENT:
        return f"상위 {top_percent:.1f}%"
    bottom_percent = (count - rank + 1) / count * 100
    return f"하위 {bottom_percent:.1f}%"


def _rank_view(
    values: dict, score_column: str, population_tag: str, population: str | None
) -> RankView | None:
    """한 모집단에서의 위치. 순위가 없으면 None (모집단이 너무 작거나 점수 결측)."""
    if population is None:
        return None
    rank = _to_float(values.get(rank_column(score_column, population_tag)))
    count = _to_float(values.get(count_column(score_column, population_tag)))
    if rank is None or not count:
        return None
    top_percent = rank / count * 100
    tier_label, tier_class = _tier_for(top_percent)
    return RankView(
        population=population,
        top_percent_text=_position_text(rank, count, top_percent),
        rank_text=f"{int(count):,}개 중 {int(rank):,}위",
        tier_label=tier_label,
        tier_class=tier_class,
    )


def _system_view(
    spec: tuple[str, str, str, tuple[tuple[str, str], ...]],
    values: dict,
    market: str,
    sector: str | None,
) -> ScoreSystemView:
    name, score_column, purpose, axis_specs = spec
    score = _to_float(values.get(score_column))
    return ScoreSystemView(
        name=name,
        purpose=purpose,
        score=score,
        score_text=format_score(score),
        market_rank=_rank_view(values, score_column, "Market", f"{market} 내"),
        sector_rank=_rank_view(
            values, score_column, "Sector", f"{sector} 섹터 내" if sector else None
        ),
        axes=[
            AxisView(
                label=label,
                value=_to_float(values.get(column)),
                text=format_score(_to_float(values.get(column))),
            )
            for label, column in axis_specs
        ],
    )


def build_score_panel(
    values: dict, market: str, sector: str | None
) -> ScorePanelView | None:
    """상세 페이지 점수 섹션을 만든다. 세 체계 모두 비어 있으면 None."""
    systems = [_system_view(spec, values, market, sector) for spec in _SYSTEM_SPECS]
    if all(system.score is None for system in systems):
        return None
    headline = systems[0]
    return ScorePanelView(
        headline=headline,
        headline_available=headline.score is not None,
        systems=systems,
        selection_note=SELECTION_NOTE,
    )
