프로그램의 함수와 구동 구조가 여기에 작성될 것이다.
제목 형식을 통해서 거대한 함수와 작은 함수를 구분한다.


# 데이터 수집 함수 및 영역
투자에 관한 데이터를 수집하는 함수 및 영역이다.

`collection/` 폴더 안에 있으며, `Andys_QIP2.py`는 이 패키지를 import해서 사용한다.
미국 등 해외 주식은 yfinance, 한국(KRX/KOSPI/KOSDAQ/KONEX) 주식은 네이버증권으로
수집한다 — 두 소스가 curated 팩터 정의와 기술적 지표 계산 로직을 공유하도록
`BaseStock`으로 공통 부분을 분리했다.

## collection/constants.py
- 레이트리밋 대기시간, 이동평균/MACD/RSI 기간, 기간수익률 조회 구간, EPS 0 대체값,
  일봉 조회 기간(`HISTORY_PERIOD_YEARS=5`), 네이버 전용 상수(User-Agent, 재시도 횟수,
  ROE 스케일 환산, 억원→원 환산) 등 수집 로직에 쓰이는 이름 있는 상수 모음.

## collection/technical.py
- `add_moving_averages` / `add_macd` / `add_rsi`: OHLCV DataFrame에 기술적 지표 컬럼을
  추가하는 순수 함수. 원래 `collection/stock.py`에 있던 `_add_*` 함수를 이름의 언더스코어를
  떼고 이 파일로 옮겼다 — 야후/네이버 양쪽에서 재사용하기 위함.
- `lookback_index(history, lookback_days)`: "N 거래일 전" 위치를 반환. history가 5년으로
  늘어난 뒤 "1년 전 종가"처럼 고정 기간 전 값을 가리킬 때 `iloc[0]`(히스토리 시작일) 대신
  이 함수를 쓴다. history가 lookback_days보다 짧으면 0(시작일)으로 대체한다.

## collection/stock_base.py
- `CURATED_COLUMNS`: 표의 컬럼명 ↔ `BaseStock` 속성명 매핑 (원래 `stock.py`에 있던 것을 이동).
- `split_raw_and_curated(row)`: `to_row()` 결과를 `raw_` 접두사 여부로 나누는 함수.
  DuckDB에 저장할 때 curated+점수(넓은 typed 테이블)와 raw 원본(JSON 테이블)을 분리하는
  지점으로 쓰인다 (`Andys_QIP2.py`의 `_persist_ticker_data` 참고).
- `BaseStock`: 데이터 소스와 무관한 curated 팩터 컨테이너 + 공용 계산 로직.
  - `SOURCE_NAME`: 하위 클래스가 재정의하는 클래스 속성 (`"yahoo"`/`"naver"`) — financial_statements/
    raw_latest 테이블의 source 컬럼 값.
  - curated 속성 ~60개 + `history`(OHLCV DataFrame)를 `__init__`에서 초기화.
  - `_compute_technical_factors()`: MA/MACD/RSI/기간수익률/거래대금회전율/변동성 계산
    (원래 `Stock._compute_technical_factors`와 동일한 로직, `lookback_index`로 1년 전 값을 안전하게 참조).
  - `_compute_buyback_to_income()`: `buyback_yield`/`close`/`eps` 중 하나라도 없으면(네이버는
    buyback_yield를 계산하지 않음) 결측으로 남긴다.
  - `_curated_row()` / `_raw_history_row()`: curated dict, history 마지막 행(raw_history__ 접두사) 생성.
  - `_raw_row()` / `to_financial_statement_rows()`: 하위 클래스가 구현해야 하는 계약(`NotImplementedError`).
  - `_with_identity_columns(rows)`: long format 재무제표 DataFrame 앞에 ticker/source 컬럼을 붙이는 헬퍼.
  - `to_row()`: `_raw_row()` + `_curated_row()`를 하나의 dict(표의 한 행)로 병합 (기존 `Stock.to_row()`와 동일한 계약).

