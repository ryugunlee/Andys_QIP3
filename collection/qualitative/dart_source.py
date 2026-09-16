"""OpenDART에서 최신 사업보고서 원문을 받아 정성 항목이 읽는 섹션만 텍스트로 만든다. DART_API_KEY 필요.

흐름: 종목코드 → corp_code(전체 목록 zip을 한 번 받아 qipinfos/에 캐시) → 공시 검색(사업보고서,
최종 정정본만) → 원본 문서 zip → XML 태그 제거 → 로마숫자 대제목("II. 사업의 내용")으로 섹션 분할.

전체 사업보고서는 대형주 기준 100만 토큰을 넘을 수 있어 기본은 DEFAULT_SECTIONS만 넣는다.
III(재무에 관한 사항·주석)은 Q7·Q8·Q9의 근거가 있지만 분량이 압도적이라 요청할 때만 포함한다.
키는 다른 수집 소스(FRED·ECOS)와 같이 .env / Actions Secrets의 환경변수로 읽는다.
"""

import io
import json
import os
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree

import requests

from collection.qualitative.sources import SourceDocument, html_to_text

DART_BASE_URL: str = "https://opendart.fss.or.kr/api"
REQUEST_TIMEOUT_SECONDS: int = 60
ANNUAL_REPORT_DETAIL_TYPE: str = "A001"  # 정기공시 > 사업보고서
STATUS_OK: str = "000"
STATUS_NO_DATA: str = "013"
# 사업보고서는 연 1회라 이 기간 안에 최신본이 반드시 하나 있다.
LOOKBACK_DAYS: int = 400
CORP_CODE_CACHE_PATH: Path = Path("qipinfos/dart_corp_codes.json")

DEFAULT_SECTIONS: tuple[str, ...] = ("II", "VI", "VII", "VIII", "IX", "X", "XI")
SECTION_NAMES: dict[str, str] = {
    "I": "회사의 개요", "II": "사업의 내용", "III": "재무에 관한 사항", "IV": "이사의 경영진단 및 분석의견",
    "V": "회계감사인의 감사의견 등", "VI": "이사회 등 회사의 기관에 관한 사항", "VII": "주주에 관한 사항",
    "VIII": "임원 및 직원 등에 관한 사항", "IX": "계열회사 등에 관한 사항", "X": "대주주 등과의 거래내용",
    "XI": "그 밖에 투자자 보호를 위하여 필요한 사항", "XII": "상세표",
}
# 유니코드 로마숫자(Ⅰ~Ⅻ)를 ASCII로 — DART 문서는 두 표기가 섞여 있다.
_ROMAN_UNICODE: dict[str, str] = {
    chr(0x2160 + index): numeral
    for index, numeral in enumerate(("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"))
}
_HEADING = re.compile(r"^\s*(XII|XI|IX|X|VIII|VII|VI|IV|V|III|II|I)\s*\.\s*(\S.*)$")


class DartError(RuntimeError):
    """OpenDART에서 원문을 받지 못했다."""


def _api_key() -> str:
    key = os.getenv("DART_API_KEY")
    if not key:
        raise DartError("DART_API_KEY 미설정 — .env(로컬) 또는 Actions Secrets에 넣어라 (opendart.fss.or.kr 무료 발급)")
    return key


