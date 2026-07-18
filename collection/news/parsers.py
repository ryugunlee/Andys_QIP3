"""RSS 엔트리 공통 파싱 헬퍼 (Google News/연합뉴스 양쪽에서 재사용)."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")


def published_at_kst(entry: object) -> str | None:
    """entry.published_parsed(UTC struct_time)를 "YYYY-MM-DD HH:MM" 한국시간 문자열로 변환.

    feedparser는 원래 시간대(RFC822 +0900 등)와 무관하게 published_parsed를 UTC로
    정규화해주므로, 두 소스(Google News/연합뉴스) 모두 이 함수 하나로 처리한다.
    """
    parsed = getattr(entry, "published_parsed", None)
    if parsed is None:
        return None
    utc_dt = datetime(*parsed[:6], tzinfo=timezone.utc)
    return utc_dt.astimezone(_KST).strftime("%Y-%m-%d %H:%M")


def strip_source_suffix(title: str, source_name: str | None) -> str:
    """Google News가 제목 끝에 덧붙이는 " - 출처명"을 한 번만 제거한다."""
    if not source_name:
        return title
    suffix = f" - {source_name}"
    if title.endswith(suffix):
        return title[: -len(suffix)]
    return title
