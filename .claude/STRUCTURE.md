프로그램의 함수와 구동 구조가 여기에 작성될 것이다.
제목 형식을 통해서 거대한 함수와 작은 함수를 구분한다.


# 데이터 수집 함수 및 영역
투자에 관한 데이터를 수집하는 함수 및 영역이다.

`collection/` 폴더 안에 있으며, `Andys_QIP2.py`는 이 패키지를 import해서 사용한다.
`get_tickers`(티커 목록 조회)는 아직 이 폴더로 옮기지 않고 `Andys_QIP2.py`에 남아있다.

## collection/constants.py
- 레이트리밋 대기시간, 이동평균/MACD/RSI 기간, 기간수익률 조회 구간, EPS 0 대체값 등
  수집 로직에 쓰이는 이름 있는 상수 모음.

## collection/stock.py
- `Stock`: 종목 하나의 데이터를 담는 클래스.
  - **raw 속성**: `info`, `history`, `cashflow`, `financials`, `balance_sheet`, `insider_purchases` —
    yfinance가 주는 원본 그대로 보관 (history는 기술적 지표 계산 후 컬럼이 추가된 채로 보관됨).
  - **curated 속성**: `company_name`, `sector`, `per`, `pbr`, ... 기존 `get_stock_basic_infomation`이
    계산하던 ~60개 팩터를 그대로 속성으로 가짐 (`CURATED_COLUMNS`에 컬럼명 ↔ 속성명 매핑 정의).
  - `fetch()`: yfinance에서 raw 데이터를 채움 (필수 데이터 없으면 `is_valid=False`로 조기 종료).
  - `compute_curated_factors()`: `_compute_valuation_factors` → `_compute_technical_factors` →
    `_compute_cashflow_factors` → `_compute_financials_factors` → `_compute_balance_sheet_factors` →
    `_compute_insider_factors` 순서로 curated 팩터를 계산 (원본 계산 순서/의존관계 그대로 유지).
  - `to_row()`: raw(출처별 접두사 `raw_info__`/`raw_cashflow__`/`raw_financials__`/
    `raw_balance_sheet__`/`raw_insider__`/`raw_history__`) + curated 데이터를 하나의 dict(표의 한 행)로 병합.
    복잡한 info 필드(companyOfficers 등 list/dict)는 JSON 문자열로 변환해 저장.
  - **주의**: percentile 기반 점수(1차/2차 정제, `analysis/` 패키지가 하는 일)는 시장 전체 데이터가
    있어야 계산 가능하므로 이 클래스의 책임이 아니다 — 종목 하나만으로는 계산할 수 없는 값이기 때문.

## collection/basic_information.py
- `get_stock_basic_infomation(tickers)`: 티커마다 `Stock`을 만들어 raw+curated 데이터를 모두 담은
  표(DataFrame)로 반환. 티커별로 raw 필드 유무가 달라도 pandas가 합집합 컬럼을 자동 생성.
  기존과 동일한 레이트리밋 재시도(Too Many Requests → 5분 대기) 로직 유지.

## collection/__init__.py
- `get_stock_basic_infomation`을 공개 API로 재노출.


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