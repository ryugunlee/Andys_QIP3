# QUANT.md — 퀀트 점수 시스템 & 수집 데이터 명세

이 문서는 현재 코드(`analysis/`, `collection/`, `storage/`)가 실제로 실행하고 있는
점수 산출 방식과 수집 데이터를 정리한다. `CLAUDE.md`가 언급하는 "선별 요건 및 방식"의
저장 위치가 이 파일이다. 값/가중치가 바뀌면 이 문서도 함께 갱신한다.

관련 코드의 단일 소스(Single Source of Truth):
- 팩터 목록·방향성: `analysis/factors.py`
- 가중치·임계값: `analysis/weights.py`
- 종합점수 수식: `analysis/composite_scores.py`
- 점수 엔진: `analysis/percentile.py`(퍼센타일), `analysis/standard_score.py`(스탠다드)
- 모집단 파이프라인: `analysis/score_pipeline.py`
- 매크로 지표 목록: `collection/macro/indicators.py`
- 화면 라벨/포맷: `presentation/metrics.py`

---

## 1. 데이터 수집

### 1.1 기업 데이터 소스

| 시장 | 소스 | 수집 모듈 |
|---|---|---|
| KOSPI/KOSDAQ/KONEX/KRX (한국) | 네이버증권 (requests 직접 호출, WiseFn 재무제표 API) | `collection/naver/` |
| NASDAQ/NYSE/AMEX 등 (해외) | yfinance | `collection/stock.py` |

두 소스 모두 종목당 다음을 수집한다.
- 최근 5년 일봉(OHLCV) → 기술적 지표 계산 (`collection/technical.py`, `collection/stock_base.py`)
- 손익계산서/재무상태표/현금흐름표 (연간, 소스가 제공하는 최근 기간)
- 밸류에이션/지분 관련 원본 정보(시가총액, PER 등 소스 제공 지표, 내부자 지분 등)

수집된 raw 데이터는 DuckDB `raw_latest`(종목당 최신 1건, JSON)와
`financial_statements`(전체 기간, long format)에 저장되고, 계산된 curated 팩터는
`snapshot_factors`에 저장된다. 한국 종목은 반드시 네이버 경로로만 수집하며
yfinance 경로에서는 방어적으로 걸러진다(`collection/tickers.py`).

### 1.2 curated 팩터 (종목당 1행, 시장 전체 비교 가능한 지표)

모든 팩터는 `collection/stock_base.py`의 `CURATED_COLUMNS`가 정의한 순서로
`snapshot_factors` 테이블에 저장된다. 계산식은 yfinance 소스(`collection/stock.py`) 기준이며,
네이버 소스도 동일한 의미의 팩터를 같은 컬럼명으로 채운다.

**밸류에이션**

| 컬럼 | 의미 | 계산식 |
|---|---|---|
| PER | 주가수익비율 | 종가 / EPS |
| PBR | 주가순자산비율 | 소스 제공값 (priceToBook) |
| PSR | 주가매출비율 | 소스 제공값 (priceToSalesTrailing12Months) |
| PCR | 주가현금흐름비율 | 시가총액 / 영업현금흐름 |
| EV/Revenue | EV/매출 | 소스 제공값 |
| EV/EBITDA | EV/EBITDA | 소스 제공값 |
| PEGR | PER/이익성장률 | 소스 제공값 (trailingPegRatio) |
| PFCR | 주가잉여현금흐름비율 | 시가총액 / (영업현금흐름 − Capex) |
| NCAV | 순유동자산/시가총액 | (유동자산 − 유동부채) / 시가총액 |
| EPS | 주당순이익 | 소스 제공값 (0이면 0.0001로 대체해 0나눗셈 방지) |

**수익성**

| 컬럼 | 의미 | 계산식 |
|---|---|---|
| ROE | 자기자본이익률 | 소스 제공값 |
| ROA | 총자산이익률 | 소스 제공값 |
| ROC | 투하자본이익률 | EBIT / (총자산 − 총부채) |
| GPTOA | 매출총이익/총자산 | 매출총이익 / 총자산 |
| Asset Turnover | 자산회전율 | 매출 / 총자산 |
| Revenue / Net Income / Operating Cashflow | 매출·순이익·영업현금흐름 | 소스 제공값 (금액) |

**성장성**

| 컬럼 | 의미 | 계산식 |
|---|---|---|
| EPSgrowth | EPS 성장률(%) | earningsGrowth × 100 |
| Revenuegrowth | 매출 성장률(%) | revenueGrowth × 100 |

