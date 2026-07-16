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

## 7. (수정 완료) `get_tickers`는 아직 `collection/`으로 옮기지 않음

`get_tickers`를 `collection/tickers.py`로 옮기고, 한국 시장은 네이버가 쓰는 6자리 코드를
접미사 없이 반환하도록 함께 수정했다 (`is_korean_market`도 같은 파일에 추가).

## 8. yfinance `.info`의 필드 구성은 종목/시장마다 다를 수 있음

`YahooStock._raw_info_row()`는 `self.info`에 있는 키를 그대로 다 담는데, 시장(NASDAQ vs KRX 등)이나
종목 종류(일반주 vs ETF)에 따라 실제로 제공되는 키 집합이 다르다. 여러 시장을 한 표에 모으면
`raw_info__*` 컬럼 중 상당수가 특정 시장/종목에서만 값이 있고 나머지는 NaN이 되는 구조적 특성이
있다 — 버그는 아니다. 네이버 경로는 아예 다른 접두사(`raw_naver_basic__`, `raw_naver_integration_total__`)를
쓰므로 이 문제가 그대로 이어지지는 않지만, DuckDB의 `raw_latest` 테이블은 payload를 JSON 하나로
저장해 소스별 필드 이름 차이를 흡수하도록 설계했다 (자세한 내용은 `.claude/STRUCTURE.md`의
storage 섹션 참고).

## 9. (대부분 해결) 네이버 경로는 야후 대비 결측 컬럼이 많아 `reliablity`/percentile 점수를 시장 간에 직접 비교하면 안 됨

