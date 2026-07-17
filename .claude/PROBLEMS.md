# 발견된 문제 및 개선 여지

작업 중 발견했지만 이번 작업 범위 밖이라 고치지 않고 기록만 해두는 항목들.

## 1. (해결 완료) "Buyback to Income" 팩터가 두 스코어링 함수에서 서로 다른 방향으로 중복 계산됨

`get_detailscore_and_finalrank`(현재 `analysis/detail_score.py`) 안에서 `"Buyback to Income"`이
`DETAIL_SHARE_FACTORS`(direction=LOWER_IS_BETTER_RECIPROCAL)와 `DETAIL_ORIGINAL_FACTORS`
(direction=HIGHER_IS_BETTER) 양쪽에 모두 들어있어 순서에 따라 결과가 결정되던 문제였다.

확인 결과 이 팩터의 점수(`{column}S`/`SS` 등)는 Vscore/Mscore/Fscore/EQC/Quant score 등
어떤 종합점수의 입력으로도 쓰이지 않았다 — 화면에는 항상 원문 값만 표시됐다
(`presentation/metrics.py`). 데이터 신뢰도(`reliability`) 계산에는 값의 존재 여부(TF)만
필요했다. 그래서 두 리스트에서 모두 제거하고, 방향성 점수 없이 TF만 계산하는
`attach_presence_flag`(`analysis/percentile.py`)로 대체했다(`analysis/factors.py`의
`PRESENCE_ONLY_FACTORS`) — 이제 점수는 산출하지 않고 원문 값만 계속 표시된다. score_pipeline의
스탠다드/섹터/산업 계열에도 같은 목록이 흘러가므로 이 팩터의 점수는 어디서도 계산되지 않는다
(이 변경으로 #19의 문제도 함께 해소됐다).

## 2. (해결 완료) "Dividend to Income"이 함수 간에 서로 다른 방향으로 재계산됨

`get_sorting_and_basicscore`(BASIC_ORIGINAL_FACTORS)가 `HIGHER_IS_BETTER`로, 이후
`get_detailscore_and_finalrank`(DETAIL_SHARE_FACTORS)가 `LOWER_IS_BETTER_RECIPROCAL`로 같은
컬럼을 이중 스코어링해 함수 호출 순서에 결과가 좌우되던 문제였다. "배당성향(배당/이익)은
낮을수록 좋은 점수를 줘야 한다"는 판단에 따라 BASIC_ORIGINAL_FACTORS에서 제거하고
DETAIL_SHARE_FACTORS의 `LOWER_IS_BETTER_RECIPROCAL` 방향만 남겼다(`analysis/factors.py`).
`get_standard_data`가 쓰는 STANDARD_DATA_FACTORS는 원래부터 이 방향으로 단일하게 정의돼
있었으므로, 이제 모든 경로가 같은 방향으로 일치한다.

## 3. (해결 완료) `"reliablity"` 컬럼명 오타

신뢰도 점수 컬럼명을 `"reliability"`로 전체 수정했다(analysis/factors.py, analysis/detail_score.py,
analysis/score_pipeline.py, Andys_QIP2.py, storage/report_export.py, presentation/metrics.py,
presentation/repository/row_mapping.py). DB 컬럼은 저장 시점에 동적으로 `ALTER TABLE ADD
COLUMN`되는 방식이라(고정 DDL 아님) 하위 호환 걱정 없이 다음 수집부터 새 컬럼명으로 채워진다.
기존에 쌓인 로컬/원격 DuckDB에 이미 `reliablity`(구) 컬럼이 있다면 재수집 시 `reliability`(신)
컬럼이 나란히 생기니, 필요하면 재수집 또는 수동으로 컬럼명을 정리한다.

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

## 6. (해결 완료) `main()`의 `.txt` 리포트가 컬럼 수 증가로 매우 커짐

DuckDB 저장소로 전환하면서 `main()`은 더 이상 `.txt`/`.csv` 파일을 만들지 않는다 — 확인 결과
`email_report`/`export_run_summary` 같은 파일 출력 함수 자체가 코드베이스에 남아있지 않았다
(`Andys_QIP2.py`, `storage/report_export.py` 확인, 저장소 전체에 `.to_csv`/`.to_string(...)`
파일 쓰기 없음). 결과는 DuckDB에만 저장되고 웹페이지(`build_site.py`) 표현에만 집중하는
지금 구조가 이 문제를 이미 해소한 상태였다.

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

## 9. (대부분 해결) 네이버 경로는 야후 대비 결측 컬럼이 많아 `reliability`/percentile 점수를 시장 간에 직접 비교하면 안 됨

처음에는 한국 주식(네이버)에 현금흐름표 데이터가 없어 PCR/PFCR/Coverage Ratio/ARP/
Depreciation Capex Ratio/NCAV/Current Ratio/ROC/GPTOA/Asset Turnover/Interest Ratio/
Debt Growth/EV 계열/Buyback 계열이 전부 결측이었으나, WiseFn(`navercomp.wisereport.co.kr`)
연동 이후 이 팩터들은 모두 실제 값으로 채워진다 (아래 #12 참고). 여전히 결측인 것은
Insider Buy Ratio/Institutionpercent/Insiderpercent(내부자거래·기관투자자 비중) 뿐이다.
이 셋 때문에 네이버 종목의 `reliability`는 야후 종목보다 구조적으로 조금 낮게 나올 수 있으므로,
같은 시장 내 상대 비교에는 문제가 없지만 한국·미국 주식을 하나의 표로 합쳐 percentile을
계산할 때는 이 차이를 감안해야 한다.

## 10. (해결 완료) 네이버 재무제표는 연간(annual) 실적만 수집하고 분기(quarter)는 수집하지 않음

WiseFn `cF3002.aspx`에 `frq`/`frqTyp=1`(분기)을 넣어도 응답 형태(YYMM 6개 = 실적 5개 기간 +
컨센서스 1개 기간)가 연간과 동일함을 실제 호출로 확인했다(2026-07-17, 005930으로 검증 —
손익계산서/재무상태표/현금흐름표 모두 동일 구조). 이에 따라
`NaverStock._fetch_wise_quarterly_statements`(`collection/naver/naver_stock.py`)가 세 재무제표를
분기로도 조회해 `financial_statements`에 `wise_income_statement_q`/`wise_balance_sheet_q`/
`wise_cash_flow_q`로 저장한다 — 재무 팩터(curated factors) 계산은 여전히 연간 데이터만
사용하므로 기존 점수에는 영향 없다.

표현 계층(`presentation/repository/financial_series.py`의 `quarterly_financials_from_df`,
`presentation/models.py`의 `StockCharts.quarterly`)과 상세 페이지 실적 막대그래프에 "연간/분기"
토글을 추가해(`presentation/static/charts.js`, `presentation/templates/stock_detail.html`)
분기 데이터가 화면에도 반영된다.

미국(yfinance) 경로는 이번 범위에 포함하지 않았다 — `quarterly_financials` 등은 여전히
미사용이다. 자세한 내용과 남은 범위는 #23 참고.

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

## 16. (해결 완료) FRED(fredgraph.csv)가 일부 네트워크에서 차단됨

미 기준금리(DFF)/미 2년물(DGS2)/미 CPI(CPIAUCSL)를 키 없는 fredgraph.csv 방식으로
구현했으나 GitHub Codespaces에서는 fred.stlouisfed.org가 타임아웃됐다(2026-07-16 확인).
FRED_API_KEY 발급 후 `fred_source.py`를 공식 API(api.stlouisfed.org)로 전환해
해결(2026-07-16). 키 미설정 시에는 여전히 경고 후 해당 소스 전체를 건너뛴다.

## 17. 경제지표 카드의 전일 대비 표시가 %와 %p를 구분하지 않음

indicators_provider는 금리·괴리율 같은 %단위 지표의 전일 대비를 %p 차이로 계산하지만,
카드 템플릿(signed_percent 필터)은 모두 "%" 기호로 표시한다. 값은 올바르나 단위 표기가
부정확하다 (예: 금리 +0.10%p가 "+0.1%"로 보임). 템플릿에 %p 구분 표시를 추가하는
소규모 개선 여지가 있다.

## 18. 네이버 marketindex(금현물) API의 pageSize 상한은 60

100을 요청하면 400 응답. collection/constants.py의 NAVER_GOLD_PAGE_SIZE=60,
MAX_PAGES=21로 5년을 커버한다. 이 역시 문서화되지 않은 내부 API라 구조 변경 시
깨질 수 있다 (#12와 같은 성격).

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

## 23. (부분 해결) 재무 실적 시계열은 연간만 존재, 분기 데이터는 수집·저장 어디에도 없음

한국(네이버 WiseFn)은 #10에서 분기(frq=1) 수집을 추가해 해결했다 —
`financial_statements`에 `wise_income_statement_q` 등으로 저장되고, 상세 페이지 실적
막대그래프의 "연간/분기" 토글로 확인할 수 있다.

미국(yfinance)은 여전히 연간 `financials`/`cashflow`/`balance_sheet`만 사용한다
(`quarterly_financials` 등 분기 속성 미사용) — 필요해지면 yfinance 쪽에서
`quarterly_financials` 등을 추가로 수집해 `financial_statements`에 statement_type을
구분해(예: `financials_q`) 저장하면 된다. 표현 계층(`quarterly_financials_from_df`,
`renderBars`)은 소스가 분기를 제공하지 않으면 빈 리스트를 반환하도록 설계해서, 지금은
토글이 자동으로 숨겨지고(빈 리스트) 미국 쪽을 나중에 추가해도 UI 변경 없이 그대로 연결된다.

## 24. 로컬/커밋된 DB 샘플이 실제로는 yfinance 경로로 수집된 한국 종목을 담고 있음

`qipinfos/andys_qip_kr.duckdb`에 있는 한국 종목(005930.KS 등)이 티커에 `.KS` 접미사가
붙고 `Company Name`이 영문("SamsungElec")이며 Sector/Industry도 영문("Technology")이다.
이는 `Andys_QIP2.py`의 정상 경로(한국 시장은 네이버, `is_korean_market()`으로 분기)라면
나올 수 없는 형태다 — 네이버 경로는 6자리 코드·한글 `stockName`을 저장한다. 즉 현재
커밋된 샘플 DB는 정식 파이프라인이 아니라 별도 경로(테스트용 yfinance 수집 등)로 만들어진
것으로 보인다.

당장은 `presentation/korean_names.py`의 보정맵으로 한글 표시를 안전망 처리했지만,
근본 해결은 한국 시장을 네이버 경로로 재수집하는 것이다(그래야 `price_daily`·
`financial_statements`도 함께 채워져 이번에 추가한 차트가 실제로 표시된다 — 현재
로컬 DB는 두 테이블 모두 0행이다). 언제·어떻게 이 샘플이 만들어졌는지는 git 이력에서
확인되지 않아 원인은 불명확하다.