**재무 건전성**

| 컬럼 | 의미 | 계산식 |
|---|---|---|
| Debt to Equity | 부채비율 | 소스 제공값 |
| Debt Growth | 부채 증가율(1년, %) | (올해 총부채 − 작년 총부채) / 작년 총부채 × 100 |
| Current Ratio | 유동비율 | 유동자산 / 유동부채 |
| Interest Ratio | 이자보상배율 | 영업이익 / 이자비용 |
| Coverage Ratio | 현금흐름/부채 비율 | 영업현금흐름 / 총부채 |
| Asset to Equity | 재무 레버리지 | 총자산 / 자기자본 |
| Depreciation Capex Ratio | 감가상각/설비투자 비율 | −감가상각비 / Capex |
| ARP | 발생액 비율(이익 품질, %) | (순이익 − 영업현금흐름) / 시가총액 × 100 |

**주주환원·지분**

| 컬럼 | 의미 | 계산식 |
|---|---|---|
| Dividend Yield | 배당수익률 | 소스 제공값 |
| Buyback Yield | 자사주매입수익률(%) | −(자사주매입 + 자사주발행) / 시가총액 × 100 |
| Dividend to Income | 배당성향 | (배당수익률 × 종가 / EPS) / 100 |
| Buyback to Income | 자사주매입/이익 | (Buyback Yield × 종가 / EPS) / 100 — **점수 미반영, 표시 전용**(존재 여부만 신뢰도에 반영) |
| Insiderpercent | 내부자 지분율 | 소스 제공값 |
| Institutionpercent | 기관 지분율 | 소스 제공값 |
| Insider Buy Ratio | 내부자 순매수 비율(%) | (내부자 순매수 주식수 × 1년 전 종가) / 시가총액 × 100 |

**수급·모멘텀**

| 컬럼 | 의미 | 계산식 |
|---|---|---|
| 3M/6M/1Y Ratio | 3개월/6개월/1년 수익률(%) | (현재 종가 / N일 전 종가) × 100 − 100 |
| 3M/1Y/10D Turnover | 거래대금/시가총액 | 기간 평균 거래대금 / 시가총액 |
| 10D Overheat | 단기 과열도 | 10일 Turnover / 3개월 Turnover |
| 3M Overheat | 중기 과열도 | 3개월 Turnover / 1년 Turnover |
| 3M/1Y Volatility | 변동성 | 기간 내 일간 등락률 절대값 평균 |

**기술적 신호** (점수 계산에는 쓰이지 않고 화면 표시 전용)

| 컬럼 | 의미 |
|---|---|
| MACD Signal | Heating / Heat Timing / Cooling / Sell Timing |
| RSI Signal | RSI가 시그널선 상향(Heating/Heat Timing) 여부 |
| RSI | OVERHEAT(>70) / UNDERHEAT(<30) / NORMAL |
| MA5/20/60/120/200 | 종가가 이동평균선 위(Hit)/아래(Miss) |

### 1.3 매크로(거시경제) 지표

`collect_macro.py`가 별도로 매일 수집한다(`collection/macro/indicators.py`가 단일 소스).
`(indicator, date)` 기준으로 DuckDB `macro_daily`에 upsert된다.

| 카테고리 | 지표 | 소스 |
|---|---|---|
| 시장 지수 | 코스피, 코스닥, 나스닥, S&P 500, VIX | yfinance |
| 환율 | 달러/원, 엔/원(100엔), 위안/원(파생), 달러/위안, 달러인덱스 | yfinance + 파생 |
| 원자재·금 | WTI, 브렌트유, 국제 금, KRX 금현물, 금 괴리율(파생) | yfinance, 네이버(KRX 금현물) |
| 금리·물가 | 미국 기준금리, 미 2년/10년/30년/3개월 국채금리, 미 장단기 금리차(파생), 미국 CPI YoY | FRED, yfinance |
| 금리·물가(한국) | 한국 기준금리, 한국 CPI YoY | 한국은행 ECOS |

파생 지표(`collection/macro/derived.py`):
- 위안/원 = 달러/원 ÷ 달러/위안
- 금 괴리율(%) = (KRX 금현물 원/g − 국제 금 환산 원/g) / 국제 금 환산 원/g × 100
- 미 장단기 금리차(%p) = 미 10년물 − 미 3개월물

---

