"""경제지표(매크로) 수집 서브패키지.

- indicators.py: 지표 정의 단일 소스 (id/한국어명/단위/소스/심볼/카테고리)
- yahoo_source.py / fred_source.py / naver_gold_source.py: 소스별 수집기
- derived.py: 수집값으로부터 파생 지표(금 괴리율, 장단기 금리차, CPI YoY) 계산

진입점은 최상위 collect_macro.py다.
"""
