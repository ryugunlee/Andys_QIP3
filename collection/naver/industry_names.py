"""네이버 업종 코드(숫자) → 한글 업종명 매핑.

종목 API(`integration`)는 업종을 `"278"` 같은 숫자 코드로만 준다. 그 상태로는
섹터/산업 비교 화면이 읽히지 않고(PROBLEMS #20), 업종별 예외 규칙(유틸리티·리츠·
인프라의 상환연수 완화 등)도 이름 없이는 판정할 수 없다.

업종 목록 페이지 1회 요청으로 전체 매핑을 얻어 캐시한다. 수집 실행 내내
수백~수천 종목이 같은 매핑을 쓰므로 `lru_cache`로 요청을 한 번에 묶는다.
페이지 구조가 바뀌거나 네트워크가 막히면 매핑을 비우고 종목 수집은 계속한다
— 그 경우 업종은 종전처럼 숫자 코드로 남는다(기능 저하일 뿐 실패가 아니다).
"""

import re
from functools import lru_cache

from collection.naver import client

# 목록 페이지의 업종 링크: <a href="/sise/sise_group_detail.naver?type=upjong&no=278">반도체와반도체장비</a>
# `&`가 HTML 이스케이프(`&amp;`)된 경우와 아닌 경우가 모두 나타나 양쪽을 함께 받는다.
_INDUSTRY_LINK_PATTERN = re.compile(
    r"sise_group_detail\.naver\?type=upjong(?:&|&amp;)no=(\d+)[^>]*>\s*([^<]+?)\s*<"
)


@lru_cache(maxsize=1)
def industry_names() -> dict[str, str]:
    """{업종코드: 한글 업종명}. 조회 실패 시 빈 dict를 반환한다."""
    html = client.fetch_industry_list()
    if html is None:
        return {}
    return {code: name for code, name in _INDUSTRY_LINK_PATTERN.findall(html)}


def industry_name(code: str | None) -> str | None:
    """업종 코드를 한글 업종명으로 바꾼다. 매핑이 없으면 코드를 그대로 돌려준다.

    이름을 못 찾았다고 업종 자체를 잃으면 섹터/산업 모집단이 통째로 사라지므로,
    실패 시에도 그룹 키로는 쓸 수 있게 원래 코드를 유지한다.
    """
    if not code:
        return None
    return industry_names().get(code, code)
