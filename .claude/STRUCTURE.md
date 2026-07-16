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
- `connect(db_path=DEFAULT_DB_PATH)`: DuckDB 파일에 연결하고 스키마(테이블 없으면 생성)를 반환.
- 테이블: `price_daily`(일봉, (ticker,date) upsert), `collection_runs`(수집 실행 1회=1행),
  `snapshot_factors`(run별 curated 팩터+점수 — 분석 파이프라인이 만드는 컬럼이 가변적이라
  run_id/ticker만 고정 DDL이고 나머지는 저장 시점에 동적으로 `ALTER TABLE ADD COLUMN`),
  `financial_statements`((ticker,source,statement_type,period,item) upsert — 회계기간 기준이라
  재수집해도 크기가 고정됨), `raw_latest`(종목당 최신 원본 응답만 JSON으로 덮어쓰기),
  `standard_cutlines`(전체/섹터/국가 percentile 커트라인, long format).

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
- `save_snapshot_factors(conn, run_id, stockdata)`: analysis 파이프라인을 거친 curated+점수 표를
  run_id 스냅샷으로 저장. 컬럼이 없으면 동적으로 `ALTER TABLE`, `INSERT ... BY NAME`으로 채움.
- `save_standard_cutlines(conn, run_id, standard_data, sector_standard_data, country_standard_data)`:
  `get_standard_data()` 결과(전체/섹터/국가 표)를 long format으로 변환해 저장.

## storage/report_export.py
- `get_run_snapshot` / `get_goodstock` / `get_market_cutlines`: run의 스냅샷, goodstock(원래
  `main()`의 필터: Finalscore 상위 10% & reliablity>80 & Quant score>50 & Fscore>50), 시장
  전체 percentile 커트라인을 DataFrame으로 조회.
- `export_run_summary(conn, run_id, output_dir)`: 이메일 첨부용 stockdata/goodstock/standarddata
  CSV를 output_dir에 쓰고 경로 목록을 반환. CSV는 영속 산출물이 아니라 발송 시점의 임시 파일이다.

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
- `main(stockmarket)`: `is_korean_market()`으로 야후/네이버 경로를 나누고, 수집 콜백으로
  `_persist_ticker_data`를 전달해 종목별 일봉/재무제표/원본을 즉시 저장한다. 기존과 동일하게
  `analysis` 파이프라인(basicscore → detailscore → standard_data)을 거친 뒤,
  `storage.record_collection_run`으로 run을 기록하고 `save_snapshot_factors`/`save_standard_cutlines`로
  스냅샷을 저장한다. 이메일은 `storage.export_run_summary`로 DB에서 뽑은 CSV를 첨부해 발송하며,
  발송 실패는 예외로 잡아 경고만 출력한다 (데이터는 이미 DB에 저장된 뒤이므로).


# 데이터 분석 함수 및 영역
투자에 관해 수집한 데이터를 정량,정성적으로 분석하는 함수 및 영역이다.

`analysis/` 폴더 안에 있으며, `Andys_QIP2.py`는 이 패키지를 import해서 사용한다.

## analysis/factors.py
- `Direction` (IntEnum): percentile 방향성(HIGHER_IS_BETTER / LOWER_IS_BETTER_RECIPROCAL / LOWER_IS_BETTER_NEGATED). 원본의 매직넘버 s(1/0/-1)를 이름으로 대체.
- `FactorSpec`: (컬럼명, 방향) 쌍을 담는 값 객체.
- `BASIC_SHARE_FACTORS` / `BASIC_ORIGINAL_FACTORS` / `BASIC_REVERSE_FACTORS` / `VC1_FACTOR_COLUMNS`: `get_sorting_and_basicscore`가 쓰는 팩터 목록.
- `DETAIL_SHARE_FACTORS` / `DETAIL_ORIGINAL_FACTORS` / `DETAIL_REVERSE_FACTORS` / `RELIABILITY_TF_COLUMNS`: `get_detailscore_and_finalrank`가 쓰는 팩터 목록.
- `STANDARD_DATA_FACTORS`: `get_standard_data`가 쓰는 전체 컬럼 목록의 단일 소스 (기존 3중 중복 제거).

## analysis/weights.py
- Vscore/Mscore/Fscore/Finalscore/EQC/Value risk/Growth risk/Quant score/reliablity 계산에 쓰이는 가중치·분모·임계값을 이름 있는 상수로 정의. 값은 원본과 동일.