## 2. 점수 산출 방식

### 2.1 방향성(Direction)

각 팩터는 "클수록 좋음/작을수록 좋음"을 다음 세 가지로 정의한다(`analysis/factors.py`).

| Direction | 의미 | 변환 |
|---|---|---|
| HIGHER_IS_BETTER | 클수록 좋음 | 그대로 순위화 |
| LOWER_IS_BETTER_RECIPROCAL | 작을수록 좋음(배수류: PER, PBR 등) | 1/x 후 순위화. x=0인 행은 순위에서 제외되고 0점 |
| LOWER_IS_BETTER_NEGATED | 작을수록 좋음(증감률류: Debt Growth, ARP) | −x 후 순위화 |

### 2.2 점수 엔진 두 가지

같은 팩터에 대해 두 계열을 병행 산출하고 평균낸다.

**① 퍼센타일 점수 (접미사 `S`)** — `analysis/percentile.py`
모집단 내 순위를 백분위(0~100, 반올림)로 환산. 결측치는 50점(중립).

**② 스탠다드 점수 (접미사 `SS`)** — `analysis/standard_score.py`
모집단의 상위 1%/하위 1% 커트라인 사이에서 값의 선형 위치를 0~100점으로 환산(구간 밖은 0/100 클램프).
극단값(이상치) 영향을 완화하기 위해 퍼센타일과 별도로 병행한다. 결측·모집단 퇴화(커트라인 동일) 시 50점.

모든 팩터·모집단 조합에 대해 `{팩터}TF`(0/1, 데이터 존재 여부) 컬럼도 함께 저장되며,
이는 신뢰도(reliability) 계산에 쓰인다.

### 2.3 모집단 3종

`analysis/score_pipeline.py`가 팩터·종합점수 각각을 3개 모집단 기준으로 계산한다.

| 모집단 | 컬럼 태그 | 설명 |
|---|---|---|
| 통화권 전체 | (없음) | DB(한국/미국)의 최신 run 전체 종목 |
| 섹터 내 | `Sec` | 같은 Sector 값을 가진 종목들 |
| 산업 내 | `Ind` | 같은 Industry 값을 가진 종목들 |

섹터/산업 표본이 `MIN_GROUP_POPULATION`(5개) 미만이거나 그룹값이 결측이면 순위 왜곡을 막기 위해
해당 종목은 중립(50점) 처리한다.

컬럼 네이밍 규칙:
- 팩터 점수: `{이름}S`(전체 퍼센타일) / `{이름}SS`(전체 스탠다드) / `{이름}SecS` / `{이름}SecSS` / `{이름}IndS` / `{이름}IndSS`
- 종합 점수: `{이름}PS`(전체 퍼센타일 계열) / `{이름}SS`(전체 스탠다드 계열) / `{이름}`(전체 평균) — 섹터·산업은 앞에 `Sec`/`Ind` 태그가 붙음 (예: `VscoreSecPS`, `VscoreSec`)
- 최종 종합점수 = (퍼센타일 계열 + 스탠다드 계열) / 2. `Finalscore`는 평균화된 `Vscore`·`Mscore`에서 별도로 재계산.

---

## 3. 팩터 → 종합점수 매핑

### 3.1 1차 스코어링(VC1) — `analysis/basic_score.py`

| 팩터 | 방향 |
|---|---|
| PER, PBR, PSR, PCR, PEGR, EV/EBITDA, EV/Revenue | 작을수록 좋음(역수) |
| ROE, ROA, Dividend Yield, Market Cap, EPSgrowth, Revenuegrowth, Insiderpercent, Institutionpercent, Debt to Equity, EPS, Net Income | 클수록 좋음 |

VC1 = (PER + PBR + PSR + PCR + EV/EBITDA 점수 합) / 5 — 가치주 여부를 보는 가장 기초적인 점수.

### 3.2 2차 스코어링(세부 팩터) — `analysis/detail_score.py`

| 팩터 | 방향 |
|---|---|
| PFCR, Dividend to Income | 작을수록 좋음(역수) |
| 3M/6M/1Y Ratio, 3M/1Y/10D Turnover, 3M/10D Overheat, 3M/1Y Volatility, Buyback Yield, Interest Ratio, Insider Buy Ratio, Asset to Equity, Coverage Ratio, NCAV, Current Ratio, ROC, GPTOA, Asset Turnover, Depreciation Capex Ratio | 클수록 좋음 |
| Debt Growth, ARP | 작을수록 좋음(음수 반전) |

