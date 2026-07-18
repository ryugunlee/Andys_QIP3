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
  끝에 신규 팩터 10종(Operating/Gross/Net Margin, Net Debt to Equity, Cash Ratio,
  Capex to Revenue, Inventory Turnover, Quick Ratio, Effective Tax Rate,
  Receivables Turnover)이 추가됐다 — 수집·저장만 하고 아직 스코어링 미연결(QUANT.md 9절).
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
  encparam, rpt, frq=NAVER_WISE_FRQ_ANNUAL)`: rpt=0(손익계산서)/1(재무상태표)/2(현금흐름표) JSON을
  가져온다. frq=0(연간)/1(분기, `NAVER_WISE_FRQ_QUARTER`) — 응답 형태(YYMM 6개=실적 5개+컨센서스
  1개)는 frq와 무관하게 동일함을 확인했다(`.claude/PROBLEMS.md` #10).
- `parsers.py`: `parse_number`/`parse_won_amount`(한글 숫자 표기 "23.04배"/"1,666조 1,894억" 파싱),
  `parse_price_history`(siseJson 응답 → OHLCV DataFrame), `parse_financial_statements`(finance/annual
  응답 → long format DataFrame), `latest_actual_periods`/`get_statement_value`(컨센서스 제외 최신
  회계기간 조회 헬퍼). `parse_wise_financial_statement(payload, statement_type)`: WiseFn 응답(5개년
  실적 + 1개년 컨센서스 추정치)을 long format으로 변환 — item은 `"ACCODE:계정명"` 형태로 저장한다
  (같은 계정명이 트리의 여러 위치에 나타날 수 있어 ACCODE로 구분해야 함). `get_wise_value`/
  `latest_period_wise_values`: ACCODE 접두사로 값을 찾는 헬퍼, 최신 기간만 raw 보관용으로 추출.
- `naver_stock.py`: `NaverStock(BaseStock)`. `fetch()`가 basic/일봉(5년)/integration/finance-annual/
  WiseFn 손익계산서·재무상태표·현금흐름표(연간+분기)를 순서대로 가져온다 (`_fetch_wise_statements`
  — 실패해도 종목은 유효하게 남고 관련 팩터만 결측이 됨).
  - `_fetch_wise_quarterly_statements`: 같은 세 재무제표를 frq=1(분기)로도 조회해
    `wise_income_statement_q`/`wise_balance_sheet_q`/`wise_cash_flow_q`에 담는다 — 재무 팩터
    계산(curated factors)에는 쓰지 않고, `financial_statements`를 거쳐 상세 페이지 실적
    막대그래프의 분기 뷰(`.claude/PROBLEMS.md` #10)에만 쓰인다.
  - `_compute_valuation_factors`: 현재 스냅샷(PER/PBR/EPS/시총/배당수익률).
  - `_compute_financial_statement_factors`: 모바일 API 기반 최신 실적(매출액/순이익/ROE/부채비율/
    EPS성장/매출성장/PSR/PEGR). Asset to Equity/ROA는 여기서 부채비율 근사치로 우선 채워진다.
  - `_compute_wise_factors`: WiseFn 원본 계정 금액(억원)으로 Operating Cashflow/PCR/PFCR/
    Buyback Yield/Depreciation Capex Ratio/Coverage Ratio/NCAV/Current Ratio/ROC/GPTOA/
    Asset Turnover/ARP/Interest Ratio/Debt Growth/EV·EBITDA/EV·Revenue를 계산하고, 가능하면
    Asset to Equity/ROA를 자산총계/자본총계 기반 정확한 값으로 덮어쓴다. 계정과목 코드(ACCODE)는
    `collection/constants.py`의 `NAVER_WISE_ACCODE_*` 상수로 고정. 신규 팩터 10종(마진 3종·
    순부채비율·현금비율·당좌비율·재고/매출채권 회전율·설비투자 집약도·유효법인세율)도 여기서
    채운다 — 추가 계정(매출원가 200360·세전이익 203120·법인세 203130·재고자산 112840·
    매출채권 190560)을 읽어 야후와 동일 의미로 계산. 야후 쪽은 `stock.py`의
    `_compute_financials_factors`(마진·유효세율)와 `_compute_balance_sheet_factors`(현금 계정
    읽기 + 나머지)가 담당.
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
  - **한국 상장 종목 방어 가드**: 루프 최상단에서 `is_korean_listed_ticker(ticker)`면 경고 후
    건너뛴다(네트워크 호출도 안 함). 한국 종목은 네이버 전용이라는 불변식을 진입점에서 보장한다
    (`.claude/PROBLEMS.md` #24, `.claude/DECISIONS.md` 2026-07-17 참고). 한국 ADR은 통과.

## collection/tickers.py
- `get_tickers(stockmarket)`: 원래 `Andys_QIP2.py`에 있던 함수를 이동 (`.claude/PROBLEMS.md` #7 해결).
  한국 시장은 네이버가 쓰는 6자리 종목 코드를 접미사 없이 그대로 반환한다 (예전에는 ".KS"를 붙였으나
  이제는 네이버 경로로 수집하므로 불필요).
- `is_korean_market(stockmarket)`: 이 시장을 네이버 경로로 수집해야 하는지 여부 (`stockmarket[0]=="K"`).
  `Andys_QIP2.main()`이 야후/네이버 경로를 분기할 때 재사용한다.
- `is_korean_listed_ticker(ticker)`: 티커가 한국거래소 상장 종목(6자리 코드 + 선택적 .KS/.KQ,
  대소문자 무관)인지 여부. yfinance 진입점 가드에서 한국 종목을 걸러내는 데 쓴다. 한국 ADR
  (미국 상장 알파벳 심볼)은 매칭되지 않는다.
- `_normalize_us_symbols(symbols)`: FDR 미국 상장 목록 심볼 정규화 — NaN/빈 값 제거, 공백 포함
  심볼(우선주·신주인수권 등, yfinance 전량 404) 제외, "."→"-" 치환(BRK.B→BRK-B), 순서 유지
  중복 제거. AMERICAN 분기와 개별 시장(NASDAQ/NYSE 등) 분기가 공유한다
  (`.claude/PROBLEMS.md` #30 해결).

## collection/__init__.py
- `get_stock_basic_infomation`, `get_naver_stock_information`, `get_tickers`, `is_korean_market`,
  `is_korean_listed_ticker`, `split_raw_and_curated`을 공개 API로 재노출.

## collection/macro/ (경제지표 수집)
진입점은 최상위 `collect_macro.py` (`python collect_macro.py` — 초회 5년 적재와 증분
갱신을 같은 upsert로 처리). 주식 파이프라인과 독립 실행.

- `indicators.py`: 지표 정의 단일 소스. `MacroIndicatorSpec(id, name_ko, unit, source,
  symbol, category, scale, show_card, ecos_cycle, ecos_item_code)` 25종 — 시장 지수(코스피/
  코스닥/나스닥/S&P500/VIX), 환율(달러·엔100·위안/원, 달러인덱스), 원자재·금(WTI/브렌트/국제
  금/KRX 금현물/금 괴리율), 금리·물가(미 기준금리/2Y/10Y/30Y/3M/장단기금리차/미 CPI YoY,
  한국 기준금리/한국 CPI YoY). 선언 순서 = 메인 페이지 카드 순서. `specs_by_source()`/
  `spec_by_id()` 헬퍼. `ecos_cycle`/`ecos_item_code`는 MacroSource.ECOS 전용 필드.
- `yahoo_source.py`: `fetch_yahoo_macro(period)` — yfinance 배치 다운로드 → (indicator, date,
  value) long DataFrame. spec.scale 적용(엔/원 100엔 기준 등).
- `fred_source.py`: `fetch_fred_macro()` — FRED 공식 API(api.stlouisfed.org, FRED_API_KEY
  필요)로 수집. CPIAUCSL은 YoY %로 변환해 us_cpi_yoy로 저장. 키 미설정/시리즈별 실패는 경고
  후 건너뛰고 나머지는 계속 (`.claude/PROBLEMS.md` #16 해결).
- `ecos_source.py`: `fetch_ecos_macro()` — 한국은행 ECOS StatisticSearch API(BOK_API_KEY
  필요)로 한국 기준금리(kr_base_rate, 722Y001/일간)·CPI(kr_cpi_yoy, 901Y009/월간, YoY %로
  변환)를 수집. 키 미설정/시리즈별 실패는 경고 후 건너뜀.
- `naver_gold_source.py`: `fetch_naver_gold_macro(max_pages)` — KRX 금현물(원/g) 히스토리를
  네이버 marketindex 페이지네이션으로 수집 (`client.fetch_market_index_prices` 사용, #18).
- `derived.py`: `compute_derived_indicators(collected)` — 금 괴리율(gold_gap_pct: KRX 원/g vs
  국제 금 USD/oz÷31.1034768×달러원 환산, %)과 미 10Y−3M 장단기 금리차. 원천 지표가 없으면
  해당 파생만 건너뜀.

`collect_macro.py`는 `python-dotenv`의 `load_dotenv()`로 로컬 `.env`(BOK_API_KEY,
FRED_API_KEY)를 읽는다. GitHub Actions에서는 `.env` 없이 리포지토리 Secrets →
`collect-macro.yml`의 `env:`로 동일한 이름의 환경변수가 주입된다.

## collection/news/ (세계 경제 뉴스 헤드라인 수집)
진입점은 최상위 `collect_news.py`. Google News RSS("세계 경제" 검색)와 연합뉴스 경제 RSS
두 소스를 병합해 url 기준 중복 제거 후 macro DB의 `news` 테이블에 upsert한다. 주식/매크로
파이프라인과 독립 실행. 헤드라인+링크(+가능한 경우 짧은 요약)만 저장하고 원문 본문은
수집하지 않는다(각 소스 저작권/이용약관 관련 판단은 `.claude/DECISIONS.md` 2026-07-18 참고).

- `constants.py`: RSS URL(Google News는 `urllib.parse.quote`로 인코딩한 검색 쿼리 포함),
  요청 타임아웃/User-Agent, 소스별 1회 수집 상한(`GOOGLE_NEWS_FETCH_LIMIT`/
  `YONHAP_FETCH_LIMIT`), DB에 유지할 최신 기사 수(`NEWS_KEEP_LIMIT`), 두 소스를 구분하는
  `origin` 태그 값(`ORIGIN_GOOGLE_NEWS`/`ORIGIN_YONHAP`) — 표현 계층이 "세계 경제" 검색
  결과를 우선 노출하는 데 쓴다(아래 news_provider.py 참고).
- `parsers.py`: `published_at_kst(entry)` — feedparser의 `published_parsed`(UTC
  struct_time, 원래 시간대와 무관하게 정규화됨)를 "YYYY-MM-DD HH:MM" 한국시간 문자열로
  변환(두 소스 공용). `strip_source_suffix(title, source_name)`: Google News가 제목 끝에
  덧붙이는 " - 출처명"을 한 번만 제거(원문 제목 자체에 출처명이 포함된 경우도 있어, 마지막
  한 번만 제거해야 원문을 훼손하지 않음).
- `google_news_source.py`: `fetch_google_news_economy(limit)` — Google News RSS 응답을
  파싱. 링크는 Google 리다이렉트 링크, 스니펫은 HTML 앵커라 summary는 항상 None으로
  둔다(헤드라인+링크만). `entry.source`(언론사명)가 없으면 "Google News"로 대체.
- `yonhap_source.py`: `fetch_yonhap_economy(limit)` — 연합뉴스 경제 RSS 응답을 파싱. 원문
  링크가 직접 제공되고 description도 평문 요약이라 summary까지 채운다.
- `__init__.py`: 두 fetch 함수를 공개 API로 재노출.

`collect_news.py`: `collect_news()`가 두 소스를 합쳐 url 기준 중복 제거한 DataFrame을
반환하고, `main()`이 macro DB에 upsert 후 `NEWS_KEEP_LIMIT` 기준으로 오래된 기사를
정리한다(`storage.prune_news`).


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
  upsert — 섹터/산업 자체 평가), `news`(url 기준 upsert — 세계 경제 뉴스 헤드라인,
  `origin` 컬럼으로 Google News/연합뉴스 구분).

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
  `main()`의 필터: Finalscore 상위 10% & reliability>80 & Quant score>50 & Fscore>50), 시장
  전체 percentile 커트라인을 DataFrame으로 조회. `get_run_snapshot`은 읽기 경계에서 `ticker`→
  `Ticker` 및 레거시 오타 컬럼 `reliablity`→`reliability`를 정규화한다(오타 수정 이전에 수집된
  DB로 build_site가 크래시하지 않도록 하는 하위호환 shim, 재수집 후에는 no-op).
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

## storage/news_repository.py
- macro_repository와 같은 패턴(register view → `INSERT ... ON CONFLICT`)을 따른다.
- `upsert_news(conn, news)`: (title, source, url, published_at, summary, origin) DataFrame을
  url 기준 upsert(같은 기사 재수집해도 중복 안 됨).
- `prune_news(conn, keep)`: published_at 기준 최신 keep건만 남기고 나머지 삭제 — RSS
  피드에서 밀려난 오래된 기사를 정리해 DB가 무한정 커지지 않게 한다.
- `get_latest_news(conn, limit)`: 최신 기사부터 limit건 반환.

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
  (`Value risk`/`Growth risk`/`reliability`)는 계열 무관 단일 컬럼.

## analysis/factors.py
- `Direction` (IntEnum): 방향성(HIGHER_IS_BETTER / LOWER_IS_BETTER_RECIPROCAL / LOWER_IS_BETTER_NEGATED). 원본의 매직넘버 s(1/0/-1)를 이름으로 대체.
- `FactorSpec`: (컬럼명, 방향) 쌍을 담는 값 객체.
- `BASIC_*` / `DETAIL_*` 팩터 목록, `RELIABILITY_TF_COLUMNS`, `STANDARD_DATA_FACTORS`
  (전체 컬럼 목록 단일 소스). (VC1 구성 팩터는 composite_scores.py로 이동)
- `PRESENCE_ONLY_FACTORS`: 다른 종합점수의 입력이 아니라 방향성 점수를 낼 필요가 없는 팩터
  목록(현재 `"Buyback to Income"` 하나) — `attach_presence_flag`로 TF만 계산한다
  (`.claude/PROBLEMS.md` #1).

## analysis/weights.py
- 종합점수 계산에 쓰이는 가중치·분모·임계값을 이름 있는 상수로 정의. 값은 원본과 동일.

## analysis/percentile.py
- `calculating_percentile(df, column, direction, score_column=None)`: 한 컬럼의 percentile 점수
  (`score_column`, 기본 `{column}S`)와 데이터 존재 플래그(`{column}TF`)를 계산하는 핵심 엔진.
  결측 50점. `score_column`으로 섹터/산업 모집단 점수도 같은 엔진으로 낸다.
- `attach_presence_flag(df, column)`: 방향성 점수 없이 `{column}TF`만 계산하는 경량 버전
  (`PRESENCE_ONLY_FACTORS` 전용).

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
  - `_apply_detail_percentiles`: share/original/reverse 순서로 percentile 적용 후
    `PRESENCE_ONLY_FACTORS`는 `attach_presence_flag`로 TF만 붙인다.
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
- `NEWS_FEATURED_LIMIT`(5)/`NEWS_LIST_LIMIT`(20): 뉴스 섹션(`_news_section.html`, 홈·주식
  분석 페이지 공용)에 노출하는 "주요 기사(요약 포함)"/"헤드라인만" 개수. `environment.py`가
  Jinja 전역값으로 등록해 템플릿이 직접 슬라이싱한다.

## presentation/models.py
- 표현용 dataclass: `StockSummary`(카드/표), `StockDetail`(상세 — `values`는 컬럼명→값,
  `qualitative`는 정성 평가로 없으면 미표시), `SearchEntry`, `EconomicIndicator`(`category`/
  `history`: 최근 6개월 일별값 — 우측 추이 사이드바용), `NewsItem`,
  `GroupScore`(섹터/산업 평가 — 상대 점수 + 대표 지표 중앙값).
- 차트용 dataclass: `PricePoint`(일봉 한 점: date/close/volume/foreign_rate),
  `AnnualFinancials`(실적 한 기간의 매출·영업이익·순이익 — 연간·분기 겸용, 없으면 None),
  `StockCharts`(prices·annual·quarterly 묶음, 데이터 없는 계열은 빈 리스트→템플릿에서 섹션/토글
  숨김). quarterly는 현재 네이버만 채워진다(`.claude/PROBLEMS.md` #10).

## presentation/korean_names.py
- `KOREAN_NAME_OVERRIDES`(종목코드→한글명 보정맵, 주요 대형·중형주)와
  `display_name(ticker, raw_name)`. yfinance 경로로 수집돼 영문명이 들어온 경우의 안전망 —
  "005930"/"005930.KS" 어느 형태든 6자리 코드로 정규화해 한글명으로 치환. row_mapping이 사용.

## presentation/metrics.py
- 지표 메타데이터 단일 소스: `MetricSpec(column, label, format, group)` 63개,
  `MetricFormat`(MONEY/PRICE/MULTIPLE/PERCENT/FRACTION_PERCENT/SCORE/TEXT/NUMBER),
  `MetricGroup`(밸류에이션~종합 점수, 선언 순서=표시 순서), `HEADLINE_SCORE_COLUMNS`,
  `specs_by_group()`. **분석에서 지표가 추가되면 여기 한 줄 추가로 상세 페이지 자동 반영.**

## presentation/formatters.py
- `format_money`(조/억·$T/$B), `format_price`(₩/$), `format_percent`/`format_fraction_percent`,
  `format_multiple`, `format_score`, `format_text`(영문 신호→한국어: Heating→상승 흐름 등),
  `format_metric`(MetricFormat dispatcher), `meter_width`(0~100 클램프), `change_class`(up/down),
  `sparkline_points(values, width, height)`: 값 목록 → SVG `<polyline points="...">` 좌표 문자열
  (빌드 타임에 계산되는 정적 스파크라인 — 우측 추이 사이드바 전용, 인터랙티브 차트는 charts.js가 담당),
  `register_filters(env)`: 위 함수들을 Jinja2 필터로 등록.

## presentation/repository/ (데이터 어댑터)
- `base.py`: `StockRepository` Protocol — `good_stocks(limit)`, `top_by_market_cap(region, limit)`,
  `iter_stock_details()`, `chart_bundle(ticker, market)`, `search_entries()`, `market_counts()`,
  `group_scores(group_type)`, `updated_date()`. 빌더는 이 계약만 의존한다.
- `row_mapping.py`: 두 구현체가 공유하는 컬럼명 상수(`COL_*`)와 행→모델 변환
  (`summary_from_row`/`detail_from_row`/`search_entry_from_row`, NaN→None 처리).
  이름은 `_display_name(row)`(→korean_names.display_name)을 거쳐 한국 종목을 한글로 표시.
- `financial_series.py`: `annual_financials_from_df(df, source)` / `quarterly_financials_from_df(df,
  source)` — 재무제표 long DataFrame에서 매출·영업이익·순이익 3계열을 뽑는다(공통 로직은
  `_period_series`). 소스별 항목 식별자(naver=ACCODE 접두사 200000/201370/203170, yahoo=Total
  Revenue/Operating Income/Net Income)를 이 파일에 캡슐화, is_consensus(컨센서스)는 제외.
  분기는 statement_type 접미사 `_q`(naver만, `_quarter_label`로 "202509"→"2025 Q3" 변환)를 읽고,
  소스가 분기를 지원하지 않으면(yahoo) 빈 리스트를 반환한다.
- `db_repository.py`: `DuckDbStockRepository` — **기본 구현체**. 주식 DB **2개(KR/US)**를 순회해
  시장별 최신 run의 snapshot_factors를 통합, 추천 종목은 `get_goodstock` 재사용.
  `group_scores`는 각 DB의 group_summary에서 Finalscore 상대 점수(퍼센타일·스탠다드 평균)와
  PER/ROE/3M 중앙값을 뽑는다. DB 없으면 경고 후 건너뜀. read_only 연결.
  `chart_bundle`은 market으로 KR/US DB와 소스(naver/yahoo)를 정해 `get_price_history`·
  `get_financial_statements`를 재사용(연간/분기 둘 다 같은 조회 결과에서 뽑음), 종목별 반복
  조회를 위해 DB 연결을 캐시한다.
- `csv_repository.py`: `CsvStockRepository` — 과거 CSV 산출물 폴백. `group_scores`는 빈 목록,
  `chart_bundle`은 시계열 산출물이 없어 항상 None(차트 섹션 미표시).
- `indicators_provider.py`: `load_economic_indicators(db_path)` → `list[EconomicIndicator] | None`.
  **구현 완료**: DuckDB macro_daily에서 지표별 최신값+전일 대비를 읽어 indicators.py 선언
  순서대로 카드 생성. %단위 지표(금리·괴리율)의 전일 대비는 %p 차이로 계산 (PROBLEMS #17).
  DB가 없거나 비면 None ("준비 중" 카드).
  - `_trend_history(conn, indicator_id)`: `get_macro_history`로 지표 하나의 전체 이력을 읽어
    최근 6개월(`_TREND_MONTHS`)치 값만 오름차순 리스트로 반환 — `EconomicIndicator.history`에
    채워 우측 추이 사이드바 스파크라인에 쓴다. 커넥션을 함수 밖에서 열어둔 채 지표마다 호출하므로
    `load_economic_indicators`는 이제 커넥션을 `try/finally` 바깥이 아닌 전체를 감싸는 형태로 닫는다.
- `news_provider.py`: `load_news(ticker=None)` → `list[NewsItem] | None`. **구현 완료**(세계
  경제 뉴스만): `ticker`를 지정하면(종목별 뉴스) 아직 미구현이라 None. `ticker=None`이면
  macro DB의 `news` 테이블을 넉넉히(`_POOL_LIMIT`) 읽어 `_prioritize_google_news()`로
  재정렬한다 — 연합뉴스는 게시 빈도가 훨씬 높아 단순 최신순 병합이면 "주요 기사" 자리를
  국내 일반 경제 기사가 차지해버리는 문제가 있어(로컬 테스트로 확인), 상위
  `NEWS_FEATURED_LIMIT`개는 `origin=="google_news"`(실제 "세계 경제" 검색 결과)를 우선
  채우고 부족분만 최신순으로 채운다. 그 아래 헤드라인 목록은 원래의 최신순 병합 그대로라
  다양성이 유지된다. DB/테이블이 없으면 None("준비 중").

## presentation/builders/ (페이지 1종 = 파일 1개)
- `environment.py`: `create_environment()` — 공유 Jinja2 환경 (로더+필터+전역값,
  `news_featured_limit`/`news_list_limit` 포함).
- `assets.py`: `copy_static()`(static→docs/static), `write_nojekyll()`.
- `index_page.py`: `build_index_page()` — 메인 (경제지표 placeholder·추천 미리보기·뉴스 placeholder·
  우측 6개월 추이 사이드바). `_group_by_category(indicators)`: `EconomicIndicator.category`로
  `MacroCategory` 선언 순서(시장 지수→환율→원자재·금→금리·물가)대로 묶어 `(카테고리명, 지표목록)`
  리스트를 만든다 — Jinja `groupby` 필터는 키를 알파벳순으로 재정렬해버려서 선언 순서를
  못 지키므로 파이썬에서 미리 묶는다. history가 2개 미만인 지표(추이를 그릴 수 없음)는 제외.
  `trend_groups` 컨텍스트로 템플릿에 전달.
- `stocks_page.py`: `build_stocks_page()` — 주식 분석 (추천 카드·KR/US 시총 상위 CSS 탭·뉴스).
- `detail_pages.py`: `build_detail_pages()` — 전 종목 상세. `ticker_filename()` sanitize,
  metrics 스펙 순회로 그룹 표 조립(템플릿은 CSV 컬럼명을 모름), 대표 점수 4종은 상단 타일.
  `repository.chart_bundle()`을 종목마다 호출해 `_chart_data()`(JS용 콤팩트 JSON, 일봉은
  병렬 배열 d/c/v로 압축, annual·quarterly 둘 다 포함)와 `_financial_table()`/
  `_financial_table_quarterly()`(실적 표 — 영업이익률·직전 기간比 성장률을 공용 `_financial_rows`가
  계산, 최근 기간부터 정렬)로 변환해 템플릿에 전달. 데이터 없으면 None(quarterly 없으면 토글도
  템플릿에서 숨김).
- `sectors_page.py`: `build_sectors_page()` — 섹터·산업 비교. `group_scores`를 표시용 문자열로
  변환(포맷터 선택은 빌더 담당)해 상대 점수 게이지 + 대표 지표 중앙값 표 렌더.
- `search_index.py`: `build_search_index()` — `data/search-index.json` (축약 키 t/n/m/s/f/c).
- `pwa.py`: `build_pwa(repository, env, output_dir)` — 홈 화면 설치용 산출물 3종을 **사이트 루트**에
  쓴다: `manifest.webmanifest`(scope "./"가 사이트 전체를 덮어야 함), `sw.js`(서비스워커 스코프가
  전 페이지를 덮어야 함), `offline.html`. 별도 앱 코드 없이 이 정적 사이트 자체가 앱이다
  (DECISIONS.md 2026-07-17 "모바일 앱 = PWA" 참고).
  - `_static_urls()`: 복사된 `static/` 실제 파일에서 프리캐시 URL을 뽑는다(목록을 손으로 적지
    않는 이유: `cache.addAll`은 하나만 404여도 전부 실패).
  - `_cache_version()`: 프리캐시 대상들의 내용 + 데이터 기준일 sha256 앞 12자. 내용이 그대로면
    버전도 그대로(불필요한 재다운로드 방지), 바뀌면 옛 캐시가 통째로 버려진다.
  - **호출 순서 주의**: 캐시 버전이 다른 빌더 산출물의 내용에서 나오므로 반드시 맨 마지막.
    같은 이유로 함수 안에서도 manifest·offline.html을 먼저 쓰고 sw.js를 마지막에 만든다
    (뒤집으면 첫 빌드가 "파일 없음"을 해싱해 빌드마다 버전이 흔들린다).
- `site_builder.py`: `build_site(repository, output_dir)` — 자산→메인→주식→섹터→상세→검색인덱스→PWA 순.
  - `EmptySiteError(RuntimeError)`: 시장 데이터 0건일 때 `build_site()`가 **output_dir을
    건드리기 전에** 던지는 예외. 빈 사이트는 정당한 산출물이 아니며, 데이터 공급이 끊긴
    실행이 배포된 사이트를 빈 껍데기로 덮어쓰는 사고를 막는 가드다(PROBLEMS #26).
    진입점 `build_site.py`가 이를 받아 0이 아닌 종료코드로 바꾸고, CI 스크립트의
    `set -e`가 커밋 단계를 건너뛰게 한다.

## presentation/templates/ · static/
- `base.html`(공통 레이아웃, 컨텍스트: root/active_page/updated_date, `{% block scripts %}`로
  페이지별 JS 선택 로드 — PWA 태그(manifest/theme-color/apple-touch-icon)와 `<body data-root>`도
  여기 있다. `{% block aside %}{% endblock %}`: `<main class="container">` 뒤·`<footer>` 앞의
  선택적 블록 — 비워두면 아무 영향 없고, index.html만 채워서 우측 추이 사이드바를 렌더한다),
  `index.html`, `stocks.html`, `stock_detail.html`, `sectors.html`, `offline.html`,
  partials(`_header`/`_install`/`_stock_card`/`_top_cap_table`/`_score_bar`/`_metric_table`/
  `_group_table`/`_indicators_section`/`_news_section`/`_trend_rail`).
- `partials/_news_section.html`: 컨텍스트 `news`(list[NewsItem] | None, index.html/stocks.html
  공용) 하나만 받아 템플릿 안에서 `news[:news_featured_limit]`(주요 기사, 요약 포함)와
  `news[news_featured_limit:...+news_list_limit]`(헤드라인+링크만)로 슬라이싱한다 — 두 값이
  이미 environment.py 전역값이라 빌더는 손댈 필요 없다. 어느 기사가 "주요"로 오는지(순서)는
  news_provider.py가 결정한다.
- `partials/_trend_rail.html`: 우측 6개월 추이 사이드바(index.html의 `aside` 블록에서 include).
  컨텍스트 `trend_groups`(카테고리명, 지표목록) 순회 → 카테고리별 `<details class="trend-group">`
  접기(첫 카테고리만 기본 펼침) 안에 지표별 이름·현재값·스파크라인(`sparkline_points` 필터로 만든
  `<polyline>`)을 나열. 등락 색은 `(history[-1]-history[0]) | change_class`로 계열 전체 추세를
  판정(전일 대비가 아니라 6개월 추세임에 주의).
- `manifest.webmanifest.jinja`·`sw.js.jinja`: HTML이 아닌 PWA 산출물 템플릿(`.jinja` 확장자로
  구분 — autoescape는 `.html`에만 걸린다). 파일명·경로의 단일 출처는 `builders/pwa.py`이며,
  offline/manifest URL은 렌더 인자로 넘겨받는다.
- `sw.js.jinja`의 캐싱 전략: 페이지 이동·`data/*.json`은 네트워크 우선(분석 결과가 매일 갱신되므로
  낡은 데이터를 보여주지 않는 게 우선), `static/*`과 매니페스트는 캐시 우선(버전이 캐시 이름에 있어
  빌드 때 통째로 무효화). 캐시에 없는 페이지를 오프라인에서 열면 **offline.html로 리다이렉트**한다
  — 본문만 돌려주면 주소가 원래 경로(`/stocks/NVDA.html`)로 남아 상대경로 자산이 전부 깨진다.
- `stock_detail.html`: 가격 섹션(`chart_data.prices`가 있을 때만, 기간 토글 1/3/6/12/60개월 +
  `<div class="chart-canvas">`), 실적 섹션(`<details class="reveal-block">` 기본 접힘 — 클릭 시
  `renderBars` 애니메이션). `financial_table_quarterly`가 있을 때만 "연간/분기"
  `.bar-period-tabs` 토글이 나타나고, 표도 연간/분기 두 `.fin-table-panel`이 함께 렌더돼(하나는
  `hidden`) 같은 토글로 전환된다. `chart_data`는 `<script id="chart-data"
  type="application/json">`로 임베드(annual/quarterly 모두 포함), 있을 때만 `static/charts.js` 로드.
- `static/style.css`: 토스풍 라이트 테마, 카드/표/점수미터/CSS 탭, 모바일 720px 브레이크포인트.
  차트 관련: `.price-chart`/`.range-tab`/`.chart-tooltip`/`.chart-hover-dot`(주가),
  `.reveal-block`/`.bar-chart-toolbar`/`.bar-period-tabs`/`.bar-legend`/`.bar-chart`/`.fin-table`
  (실적, `.range-tab` 스타일을 연/분기 토글에도 재사용).
  설치 관련: `.install-cta`/`.install-button`/`.install-guide`(iOS 안내 팝오버). 모바일에서는
  설치 버튼이 검색창과 **같은 줄**에 오도록 `.search-box`가 `flex: 1 1 200px` — 헤더가 sticky라
  줄이 늘면 그만큼 본문이 가려지므로 두 줄을 넘기지 않는다.
  우측 추이 사이드바: `.trend-rail`은 기본 `display:none`, `@media (min-width: 1560px)`에서만
  `position: fixed`로 노출(중앙 정렬 `.container`(1080px) 바깥 여백이 패널+간격을 담을 만큼
  넓어지는 지점 — 그 아래 폭에서는 렌더 자체를 숨긴다, 본문 하단 이동은 하지 않기로 결정
  했다 — `.claude/DECISIONS.md` 참고). `.trend-group`은 `.reveal-block`과 같은 `<details>`
  접기 패턴을 재사용(별도 CSS로 복제 — 실적 섹션과 폭·글자크기가 달라 공유하면 오히려 결합도만
  높아짐). `.trend-chart polyline`은 `.up`/`.down` 클래스로 `--up`/`--down` 색.
  뉴스: `.news-summary`(주요 기사 요약 문단), `.news-list-compact`(헤드라인만 나열하는 목록 —
  `.news-list`보다 padding이 좁고 제목·출처·날짜가 한 줄에 오도록 flex-wrap).
- `static/charts.js`: 외부 라이브러리 없는 바닐라 SVG 차트 (search.js와 같은 자체구현 철학).
  `renderPrice()` — 영역(area) 차트, 기간별 슬라이스, mousemove로 크로스헤어·툴팁,
  상승/하락 색은 CSS 변수 `--up`/`--down`(한국 관례: 상승 빨강/하락 파랑) 사용.
  `renderBars(root, series)` — 매출/영업이익/순이익 그룹 막대(연간·분기 겸용, series만 바뀜),
  `<details>` toggle 이벤트에서 최초 1회 렌더 + 0선에서 자라는 rAF 트윈 애니메이션.
  `.bar-period-tabs` 클릭 시 `data.annual`/`data.quarterly`를 바꿔가며 `renderBars` 재호출하고
  `.fin-table-panel`의 `hidden`도 함께 토글. `init()`이 `#chart-data`의 JSON을 파싱해 배정.
- `static/sw-register.js`: 서비스워커 등록만 담당. `sw.js`는 사이트 루트에 있어야 스코프가 전
  페이지를 덮으므로 `<body data-root>`로 경로를 만든다. 실패해도 조용히 넘어간다(사이트는 그대로
  동작하고 캐시·설치만 빠짐).
- `static/install.js`: 설치 버튼 UI만 담당(등록과 책임 분리). 안드로이드·데스크톱 크롬은
  `beforeinstallprompt`를 붙잡아 뒀다가 버튼 클릭 시 네이티브 설치창을 띄우고, 설치 API가 없는
  iOS 사파리는 "공유 → 홈 화면에 추가" 안내 팝오버를 대신 띄운다. 이미 설치된(standalone) 상태나
  설치 불가 환경에서는 버튼 자체가 나오지 않는다(`_install.html`이 `hidden`으로 시작).
- `static/icons/`: PWA 아이콘(192·512·maskable 512·apple-touch 180). accent 바탕에 흰색 오름차순
  막대. Pillow를 의존성에 추가하지 않으려고 표준 라이브러리(zlib+struct)로 구운 것이라, 디자인을
  바꿀 일이 있으면 아이콘을 다시 생성하는 일회성 스크립트를 새로 작성해야 한다.

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
  호출하고, `collect_macro.py` 실행 후 사이트는 다시 빌드하지 않는다 — 그 주의 시장별
  수집이 사이트를 재빌드할 때까지 경제지표 반영이 지연된다는 뜻(`.claude/PROBLEMS.md`
  #31, 이번 작업 범위 밖이라 그대로 둠).
- `collect-news.yml`(매일 22:30 UTC — 같은 macro DB 자산을 다루는 collect-macro.yml과 1시간
  간격을 둬 `--clobber` 업로드 경합을 피함): restore_db(전체, `build_site.py`가 KR·US 주식
  DB도 읽으므로) → `python collect_news.py` → save_db(매크로 DB만) → build_and_commit_site.
  뉴스는 홈/주식 분석 페이지에 바로 반영돼야 하므로, 매크로와 달리 수집 직후 사이트도
  재빌드한다.
- `deploy-site.yml`(수동 + presentation/build_site 변경 push): 데이터 수집과 **독립적으로**
  docs/를 재배포하는 통로. restore_db(전체) → build_and_commit_site만 실행하고 save_db는 하지
  않는다(읽기 전용). presentation 코드만 바꿔도 사이트를 갱신할 수 있게 한다. `push` paths에서
  `docs/**`는 제외한다 — build_and_commit_site가 docs/만 커밋하므로 넣으면 자기 자신을 무한
  재실행한다 (`.claude/DECISIONS.md` 2026-07-17 참고).
- 모든 워크플로는 `permissions.contents: write`로 `docs/`를 직접 push하고, gh CLI 인증은
  `github.token`(기본 `GITHUB_TOKEN`)만 사용한다 — 추가 Secrets 불필요.

## Andys_QIP2.py 진입점 변경
`if __name__ == "__main__"`에서 `sys.argv`가 있으면(CI) 그 값으로 `main()`을 1회만 실행하고
종료, 없으면(로컬 대화형) 기존과 동일하게 `input()` 프롬프트 + 매일 09:00 스케줄 무한 루프를
그대로 유지한다 — 로컬 사용 방식은 바뀌지 않았다.
- `static/search.js`: 유일한 JS — 첫 입력 시 인덱스 지연 로드, 부분일치 상위 20개 드롭다운.