## analysis/percentile.py
- `calculating_percentile(df, column, direction)`: 하나의 컬럼에 대해 percentile 점수(`{column}S`)와 데이터 존재 플래그(`{column}TF`)를 계산하는 핵심 엔진.

## analysis/basic_score.py
- `get_sorting_and_basicscore(stockdata)`: 밸류에이션 팩터 percentile 계산 + VC1 산출. (1차 스코어링)

## analysis/detail_score.py
- `get_detailscore_and_finalrank(stockinfo)`: 세부 팩터 percentile 적용 후 아래 파생 스코어를 모두 붙이는 오케스트레이터. (2차 스코어링, 최종 랭크)
  - `_apply_detail_percentiles`: share/original/reverse 팩터 순서대로 percentile 적용 (이 순서가 "Buyback to Income" 중복 스코어링의 최종값을 결정하므로 순서 유지 필수).
  - `_compute_vscore` / `_compute_mscore` / `_compute_fscore` / `_compute_finalscore`: 밸류/모멘텀/펀더멘털/최종 스코어.
  - `_compute_eqc`: 이익의 질(Earnings Quality) 점수.
  - `_compute_value_risk` / `_compute_growth_risk`: 가치·성장 리스크 O/X 플래그.
  - `_compute_quant_score`: 퀀트 지표 종합 점수.
  - `_compute_reliability`: 데이터 신뢰도(`reliablity`) 점수 — 18개 팩터의 TF 플래그 합.

## analysis/standard_data.py
- `_percentile_threshold(df, column, percentile, direction)`: 특정 percentile 커트라인 값을 계산하는 헬퍼 (원본 nested `get_data` 승격).
- `_build_standard_table(df)`: 데이터프레임 부분집합 하나(전체/섹터/국가)에 대해 10~90% 구간 커트라인 표를 생성 — market/sector/country 3곳에서 공통 재사용.
- `get_standard_data(stockdata)`: 전체 시장 표(+"Top" 라벨) / 섹터별 표 dict / 국가별 표 dict 반환.

## analysis/__init__.py
- 위 함수들 중 `calculating_percentile`, `get_sorting_and_basicscore`, `get_detailscore_and_finalrank`, `get_standard_data`를 공개 API로 재노출.


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
  `qualitative`는 정성 평가로 없으면 미표시), `SearchEntry`, `EconomicIndicator`, `NewsItem`.

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
  `iter_stock_details()`, `search_entries()`, `market_counts()`, `updated_date()`.
  빌더는 이 계약만 의존한다. 저장 방식이 바뀌면 구현체를 추가하고 build_site.py에서 교체.
- `row_mapping.py`: 두 구현체가 공유하는 컬럼명 상수(`COL_*`)와 행→모델 변환
  (`summary_from_row`/`detail_from_row`/`search_entry_from_row`, NaN→None 처리).
- `db_repository.py`: `DuckDbStockRepository` — **기본 구현체**. collection_runs에서 시장별
  최신 run을 찾아 snapshot_factors를 통합, 추천 종목은 `storage.report_export.get_goodstock`
  재사용(파이프라인과 동일 기준). DB 없으면 경고 후 빈 데이터. read_only 연결.
- `csv_repository.py`: `CsvStockRepository` — 과거 CSV 산출물(qipinfos/{시장}stockdata2/) 폴백.
  없는 시장은 경고 후 스킵.
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
- `search_index.py`: `build_search_index()` — `data/search-index.json` (축약 키 t/n/m/s/f/c).
- `site_builder.py`: `build_site(repository, output_dir)` — 자산→메인→주식→상세→검색인덱스 순 실행.

## presentation/templates/ · static/
- `base.html`(공통 레이아웃, 컨텍스트: root/active_page/updated_date), `index.html`, `stocks.html`,
  `stock_detail.html`, partials(`_header`/`_stock_card`/`_top_cap_table`/`_score_bar`/`_metric_table`/
  `_indicators_section`/`_news_section`).
- `static/style.css`: 토스풍 라이트 테마, 카드/표/점수미터/CSS 탭, 모바일 720px 브레이크포인트.
- `static/search.js`: 유일한 JS — 첫 입력 시 인덱스 지연 로드, 부분일치 상위 20개 드롭다운.