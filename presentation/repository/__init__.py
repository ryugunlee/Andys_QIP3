"""데이터 어댑터 계층: 분석 산출물을 표현용 모델로 읽어온다.

- base.py: StockRepository 프로토콜(계약). 빌더는 이 계약만 의존한다.
- csv_repository.py: 현재 구현체 (qipinfos/ CSV). 저장 방식이 DB로 바뀌면
  같은 계약을 만족하는 구현체를 추가하고 build_site.py에서 교체하면 된다.
- indicators_provider.py / news_provider.py: 아직 수집이 구현되지 않은
  경제지표·뉴스의 연결 지점 (미구현 동안 None 반환).
"""

from presentation.repository.base import StockRepository
from presentation.repository.csv_repository import CsvStockRepository

__all__ = ["StockRepository", "CsvStockRepository"]
