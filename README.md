# Andys_QIP3

주식 투자 보조 프로그램. 투자자가 스스로 판단할 수 있도록 정량 분석 정보를 제공한다 (매수·매도 권유 없음).

## 구성

1. **데이터 수집** (`collection/`) — 미국 등 해외는 yfinance, 한국은 네이버증권으로 수집, 약 60개 지표 계산
2. **데이터 분석** (`analysis/`) — 백분위 기반 점수화 (Vscore/Mscore/Fscore/Finalscore 등), 우량주 선별
3. **데이터 표현** (`presentation/`) — 분석 산출물을 정적 웹사이트로 생성 (GitHub Pages 배포)

수집·분석 결과는 DuckDB(`qipinfos/andys_qip.duckdb`)에 저장된다 (`storage/`).

## 사용법

```bash
pip install -r requirements.txt

# 1) 시장별 수집·분석 (시장마다 실행, 결과는 qipinfos/andys_qip.duckdb에 저장)
python Andys_QIP2.py   # 예: KOSPI, KOSDAQ, NASDAQ, NYSE

# 2) 정적 사이트 생성 (모든 시장 갱신 후 1회, DuckDB → docs/)
python build_site.py   # DB가 없으면 과거 CSV 산출물로 폴백

# 3) 로컬 미리보기
python -m http.server -d docs 8000
```

## 배포 (GitHub Pages)

`docs/`를 커밋한 뒤 저장소 **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`** 로 설정한다.
데이터 갱신 시 `build_site.py` 재실행 후 `docs/`를 다시 커밋하면 자동 반영된다.

## 페이지 구조

- `/` — 세계 경제 지표(우측: 데스크탑 넓은 화면에서 카테고리별 6개월 추이 사이드바)·추천 종목·세계 경제 뉴스(주요 기사 5개 + 헤드라인 20개)
- `/stocks/` — 검색, 추천 종목, 한국/미국 시가총액 상위
- `/stocks/{티커}.html` — 종목별 상세 지표(밸류에이션·수익성·성장성·재무 건전성·주주환원·모멘텀·기술 신호·종합 점수)
- `/sectors/` — 섹터·산업 비교
- `/admin/` — 관리자 화면(로그인 필요). 정성 평가를 종목 단위로 실행하고 실행 권한을 관리한다


## 관리자 화면 설정 (정성 평가 웹 실행)

`/admin/`에서 종목을 골라 정성 평가(`grade_qualitative.py extract` + `grade`)를 실행할 수 있다.
실행은 브라우저가 아니라 GitHub Actions(`qualitative-run.yml`)가 하고, 누가 실행할 수 있는지는
Supabase가 판정한다. 아래 설정을 마치기 전까지 `/admin/`은 "설정이 끝나지 않았습니다"만 보여준다.

```
브라우저(로그인) → Supabase Edge Function(권한 확인 + GitHub 토큰 보관)
                 → GitHub Actions(채점·판정·사이트 재빌드) → 종목 상세 페이지 등급카드
```

GitHub 토큰을 Edge Function 안에만 두는 것이 이 구조의 핵심이다. 정적 사이트에 토큰을 실으면
소스 보기만으로 누구나 워크플로를 돌려 LLM 비용을 태울 수 있다.

### 1. Supabase — 스키마 올리기

계정은 [Andys_PFmanager](https://github.com/Markias21/Andys_PFmanager)와 **같은 프로젝트**를 쓴다.
그래야 이메일·비밀번호와 관리자 목록이 두 앱에서 같아진다.

1. PFmanager의 `supabase/schema.sql`이 이미 실행된 프로젝트를 연다.
2. **SQL Editor**에 이 저장소의 [`supabase/schema_qip3.sql`](supabase/schema_qip3.sql)을 붙여넣고 실행한다.
   여러 번 실행해도 안전하다.
3. 접속 정보 두 개를 적어 둔다.
   - **Project URL** (`https://<프로젝트>.supabase.co`) — Integrations → Data API
   - **Publishable key** (`sb_publishable_…`) — Settings → API Keys

> publishable 키는 브라우저에 실려 공개되는 값이라 `docs/static/config.js`로 커밋된다.
> 남의 데이터를 막는 것은 키가 아니라 RLS 정책이다. `service_role`·`secret` 키는 쓰지 않는다.

내가 관리자인지 확인하려면 SQL Editor에서:

```sql
select * from public.admins;
-- 비어 있으면 (PFmanager README와 같은 방법으로) 직접 넣는다
insert into public.admins (user_id)
select id from auth.users where email = '내이메일@example.com';
```

### 2. GitHub — 워크플로를 깨울 토큰 만들기

