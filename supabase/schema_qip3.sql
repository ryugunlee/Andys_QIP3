-- Andy's QIP — Supabase 추가 스키마 (관리자 로그인 + 정성 평가 웹 실행)
--
-- 이 파일은 **Andys_PFmanager와 같은 Supabase 프로젝트**의 SQL Editor에 붙여넣고 실행한다.
-- PFmanager의 supabase/schema.sql이 먼저 실행돼 있어야 한다 — 아래 정책들이 그 파일이 만든
-- auth.users · public.admins · public.is_admin() 을 그대로 재사용하기 때문이다.
-- 여러 번 실행해도 안전하다.
--
-- 계정을 공유하는 이유와 대안은 .claude/DECISIONS.md (2026-09-16 "정성 평가 웹 실행") 참고.
-- QIP3가 만드는 것은 전부 qip_ 접두사를 붙여 PFmanager 테이블과 섞이지 않게 한다.
--
-- 권한은 두 축으로 나뉜다.
--   PFmanager의 allowed_emails = "가입할 수 있는가"  (Auth 훅이 가입 자체를 막는다)
--   여기의 qip_permissions      = "정성 평가를 돌릴 수 있는가, 어느 티어까지"
-- 둘은 독립이다. 가입은 되지만 QIP3 실행은 못 하는 사람을 만들 수 있다.

-- ── 실행 권한 ─────────────────────────────────────────────────
-- user_id가 아니라 email을 키로 쓴다. 상대가 아직 가입하기 전에도 권한을 미리 줄 수 있어야
-- 하기 때문이다(PFmanager의 allowed_emails와 같은 이유·같은 방식).
create table if not exists public.qip_permissions (
    email       text        primary key check (email = lower(email)),
    max_tier    text        not null check (max_tier in ('quick', 'deep')),
    daily_limit integer     not null default 3 check (daily_limit between 1 and 50),
    note        text        check (note is null or length(note) <= 60),
    granted_by  uuid        default auth.uid() references auth.users (id) on delete set null,
    created_at  timestamptz not null default now()
);

-- ── 전역 차단 스위치 ──────────────────────────────────────────
-- 이상 징후가 보일 때 코드 배포 없이 대시보드에서 한 줄로 모든 과금 경로를 끄기 위한 비상 밸브.
-- 행은 언제나 하나뿐이다(id = true 체크가 두 번째 행을 막는다).
create table if not exists public.qip_runtime_flags (
    id      boolean primary key default true check (id),
    enabled boolean not null default true,
    reason  text    check (reason is null or length(reason) <= 200)
);

insert into public.qip_runtime_flags (id, enabled) values (true, true)
on conflict (id) do nothing;

-- ── 실행 요청 이력 ────────────────────────────────────────────
-- 일일 상한의 근거이자 관리자 화면의 "최근 작업" 목록이다.
-- ticker/tier/provider의 check 제약이 GitHub 워크플로로 넘어가는 입력의 1차 방어선이다 —
-- 정규식을 통과하지 못한 값은 애초에 저장되지 않으므로 dispatch까지 갈 수 없다.
create table if not exists public.qip_qualitative_jobs (
    id           bigint      generated always as identity primary key,
    ticker       text        not null check (ticker ~ '^[A-Za-z0-9.]{1,10}$'),
    tier         text        not null check (tier in ('quick', 'deep')),
    provider     text        not null check (provider in ('anthropic', 'compat')),
    requested_by uuid        not null default auth.uid() references auth.users (id) on delete cascade,
    run_url      text        check (run_url is null or run_url like 'https://github.com/%'),
    created_at   timestamptz not null default now()
);

create index if not exists idx_qip_jobs_requester on public.qip_qualitative_jobs (requested_by, created_at desc);

-- ── 권한 판정 함수 ────────────────────────────────────────────
-- security definer로 qip_permissions 자신의 RLS를 우회한다. 그러지 않으면 "내 권한을 보려면
-- 권한 테이블을 읽어야 하는데, 그 테이블은 관리자만 읽는다"는 순환에 빠진다
-- (PFmanager의 is_admin()이 같은 이유로 security definer다).

-- 이 사람이 돌릴 수 있는 최대 티어. 권한이 없으면 null.
create or replace function public.qip_max_tier()
returns text
language sql
stable
security definer
set search_path = public
as $$
    select case
        when public.is_admin() then 'deep'
        else (select max_tier from public.qip_permissions
              where email = lower(coalesce(auth.email(), '')))
    end;
$$;