처음에는 한국 주식(네이버)에 현금흐름표 데이터가 없어 PCR/PFCR/Coverage Ratio/ARP/
Depreciation Capex Ratio/NCAV/Current Ratio/ROC/GPTOA/Asset Turnover/Interest Ratio/
Debt Growth/EV 계열/Buyback 계열이 전부 결측이었으나, WiseFn(`navercomp.wisereport.co.kr`)
연동 이후 이 팩터들은 모두 실제 값으로 채워진다 (아래 #12 참고). 여전히 결측인 것은
Insider Buy Ratio/Institutionpercent/Insiderpercent(내부자거래·기관투자자 비중) 뿐이다.
이 셋 때문에 네이버 종목의 `reliablity`는 야후 종목보다 구조적으로 조금 낮게 나올 수 있으므로,
같은 시장 내 상대 비교에는 문제가 없지만 한국·미국 주식을 하나의 표로 합쳐 percentile을
계산할 때는 이 차이를 감안해야 한다.

## 10. 네이버 재무제표는 연간(annual) 실적만 수집하고 분기(quarter)는 수집하지 않음

`collection/naver`는 모바일 API의 `finance/annual`과 WiseFn의 `cF3002.aspx`(frq=0, 연간) 둘 다
연간 데이터만 쓴다. 두 소스 모두 분기(quarter) 파라미터가 존재하는 것을 확인했지만
(`.claude/STRUCTURE.md` 참고) 이번 작업 범위에서는 쓰지 않았다. 최신 분기 실적 기반으로 팩터를
더 자주 갱신하고 싶다면 이 파라미터를 추가로 연동하는 작업이 필요하다.

## 11. `NaverStock`의 PSR/PEGR은 여전히 근사치로 계산되고, Asset to Equity/ROA는 WiseFn 성공 시에만 정확한 값을 씀

`PSR = 시가총액 / 매출액`, `PEGR = PER / EPS성장률`은 야후처럼 직접 제공되는 값이 없어 계속
간접 계산한다. `Asset to Equity`/`ROA`는 원래 `부채비율`로부터 근사(`1 + 부채비율/100`)했으나,
WiseFn 재무상태표에서 자산총계/자본총계를 직접 얻을 수 있어 이제 그 값으로 덮어쓴다
(`NaverStock._compute_wise_factors`). WiseFn 조회가 실패하면(아래 #12) 근사치로 남는다 —
같은 컬럼이라도 종목마다 계산 방법이 다를 수 있다는 점을 투자 판단 시 감안해야 한다.

## 12. WiseFn 재무제표 연동은 문서화되지 않은 내부 API에 의존함 (encparam + Referer)

`collection/naver`가 현금흐름표 등을 가져오는 `navercomp.wisereport.co.kr/company/cF3002.aspx`는
네이버 공식 문서가 없는 내부 API다. `c1030001.aspx` 페이지의 HTML에서 정규식으로 `encparam`
토큰을 추출한 뒤(`client.fetch_wise_encparam`), 그 값과 `Referer` 헤더를 함께 보내야 응답이
온다 (Referer 없이는 빈 응답). `encparam`은 종목마다 다르며(삼성전자/SK하이닉스로 교차 검증),
계정과목 코드(ACCODE, `collection/constants.py`의 `NAVER_WISE_ACCODE_*`)는 두 종목에서 동일함을
확인해 고정 상수로 삼았다. 다만 이 모든 것은 WiseFn이 페이지 구조를 바꾸면 (정규식이 encparam을
못 찾거나, ACCODE 체계가 바뀌면) 예고 없이 깨질 수 있는 리버스 엔지니어링 기반 연동이다.
`_fetch_wise_statements`는 실패해도 종목 자체를 무효화하지 않고 관련 팩터만 결측으로 남기도록
방어적으로 설계했지만, 이 엔드포인트가 막히면 #9에서 해결했다고 적은 팩터들이 다시 결측으로
돌아간다는 점을 유지보수 시 알고 있어야 한다.

## 13. 상세 페이지의 링크 규칙과 파일명 규칙이 별도로 존재함

카드/검색(JS)의 링크는 `urlencode(티커)`, 파일명은 `[^A-Za-z0-9._-]`→`_` 치환
(`presentation/builders/detail_pages.py:ticker_filename`). 현재 티커 문자 집합
(영숫자/점/하이픈)에서는 두 규칙이 동일한 결과를 내지만, 특수문자가 포함된 티커가
생기면 링크가 깨진다. 그 경우 두 규칙을 한 함수로 통일해야 한다.

## 14. CSV 폴백 레포지토리는 4개 시장 폴더명에 고정되어 있음

`CsvStockRepository`는 `config.MARKETS`(KOSPI/KOSDAQ/NASDAQ/NYSE) 폴더명 규칙의
과거 CSV만 읽는다. KRX·AMERICAN 등 다른 시장명으로 실행한 산출물은 CSV 폴백에서
보이지 않는다. 반면 기본 경로인 `DuckDbStockRepository`는 collection_runs에 기록된
시장명을 그대로 쓰므로 어떤 시장이든 처리한다. CSV 폴백은 과도기용이므로
확장하지 않고, DuckDB 정착 후 제거를 검토한다.

## 15. yfinance `dividendYield`의 단위가 버전에 따라 달랐던 이력

yfinance는 버전에 따라 배당수익률을 소수(0.0055) 또는 %(0.55)로 반환한 이력이 있다.
표현 계층은 %로 간주해 그대로 표시한다(`presentation/metrics.py`의 Dividend Yield =
PERCENT). 사이트에서 배당수익률이 100배 이상하게 보이면 이 포맷 지정을 조정할 것.
네이버 경로는 `parse_number`로 %값을 그대로 파싱하므로 영향 없다.

## 16. FRED(fredgraph.csv)가 일부 네트워크에서 차단됨

미 기준금리(DFF)/미 2년물(DGS2)/미 CPI(CPIAUCSL)는 키 없는 fredgraph.csv 방식으로
구현했지만, GitHub Codespaces에서는 fred.stlouisfed.org가 타임아웃된다(2026-07-16 확인).
수집기는 시리즈별로 경고만 내고 계속 진행하므로 해당 지표만 결측이 된다.
해결책은 FRED API 키 발급 후 공식 API 전환 — API_REQUESTS.txt에 기록되어 있다.

## 17. 경제지표 카드의 전일 대비 표시가 %와 %p를 구분하지 않음

indicators_provider는 금리·괴리율 같은 %단위 지표의 전일 대비를 %p 차이로 계산하지만,
카드 템플릿(signed_percent 필터)은 모두 "%" 기호로 표시한다. 값은 올바르나 단위 표기가
부정확하다 (예: 금리 +0.10%p가 "+0.1%"로 보임). 템플릿에 %p 구분 표시를 추가하는
소규모 개선 여지가 있다.

## 18. 네이버 marketindex(금현물) API의 pageSize 상한은 60

100을 요청하면 400 응답. collection/constants.py의 NAVER_GOLD_PAGE_SIZE=60,
MAX_PAGES=21로 5년을 커버한다. 이 역시 문서화되지 않은 내부 API라 구조 변경 시
깨질 수 있다 (#12와 같은 성격).

## 19. 스탠다드스코어와 퍼센타일스코어의 "Buyback to Income" 중복 순서 의존

#1의 중복 스코어링(share/original 두 리스트에 모두 등장, 뒤 계산이 덮어씀)은
퍼센타일 계열뿐 아니라 새 스탠다드 계열·섹터/산업 모집단에도 그대로 적용된다.
score_pipeline은 factors.py의 팩터 목록 순서를 두 엔진 모두에 동일하게 흘려보내
"기존 동작 보존"을 계열 전반으로 일관되게 유지한다. 근본 수정(중복 제거)은
투자 로직 판단이 필요하므로 #1과 함께 보류.

## 20. 섹터/산업 자체 평가 시 한국 종목의 업종이 숫자 코드

group_summary는 Sector/Industry 컬럼 값으로 그룹을 묶는데, 네이버 경로의 한국
종목은 아직 한글 업종명이 아니라 숫자 업종 코드다(#: collection 후속 과제).
그룹핑·점수 계산 자체는 코드로도 정상 동작하지만, 섹터 페이지의 그룹 이름이
숫자로 보인다. 한글 업종명 수집이 붙으면 표현은 자동으로 개선된다.

## 21. 통화권 점수 모집단이 "DB의 시장별 최신 run"이라 시장 갱신 시점이 섞일 수 있음

compute_scores의 모집단은 get_latest_snapshots(시장별 최신 run 통합)다.
예를 들어 KOSPI를 오늘, KOSDAQ를 사흘 전 수집했다면 한국 모집단은 두 시점이
섞인다. 같은 통화권을 하루에 모두 갱신하면 문제없지만, 부분 갱신 시 커트라인이
약간 어긋날 수 있다. 정확성이 필요하면 통화권 단위로 같은 날 일괄 수집하거나,
compute_scores.py로 전체 재점수를 돌리면 된다.

## 22. 섹터/산업 모집단 점수의 소규모 그룹 처리

score_pipeline.MIN_GROUP_POPULATION(=5) 미만 그룹은 팩터 점수·종합점수(Sec/Ind
계열)를 중립 50으로 채운다. 표본이 적어 커트라인이 무의미하기 때문. 결과적으로
소형 섹터 종목의 `VscoreSec` 등은 50 부근에 몰릴 수 있는데, 이는 "평가 불가"의
의미이지 "평균 수준"이 아니라는 점을 표현 계층에서 언젠가 구분해주면 좋다
(현재는 값만 저장, UI 구분 없음).
