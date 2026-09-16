"""정성 평가 진입점 — LLM 채점 추출과 등급 판정을 명령줄로 실행한다.

세 명령이 있고, 각각 독립적으로 쓸 수 있다:

    python grade_qualitative.py template 005930 --sector-group 자본집약사이클
        → qualitative/observations/005930.json 빈 템플릿. 사람이 손으로 채우는 경로.
    python grade_qualitative.py extract 005930 [원문.txt] [--tier quick|deep] [--provider anthropic|compat]
                                 [--asof 2026-03-18] [--items Q1Q4Q6] [--sections II,VI]
        → LLM 1회 호출로 9항목을 채점한 관측값 JSON. 원문을 생략하면 한국은 OpenDART 사업보고서,
          미국은 SEC EDGAR 10-K를 자동으로 받아 qualitative/sources/에 저장한 뒤 쓴다.
          quick(기본)은 싸고 넓게(Sonnet 5 또는 OpenAI 호환 저가 모델, 섹션 II·VI·X), deep은 Opus 5로
          III(재무·주석)까지 읽는다 — 티어 정의는 collection/qualitative/tiers.py.
    python grade_qualitative.py grade 005930 [--market KOSPI] [--no-save]
        → 등급카드 출력(★ 플래그 포함), qualitative_grades 테이블에 저장.
    python grade_qualitative.py revalidate 005930 원문.txt 응답.response.json --asof 2026-03-10
        → 저장해 둔 LLM 원본 응답을 현재 규칙(스키마·인용 대조·어휘)으로 다시 검증해 관측값 JSON을 만든다.
          LLM을 다시 부르지 않는다 — 규칙·프롬프트를 고치며 반복할 때 쓴다.

추출 단계는 정량 DB를 읽지 않는다(주가·정량 점수를 보지 않는다 — `.claude/정성 평가 규칙.md` 6절).
DB는 grade 단계에서 ★ 플래그 계산과 저장에만 연다. ANTHROPIC_API_KEY·DART_API_KEY·EDGAR_USER_AGENT는
로컬 .env에서 읽는다.
"""

import argparse
import json
import os
from datetime import date
from functools import partial
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
from collection.qualitative import (
    blank_observations,
    compat_extract_structured,
    create_client,
    create_compat_client,
    extract_observations,
    extract_structured,
    load_source,
)
from collection.qualitative.dart_source import SECTION_NAMES, fetch_dart_report
from collection.qualitative.edgar_source import fetch_edgar_10k
from collection.qualitative.sources import SOURCES_DIR, SourceDocument, save_source_text
from collection.qualitative.tiers import PROVIDER_ANTHROPIC, PROVIDER_COMPAT, TIER_DEEP, TIER_QUICK, TIERS, Tier
from collection.qualitative.items import ITEM_CODES, ITEMS_BY_CODE
from collection.sector_groups import GROUP_ASSET, GROUP_CYCLICAL, GROUP_GENERAL, GROUP_INTANGIBLE
from collection.tickers import is_korean_listed_ticker

load_dotenv()

SECTOR_GROUP_CHOICES: tuple[str, ...] = (GROUP_GENERAL, GROUP_ASSET, GROUP_INTANGIBLE, GROUP_CYCLICAL)
_MONTHS_PER_YEAR: int = 12
_ITEMS_PER_CARD_LINE: int = 5
_STATUS_NOT_INVESTIGATED: str = "not_investigated"
# 한국어 원문은 글자 수가 곧 토큰 수에 가깝다. 이보다 크면 비용·컨텍스트 사고를 막기 위해 멈춘다.
MAX_SOURCE_CHARS: int = 600_000


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


def _item_label(code: str, result, observation) -> str:
    title = ITEMS_BY_CODE[code].short
    if result.score is None:
        not_applicable = observation is not None and (observation.raw or {}).get("order_book_business") is False
        return f"{code} {title} {'해당없음' if not_applicable else '-'}"
    mark = "*" if result.weak else ""
    return f"{code} {title} {result.grade}({result.score:.0f}){mark}"


def _item_lines(result: GradeResult, by_code: dict) -> list[str]:
    labels = [_item_label(code, item, by_code.get(code)) for code, item in result.items.items()]
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
    scorer = f" / {observation_set.tier} · {observation_set.model}" if observation_set.model else ""
    lines = [
        f"[식별]   {observation_set.ticker} / 섹터군 {observation_set.sector_group or '미지정'} / "
        f"관측 {observation_set.asof} / 판정 {graded_on} / 유효 {valid_until}{scorer}",
    ]
    by_code = observation_set.by_code()
    item_lines = _item_lines(result, by_code)
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
        "tier": observation_set.tier,
        "model": observation_set.model,
        "valid_until": _add_months(graded_on, GRADE_VALID_MONTHS),
        "observations_path": str(path),
    }