[Fine-grained personal access token](https://github.com/settings/personal-access-tokens/new)을 만든다.
이 저장소를 소유한 계정으로 만들어야 한다.

- **Repository access**: Only select repositories → 이 저장소 하나
- **Permissions**: Repository permissions → **Actions: Read and write** (이것 하나면 된다)
- **Expiration**: 만료일을 반드시 둔다 (만료되면 실행 버튼이 502로 실패한다 — 그때 다시 만들어 4번을 반복)

### 3. GitHub — 저장소 시크릿 등록

Settings → Secrets and variables → Actions → New repository secret.

| 이름 | 값 | 쓰는 곳 |
|---|---|---|
| `SUPABASE_URL` | 1번의 Project URL | 사이트 빌드 (`config.js` 생성) |
| `SUPABASE_ANON_KEY` | 1번의 publishable 키 | 사이트 빌드 |
| `SUPABASE_ACCESS_TOKEN` | [계정 토큰](https://supabase.com/dashboard/account/tokens) (`sbp_…`) | Edge Function 배포 |
| `SUPABASE_PROJECT_REF` | Project URL의 `https://<여기>.supabase.co` | Edge Function 배포 |
| `DEEPSEEK_API_KEY` | DeepSeek API 키 | quick 티어 채점 |
| `ANTHROPIC_API_KEY` | Anthropic API 키 | deep 티어 채점 |
| `DART_API_KEY` | (이미 등록돼 있다) | 사업보고서 수집 |

`DEEPSEEK_API_KEY`·`ANTHROPIC_API_KEY`는 `qualitative-run.yml`에서만 쓴다. 정기 실행
(`qualitative-weekly.yml`)은 지금도 AI 키 없이 도는 무과금 경로다 — 과금 가능한 경로를 하나로
한정해 두었다.

### 4. Supabase — Edge Function 시크릿 등록과 배포

Dashboard → Edge Functions → Secrets 에 세 개를 넣는다.

| 이름 | 값 |
|---|---|
| `GH_DISPATCH_TOKEN` | 2번에서 만든 토큰 |
| `GH_REPO` | `소유자/저장소` (예: `ryugunlee/Andys_QIP3`) |
| `ALLOWED_ORIGIN` | 사이트 출처 (예: `https://ryugunlee.github.io`) |

그다음 Actions에서 **Deploy Edge Functions** 워크플로를 수동 실행한다
(`supabase/functions/**`를 고쳐 push해도 자동 실행된다).

### 5. 사이트 재배포와 확인

Actions에서 **Deploy Site**를 수동 실행한다. 빌드 로그에
`[presentation] Supabase 접속 정보 기록: https://…`가 찍히면 `config.js`가 제대로 들어간 것이다.

배포 후 `/admin/`에 접속해 로그인하고, 종목 코드(예: `005930`)를 넣어 실행해 본다.
2~4분 뒤 "최근 실행"이 성공으로 바뀌고, 사이트가 다시 빌드되면 종목 상세 페이지에 등급카드가 나온다.

### 6. 다른 사람에게 실행 권한 주기

권한은 두 축으로 나뉜다.

1. **가입 자격** — PFmanager의 허용 이메일 목록(`allowed_emails`). 여기에 없는 이메일은 아예 가입되지 않는다.
2. **실행 권한** — QIP3 관리자 화면의 "실행 권한 관리"(`qip_permissions`). 최대 티어(quick/deep)와
   일일 상한을 사람마다 정한다.

아직 계정이 없는 사람이라면 1번(PFmanager 쪽)을 먼저 해야 한다. 관리자는 `qip_permissions`에
등록하지 않아도 deep까지 상한 없이 실행할 수 있다.

### 7. 비상 정지

과금을 즉시 멈추려면 SQL Editor에서 한 줄이면 된다. 배포가 필요 없고, 이미 로그인한 사람도
다음 요청부터 바로 막힌다.

```sql
update public.qip_runtime_flags set enabled = false, reason = '점검 중';
```

### 알려진 제약

- **미국 종목은 웹에서 실행할 수 없다.** Actions 러너의 IP가 SEC EDGAR에 차단돼 있다.
  관리자 화면이 실행 전에 막는다. 미국 종목은 로컬에서 `grade_qualitative.py`로 실행한다.
- **PFmanager에 로그인해도 여기서는 다시 로그인해야 한다.** 두 사이트의 도메인이 달라
  브라우저가 세션을 공유하지 않는다. 계정(이메일·비밀번호)은 같다.
- **실행 로그는 실시간으로 보이지 않는다.** "최근 실행"의 상태(대기/진행/성공/실패)만 보이고,
  자세한 로그는 옆의 "실행 기록" 링크로 GitHub Actions에서 본다.
