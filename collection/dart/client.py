"""OpenDART HTTP 클라이언트와 corp_code 매핑 — 수집·정성 양쪽이 공유한다.

원래 `collection/qualitative/dart_source.py`에 있었으나, 재무제표 수집(`statements.py`)도
같은 키·같은 corp_code 목록을 써야 해서 여기로 올렸다 (`.claude/PROBLEMS.md` #44).
`dart_source.py`는 이제 이 모듈을 import한다 — corp_code 캐시를 공유하므로 요청도 절약된다.

키는 다른 수집 소스(FRED·ECOS)와 같이 환경변수 `DART_API_KEY`로 읽는다
(.env 로컬 / Actions Secrets, opendart.fss.or.kr 무료 발급).
"""

import io
import json
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import requests

DART_BASE_URL: str = "https://opendart.fss.or.kr/api"
REQUEST_TIMEOUT_SECONDS: int = 60

# 응답 status 코드 (OpenDART 공통).
STATUS_OK: str = "000"
STATUS_NO_DATA: str = "013"

CORP_CODE_CACHE_PATH: Path = Path("qipinfos/dart_corp_codes.json")


class DartError(RuntimeError):
    """OpenDART에서 필요한 데이터를 받지 못했다."""


def _api_key() -> str:
    key = os.getenv("DART_API_KEY")
    if not key:
        raise DartError(
            "DART_API_KEY 미설정 — .env(로컬) 또는 Actions Secrets에 넣어라"
            " (opendart.fss.or.kr 무료 발급)"
        )
    return key


def get(path: str, **params) -> requests.Response:
    """OpenDART 엔드포인트 호출. HTTP 오류는 예외로 올린다(응답 status는 호출부가 본다)."""
    response = requests.get(
        f"{DART_BASE_URL}/{path}",
        params={"crtfc_key": _api_key(), **params},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response


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


def load_corp_codes() -> dict[str, str]:
    """{종목코드: corp_code} 전체 매핑. 처음 한 번만 받아 `qipinfos/`에 캐시한다."""
    if CORP_CODE_CACHE_PATH.exists():
        return json.loads(CORP_CODE_CACHE_PATH.read_text(encoding="utf-8"))
    archive = zipfile.ZipFile(io.BytesIO(get("corpCode.xml").content))
    mapping = parse_corp_codes(archive.read(archive.namelist()[0]))
    CORP_CODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORP_CODE_CACHE_PATH.write_text(
        json.dumps(mapping, ensure_ascii=False), encoding="utf-8"
    )
    return mapping


def corp_code_for(stock_code: str) -> str:
    """종목코드 → corp_code. 목록에 없으면 `DartError`."""
    mapping = load_corp_codes()
    if stock_code not in mapping:
        raise DartError(f"DART corp_code 목록에 종목코드 {stock_code}가 없다")
    return mapping[stock_code]