-- 하루에 몇 건까지 돌릴 수 있는가. 관리자는 상한 없음(null)이다.
create or replace function public.qip_daily_limit()
returns integer
language sql
stable
security definer
set search_path = public
as $$
    select case
        when public.is_admin() then null
        else (select daily_limit from public.qip_permissions
              where email = lower(coalesce(auth.email(), '')))
    end;
$$;

create or replace function public.qip_used_today()
returns integer
language sql
stable
security definer
set search_path = public
as $$
    select count(*)::integer from public.qip_qualitative_jobs
    where requested_by = auth.uid() and created_at >= date_trunc('day', now());
$$;

-- 지금 이 요청을 받아도 되는가. INSERT 정책이 이 함수를 그대로 쓴다 —
-- 즉 상한을 지키는 주체는 화면도 Edge Function도 아니고 데이터베이스다.
-- deep 권한이 없는 사람은 tier='deep' 행을 아예 만들 수 없다.
create or replace function public.qip_can_request(requested_tier text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select
        coalesce((select enabled from public.qip_runtime_flags where id), false)
        and (
            public.qip_max_tier() = 'deep'
            or (public.qip_max_tier() = 'quick' and requested_tier = 'quick')
        )
        and (
            public.qip_daily_limit() is null
            or public.qip_used_today() < public.qip_daily_limit()
        );
$$;

-- 화면과 Edge Function이 로그인 직후 한 번 불러 "무엇을 할 수 있는지"를 받아간다.
-- RLS는 조용히 막기만 할 뿐 이유를 알려주지 않으므로, 사람에게 보여줄 설명은 여기서 만든다.
create or replace function public.qip_my_access()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select jsonb_build_object(
        'is_admin',    public.is_admin(),
        'max_tier',    public.qip_max_tier(),
        'daily_limit', public.qip_daily_limit(),
        'used_today',  public.qip_used_today(),
        'enabled',     coalesce((select enabled from public.qip_runtime_flags where id), false),
        'email',       auth.email()
    );
$$;

-- ── 행 수준 보안 ──────────────────────────────────────────────
alter table public.qip_permissions enable row level security;
alter table public.qip_runtime_flags enable row level security;
alter table public.qip_qualitative_jobs enable row level security;

-- 권한을 나눠 주는 것은 관리자만 할 수 있다.
drop policy if exists "admins manage qip permissions" on public.qip_permissions;
create policy "admins manage qip permissions" on public.qip_permissions
    for all
    using (public.is_admin())
    with check (public.is_admin());

-- 전역 스위치는 누구나 읽고(화면에 "실행 중지 중" 안내를 띄우려면 필요) 관리자만 끈다.
drop policy if exists "read qip flags" on public.qip_runtime_flags;
create policy "read qip flags" on public.qip_runtime_flags
    for select
    using (true);

drop policy if exists "admins update qip flags" on public.qip_runtime_flags;
create policy "admins update qip flags" on public.qip_runtime_flags
    for update
    using (public.is_admin())
    with check (public.is_admin());

-- 자기 요청만 본다. 관리자는 전부 본다(누가 무엇을 돌렸는지 확인해야 하므로).
drop policy if exists "own or all qip jobs" on public.qip_qualitative_jobs;
create policy "own or all qip jobs" on public.qip_qualitative_jobs
    for select
    using (requested_by = auth.uid() or public.is_admin());

-- 핵심 정책: 요청을 만들 수 있는 조건 자체가 권한·티어·일일 상한·전역 스위치다.
-- Edge Function의 사전 검사는 친절한 오류 메시지를 위한 것이고, 실제 방어는 여기다.
drop policy if exists "request within quota" on public.qip_qualitative_jobs;
create policy "request within quota" on public.qip_qualitative_jobs
    for insert
    with check (requested_by = auth.uid() and public.qip_can_request(tier));

-- 실행 링크를 나중에 채워 넣는 UPDATE만 자기 행에 허용한다(Edge Function이 dispatch 직후 수행).
drop policy if exists "annotate own qip job" on public.qip_qualitative_jobs;
create policy "annotate own qip job" on public.qip_qualitative_jobs
    for update
    using (requested_by = auth.uid())
    with check (requested_by = auth.uid());

-- ── 접근 권한 ─────────────────────────────────────────────────
-- 비로그인(anon)에게는 아무것도 주지 않는다. 권한 판정 함수도 로그인한 사람만 부른다.
grant select, insert, update, delete on public.qip_permissions to authenticated;
grant select, update on public.qip_runtime_flags to authenticated;
grant select, insert, update on public.qip_qualitative_jobs to authenticated;
grant usage, select on all sequences in schema public to authenticated;
grant execute on function public.qip_my_access() to authenticated;
grant execute on function public.qip_can_request(text) to authenticated;
