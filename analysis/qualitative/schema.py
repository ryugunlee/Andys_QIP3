"""관측값 JSON(L2 산출물)의 자료구조와 파일 입출력.

`.claude/정성 평가 규칙.md` 4-1의 스키마를 그대로 옮겼다. 관측값 파일은
`qualitative/observations/<티커>.json`에 git으로 추적한다 — 사람이 검토·수정한 diff가
남아야 재현성 검증(5-3)이 가능하기 때문이다. 등급 결과만 DuckDB에 들어간다.

status 규약:
- observed:         사실이 원문에서 확인됨
- weak:             확인됐으나 증거가 3~4급뿐이거나 인용 대조 실패 → 점수 상한 1점
- missing:          공시 자체에 없음 → 분자·분모 모두 제외
- not_investigated: 확인하지 않음 → missing과 같이 제외하되 비율이 크면 판정 미완료
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUS_OBSERVED: str = "observed"
STATUS_WEAK: str = "weak"
STATUS_MISSING: str = "missing"
STATUS_NOT_INVESTIGATED: str = "not_investigated"
STATUSES: tuple[str, ...] = (STATUS_OBSERVED, STATUS_WEAK, STATUS_MISSING, STATUS_NOT_INVESTIGATED)

# 증거 등급 (규칙서 ①-2). 3급 이하만 있으면 weak.
EVIDENCE_GRADE_PRIMARY: int = 1
EVIDENCE_GRADE_SECONDARY: int = 2
EVIDENCE_GRADE_WEAK_MIN: int = 3

OBSERVATIONS_DIR: Path = Path("qualitative/observations")


@dataclass
class Evidence:
    source: str
    date: str
    grade: int
    quote: str = ""
    locator: str = ""


@dataclass
class Observation:
    item: str
    status: str
    raw: dict | None = None
    evidence: list[Evidence] = field(default_factory=list)
    note: str = ""

    def is_excluded(self) -> bool:
        return self.status in (STATUS_MISSING, STATUS_NOT_INVESTIGATED)


@dataclass
class ObservationSet:
    ticker: str
    asof: str
    sector_group: str | None
    observations: list[Observation]
    source_title: str = ""

    def by_code(self) -> dict[str, Observation]:
        return {observation.item: observation for observation in self.observations}


def observation_path(ticker: str) -> Path:
    return OBSERVATIONS_DIR / f"{ticker}.json"


def save_observations(observation_set: ObservationSet, path: Path | None = None) -> Path:
    target = path or observation_path(observation_set.ticker)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(observation_set), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def load_observations(path: Path) -> ObservationSet:
    payload = json.loads(path.read_text(encoding="utf-8"))
    observations = [
        Observation(
            item=entry["item"],
            status=entry["status"],
            raw=entry.get("raw"),
            evidence=[Evidence(**evidence) for evidence in entry.get("evidence", [])],
            note=entry.get("note", ""),
        )
        for entry in payload["observations"]
    ]
    return ObservationSet(
        ticker=payload["ticker"],
        asof=payload["asof"],
        sector_group=payload.get("sector_group"),
        observations=observations,
        source_title=payload.get("source_title", ""),
    )
