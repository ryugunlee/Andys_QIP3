"""OpenDART(전자공시) 수집 — 한국 재무제표의 공식 경로.

WiseFn(`navercomp.wisereport.co.kr`) 스크레이핑을 대체하기 위해 만들었다. WiseFn은
FnGuide가 저작권과 무단 데이터베이스 구축 금지를 명시하는 사이트이고, 실제로 2026-09-22
수집에서 연결을 차단해 746종목을 날렸다 (`.claude/PROBLEMS.md` #43, #44).

OpenDART는 금융감독원 공식 무료 API다 — 누구나 키를 발급받을 수 있고 일일 약 20,000 호출을
쓸 수 있다. 재무상태표·손익계산서·포괄손익계산서·현금흐름표·자본변동표를 회사/연도/보고서
단위로 준다.

`client`는 정성 평가(`collection/qualitative/dart_source.py`)와 공유한다 — 같은 키,
같은 corp_code 캐시를 쓴다.
"""

from collection.dart.client import DartError, corp_code_for, load_corp_codes

__all__ = ["DartError", "corp_code_for", "load_corp_codes"]
