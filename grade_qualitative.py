"""정성 평가 진입점 — LLM 채점 추출과 등급 판정을 명령줄로 실행한다.

세 명령이 있고, 각각 독립적으로 쓸 수 있다:

    python grade_qualitative.py template 005930 --sector-group 자본집약사이클
        → qualitative/observations/005930.json 빈 템플릿. 사람이 손으로 채우는 경로.
    python grade_qualitative.py extract 005930 원문.txt --asof 2026-03-18 [--items Q1Q4Q6]
        → LLM 1회 호출로 9항목을 채점한 관측값 JSON.
    python grade_qualitative.py grade 005930 [--market KOSPI] [--no-save]
        → 등급카드 출력(★ 플래그 포함), qualitative_grades 테이블에 저장.

추출 단계는 정량 DB를 읽지 않는다(주가·정량 점수를 보지 않는다 — `.claude/정성 평가 규칙.md` 6절).
DB는 grade 단계에서 ★ 플래그 계산과 저장에만 연다. ANTHROPIC_API_KEY는 로컬 .env에서 읽는다.
"""

import argparse
import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

import storage
from analysis.qualitative import (
    GradeResult,
    ObservationSet,
    TrendFlag,
    compute_trend_flag,
    load_observations,
    observation_path,
    qualitative_grade,
    save_observations,
)
from analysis.qualitative.weights import DECISION_REJECT, GRADE_VALID_MONTHS
from collection.qualitative import blank_observations, create_client, extract_observations, load_source
from collection.qualitative.items import ITEM_CODES, ITEMS_BY_CODE
from collection.sector_groups import GROUP_ASSET, GROUP_CYCLICAL, GROUP_GENERAL, GROUP_INTANGIBLE
from collection.tickers import is_korean_listed_ticker

load_dotenv()

SECTOR_GROUP_CHOICES: tuple[str, ...] = (GROUP_GENERAL, GROUP_ASSET, GROUP_INTANGIBLE, GROUP_CYCLICAL)
_MONTHS_PER_YEAR: int = 12
_ITEMS_PER_CARD_LINE: int = 5
_STATUS_NOT_INVESTIGATED: str = "not_investigated"


def _add_months(base: date, months: int) -> date:
    month_index = base.month - 1 + months
    year = base.year + month_index // _MONTHS_PER_YEAR
    month = month_index % _MONTHS_PER_YEAR + 1
    return date(year, month, 1)


def _parse_items(text: str | None) -> tuple[str, ...]:
    if not text:
        return ITEM_CODES
    codes = tuple(f"Q{digit}" for digit in text.upper().replace("Q", ""))
    unknown = [code for code in codes if code not in ITEMS_BY_CODE]
    if unknown:
        raise SystemExit(f"알 수 없는 항목 코드: {', '.join(unknown)} (Q1~Q9)")
    return codes


def _item_label(code: str, result) -> str:
    title = ITEMS_BY_CODE[code].short
    if result.score is None:
        return f"{code} {title} -"
    mark = "*" if result.weak else ""
    return f"{code} {title} {result.grade}({result.score:.0f}){mark}"


def _item_lines(result: GradeResult) -> list[str]:
    labels = [_item_label(code, item) for code, item in result.items.items()]
    return [
        "  ".join(labels[start:start + _ITEMS_PER_CARD_LINE])
        for start in range(0, len(labels), _ITEMS_PER_CARD_LINE)
    ]


def _trend_line(flag: TrendFlag | None) -> str:
    if flag is None or flag.return_6m is None:
        return "[★]      계산 불가 (일봉·재무 데이터 없음)"
    income = f"영업이익 {flag.income_change:+.0%}" if flag.income_change is not None else "영업이익 변화 미상"
    if flag.code is None:
        return f"[★]      없음 — 6개월 {flag.return_6m:+.0%}, {income}"
    return f"[★]      {flag.code} — 6개월 {flag.return_6m:+.0%}, {income} → 원인 확인 필요"


def format_grade_card(
    observation_set: ObservationSet, result: GradeResult, graded_on: date, flag: TrendFlag | None
) -> str:
    """`.claude/정성 평가 규칙.md` 7절 양식. `*`는 weak(점수 상한 적용) 항목."""
    valid_until = _add_months(graded_on, GRADE_VALID_MONTHS)
    lines = [
        f"[식별]   {observation_set.ticker} / 섹터군 {observation_set.sector_group or '미지정'} / "
        f"관측 {observation_set.asof} / 판정 {graded_on} / 유효 {valid_until}",
    ]
    item_lines = _item_lines(result)
    lines.append(f"[항목]   {item_lines[0]}")
    lines.extend(f"         {line}" for line in item_lines[1:])
    if result.veto_reasons:
        lines.append(f"[종합]   F → 기각   [결격] {', '.join(result.veto_reasons)}")
    elif result.composite is None:
        lines.append(f"[종합]   {result.decision} — 유효 항목 {result.valid_items}개")
    else:
        caps = f" (상한: {', '.join(result.cap_reasons)})" if result.cap_reasons else ""
        lines.append(f"[종합]   {result.composite} ({result.score})  배수 {result.multiplier:.2f}{caps} → {result.decision}")
        lines.append("         배수는 집행률과 곱하지 않는다 — 판단 재료로 나란히 본다   [결격] 통과")
    by_code = observation_set.by_code()
    watch = [
        f"{code} {ITEMS_BY_CODE[code].short} {result.items[code].grade} — {by_code[code].rationale}"
        for code in result.watch_items
    ]
    lines.append("[주의]   " + (" / ".join(watch) if watch else "없음"))
    lines.append(_trend_line(flag))
    uninvestigated = [code for code, obs in by_code.items() if obs.status == _STATUS_NOT_INVESTIGATED]
    lines.append(f"[미조사]  {', '.join(uninvestigated) or '없음'}")
    return "\n".join(lines)