---

## 4. 종합 점수 공식 (`analysis/composite_scores.py`, 가중치는 `analysis/weights.py`)

아래 수식의 팩터 점수는 계열 접미사(S/SS/SecS/…)를 붙여 그대로 대입한다.

| 점수 | 의미 | 수식 |
|---|---|---|
| VC1 | 기본 가치 점수 | (PER + PBR + PSR + PCR + EV/EBITDA) / 5 |
| Vscore | 가치 점수 | (PER + EV/EBITDA×1.2 + PCR×1.1 + PSR×0.9 + Buyback Yield×0.9 + Dividend Yield×0.4) / 5.5 |
| Mscore | 모멘텀 점수 | (3M Ratio×1.2 + 6M Ratio×1.6 + 1Y Ratio) / 3.8 |
| Fscore | 펀더멘털 점수 | (Insider Buy Ratio×0.6 + EPSgrowth×1.4 + Revenuegrowth×1.2 + PEGR) / 4.2 |
| Finalscore | 종합 점수(대표) | Vscore×0.63 + Mscore×0.37 |
| EQC | 이익 품질 점수 | Depreciation Capex Ratio + ARP×1.7 + Coverage Ratio×1.3 |
| Quant score | 퀀트 점수 | (NCAV + GPTOA + Asset Turnover + PFCR) / 4 |
| reliability | 데이터 신뢰도(0~100) | (17개 핵심 팩터 중 데이터 존재 개수) × 100 / 17 |

`reliability` 산출에 쓰이는 17개 핵심 팩터: PER, PBR, PSR, PCR, EV/EBITDA, Debt Growth, ARP,
Insider Buy Ratio, Coverage Ratio, Asset to Equity, NCAV, Current Ratio, ROC, GPTOA, Asset Turnover,
PFCR, Buyback to Income, Depreciation Capex Ratio.

---

## 5. 리스크 플래그 (`analysis/detail_score.py`, 계열 무관 단일 지표)

| 플래그 | O(위험) 조건 |
|---|---|
| Value risk | Debt GrowthS < 15 **또는** PBRS < 40 |
| Growth risk | 순이익 ≤ 0 **또는** EPSgrowthS ≤ 30 **또는** RevenuegrowthS ≤ 30 이면 O (셋 다 충족해야 X) |

(퍼센타일 점수 기준 컬럼을 사용한다. Value risk는 다소 반직관적으로 보일 수 있으나
"낮은 백분위(=위험 신호)일 때 O"로 코드가 그대로 유지되어 있다 — 원본 로직 그대로.)

---

## 6. 섹터/산업 자체 비교 — `analysis/group_summary.py`

각 섹터(산업)의 주요 팩터 **중앙값**을 집계한 뒤, "섹터/산업이 행"인 표를 모집단으로 삼아
동일한 두 점수 엔진(퍼센타일+스탠다드)을 적용한다. 이를 통해 어떤 섹터/산업이 다른 섹터/산업
대비 우위인지 0~100점으로 비교 가능하다. 절대 금액 팩터(Market Cap, Revenue, Operating
Cashflow, Net Income, EPS)는 규모 집계 의미가 약해 제외한다. 표본이 5개 미만인 그룹은 제외한다.

---

## 7. 추천 종목(goodstock) 선정 기준 — `storage/report_export.py`

아래 4개 조건을 **모두** 만족하는 종목만 추천 목록에 포함된다.

| 조건 | 임계값 |
|---|---|
| Finalscore | 해당 run의 상위 10% (90번째 백분위 초과) |
| reliability | 80 초과 |
| Quant score | 50 초과 |
| Fscore | 50 초과 |

결과는 Finalscore 내림차순으로 정렬된다. (매수/매도 권유가 아니라 후보 선별 필터이며,
정성적 조사는 이후 사람이 판단한다 — `CLAUDE.md` 원칙 참고.)

---

## 8. 스탠다드 커트라인 표 — `analysis/standard_data.py`

전체 시장/섹터별/국가별로 10~90% 구간(10%p 단위)의 팩터별 커트라인 값을 별도 테이블로
저장한다(`get_standard_data`). 화면에서 "상위 X%는 어느 정도 값인가"를 참고자료로 보여주기 위함이며,
스탠다드 점수(SS 계열, 상/하위 1% 기준) 산출 로직과는 별개의 참고용 산출물이다.