## collection/stock.py (야후 경로)
- `YahooStock(BaseStock)`: yfinance 전용 raw 데이터 수집 + 재무 팩터 계산. `Stock`은 이 클래스의
  하위 호환 별칭이다 (`collection/basic_information.py` 등이 `Stock`을 참조).
  - **raw 속성**: `info`, `cashflow`, `financials`, `balance_sheet`, `insider_purchases` — yfinance 원본 그대로.
  - `fetch()`: yfinance에서 raw 데이터를 채움 (필수 데이터 없으면 `is_valid=False`). `history(period="5y")`.
  - `compute_curated_factors()`: `_compute_valuation_factors` → `_compute_technical_factors`(BaseStock) →
    `_compute_cashflow_factors` → `_compute_financials_factors` → `_compute_balance_sheet_factors` →
    `_compute_insider_factors` → `_compute_buyback_to_income`(BaseStock) 순서 (원본 순서/의존관계 유지).
  - `_compute_insider_factors`: `lookback_index`로 "1년 전 종가"를 안전하게 참조하도록 수정 (5년 히스토리
    전환 전에는 `iloc[0]`이 곧 1년 전이었으나, 지금은 그렇지 않다).
  - `_raw_row()`: `raw_info__`/`raw_cashflow__`/`raw_financials__`/`raw_balance_sheet__`/`raw_insider__`/
    `raw_history__` 접두사 dict를 조합. 복잡한 info 필드는 JSON 문자열로 변환.
  - `to_financial_statement_rows()`: cashflow/financials/balance_sheet 전체 회계기간을
    long format(ticker, source, statement_type, period, item, value, is_consensus)으로 변환.

