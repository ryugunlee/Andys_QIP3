# 작업 중 결정사항
코딩 작업 중 주요하거나 다시 찾아보게 될 수도 있는 방향상의 결정사항을 여기에 적고, 그렇게 결정한 이유와 아이디어 등 배경을 작성한다.
AI가 선택지로 제시하여 결정한 이력들도 여기에 남아, 다시 사용된다.
결정 사항이 충돌하는 명령을 하게 될 경우, 참고 자료로서 보여주며 결정 사항에 대해 다시 질문한다.


## AI가 했던 설계 관련 질문 및 결정사항.
클로드 코드가 질문하여 답변한 것들은 여기에 작성된다.

### (2026-07-18) 홈/주식 분석 페이지 뉴스 = Google News RSS("세계 경제") + 연합뉴스 경제 RSS 병합
"홈에서 세계 경제 관련 뉴스 기사 링크와 헤드라인을 수집해 올 수 있을까?"라는 요청에 대해, 이미
설계돼 있던 뉴스 연결 지점(`presentation/models.py`의 `NewsItem`, `news_provider.py`의
`load_news()` placeholder, `_news_section.html`)을 실제로 채우는 작업으로 진행했다.

소스 결정 과정에서 두 가지를 질문하고 답변받았다:
- **소스**: Google News RSS(`news.google.com/rss/search?q=세계+경제&hl=ko&gl=KR&ceid=KR:ko`) +
  연합뉴스 경제 RSS(`yna.co.kr/rss/economy.xml`) 둘 다 병합하기로 결정(다양성 우선, 중복은
  url 기준 제거).
- **Google News RSS 이용약관 리스크**: 실제로 받아보니 저작권 문구가 "개인용 피드리더,
  비상업적 용도로만 사용 가능, 그 외 용도는 명시적으로 금지"였다. 이 프로젝트는 공개
  웹사이트라 문면상 이 범위를 벗어난다는 점을 알렸고, 개발자가 **"그대로 포함"**을 택해
  리스크를 인지한 상태로 진행했다. 헤드라인+링크(+연합뉴스 쪽만 짧은 요약)만 저장하고 본문은
  저장하지 않는 애그리게이터 방식으로 제한했다.
- **자동화**: 매크로 워크플로(`collect-macro.yml`)처럼 매일 GitHub Actions로 수집한다
  (`collect-news.yml`, 22:30 UTC — 같은 macro DB 자산을 다루는 collect-macro.yml 23:30 UTC와
  1시간 간격을 둬 `--clobber` 업로드 경합을 피함). 뉴스는 홈에 바로 반영돼야 하므로, 매크로와
  달리 이 워크플로는 수집 직후 `build_and_commit_site.sh`까지 실행해 사이트도 재빌드한다.
- **노출 개수**: "주요 기사 5개(요약 포함) + 헤드라인만 20개"로 답변받아 2단 레이아웃으로
  구현했다(`presentation/config.py`의 `NEWS_FEATURED_LIMIT`/`NEWS_LIST_LIMIT`).

구현 중 발견한 문제: 연합뉴스 경제 RSS는 게시 빈도가 훨씬 높아(하루 수십 건), 단순 발행일
최신순으로 두 소스를 병합하면 "주요 5개" 자리가 국내 일반 경제 기사(부동산·소송 등)로
채워지고 정작 "세계 경제" 검색 결과(Google News)가 밀려나는 것을 로컬 테스트로 확인했다.
그래서 수집 시점에 `origin`(google_news/yonhap) 태그를 붙이고, 표현 계층
(`news_provider.py`)에서 주요 5개는 Google News를 우선 채우고 부족분만 최신순으로 채우도록
했다 — 그 아래 헤드라인 20개는 원래대로 최신순 병합이라 다양성은 유지된다.

구현 파일: `collection/news/`(constants/parsers/google_news_source/yonhap_source),
`storage/news_repository.py` + `storage/database.py`의 `news` 테이블, `collect_news.py`
진입점, `presentation/repository/news_provider.py`, `presentation/config.py`의 뉴스 노출
개수 상수, `_news_section.html`/`style.css`의 2단 레이아웃, `.github/workflows/collect-news.yml`.
자세한 위치는 STRUCTURE.md 참고.

### (2026-07-17) 모바일 앱 = Flutter가 아니라 PWA. 표현 계층 언어는 TypeScript 유지
"Flutter로 모바일 앱을 만들고, 웹에 설치 링크를 보여 달라"는 요청에 대해 **PWA(홈 화면에 추가)**로
결정했다. Flutter/Dart는 도입하지 않는다.

