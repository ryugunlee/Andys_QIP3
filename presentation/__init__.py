"""데이터 표현 계층: 분석 산출물을 정적 웹사이트로 렌더링하는 패키지.

- repository/ : 분석 산출물(CSV, 추후 DB)을 표현용 모델로 읽어오는 데이터 어댑터
- metrics.py  : 화면에 보여줄 지표의 메타데이터(라벨/포맷/그룹) 단일 소스
- builders/   : 페이지 종류별 HTML 생성기
- templates/  : Jinja2 템플릿, static/ : CSS·검색 JS

진입점은 최상위 build_site.py 스크립트다.
"""
