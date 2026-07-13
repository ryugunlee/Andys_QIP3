"""표현 계층이 의존하는 데이터 저장소 계약(StockRepository).

빌더/템플릿은 이 프로토콜과 models.py의 모델만 알고, 데이터가 CSV에서 오는지
DB에서 오는지 모른다. 저장 방식이 바뀌면 이 계약을 만족하는 구현체를
추가하고 build_site.py에서 교체하는 것으로 끝난다.
"""

from typing import Iterator, Protocol

from presentation.models import SearchEntry, StockDetail, StockSummary


class StockRepository(Protocol):
    def good_stocks(self, limit: int | None = None) -> list[StockSummary]:
        """추천 종목(분석 영역이 선별한 goodstock)을 Finalscore 내림차순으로 반환."""
        ...

    def top_by_market_cap(self, region: str, limit: int) -> list[StockSummary]:
        """시가총액 상위 종목. region은 config.REGION_KR 또는 config.REGION_US."""
        ...

    def iter_stock_details(self) -> Iterator[StockDetail]:
        """전 종목의 상세 정보를 순회한다 (상세 페이지 생성용)."""
        ...

    def search_entries(self) -> list[SearchEntry]:
        """검색 인덱스(JSON)에 넣을 전 종목 경량 목록."""
        ...

    def market_counts(self) -> dict[str, int]:
        """시장명 -> 분석된 종목 수. 데이터가 없는 시장은 포함하지 않는다."""
        ...

    def updated_date(self) -> str | None:
        """데이터 기준일("YYYY-MM-DD"). 데이터가 전혀 없으면 None."""
        ...