그렇게 정한 이유:
- **iOS 설치 링크는 Flutter로도 불가능하다.** 아이폰은 App Store/TestFlight를 거치지 않고 설치할
  방법이 없고 둘 다 Apple Developer Program(연 $99)과 심사가 필요하다. 즉 요청의 핵심인
  "웹 들어가서 링크로 설치"를 Flutter는 안드로이드에서만, PWA는 iOS·안드로이드 양쪽에서 달성한다.
  목적 자체를 PWA가 더 정확히 만족한다.
- 안드로이드 APK 직접 배포도 "출처를 알 수 없는 앱" 허용·Play Protect 경고라는 마찰이 있고,
  스토어 등록은 비용·심사·신원확인이 따른다.
- 백엔드 서버가 없어 앱을 만들어도 결국 GitHub Pages의 정적 JSON을 읽는 구조가 된다. 그러면
  웹과 정보 신선도가 같으므로 네이티브의 이점이 크지 않다.
- **CLAUDE.md "데이터 표현 영역은 TypeScript 예정"과 Dart가 충돌**한다. 이 충돌을 질문했고,
  개발자가 "TypeScript 유지(PWA)"를 택했다. 표현 계층 언어를 Python(Jinja)+TS+Dart 셋으로
  늘리지 않는다.

이 선택의 큰 이점: PWA는 **사이트 자체가 앱**이라 앱 전용 코드도, 앱용 JSON API도 없다. 그래서
"앱이 다룰 데이터 범위 = 웹과 동일 전부"(질문에 대한 개발자 답변)가 추가 작업 없이 자동 충족되고,
표현 계층을 고치면 설치된 앱도 그대로 따라 바뀐다. 유지보수 대상이 하나로 유지된다.

한계(알고 선택한 것): 푸시 알림(iOS 제약 큼)·스토어 노출·네이티브 성능은 포기한다. 나중에 이것들이
정말 필요해지면 그때 다시 판단한다 — PWA를 넣었다고 앱 개발이 막히지는 않는다.

구현은 `presentation/builders/pwa.py` + `templates/{manifest.webmanifest,sw.js}.jinja` +
`static/{install,sw-register}.js` (STRUCTURE.md 참고).

