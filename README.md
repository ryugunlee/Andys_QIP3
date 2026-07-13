# Andys_QIP3

주식 투자 보조 프로그램. 투자자가 스스로 판단할 수 있도록 정량 분석 정보를 제공한다 (매수·매도 권유 없음).

## 구성

1. **데이터 수집** (`collection/`) — yfinance·FinanceDataReader로 종목 데이터 수집, 약 60개 지표 계산
2. **데이터 분석** (`analysis/`) — 백분위 기반 점수화 (Vscore/Mscore/Fscore/Finalscore 등), 우량주 선별
3. **데이터 표현** (`presentation/`) — 분석 산출물을 정적 웹사이트로 생성 (GitHub Pages 배포)

## 사용법

```bash
pip install -r requirements.txt

# 1) 시장별 수집·분석 (시장마다 실행, 결과는 qipinfos/에 저장)
python Andys_QIP2.py   # 예: KOSPI, KOSDAQ, NASDAQ, NYSE

# 2) 정적 사이트 생성 (모든 시장 갱신 후 1회)
python build_site.py   # qipinfos/ → docs/

# 3) 로컬 미리보기
python -m http.server -d docs 8000
```

## 배포 (GitHub Pages)

`docs/`를 커밋한 뒤 저장소 **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`** 로 설정한다.
데이터 갱신 시 `build_site.py` 재실행 후 `docs/`를 다시 커밋하면 자동 반영된다.

## 페이지 구조

- `/` — 세계 경제 지표(준비 중)·추천 종목·뉴스(준비 중)
- `/stocks/` — 검색, 추천 종목, 한국/미국 시가총액 상위
- `/stocks/{티커}.html` — 종목별 상세 지표(밸류에이션·수익성·성장성·재무 건전성·주주환원·모멘텀·기술 신호·종합 점수)
