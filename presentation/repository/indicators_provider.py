"""세계 경제 지표(금값, 유가, 금리, 환율 등) 연결 지점.

아직 수집 영역에 경제 지표 수집이 구현되지 않아 None을 반환한다.
수집이 구현되면 이 함수 본문만 산출물을 읽어 EconomicIndicator 리스트를
반환하도록 교체하면 된다 — 템플릿·빌더·모델은 수정할 필요가 없다.
반환 타입이 계약이다: None = "준비 중" 표시, 리스트 = 지표 카드 렌더링.
"""

from presentation.models import EconomicIndicator


def load_economic_indicators() -> list[EconomicIndicator] | None:
    return None