def command_template(args: argparse.Namespace) -> None:
    path = save_observations(blank_observations(args.ticker, args.asof, args.sector_group))
    print(f"[qualitative] 템플릿 생성: {path}")


def _parse_sections(text: str | None, all_sections: bool, tier: Tier) -> tuple[str, ...] | None:
    if all_sections:
        return None
    if not text:
        return tier.sections
    sections = tuple(part.strip().upper() for part in text.replace(" ", ",").split(",") if part.strip())
    unknown = [numeral for numeral in sections if numeral not in SECTION_NAMES]
    if unknown:
        raise SystemExit(f"알 수 없는 섹션: {', '.join(unknown)} (I~XII)")
    return sections


def _scorer(tier: Tier, provider: str):
    """티어·provider에 맞는 (채점 호출 함수, 모델 id). 추출기는 provider를 모른다."""
    if provider == PROVIDER_COMPAT:
        client, model = create_compat_client()
        print(f"[qualitative] 티어 {tier.name} / provider 호환 엔드포인트 / 모델 {model}")
        return partial(compat_extract_structured, client, model), model
    print(f"[qualitative] 티어 {tier.name} / provider anthropic / 모델 {tier.anthropic_model} (effort {tier.effort})")
    return partial(extract_structured, create_client(), model=tier.anthropic_model, effort=tier.effort), tier.anthropic_model


def cached_source(ticker: str) -> Path | None:
    """주간 워크플로가 미리 받아 둔(또는 이전 실행이 남긴) 원문 중 가장 최근 것."""
    candidates = sorted(SOURCES_DIR.glob(f"{ticker}_*.txt"))
    return candidates[-1] if candidates else None


def _fetch_source(args: argparse.Namespace, tier: Tier) -> tuple[SourceDocument, str]:
    """원문 인수가 없을 때: 캐시된 원문이 있으면 그것을, 없으면 시장별로 자동 수집한다. (문서, 기준일 stamp)"""
    cached = None if args.refetch else cached_source(args.ticker)
    if cached is not None:
        print(f"[qualitative] 캐시된 원문 사용: {cached} (--refetch로 다시 받을 수 있다)")
        return load_source(cached), cached.stem.split("_")[-1]
    if is_korean_listed_ticker(args.ticker):
        document, meta = fetch_dart_report(args.ticker, _parse_sections(args.sections, args.all_sections, tier))
        names = ", ".join(f"{numeral} {SECTION_NAMES.get(numeral, '')}".strip() for numeral in meta["sections"])
        print(f"[qualitative] DART {meta['report_nm']} 접수 {meta['rcept_dt']} — 전체 {meta['full_chars']:,}자 중 "
              f"{meta['chars']:,}자 사용 (섹션: {names or '대제목 미검출 → 전체'})")
        stamp = meta["rcept_dt"]
    else:
        document, meta = fetch_edgar_10k(args.ticker)
        print(f"[qualitative] EDGAR 10-K report {meta['report_date']} filed {meta['filing_date']} — {meta['chars']:,}자")
        stamp = meta["filing_date"].replace("-", "")
    path = save_source_text(args.ticker, stamp, document.text or "")
    print(f"[qualitative] 원문 저장: {path} (다음엔 이 파일을 extract에 넘기면 다시 받지 않는다)")
    return document, stamp


def command_extract(args: argparse.Namespace) -> None:
    tier = TIERS[args.tier]
    asof = args.asof
    if args.source:
        document = load_source(Path(args.source))
    else:
        document, stamp = _fetch_source(args, tier)
        asof = asof or f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
    asof = asof or date.today().isoformat()
    chars = len(document.text or "")
    if chars > MAX_SOURCE_CHARS and not args.force:
        raise SystemExit(
            f"원문이 {chars:,}자로 상한 {MAX_SOURCE_CHARS:,}자를 넘는다 — --sections로 줄이거나 --force로 강행하라"
        )
    call, model = _scorer(tier, args.provider)
    observation_set = extract_observations(
        call, document, args.ticker, asof, args.sector_group, items=_parse_items(args.items), tier=tier.name, model=model,
    )
    path = save_observations(observation_set)
    scored = sum(1 for obs in observation_set.observations if obs.score is not None)
    print(f"[qualitative] 관측값 저장: {path} (채점 {scored}개 / 결측·미조사 {len(observation_set.observations) - scored}개)")


def command_revalidate(args: argparse.Namespace) -> None:
    document = load_source(Path(args.source))
    saved_payload = json.loads(Path(args.response).read_text(encoding="utf-8"))
    observation_set = extract_observations(
        lambda **_: saved_payload, document, args.ticker, args.asof, args.sector_group, items=_parse_items(args.items),
        tier=args.tier, model=args.model,
    )
    path = save_observations(observation_set)
    scored = sum(1 for obs in observation_set.observations if obs.score is not None)
    print(f"[qualitative] 재검증 저장: {path} (채점 {scored}개 / 결측·미조사 {len(observation_set.observations) - scored}개)")