def _grade_row(
    observation_set: ObservationSet, result: GradeResult, graded_on: date, path: Path, flag: TrendFlag | None
) -> dict:
    item_scores = {code: {"score": item.score, "grade": item.grade} for code, item in result.items.items()}
    return {
        "ticker": observation_set.ticker,
        "graded_on": graded_on,
        "observed_asof": date.fromisoformat(observation_set.asof),  # asof는 DuckDB 예약어
        "sector_group": observation_set.sector_group,
        "item_scores": json.dumps(item_scores),
        "composite": result.composite,
        "score": result.score,
        "multiplier": result.multiplier,
        "decision": result.decision,
        "veto_reasons": "|".join(result.veto_reasons),
        "cap_reasons": "|".join(result.cap_reasons),
        "watch_items": "|".join(result.watch_items),
        "valid_items": result.valid_items,
        "trend_flag": flag.code if flag else None,
        "valid_until": _add_months(graded_on, GRADE_VALID_MONTHS),
        "observations_path": str(path),
    }


def command_template(args: argparse.Namespace) -> None:
    path = save_observations(blank_observations(args.ticker, args.asof, args.sector_group))
    print(f"[qualitative] 템플릿 생성: {path}")


def command_extract(args: argparse.Namespace) -> None:
    document = load_source(Path(args.source))
    observation_set = extract_observations(
        create_client(), document, args.ticker, args.asof, args.sector_group, items=_parse_items(args.items),
    )
    path = save_observations(observation_set)
    scored = sum(1 for obs in observation_set.observations if obs.score is not None)
    print(f"[qualitative] 관측값 저장: {path} (채점 {scored}개 / 결측·미조사 {len(observation_set.observations) - scored}개)")


def command_grade(args: argparse.Namespace) -> None:
    path = observation_path(args.ticker)
    observation_set = load_observations(path)
    result = qualitative_grade(observation_set)
    graded_on = date.today()

    is_korean = is_korean_listed_ticker(args.ticker)
    market = args.market or ("KOSPI" if is_korean else "NASDAQ")
    source = "naver" if is_korean else "yahoo"
    db_path = storage.stock_db_path_for_market(market)
    flag: TrendFlag | None = None
    if os.path.exists(db_path):
        conn = storage.connect(db_path)
        try:
            flag = compute_trend_flag(conn, args.ticker, source)
            if not args.no_save:
                storage.upsert_qualitative_grade(conn, _grade_row(observation_set, result, graded_on, path, flag))
        finally:
            conn.close()
    print(format_grade_card(observation_set, result, graded_on, flag))
    if args.no_save:
        return
    if os.path.exists(db_path):
        print(f"[qualitative] qualitative_grades 저장 완료 ({market} DB)")
    else:
        print(f"[qualitative] DB 없음({db_path}) — 저장·★ 플래그 생략")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="정성 평가 — LLM 채점 추출과 등급 판정")
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser("template", help="수동 입력용 빈 관측값 JSON")
    template.add_argument("ticker")
    template.add_argument("--asof", default=date.today().isoformat())
    template.add_argument("--sector-group", choices=SECTOR_GROUP_CHOICES, default=None)
    template.set_defaults(handler=command_template)

    extract = commands.add_parser("extract", help="원문에서 LLM으로 9항목 채점")
    extract.add_argument("ticker")
    extract.add_argument("source", help="사업보고서·10-K 원문 (txt/md/html/pdf)")
    extract.add_argument("--asof", default=date.today().isoformat(), help="원문 기준일")
    extract.add_argument("--sector-group", choices=SECTOR_GROUP_CHOICES, default=None)
    extract.add_argument("--items", default=None, help="채점할 항목 코드만 (예: Q1Q4Q6 또는 146)")
    extract.set_defaults(handler=command_extract)

    grade = commands.add_parser("grade", help="관측값 JSON을 판정해 등급카드 출력·저장")
    grade.add_argument("ticker")
    grade.add_argument("--market", default=None, help="DB를 고르는 시장명 (기본: 티커로 추정)")
    grade.add_argument("--no-save", action="store_true")
    grade.set_defaults(handler=command_grade)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
