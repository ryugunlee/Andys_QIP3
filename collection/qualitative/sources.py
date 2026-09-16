"""원문 로더 — 로컬 파일을 LLM에 넘길 문서로 만들고, 자동 수집한 원문을 저장한다.

자동 수집은 `dart_source.py`(한국 사업보고서)·`edgar_source.py`(미국 10-K)가 맡고, 받은 텍스트는
`qualitative/sources/`(git 제외)에 저장해 인용 대조와 재실행에 다시 쓴다.

텍스트(txt/md/html)는 본문을 그대로 보관해 **인용 대조**(추출된 quote가 원문에 실제로
있는지)를 할 수 있다. PDF는 API의 document 블록으로 넘기고 페이지 로케이터를 받되,
본문 텍스트가 없어 인용 대조는 하지 못한다(`.claude/PROBLEMS.md` 참고).
"""

import base64
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

TEXT_SUFFIXES: tuple[str, ...] = (".txt", ".md")
HTML_SUFFIXES: tuple[str, ...] = (".html", ".htm")
PDF_SUFFIX: str = ".pdf"

SOURCES_DIR: Path = Path("qualitative/sources")

MEDIA_TYPE_TEXT: str = "text/plain"
MEDIA_TYPE_PDF: str = "application/pdf"


@dataclass(frozen=True)
class SourceDocument:
    title: str
    text: str | None = None
    pdf_base64: str | None = None

    @property
    def can_verify_quotes(self) -> bool:
        return self.text is not None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        return "\n".join(self._chunks)


def html_to_text(markup: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(markup)
    return re.sub(r"\n{3,}", "\n\n", extractor.text())


def load_source(path: Path) -> SourceDocument:
    suffix = path.suffix.lower()
    title = path.stem
    if suffix in TEXT_SUFFIXES:
        return SourceDocument(title=title, text=path.read_text(encoding="utf-8"))
    if suffix in HTML_SUFFIXES:
        return SourceDocument(title=title, text=html_to_text(path.read_text(encoding="utf-8", errors="ignore")))
    if suffix == PDF_SUFFIX:
        encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        return SourceDocument(title=title, pdf_base64=encoded)
    raise ValueError(f"지원하지 않는 원문 형식: {path.suffix} (txt/md/html/pdf만 가능)")


def save_source_text(ticker: str, stamp: str, text: str) -> Path:
    """자동 수집한 원문을 재사용할 수 있게 파일로 남긴다. 다음 실행은 이 경로를 `extract`에 넘기면 된다."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path = SOURCES_DIR / f"{ticker}_{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def save_raw_response(ticker: str, asof: str, payload: dict) -> Path:
    """LLM 원본 응답을 남긴다 — 검증 로직을 고쳐도 재호출 없이 다시 검증할 수 있게."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path = SOURCES_DIR / f"{ticker}_{asof.replace('-', '')}.response.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def document_block(document: SourceDocument) -> dict:
    """API의 document 콘텐츠 블록. 프롬프트 캐시 경계를 여기에 둔다 — 같은 원문에 축별로
    여러 번 질문하므로 원문 토큰은 첫 호출에만 정가로 든다."""
    if document.text is not None:
        source = {"type": "text", "media_type": MEDIA_TYPE_TEXT, "data": document.text}
    else:
        source = {"type": "base64", "media_type": MEDIA_TYPE_PDF, "data": document.pdf_base64}
    return {
        "type": "document",
        "source": source,
        "title": document.title,
        "cache_control": {"type": "ephemeral"},
    }