def grade_ticker(ticker: str, market: str | None, save: bool) -> str:
    """관측값 JSON → 판정 → (DB가 있으면) ★ 플래그 계산·저장. 등급카드 문자열을 돌려준다."""
    path = observation_path(ticker)
    observation_set = load_observations(path)
    result = qualitative_grade(observation_set)
    graded_on = date.today()

    is_korean = is_korean_listed_ticker(ticker)
    market = market or ("KOSPI" if is_korean else "NASDAQ")
    source = "naver" if is_korean else "yahoo"
    db_path = storage.stock_db_path_for_market(market)
    flag: TrendFlag | None = None
    if os.path.exists(db_path):
        conn = storage.connect(db_path)
        try:
            flag = compute_trend_flag(conn, ticker, source)
            if save:
                storage.upsert_qualitative_grade(conn, _grade_row(observation_set, result, graded_on, path, flag))
        finally:
            conn.close()
    card = format_grade_card(observation_set, result, graded_on, flag)
    if save:
        card += (f"\n[qualitative] qualitative_grades 저장 완료 ({market} DB)" if os.path.exists(db_path)
                 else f"\n[qualitative] DB 없음({db_path}) — 저장·★ 플래그 생략")
    return card


def command_grade(args: argparse.Namespace) -> None:
    print(grade_ticker(args.ticker, args.market, save=not args.no_save))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="정성 평가 — LLM 채점 추출과 등급 판정")
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser("template", help="수동 입력용 빈 관측값 JSON")
    template.add_argument("ticker")
    template.add_argument("--asof", default=date.today().isoformat())
    template.add_argument("--sector-group", choices=SECTOR_GROUP_CHOICES, default=None)
    template.set_defaults(handler=command_template)

    extract = commands.add_parser("extract", help="원문에서 LLM으로 9항목 채점 (원문 생략 시 자동 수집)")
    extract.add_argument("ticker")
    extract.add_argument("source", nargs="?", default=None, help="사업보고서·10-K 원문 (txt/md/html/pdf). 생략하면 DART/EDGAR 자동 수집")
    extract.add_argument("--asof", default=None, help="원문 기준일 (기본: 자동 수집 접수일 또는 오늘)")
    extract.add_argument("--tier", choices=(TIER_QUICK, TIER_DEEP), default=TIER_QUICK, help="quick: 싸고 넓게 / deep: Opus로 재무·주석까지")
    extract.add_argument("--provider", choices=(PROVIDER_ANTHROPIC, PROVIDER_COMPAT), default=PROVIDER_ANTHROPIC,
                         help="compat = OpenAI 호환 엔드포인트(DeepSeek 등, COMPAT_LLM_* 환경변수)")
    extract.add_argument("--sections", default=None, help="DART 섹션 로마숫자 (기본: 티어별 — quick II,VI,X,III* / deep I,II,III,VI,VII,X,XI). III*=재무 핵심 주석만")
    extract.add_argument("--all-sections", action="store_true", help="DART 사업보고서 전체 사용")
    extract.add_argument("--force", action="store_true", help=f"원문 {MAX_SOURCE_CHARS:,}자 상한 무시")
    extract.add_argument("--refetch", action="store_true", help="qualitative/sources/에 캐시된 원문이 있어도 다시 받는다")
    extract.add_argument("--sector-group", choices=SECTOR_GROUP_CHOICES, default=None)
    extract.add_argument("--items", default=None, help="채점할 항목 코드만 (예: Q1Q4Q6 또는 146)")
    extract.set_defaults(handler=command_extract)

    revalidate = commands.add_parser("revalidate", help="저장된 LLM 원본 응답을 현재 규칙으로 재검증 (재호출 없음)")
    revalidate.add_argument("ticker")
    revalidate.add_argument("source", help="그 응답을 만들 때 쓴 원문 파일")
    revalidate.add_argument("response", help="qualitative/sources/<티커>_<기준일>.response.json")
    revalidate.add_argument("--asof", required=True)
    revalidate.add_argument("--sector-group", choices=SECTOR_GROUP_CHOICES, default=None)
    revalidate.add_argument("--items", default=None)
    revalidate.add_argument("--tier", choices=(TIER_QUICK, TIER_DEEP), default=None, help="그 응답을 만든 티어 (기록용)")
    revalidate.add_argument("--model", default=None, help="그 응답을 만든 모델 id (기록용)")
    revalidate.set_defaults(handler=command_revalidate)

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