## collection/naver/ (한국 경로)
재무 데이터를 두 소스에서 가져온다: 모바일 API(`finance/annual`, 이미 계산된 비율)와
WiseFn(`navercomp.wisereport.co.kr`, 네이버 coinfo 페이지의 "재무분석" 탭이 iframe으로 불러오는
실제 소스 — 손익계산서/재무상태표/**현금흐름표** 원본 계정 금액). 후자 덕분에 Buyback Yield/
PFCR/Coverage Ratio/NCAV/Current Ratio/ROC/GPTOA/ARP/Interest Ratio/Debt Growth/EV 계열까지
계산할 수 있다. 자세한 배경과 리스크는 `.claude/PROBLEMS.md` #9~#12 참고.

- `endpoints.py`: URL 템플릿. siseJson(일봉), basic/integration/finance-annual(모바일 API),
  `WISE_COMPANY_PAGE_URL_TEMPLATE`(`c1030001.aspx`, encparam 토큰 추출용)와
  `WISE_FINANCIAL_STATEMENT_URL`(`cF3002.aspx`, 실제 재무제표 JSON).
- `client.py`: User-Agent 헤더 + 요청 간 스로틀 + 429 재시도 HTTP 클라이언트. 404/409(잘못된
  티커 코드)는 예외 대신 None을 반환해 `fetch()`가 yfinance와 동일한 패턴으로 처리하게 한다.
  `_get()`는 `extra_headers`를 받을 수 있다 — WiseFn 호출에 `Referer` 헤더가 반드시 필요하기 때문
  (없으면 빈 응답). `fetch_wise_encparam(code)`: `c1030001.aspx` HTML에서 정규식으로 encparam
  토큰을 추출 (종목마다 다름, 삼성전자/SK하이닉스로 교차 검증). `fetch_wise_financial_statement(code,
  encparam, rpt)`: rpt=0(손익계산서)/1(재무상태표)/2(현금흐름표) JSON을 가져온다.
- `parsers.py`: `parse_number`/`parse_won_amount`(한글 숫자 표기 "23.04배"/"1,666조 1,894억" 파싱),
  `parse_price_history`(siseJson 응답 → OHLCV DataFrame), `parse_financial_statements`(finance/annual
  응답 → long format DataFrame), `latest_actual_periods`/`get_statement_value`(컨센서스 제외 최신
  회계기간 조회 헬퍼). `parse_wise_financial_statement(payload, statement_type)`: WiseFn 응답(5개년
  실적 + 1개년 컨센서스 추정치)을 long format으로 변환 — item은 `"ACCODE:계정명"` 형태로 저장한다
  (같은 계정명이 트리의 여러 위치에 나타날 수 있어 ACCODE로 구분해야 함). `get_wise_value`/
  `latest_period_wise_values`: ACCODE 접두사로 값을 찾는 헬퍼, 최신 기간만 raw 보관용으로 추출.
- `naver_stock.py`: `NaverStock(BaseStock)`. `fetch()`가 basic/일봉(5년)/integration/finance-annual/
  WiseFn 손익계산서·재무상태표·현금흐름표를 순서대로 가져온다 (`_fetch_wise_statements` — 실패해도
  종목은 유효하게 남고 관련 팩터만 결측이 됨).
  - `_compute_valuation_factors`: 현재 스냅샷(PER/PBR/EPS/시총/배당수익률).
  - `_compute_financial_statement_factors`: 모바일 API 기반 최신 실적(매출액/순이익/ROE/부채비율/
    EPS성장/매출성장/PSR/PEGR). Asset to Equity/ROA는 여기서 부채비율 근사치로 우선 채워진다.
  - `_compute_wise_factors`: WiseFn 원본 계정 금액(억원)으로 Operating Cashflow/PCR/PFCR/
    Buyback Yield/Depreciation Capex Ratio/Coverage Ratio/NCAV/Current Ratio/ROC/GPTOA/
    Asset Turnover/ARP/Interest Ratio/Debt Growth/EV·EBITDA/EV·Revenue를 계산하고, 가능하면
    Asset to Equity/ROA를 자산총계/자본총계 기반 정확한 값으로 덮어쓴다. 계정과목 코드(ACCODE)는
    `collection/constants.py`의 `NAVER_WISE_ACCODE_*` 상수로 고정.
  - 여전히 없는 것: 내부자거래/기관투자자 비중(Insider Buy Ratio/Institutionpercent/Insiderpercent).
  - 업종(Sector/Industry)은 한글 업종명 API를 찾지 못해 숫자 업종 코드를 임시로 사용한다.
- `basic_information.py`: `get_naver_stock_information(tickers, on_ticker_collected=None)` — 야후 경로와
  동일한 인터페이스(표 반환 + errortickers, `on_ticker_collected` 콜백으로 저장 위임).
- `__init__.py`: `get_naver_stock_information`을 공개 API로 재노출.

## collection/basic_information.py (야후 경로)
- `get_stock_basic_infomation(tickers, on_ticker_collected=None)`: 티커마다 `Stock`을 만들어
  raw+curated 데이터를 모두 담은 표(DataFrame)로 반환. 티커별로 raw 필드 유무가 달라도 pandas가
  합집합 컬럼을 자동 생성. 레이트리밋 재시도(Too Many Requests → 5분 대기) 로직 유지.
  `on_ticker_collected`가 주어지면 팩터 계산 직후 Stock 인스턴스로 호출한다 — 수집 계층이
  저장(storage) 계층을 몰라도 되도록 콜백으로 위임한다.

## collection/tickers.py
- `get_tickers(stockmarket)`: 원래 `Andys_QIP2.py`에 있던 함수를 이동 (`.claude/PROBLEMS.md` #7 해결).
  한국 시장은 네이버가 쓰는 6자리 종목 코드를 접미사 없이 그대로 반환한다 (예전에는 ".KS"를 붙였으나
  이제는 네이버 경로로 수집하므로 불필요).
- `is_korean_market(stockmarket)`: 이 시장을 네이버 경로로 수집해야 하는지 여부 (`stockmarket[0]=="K"`).
  `Andys_QIP2.main()`이 야후/네이버 경로를 분기할 때 재사용한다.

## collection/__init__.py
- `get_stock_basic_infomation`, `get_naver_stock_information`, `get_tickers`, `is_korean_market`,
  `split_raw_and_curated`을 공개 API로 재노출.

## collection/macro/ (경제지표 수집)
진입점은 최상위 `collect_macro.py` (`python collect_macro.py` — 초회 5년 적재와 증분
갱신을 같은 upsert로 처리). 주식 파이프라인과 독립 실행.

- `indicators.py`: 지표 정의 단일 소스. `MacroIndicatorSpec(id, name_ko, unit, source,
  symbol, category, scale)` 23종 — 시장 지수(코스피/코스닥/나스닥/S&P500/VIX), 환율(달러·
  엔100·위안/원, 달러인덱스), 원자재·금(WTI/브렌트/국제 금/KRX 금현물/금 괴리율), 금리·물가
  (미 기준금리/2Y/10Y/30Y/3M/장단기금리차/미 CPI YoY, ECOS 보류 2종). 선언 순서 = 메인 페이지
  카드 순서. `specs_by_source()`/`spec_by_id()` 헬퍼.
- `yahoo_source.py`: `fetch_yahoo_macro(period)` — yfinance 배치 다운로드 → (indicator, date,
  value) long DataFrame. spec.scale 적용(엔/원 100엔 기준 등).
- `fred_source.py`: `fetch_fred_macro()` — fredgraph.csv 키리스 다운로드. CPIAUCSL은 YoY %로
  변환해 us_cpi_yoy로 저장. 시리즈별 실패는 경고 후 계속 (`.claude/PROBLEMS.md` #16).
- `naver_gold_source.py`: `fetch_naver_gold_macro(max_pages)` — KRX 금현물(원/g) 히스토리를
  네이버 marketindex 페이지네이션으로 수집 (`client.fetch_market_index_prices` 사용, #18).
- `derived.py`: `compute_derived_indicators(collected)` — 금 괴리율(gold_gap_pct: KRX 원/g vs
  국제 금 USD/oz÷31.1034768×달러원 환산, %)과 미 10Y−3M 장단기 금리차. 원천 지표가 없으면
  해당 파생만 건너뜀.


# 저장 함수 및 영역
수집·분석 결과를 DuckDB에 저장하고 조회하는 영역이다. CSV/txt 산출물을 대체한다.

`storage/` 폴더 안에 있으며, `Andys_QIP2.py`가 이 패키지를 import해서 사용한다.
DB 파일 경로는 `storage.DEFAULT_DB_PATH`(`./qipinfos/andys_qip.duckdb`) — `qipinfos/`는
git에 커밋하지 않는다.

## storage/database.py
- DB 파일은 용도별 3개로 분리: `KR_STOCK_DB_PATH`(한국 시장 종목), `US_STOCK_DB_PATH`
  (미국 시장 종목 — ADR 포함), `MACRO_DB_PATH`(매크로 지표). 점수 모집단을 통화권 단위로
  내기 위한 분리.
- `stock_db_path_for_market(market)`: 시장명이 K로 시작하면 KR DB, 아니면 US DB.
- `connect(db_path)`: DuckDB 파일에 연결하고 스키마(테이블 없으면 생성)를 반환. 경로는
  명시적으로 받는다(위 상수 중 하나). 세 DB 모두 같은 스키마로 생성.
- 테이블: `price_daily`(일봉, (ticker,date) upsert), `collection_runs`(수집 실행 1회=1행),
  `snapshot_factors`(run별 curated 팩터+점수 — 분석 파이프라인이 만드는 컬럼이 가변적이라
  run_id/ticker만 고정 DDL이고 나머지는 저장 시점에 동적으로 `ALTER TABLE ADD COLUMN`),
  `financial_statements`((ticker,source,statement_type,period,item) upsert — 회계기간 기준이라
  재수집해도 크기가 고정됨), `raw_latest`(종목당 최신 원본 응답만 JSON으로 덮어쓰기),
  `standard_cutlines`(전체/섹터/국가 percentile 커트라인, long format),
  `macro_daily`((indicator,date) upsert), `group_summary`((group_type,group_value,factor)
  upsert — 섹터/산업 자체 평가).

## storage/price_repository.py
- `upsert_price_history(conn, ticker, source, ohlcv)`: OHLCV DataFrame을 (ticker,date) 기준 upsert.
- `get_price_history(conn, ticker)`: 저장된 일봉을 날짜순 DataFrame으로 조회.

## storage/financial_repository.py
- `upsert_financial_statements(conn, statements)`: long format 재무제표 DataFrame을 upsert.
- `get_financial_statements(conn, ticker, source)`: 종목의 저장된 재무제표 조회.

## storage/raw_repository.py
- `upsert_raw_latest(conn, ticker, source, payload)`: 원본 응답 dict를 종목당 최신본으로 덮어쓰기.
- `get_raw_latest(conn, ticker)`: 종목의 최신 raw payload 조회.

## storage/snapshot_repository.py
- `record_collection_run(conn, market, source, ticker_count, error_tickers)`: 수집 실행 1건을 기록하고 run_id 반환.
- `save_snapshot_factors(conn, run_id, stockdata)`: 수집 직후 curated 팩터 표를 run_id 스냅샷으로
  저장. 컬럼이 없으면 동적으로 `ALTER TABLE`, `INSERT ... BY NAME`으로 채움.
- `update_snapshot_scores(conn, scores)`: 점수 파이프라인(analysis.compute_scores) 결과를
  (run_id, ticker) 기준 UPDATE. 점수 모집단이 통화권 전체(여러 run)라 INSERT가 아닌 UPDATE.
  새 점수 컬럼은 `_ensure_snapshot_columns`로 동적 추가.
- `save_standard_cutlines(conn, run_id, standard_data, sector_standard_data, country_standard_data)`:
  `get_standard_data()` 결과(전체/섹터/국가 표)를 long format으로 변환해 저장.

## storage/report_export.py
- `get_run_snapshot` / `get_goodstock` / `get_market_cutlines`: run의 스냅샷, goodstock(원래
  `main()`의 필터: Finalscore 상위 10% & reliablity>80 & Quant score>50 & Fscore>50), 시장
  전체 percentile 커트라인을 DataFrame으로 조회.
- `get_latest_snapshots(conn)`: 이 DB(통화권)의 시장별 최신 run 스냅샷을 통합해 반환
  (점수 산출의 모집단, 중복 티커는 최신 run만 유지).
- `export_run_summary(conn, run_id, output_dir)`: 이메일 첨부용 stockdata/goodstock/standarddata
  CSV를 output_dir에 쓰고 경로 목록을 반환. CSV는 영속 산출물이 아니라 발송 시점의 임시 파일이다.

## storage/group_summary_repository.py
- `upsert_group_summary(conn, group_type, summary)`: 섹터/산업 자체 평가 long DataFrame을
  (group_type, group_value, factor) 기준 upsert (재점수 시 갱신, 크기 고정).
- `get_group_summary(conn, group_type)`: group_type("sector"|"industry")의 요약 전체 조회.

## storage/macro_repository.py
- `upsert_macro_values(conn, values)`: (indicator, date, value) long DataFrame을 upsert
  (NaN 값 행은 저장하지 않음). `get_macro_history(conn, indicator)`: 지표 하나의 시계열.
- `get_latest_macro_pairs(conn)`: 지표별 (최신 날짜, 최신값, 직전값) — 표현 계층의
  전일 대비 계산용.

## storage/__init__.py
- 위 함수들을 공개 API로 재노출.


# Andys_QIP2.py (진입점)
- `_persist_ticker_data(conn, stock, source)`: 수집 콜백. 종목의 일봉/재무제표/원본 데이터를
  DuckDB에 저장한다 (`storage.upsert_price_history`/`upsert_financial_statements`/`upsert_raw_latest`).
- `email_report(title, text, folder_path)`: 환경변수(`GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`)로
  Gmail 발송. folder_path 안의 csv/txt/json을 첨부 (변경 없음).
- `main(stockmarket)`: `is_korean_market()`으로 야후/네이버 경로를 나누고, 시장에 맞는 DB
  (`stock_db_path_for_market`)에 연결한다. 수집 콜백으로 종목별 일봉/재무제표/원본을 즉시 저장하고
  curated 팩터를 `save_snapshot_factors`로 저장한 뒤, **이 통화권 DB의 시장별 최신 run 전체를
  모집단으로 `compute_scores`를 돌려** `update_snapshot_scores`로 점수를 갱신한다(시장 1개가 아닌
  통화권 전체 기준). 이어 커트라인(`save_standard_cutlines`)과 섹터/산업 자체 평가
  (`compute_group_summary`→`upsert_group_summary`)를 저장하고, 이메일은 `export_run_summary`로
  DB에서 뽑은 CSV를 첨부해 발송한다(실패는 경고만).

# compute_scores.py (진입점)
- 수집 없이 점수만 재계산한다(가중치·방식 변경 후 재산출용). `python compute_scores.py [KR|US|ALL]`.
  각 통화권 DB에서 `get_latest_snapshots`→`compute_scores`→`update_snapshot_scores`,
  커트라인·그룹 요약도 함께 갱신.


# 데이터 분석 함수 및 영역
투자에 관해 수집한 데이터를 정량,정성적으로 분석하는 함수 및 영역이다.

`analysis/` 폴더 안에 있으며, `Andys_QIP2.py`는 이 패키지를 import해서 사용한다.

**점수 컬럼 네이밍 규칙** (score_pipeline.py 산출): 모집단 태그 × 계열 태그의 조합.
- 모집단: `""`(통화권 전체) / `Sec`(같은 섹터 내) / `Ind`(같은 산업 내)
- 팩터 점수: `{이름}[Sec|Ind]S`(퍼센타일) / `{이름}[Sec|Ind]SS`(스탠다드), 데이터 유무 `{이름}TF`
- 종합 점수: `{이름}[Sec|Ind]PS`(퍼센타일 계열) / `{이름}[Sec|Ind]SS`(스탠다드 계열) /
  `{이름}[Sec|Ind]`(둘의 평균 = 최종값, 예: `Vscore`는 기존명 그대로 평균으로 재정의).
- 종합 점수 이름: VC1/Vscore/Mscore/Fscore/EQC/Quant score/Finalscore. 리스크/신뢰도
  (`Value risk`/`Growth risk`/`reliablity`)는 계열 무관 단일 컬럼.

## analysis/factors.py
- `Direction` (IntEnum): 방향성(HIGHER_IS_BETTER / LOWER_IS_BETTER_RECIPROCAL / LOWER_IS_BETTER_NEGATED). 원본의 매직넘버 s(1/0/-1)를 이름으로 대체.
- `FactorSpec`: (컬럼명, 방향) 쌍을 담는 값 객체.
- `BASIC_*` / `DETAIL_*` 팩터 목록, `RELIABILITY_TF_COLUMNS`, `STANDARD_DATA_FACTORS`
  (전체 컬럼 목록 단일 소스). (VC1 구성 팩터는 composite_scores.py로 이동)

## analysis/weights.py
- 종합점수 계산에 쓰이는 가중치·분모·임계값을 이름 있는 상수로 정의. 값은 원본과 동일.

## analysis/percentile.py
- `calculating_percentile(df, column, direction, score_column=None)`: 한 컬럼의 percentile 점수
  (`score_column`, 기본 `{column}S`)와 데이터 존재 플래그(`{column}TF`)를 계산하는 핵심 엔진.
  결측 50점. `score_column`으로 섹터/산업 모집단 점수도 같은 엔진으로 낸다.

## analysis/standard_score.py
- `calculating_standard(df, column, direction, score_column=None)`: 스탠다드스코어 엔진.
  상위 1%(`UPPER_CUTLINE_QUANTILE`)·하위 1% 커트라인 사이 선형 위치 ×100, [0,100] 클램프
  (하위1% 이하=0·상위1% 이상=100). 결측·모집단 퇴화=50.
- `numeric_values` / `transform_by_direction`: 문자열 제거·방향 변환 헬퍼 (score_pipeline이 벡터
  연산에서 재사용). `NEUTRAL_SCORE`/`MIN_SCORE`/`MAX_SCORE`/커트라인 분위수 상수.

## analysis/composite_scores.py
- 종합점수 수식의 단일 소스. `compute_vc1/vscore/mscore/fscore/eqc/quant_score(df, suffix)`는
  팩터 접미사(예: "S", "SS", "SecS")만 바꿔 여러 계열에 재사용. `compute_finalscore(vscore, mscore)`
  = 0.63·V + 0.37·M. `VC1_FACTORS`(접미사 없는 이름) 정의.

## analysis/basic_score.py
- `get_sorting_and_basicscore(stockdata)`: 밸류에이션 팩터 percentile + VC1(composite_scores 위임).
  퍼센타일 계열의 1차 단계. compute_scores 내부에서 재사용.

## analysis/detail_score.py
- `get_detailscore_and_finalrank(stockinfo)`: 세부 팩터 percentile 적용 후 종합점수(composite_scores
  위임)·리스크·신뢰도를 붙인다. 퍼센타일 계열의 2차 단계.
  - `_apply_detail_percentiles`: share/original/reverse 순서 (이 순서가 "Buyback to Income" 중복
    스코어링의 최종값을 결정하므로 유지 필수).
  - `compute_value_risk` / `compute_growth_risk` / `compute_reliability`: 계열 무관 단일 지표
    (O/X 플래그, 데이터 신뢰도). 공개 함수로 score_pipeline과 공유.

## analysis/score_pipeline.py
- `compute_scores(stockdata)`: **표준 점수 진입점**. 통화권 전체 모집단 표에 대해 모집단 3종
  (전체/섹터/산업) × 계열 2종(퍼센타일/스탠다드) 점수와 그 평균을 모두 산출.
  섹터/산업은 groupby 벡터 연산(그룹×팩터 엔진 호출 대비 대폭 빠름), 표본 `MIN_GROUP_POPULATION`
  미만·결측 그룹은 중립 50. `GROUP_POPULATIONS`에 (태그, 컬럼) 추가로 새 모집단 확장.
- `score_output_columns(scored, source_columns)`: compute_scores가 새로 만든 점수 컬럼 목록
  (저장 시 UPDATE 대상).

## analysis/group_summary.py
- `compute_group_summary(scored, group_column)`: 섹터/산업 자체 평가. 그룹별 팩터 **중앙값**을
  집계해 "그룹이 행"인 표를 만들고, 그 표를 모집단으로 퍼센타일+스탠다드 점수 적용 → 그룹 간
  상대 우위. long format(group_value, ticker_count, factor, median_value, score_s, score_ss).
  금액 팩터 제외, 표본 `MIN_GROUP_POPULATION` 미만 그룹 제외.

## analysis/standard_data.py
- `_percentile_threshold` / `_build_standard_table` / `get_standard_data(stockdata)`: 전체/섹터/국가
  10~90% 구간 percentile 커트라인 표 생성 (표현·참고용, 점수 산출과는 별개).

## analysis/__init__.py
- `compute_scores`, `score_output_columns`, `compute_group_summary`, `calculating_percentile`,
  `calculating_standard`, `get_sorting_and_basicscore`, `get_detailscore_and_finalrank`,
  `get_standard_data`를 공개 API로 재노출.


# 데이터 표현 함수 및 영역
웹페이지를 통하여 데이터를 보여주는 함수 및 영역이다.

`presentation/` 폴더 안에 있으며, 진입점은 최상위 `build_site.py`다
(`python build_site.py` → `docs/`에 정적 사이트 생성, GitHub Pages는 main/docs 설정).
3층 분리: **repository(어디서 읽나) / models·metrics(무엇을 보여주나) /
builders·templates(어떻게 보여주나)**. JS는 검색용 `search.js` 하나뿐이다.

## build_site.py (진입점)
- `select_repository(db_path, data_dir)`: DuckDB 파일이 있으면 `DuckDbStockRepository`,
  없으면 `CsvStockRepository`(과거 CSV 산출물) 폴백.
- `main()`: `--db-path`/`--data-dir`/`--output` 인자 파싱 후 `build_site()` 실행.

## presentation/config.py
- 시장 목록(`MARKETS`), `REGION_KR`/`REGION_US`, 기본 경로, 사이트 제목/면책 문구,
  노출 종목 개수 상수. `is_korean_market_name(market)`: 시장명이 K로 시작하면 한국
  (collection.tickers.is_korean_market과 같은 규칙 — 계층 분리를 위해 별도 정의).

## presentation/models.py
- 표현용 dataclass: `StockSummary`(카드/표), `StockDetail`(상세 — `values`는 컬럼명→값,
  `qualitative`는 정성 평가로 없으면 미표시), `SearchEntry`, `EconomicIndicator`, `NewsItem`,
  `GroupScore`(섹터/산업 평가 — 상대 점수 + 대표 지표 중앙값).

## presentation/metrics.py
- 지표 메타데이터 단일 소스: `MetricSpec(column, label, format, group)` 63개,
  `MetricFormat`(MONEY/PRICE/MULTIPLE/PERCENT/FRACTION_PERCENT/SCORE/TEXT/NUMBER),
  `MetricGroup`(밸류에이션~종합 점수, 선언 순서=표시 순서), `HEADLINE_SCORE_COLUMNS`,
  `specs_by_group()`. **분석에서 지표가 추가되면 여기 한 줄 추가로 상세 페이지 자동 반영.**

## presentation/formatters.py
- `format_money`(조/억·$T/$B), `format_price`(₩/$), `format_percent`/`format_fraction_percent`,
  `format_multiple`, `format_score`, `format_text`(영문 신호→한국어: Heating→상승 흐름 등),
  `format_metric`(MetricFormat dispatcher), `meter_width`(0~100 클램프), `change_class`(up/down),
  `register_filters(env)`: 위 함수들을 Jinja2 필터로 등록.

## presentation/repository/ (데이터 어댑터)
- `base.py`: `StockRepository` Protocol — `good_stocks(limit)`, `top_by_market_cap(region, limit)`,
  `iter_stock_details()`, `search_entries()`, `market_counts()`, `group_scores(group_type)`,
  `updated_date()`. 빌더는 이 계약만 의존한다. 저장 방식이 바뀌면 구현체를 추가하고 교체.
- `row_mapping.py`: 두 구현체가 공유하는 컬럼명 상수(`COL_*`)와 행→모델 변환
  (`summary_from_row`/`detail_from_row`/`search_entry_from_row`, NaN→None 처리).
- `db_repository.py`: `DuckDbStockRepository` — **기본 구현체**. 주식 DB **2개(KR/US)**를 순회해
  시장별 최신 run의 snapshot_factors를 통합, 추천 종목은 `get_goodstock` 재사용.
  `group_scores`는 각 DB의 group_summary에서 Finalscore 상대 점수(퍼센타일·스탠다드 평균)와
  PER/ROE/3M 중앙값을 뽑는다. DB 없으면 경고 후 건너뜀. read_only 연결.
- `csv_repository.py`: `CsvStockRepository` — 과거 CSV 산출물 폴백. `group_scores`는 빈 목록.
- `indicators_provider.py`: `load_economic_indicators(db_path)` → `list[EconomicIndicator] | None`.
  **구현 완료**: DuckDB macro_daily에서 지표별 최신값+전일 대비를 읽어 indicators.py 선언
  순서대로 카드 생성. %단위 지표(금리·괴리율)의 전일 대비는 %p 차이로 계산 (PROBLEMS #17).
  DB가 없거나 비면 None ("준비 중" 카드).
- `news_provider.py`: `load_news(ticker=None)` → `list[NewsItem] | None`. 뉴스도 동일한 계약.

## presentation/builders/ (페이지 1종 = 파일 1개)
- `environment.py`: `create_environment()` — 공유 Jinja2 환경 (로더+필터+전역값).
- `assets.py`: `copy_static()`(static→docs/static), `write_nojekyll()`.
- `index_page.py`: `build_index_page()` — 메인 (경제지표 placeholder·추천 미리보기·뉴스 placeholder).
- `stocks_page.py`: `build_stocks_page()` — 주식 분석 (추천 카드·KR/US 시총 상위 CSS 탭·뉴스).
- `detail_pages.py`: `build_detail_pages()` — 전 종목 상세. `ticker_filename()` sanitize,
  metrics 스펙 순회로 그룹 표 조립(템플릿은 CSV 컬럼명을 모름), 대표 점수 4종은 상단 타일.
- `sectors_page.py`: `build_sectors_page()` — 섹터·산업 비교. `group_scores`를 표시용 문자열로
  변환(포맷터 선택은 빌더 담당)해 상대 점수 게이지 + 대표 지표 중앙값 표 렌더.
- `search_index.py`: `build_search_index()` — `data/search-index.json` (축약 키 t/n/m/s/f/c).
- `site_builder.py`: `build_site(repository, output_dir)` — 자산→메인→주식→섹터→상세→검색인덱스 순.

## presentation/templates/ · static/
- `base.html`(공통 레이아웃, 컨텍스트: root/active_page/updated_date), `index.html`, `stocks.html`,
  `stock_detail.html`, `sectors.html`, partials(`_header`/`_stock_card`/`_top_cap_table`/`_score_bar`/
  `_metric_table`/`_group_table`/`_indicators_section`/`_news_section`).
- `static/style.css`: 토스풍 라이트 테마, 카드/표/점수미터/CSS 탭, 모바일 720px 브레이크포인트.

# 자동화 (GitHub Actions)
`Andys_QIP2.py`/`collect_macro.py`/`build_site.py`를 GitHub Actions 스케줄로 무인 실행한다.
러너가 실행마다 초기화되므로, git에 커밋하지 않는 `qipinfos/*.duckdb`를 저장소의 draft
릴리스(태그 `data-store`)에 자산으로 올려 실행 간 영속시킨다 (공개 Releases 목록에는 노출 안 됨).
이메일 리포트 기능은 제거했다 — 결과는 사이트(docs/)로 확인하는 것으로 대체.

## .github/scripts/ (워크플로가 공유하는 쉘 스크립트)
- `restore_db.sh [패턴]`: `data-store` 릴리스에서 `qipinfos/`로 DuckDB를 내려받는다. 패턴 인자를
  생략하면 `*.duckdb`(3종 전체), 매크로 워크플로처럼 특정 파일만 필요하면 파일명을 넘긴다.
  릴리스나 해당 자산이 아직 없으면(최초 실행) 에러 없이 넘어간다.
- `save_db.sh [파일 경로...]`: 인자 없으면 kr/us/macro 3종 전체, 있으면 넘겨준 파일만 `data-store`
  릴리스에 업로드(`--clobber`)한다. 릴리스가 없으면 draft로 새로 만든다.
- `build_and_commit_site.sh`: `build_site.py` 실행 후 `docs/`에 변경이 있을 때만
  `github-actions[bot]` 이름으로 커밋·푸시한다 (동시 실행 대비 `git pull --rebase` 포함).

## .github/workflows/ (시장별·매크로 스케줄)
- `collect-kospi.yml`(월 22:00 UTC), `collect-kosdaq.yml`(화 22:00 UTC),
  `collect-nasdaq.yml`(수 23:00 UTC), `collect-nyse.yml`(목 23:00 UTC): 각각
  restore_db → `python Andys_QIP2.py {시장}` → save_db → build_and_commit_site 순.
  `workflow_dispatch`로 수동 실행도 가능. KR 워크플로는 timeout 300분, US(yfinance, 종목 수
  많고 속도 예측 어려움)는 340분으로 6시간 잡 한도 내에 여유를 둠.
- `collect-macro.yml`(매일 23:30 UTC): restore_db/save_db를 매크로 DB 하나로 한정해서만
  호출하고, `collect_macro.py` 실행 후 사이트는 다시 빌드하지 않는다 — `build_site.py`가
  아직 매크로 DB를 읽지 않기 때문(README의 "세계 경제 지표 준비 중" 항목이 구현되면
  이 워크플로에도 build_and_commit_site 단계를 추가해야 한다).
- 모든 워크플로는 `permissions.contents: write`로 `docs/`를 직접 push하고, gh CLI 인증은
  `github.token`(기본 `GITHUB_TOKEN`)만 사용한다 — 추가 Secrets 불필요.

## Andys_QIP2.py 진입점 변경
`if __name__ == "__main__"`에서 `sys.argv`가 있으면(CI) 그 값으로 `main()`을 1회만 실행하고
종료, 없으면(로컬 대화형) 기존과 동일하게 `input()` 프롬프트 + 매일 09:00 스케줄 무한 루프를
그대로 유지한다 — 로컬 사용 방식은 바뀌지 않았다.
- `static/search.js`: 유일한 JS — 첫 입력 시 인덱스 지연 로드, 부분일치 상위 20개 드롭다운.