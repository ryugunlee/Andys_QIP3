# 발견된 문제 및 개선 여지

작업 중 발견했지만 이번 작업 범위 밖이라 고치지 않고 기록만 해두는 항목들.

## 1. "Buyback to Income" 팩터가 두 스코어링 함수에서 서로 다른 방향으로 중복 계산됨

`get_detailscore_and_finalrank`(현재 `analysis/detail_score.py`) 안에서 `"Buyback to Income"`이
`DETAIL_SHARE_FACTORS`(direction=LOWER_IS_BETTER_RECIPROCAL, s=1)와
`DETAIL_ORIGINAL_FACTORS`(direction=HIGHER_IS_BETTER, s=0) 양쪽에 모두 들어있다.
percentile 적용이 share → original 순서로 실행되므로, 나중에 실행되는 s=0 계산이
`{column}S` 값을 덮어써서 최종적으로 남는다.

의도한 동작인지 단순 실수인지 불명확하다. 현재 결과값이 이 순서에 의존하고 있어서
이번 리팩토링에서는 임의로 "고치지" 않고 순서를 그대로 보존했다 (`analysis/detail_score.py`의
`_apply_detail_percentiles` 주석 참고). 실제로 어느 방향이 맞는지는 투자 로직 관점에서
사용자가 판단해야 한다.

## 2. "Dividend to Income"이 함수 간에 서로 다른 방향으로 재계산됨

`get_sorting_and_basicscore`에서 `"Dividend to Income"`을 `HIGHER_IS_BETTER`(s=0)로 스코어링하고,
이후 `main()`이 호출하는 `get_detailscore_and_finalrank`에서 같은 컬럼을
`LOWER_IS_BETTER_RECIPROCAL`(s=1)로 다시 스코어링한다. 두 함수가 반드시 이 순서(basic → detail)로
호출되어야 현재와 같은 결과가 나오는 숨은 의존성이다. 함수 호출 순서를 바꾸면 결과가 달라진다.

## 3. `"reliablity"` 컬럼명 오타

`get_detailscore_and_finalrank`가 반환하는 신뢰도 점수 컬럼명이 `"reliability"`가 아니라
`"reliablity"`(오타)로 되어 있다. `main()`이 정확히 이 문자열로 컬럼을 읽고 있어서
지금 고치면 하위 호환이 깨진다. 나중에 전체적으로 컬럼명을 정리할 기회가 있을 때 함께 수정 권장.

## 4. (수정 완료) 프로젝트에 의존성 매니페스트(requirements.txt)가 없음

`Andys_QIP2.py`가 pandas, numpy, yfinance, FinanceDataReader, tqdm, schedule을 쓰는데
이를 명시한 `requirements.txt`/`pyproject.toml`이 저장소에 없었다.
개발 환경 정비 작업에서 `requirements.txt`를 추가해 해결했다. 새 라이브러리를 도입하면
반드시 이 파일에 추가해야 한다 (CLAUDE.md 기술 스택 참고).

## 5. (수정 완료) `get_standard_data`의 "Buyback Yield" 컬럼 중복

과거 `get_standard_data` 함수에서 전체/섹터/국가 3곳 모두 `"Buyback Yield"`가 컬럼 목록에
두 번(Dividend Yield 뒤, Interest Ratio 앞) 들어가 있었다. 두 위치의 값이 항상 동일함을
합성 데이터로 검증했고, 다른 지표가 빠진 것이 아니라 단순 복붙 실수였음을 확인해 두 번째
등장을 제거했다 (`analysis/factors.py`의 `STANDARD_DATA_FACTORS`).

## 6. `main()`의 `.txt` 리포트가 컬럼 수 증가로 매우 커짐

`Stock` 클래스가 raw 데이터(`raw_info__*`, `raw_cashflow__*` 등)까지 표에 담으면서 티커당
컬럼 수가 ~60개에서 ~470개로 늘었다. `main()`은 여전히 `stockdata.to_string()`으로 표 전체를
`.txt` 파일에 그대로 쓰고 있어서, 리포트 파일이 매우 커지고 사람이 읽기 어려워진다.
"일단 모든 데이터를 표에 남긴다"는 이번 작업 목적에 맞게 지금은 손대지 않았지만, `main()`/이메일
리포트가 어떤 컬럼만 보여줄지 고르는 표현 계층 작업이 필요하다 (이번 작업 범위 밖).

## 7. `get_tickers`는 아직 `collection/`으로 옮기지 않음

`Stock` 클래스와 `get_stock_basic_infomation`은 `collection/` 패키지로 옮겼지만, 티커 목록을
가져오는 `get_tickers`는 여전히 `Andys_QIP2.py`에 남아있다. 데이터 수집 계층을 완전히 분리하려면
이것도 옮겨야 하지만, 이번 요청 범위(Stock 클래스 도입)에 포함되지 않아 그대로 두었다.

## 8. yfinance `.info`의 필드 구성은 종목/시장마다 다를 수 있음

`Stock._raw_info_row()`는 `self.info`에 있는 키를 그대로 다 담는데, 시장(NASDAQ vs KRX 등)이나
종목 종류(일반주 vs ETF)에 따라 실제로 제공되는 키 집합이 다르다. 여러 시장을 한 표에 모으면
`raw_info__*` 컬럼 중 상당수가 특정 시장/종목에서만 값이 있고 나머지는 NaN이 되는 구조적 특성이
있다 — 버그는 아니지만, 나중에 한국 주식(네이버 크롤링 등 다른 소스)을 같은 표에 합칠 때
`raw_info__*` 계열 컬럼은 소스별로 필드 이름 자체가 다를 수 있다는 점을 감안해야 한다.
