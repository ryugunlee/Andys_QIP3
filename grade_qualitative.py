"""정성 평가 진입점 — 관측값 추출(L2)과 등급 판정(L3)을 명령줄로 실행한다.

세 명령이 있고, 각각 독립적으로 쓸 수 있다:

    python grade_qualitative.py template 005930 --sector-group 자본집약사이클
        → qualitative/observations/005930.json 빈 템플릿. 사람이 손으로 채우는 파일럿 경로.
    python grade_qualitative.py extract 005930 원문.txt --asof 2026-03-18 [--axes GDI]
        → LLM이 A·B급 항목을 채운 관측값 JSON. C급 항목은 not_investigated로 남는다.
    python grade_qualitative.py grade 005930 [--market KOSPI] [--no-save]
        → 등급카드를 출력하고 qualitative_grades 테이블에 저장.

`.claude/정성 평가 규칙.md` 8-2의 순서를 따르면 추출 단계에서는 주가·정량 점수를 보지 않는다.
그래서 이 스크립트는 정량 DB를 읽지 않는다 — 판정 결과를 저장할 때만 DB를 연다.
ANTHROPIC_API_KEY는 로컬 .env(python-dotenv)에서 읽는다.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

import storage
from analysis.qualitative import GradeResult, ObservationSet, load_observations, observation_path, qualitative_grade, save_observations
from analysis.qualitative.weights import DECISION_REJECT, GRADE_VALID_MONTHS, ITEM_MAX_POINTS
from collection.qualitative import blank_observations, create_client, extract_observations, load_source
from collection.qualitative.items import AXIS_CODES, ITEMS_BY_CODE
from collection.sector_groups import GROUP_ASSET, GROUP_CYCLICAL, GROUP_GENERAL, GROUP_INTANGIBLE
from collection.tickers import is_korean_listed_ticker

load_dotenv()

SECTOR_GROUP_CHOICES: tuple[str, ...] = (GROUP_GENERAL, GROUP_ASSET, GROUP_INTANGIBLE, GROUP_CYCLICAL)
_MONTHS_PER_YEAR: int = 12


def _add_months(base: date, months: int) -> date:
    month_index = base.month - 1 + months
    year = base.year + month_index // _MONTHS_PER_YEAR
    month = month_index % _MONTHS_PER_YEAR + 1
    return date(year, month, 1)


def _format_axis_line(result: GradeResult) -> str:
    return "  ".join(
        f"{axis}:{axis_result.grade}({axis_result.earned}/{axis_result.max_points})"
        for axis, axis_result in result.axes.items()
    )


def format_grade_card(observation_set: ObservationSet, result: GradeResult, graded_on: date) -> str:
    """`.claude/정성 평가 규칙.md` 9-1 양식 중 1단계에서 산출하는 칸만 채운 등급카드."""
    valid_until = _add_months(graded_on, GRADE_VALID_MONTHS)
    lines = [
        f"[식별]      {observation_set.ticker} / 섹터군 {observation_set.sector_group or '미지정'} / "
        f"관측 기준일 {observation_set.asof} / 판정일 {graded_on} / 유효기한 {valid_until}",
        f"[정성 등급]  {_format_axis_line(result)}",
    ]
    if result.composite is not None:
        lines.append(f"            종합: {result.composite} ({result.score}점)")
    if result.veto_reasons:
        lines.append(f"[결격 검사]  기각 — {', '.join(result.veto_reasons)}")
    else:
        lines.append("[결격 검사]  통과 (G5 / I6)")
    if result.multiplier is not None and result.decision != DECISION_REJECT:
        caps = ", ".join(result.cap_reasons) if result.cap_reasons else "없음"
        lines.append(f"[배수]      {result.multiplier:.2f} (하한 규칙: {caps}) → {result.decision}")
        lines.append("            집행률과 곱하지 않는다 — 판단 재료로 나란히 본다")
    else:
        lines.append(f"[판정]      {result.decision}")
    lines.append(f"[감시 대상]  0·{ITEM_MAX_POINTS - 1}점 항목 {len(result.watch_items)}개")
    for code in result.watch_items:
        points = next(axis.item_points[code] for axis in result.axes.values() if code in axis.item_points)
        lines.append(f"  {code} {ITEMS_BY_CODE[code].title} — {points}점")
    uninvestigated = [
        observation.item for observation in observation_set.observations
        if observation.status == "not_investigated"
    ]
    lines.append(f"[미조사 항목] {result.not_investigated_share:.0%} — {', '.join(uninvestigated) or '없음'}")
    return "\n".join(lines)


def _grade_row(observation_set: ObservationSet, result: GradeResult, graded_on: date, path: Path) -> dict:
    return {
        "ticker": observation_set.ticker,
        "graded_on": graded_on,
        "observed_asof": date.fromisoformat(observation_set.asof),  # asof는 DuckDB 예약어
        "sector_group": observation_set.sector_group,
        "axis_grades": json.dumps({axis: axis_result.grade for axis, axis_result in result.axes.items()}),
        "composite": result.composite,
        "score": result.score,
        "multiplier": result.multiplier,
        "decision": result.decision,
        "veto_reasons": "|".join(result.veto_reasons),
        "cap_reasons": "|".join(result.cap_reasons),
        "watch_items": "|".join(result.watch_items),
        "not_investigated_share": result.not_investigated_share,
        "valid_until": _add_months(graded_on, GRADE_VALID_MONTHS),
        "observations_path": str(path),
    }


def command_template(args: argparse.Namespace) -> None:
    path = save_observations(blank_observations(args.ticker, args.asof, args.sector_group))
    print(f"[qualitative] 템플릿 생성: {path}")


def command_extract(args: argparse.Namespace) -> None:
    document = load_source(Path(args.source))
    axes = tuple(args.axes) if args.axes else AXIS_CODES
    observation_set = extract_observations(
        create_client(), document, args.ticker, args.asof, args.sector_group,
        axes=axes, double_check=not args.no_double_check,
    )
    path = save_observations(observation_set)
    print(f"[qualitative] 관측값 저장: {path} ({len(observation_set.observations)}개 항목)")


def command_grade(args: argparse.Namespace) -> None:
    path = observation_path(args.ticker)
    observation_set = load_observations(path)
    result = qualitative_grade(observation_set)
    graded_on = date.today()
    print(format_grade_card(observation_set, result, graded_on))
    if args.no_save:
        return
    market = args.market or ("KOSPI" if is_korean_listed_ticker(args.ticker) else "NASDAQ")
    conn = storage.connect(storage.stock_db_path_for_market(market))
    try:
        storage.upsert_qualitative_grade(conn, _grade_row(observation_set, result, graded_on, path))
    finally:
        conn.close()
    print(f"[qualitative] qualitative_grades 저장 완료 ({market} DB)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="정성 평가 — 관측값 추출과 등급 판정")
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser("template", help="수동 입력용 빈 관측값 JSON")
    template.add_argument("ticker")
    template.add_argument("--asof", default=date.today().isoformat())
    template.add_argument("--sector-group", choices=SECTOR_GROUP_CHOICES, default=None)
    template.set_defaults(handler=command_template)

    extract = commands.add_parser("extract", help="원문에서 LLM으로 관측값 추출")
    extract.add_argument("ticker")
    extract.add_argument("source", help="사업보고서·10-K 원문 (txt/md/html/pdf)")
    extract.add_argument("--asof", default=date.today().isoformat(), help="원문 기준일")
    extract.add_argument("--sector-group", choices=SECTOR_GROUP_CHOICES, default=None)
    extract.add_argument("--axes", default=None, help="추출할 축 코드만 (예: GDI)")
    extract.add_argument("--no-double-check", action="store_true", help="핵심 항목 2회 추출 생략")
    extract.set_defaults(handler=command_extract)

    grade = commands.add_parser("grade", help="관측값 JSON을 판정해 등급카드 출력·저장")
    grade.add_argument("ticker")
    grade.add_argument("--market", default=None, help="저장할 DB를 고르는 시장명 (기본: 티커로 추정)")
    grade.add_argument("--no-save", action="store_true")
    grade.set_defaults(handler=command_grade)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