def _get(path: str, **params) -> requests.Response:
    response = requests.get(
        f"{DART_BASE_URL}/{path}", params={"crtfc_key": _api_key(), **params}, timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response


# --- corp_code ---
def parse_corp_codes(xml_bytes: bytes) -> dict[str, str]:
    """corpCode.xml → {종목코드: corp_code}. 비상장(종목코드 공백)은 뺀다."""
    root = ElementTree.fromstring(xml_bytes)
    mapping: dict[str, str] = {}
    for entry in root.iter("list"):
        stock_code = (entry.findtext("stock_code") or "").strip()
        corp_code = (entry.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            mapping[stock_code] = corp_code
    return mapping


def _load_corp_codes() -> dict[str, str]:
    if CORP_CODE_CACHE_PATH.exists():
        return json.loads(CORP_CODE_CACHE_PATH.read_text(encoding="utf-8"))
    archive = zipfile.ZipFile(io.BytesIO(_get("corpCode.xml").content))
    mapping = parse_corp_codes(archive.read(archive.namelist()[0]))
    CORP_CODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORP_CODE_CACHE_PATH.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return mapping


def corp_code_for(stock_code: str) -> str:
    mapping = _load_corp_codes()
    if stock_code not in mapping:
        raise DartError(f"DART corp_code 목록에 종목코드 {stock_code}가 없다")
    return mapping[stock_code]


# --- 공시 검색 ---
def latest_annual_report(corp_code: str) -> dict:
    """가장 최근 사업보고서(정정본이 있으면 최종본)의 접수번호·접수일·보고서명."""
    begin = (date.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    payload = _get(
        "list.json", corp_code=corp_code, bgn_de=begin, pblntf_detail_ty=ANNUAL_REPORT_DETAIL_TYPE,
        last_reprt_at="Y", page_count=100,
    ).json()
    status = payload.get("status")
    if status == STATUS_NO_DATA or not payload.get("list"):
        raise DartError(f"최근 {LOOKBACK_DAYS}일 안에 사업보고서 공시가 없다 (corp_code {corp_code})")
    if status != STATUS_OK:
        raise DartError(f"OpenDART 오류 {status}: {payload.get('message')}")
    newest = max(payload["list"], key=lambda item: item["rcept_dt"])
    return {"rcept_no": newest["rcept_no"], "rcept_dt": newest["rcept_dt"], "report_nm": newest["report_nm"]}


# --- 원문 ---
def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949", errors="ignore")


def _main_xml(archive: zipfile.ZipFile, rcept_no: str) -> bytes:
    """원본 zip에는 본문 XML과 첨부가 섞여 있다. 접수번호로 시작하는 파일, 없으면 가장 큰 파일."""
    names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
    if not names:
        raise DartError(f"원본 zip에 XML이 없다 (rcept_no {rcept_no})")
    main = [name for name in names if Path(name).stem.startswith(rcept_no)]
    chosen = main[0] if main else max(names, key=lambda name: archive.getinfo(name).file_size)
    return archive.read(chosen)


def normalize_roman(text: str) -> str:
    for unicode_numeral, ascii_numeral in _ROMAN_UNICODE.items():
        text = text.replace(unicode_numeral, ascii_numeral)
    return text


def fetch_document_text(rcept_no: str) -> str:
    archive = zipfile.ZipFile(io.BytesIO(_get("document.xml", rcept_no=rcept_no).content))
    return normalize_roman(html_to_text(_decode(_main_xml(archive, rcept_no))))


# --- 섹션 ---
def split_sections(text: str) -> dict[str, str]:
    """로마숫자 대제목 기준으로 나눈다. 목차와 본문에 같은 제목이 두 번 나오므로 같은 번호는 이어 붙인다."""
    buckets: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            current = match.group(1)
            buckets.setdefault(current, [])
        if current is not None:
            buckets[current].append(line)
    return {numeral: "\n".join(lines) for numeral, lines in buckets.items()}


def select_sections(text: str, sections: tuple[str, ...]) -> tuple[str, list[str]]:
    """요청한 섹션만 이어 붙인다. 대제목을 하나도 못 찾으면 전체를 돌려주고 빈 목록으로 알린다."""
    found = split_sections(text)
    if not found:
        return text, []
    chosen = [numeral for numeral in sections if numeral in found]
    return "\n\n".join(found[numeral] for numeral in chosen), chosen


def fetch_dart_report(stock_code: str, sections: tuple[str, ...] | None = DEFAULT_SECTIONS) -> tuple[SourceDocument, dict]:
    """종목코드 → (선택 섹션 텍스트 문서, 메타). sections=None이면 전체."""
    report = latest_annual_report(corp_code_for(stock_code))
    full_text = fetch_document_text(report["rcept_no"])
    if sections is None:
        text, chosen = full_text, ["전체"]
    else:
        text, chosen = select_sections(full_text, sections)
    title = f"{report['report_nm']} (접수 {report['rcept_dt']})"
    meta = {**report, "sections": chosen, "full_chars": len(full_text), "chars": len(text)}
    return SourceDocument(title=title, text=text), meta
