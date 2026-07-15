"""데이터 어댑터 계층: 분석 산출물을 표현용 모델로 읽어온다.

- base.py: StockRepository 프로토콜(계약). 빌더는 이 계약만 의존한다.
- db_repository.py: 기본 구현체 (qipinfos/andys_qip.duckdb — 현재 파이프라인 산출물).
- csv_repository.py: 과거 CSV 산출물용 폴백 구현체.
- row_mapping.py: 두 구현체가 공유하는 행→모델 변환.
- indicators_provider.py / news_provider.py: 아직 수집이 구현되지 않은
  경제지표·뉴스의 연결 지점 (미구현 동안 None 반환).
"""

from presentation.repository.base import StockRepository
from presentation.repository.csv_repository import CsvStockRepository
from presentation.repository.db_repository import DuckDbStockRepository

__all__ = ["StockRepository", "CsvStockRepository", "DuckDbStockRepository"]