### (2026-07-17) 네이버 분기 실적 연동 범위 = 수집+저장+막대그래프 연/분기 토글
PROBLEMS.md #10 해결 시 "분기를 어디까지 연동할지" 질문에, 수집·저장뿐 아니라 종목 상세
페이지 실적 막대그래프에 "연간/분기" 전환 토글까지 붙이기로 결정했다. WiseFn `cF3002.aspx`는
frq=1(분기)로도 연간과 동일한 응답 형태를 주므로 파서를 그대로 재사용했고, 재무 팩터(점수)
계산은 여전히 연간만 쓴다(분기는 표시 전용). 미국(yfinance) 분기는 이번 범위 밖(#23 참고).

### (2026-07-17) 한국 상장 종목은 네이버 전용, yfinance 진입점 가드로 불변식 보장
개발자 지시: "한국 주식은 오직 네이버증권에서만 가져온다(한국 ADR 제외)". 라우팅
(Andys_QIP2.main의 is_korean_market 분기)은 이미 정상이지만, 과거 오염 샘플(#24: .KS 접미사·
영문명 한국 종목)이 다시 섞이지 않도록 yfinance 진입점(get_stock_basic_infomation)에
`is_korean_listed_ticker`(6자리 코드·.KS/.KQ) 가드를 추가해 한국 상장 티커를 건너뛴다.
한국 ADR은 알파벳 심볼이라 가드에 걸리지 않고 정상 수집된다.

### (2026-07-17) docs 재배포 워크플로 트리거 = 수동 + presentation 변경 시 자동
표현 계층만 바꿔도(데이터 재수집 없이) 사이트가 갱신되도록 독립 워크플로
(`.github/workflows/deploy-site.yml`)를 추가했다. 트리거는 workflow_dispatch(수동) +
main push(paths: presentation/**·build_site.py). `build_and_commit_site.sh`가 docs/만
커밋하므로 docs/**는 트리거에서 제외해 무한 루프를 막았다.


### (2026-07-17) 빈 사이트는 산출물이 아니라 실패로 다룬다
`build_site.py`가 데이터 0건일 때 경고만 남기고 빈 사이트를 만들어 CI가 배포본을
덮어쓴 사고(PROBLEMS #26)를 겪고, "데이터가 없으면 빈 사이트를 만드는" 동작 자체를
버그로 판단했다. `EmptySiteError`로 중단하고 종료코드 1로 끝낸다. 대안으로 "CI에서만
커밋을 막는" 방법도 있었으나, 잘못된 산출물을 만든 뒤 거르는 것보다 **애초에 만들지
않는 쪽**이 옳다고 보아 표현 계층 자체에 가드를 넣었다. 부작용: 데이터 없이 사이트
미리보기를 만들 수는 없게 됐다 — 필요해지면 명시적 플래그(`--allow-empty` 등)를 추가한다.

### (2026-07-17) CI 데이터 공급은 data-store 릴리스 씨앗으로 해결 (docs 중심 리팩터링은 기각)
사용자가 "docs를 중심으로 표현 영역을 리팩터링"하는 선택지를 제시했으나, `docs/`는
`presentation/`이 만드는 **생성 산출물**이지 소스가 아니므로 방향이 뒤집힌다고 판단해
현 구조(`presentation/` → `build_site.py` → `docs/`)를 유지하기로 합의했다. 실제 고장은
구조가 아니라 **CI의 데이터 공급 부재**였고, 로컬 DuckDB 3종을 `save_db.sh`로
`data-store` draft 릴리스에 올려 씨앗을 심는 것으로 해결했다. 이후로는 수집 워크플로가
그 위에 누적한다.

### (2026-07-17) 전체 시장 수동 수집은 하지 않고 스케줄(월·화·수·목)에 맡긴다
사용자 요청으로 수동 전체 수집은 실행하지 않기로 했다. 검증은 `deploy-site.yml`
(복원→빌드→커밋 경로)로만 수행했다. 실제로 이 시점에 스케줄 워크플로가 처음으로
깨어나 `Collect Macro`(성공)와 `Collect NYSE`가 자동 실행됐다 — 스케줄 경로가
동작함이 확인됐다.


## 개발자 설계 관련 결정사항.
개발자가 독단적으로 설정한 설계 관련 결정사항은 여기에 작성된다.

### 개별 정보에 관해, 가능한 한 신뢰할 수 있는 정보를 가졌을 곳으로 추측되는 곳에서 가져온다.
한국 주식(KRX,KOSPI,KOSDAQ 등)에 대한 정보는 네이버증권에서 가져온다.
미국 주식(NASDAQ,NYSE 등)에 대한 정보는 YFINANCE에서 가져온다.
그러나 더 신뢰할 수 있는 정보를 가졌을 것으로 추측되는 곳이 있다면, 그곳에서 가져온다.

### 가능한 한 많은 정보를 분기별로 가져온다. 비록 사용하지 않더라도, 보관은 한다.

### (2026-07-17) IMD 순위·전쟁 중인 국가·피델리티 경제사이클은 보류, 6개월 추이는 데스크탑 우측 사이드바로

"IMD 국가경쟁력 순위 / 전쟁 중인 국가 / 피델리티 경제사이클 표시 / 기존 지표 6개월 추이
그래프" 4가지를 요청받아 조사한 결과, 앞의 3개는 무료 실시간 자동 수집 API가 없다는 걸
확인하고 두 가지 대안(수동 큐레이션 vs 위키피디아 등 크롤링)을 제시했다. 개발자가
"둘 다 별로다, 지금은 하지 말고 PROBLEMS.md에 기록만 남겨라. 나중에 AI를 활용하는 방식을
고려하겠다"고 답해 **세 항목 모두 보류**했다(`.claude/PROBLEMS.md` #29 참고).

6개월 추이 그래프는 표시 위치로 "메인페이지에 새 섹션 추가"를, 레이아웃으로는
"데스크탑 우측 사이드바(중앙 정렬 컨테이너 바깥 여백 활용, 모바일에서는 숨김)"를 골랐고,
지표가 25종이라 사이드바가 길어지지 않도록 카테고리(시장 지수/환율/원자재·금/금리·물가)별
접기 토글로 묶기로 했다.

구현: `presentation/models.py`(`EconomicIndicator.category`/`history`),
`presentation/repository/indicators_provider.py`(`_trend_history`),
`presentation/formatters.py`(`sparkline_points` — 빌드 타임 정적 SVG, 별도 JS 없음),
`presentation/builders/index_page.py`(`_group_by_category`),
`presentation/templates/partials/_trend_rail.html`, `base.html`의 `{% block aside %}`,
`static/style.css`의 `.trend-rail`(`@media (min-width: 1560px)`에서만 노출). 상세는
`.claude/STRUCTURE.md` 참고.