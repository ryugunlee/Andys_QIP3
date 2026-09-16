/**
 * 정성 평가 실행 요청을 받아 GitHub Actions 워크플로를 깨우는 Edge Function.
 *
 * 왜 이 함수가 필요한가 — QIP3 사이트는 GitHub Pages의 정적 파일이라 서버가 없다.
 * 브라우저가 workflow_dispatch를 직접 부르려면 GitHub 토큰이 필요한데, 정적 사이트에 토큰을
 * 두면 소스 보기 한 번으로 누구나 남의 계정 워크플로를 무한히 돌릴 수 있다(= LLM 과금).
 * 그래서 토큰은 이 함수의 시크릿에만 두고, 브라우저는 "실행해 달라"고 부탁만 한다.
 *
 * 권한을 실제로 지키는 것은 이 파일이 아니라 데이터베이스다. jobs 테이블의 INSERT 정책이
 * qip_can_request(tier)를 호출하므로, 티어 권한·일일 상한·전역 스위치를 넘긴 요청은 행 자체가
 * 만들어지지 않는다. 여기의 사전 검사는 사람에게 이유를 설명하기 위한 것이다
 * (supabase/schema_qip3.sql 참고).
 *
 * 라우트:
 *   POST /  {ticker, tier, provider}  → 워크플로 실행, 만들어진 job 행을 돌려준다
 *   GET  /                            → 최근 실행의 진행 상태 (GitHub API를 대신 읽어준다)
 *
 * 필요한 시크릿 (supabase secrets set):
 *   GH_DISPATCH_TOKEN  fine-grained PAT — 대상 저장소의 Actions: Read and write 하나만
 *   GH_REPO            "owner/repo" (예: ryugunlee/Andys_QIP3)
 *   ALLOWED_ORIGIN     이 함수를 부를 수 있는 사이트 출처
 */

const WORKFLOW_FILE = "qualitative-run.yml";
const WORKFLOW_REF = "main";
const GITHUB_API = "https://api.github.com";
const RECENT_RUN_LIMIT = 10;

/** 티커에 셸 메타문자나 공백이 섞이면 워크플로 입력으로 넘기지 않는다(DB 제약과 같은 규칙). */
const TICKER_PATTERN = /^[A-Za-z0-9.]{1,10}$/;
/** 한국 상장 종목은 6자리 숫자다. 미국(EDGAR)은 러너 IP가 차단돼 실행해도 실패한다. */
const KOREAN_TICKER_PATTERN = /^[0-9]{6}$/;

const TIERS = ["quick", "deep"] as const;
const PROVIDERS = ["anthropic", "compat"] as const;

type Tier = (typeof TIERS)[number];
type Provider = (typeof PROVIDERS)[number];

interface DispatchRequest {
  ticker: string;
  tier: Tier;
  provider: Provider;
}

interface Access {
  is_admin: boolean;
  max_tier: Tier | null;
  daily_limit: number | null;
  used_today: number;
  enabled: boolean;
  email: string | null;
}

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const GH_TOKEN = Deno.env.get("GH_DISPATCH_TOKEN") ?? "";
const GH_REPO = Deno.env.get("GH_REPO") ?? "";
const ALLOWED_ORIGIN = Deno.env.get("ALLOWED_ORIGIN") ?? "*";

/**
 * 브라우저(static/supabase.js)는 Authorization 외에 apikey 헤더도 싣는다. 여기 빠진 헤더가 하나라도
 * 있으면 preflight(OPTIONS)가 거절되어 본 요청이 아예 나가지 않는다 — 화면에는 "서버에 연결하지
 * 못했습니다"만 보인다. x-client-info는 supabase-js가 붙이는 헤더라 함께 열어 둔다.
 */
function corsHeaders(): HeadersInit {
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(), "Content-Type": "application/json" },
  });
}

function fail(status: number, message: string): Response {
  return json({ message }, status);
}

/* ── Supabase (요청자의 자격 그대로 사용) ──────────────────────────
   service_role 키는 쓰지 않는다. 사용자의 JWT로 부르기 때문에 RLS가 그대로 적용되고,
   이 함수에 버그가 있어도 사용자가 원래 할 수 있는 것 이상은 일어나지 않는다.

   apikey도 브라우저가 보낸 값(publishable 키)을 그대로 넘긴다. 런타임이 주입하는
   SUPABASE_ANON_KEY는 예전 anon 키라, 대시보드에서 예전 키를 꺼 두면 PostgREST가 거절한다.
   브라우저가 apikey를 싣지 않은 경우에만 그 값으로 대신한다. */

interface Caller {
  token: string;
  apikey: string;
}

function callerOf(request: Request): Caller {
  return {
    token: request.headers.get("Authorization") ?? "",
    apikey: request.headers.get("apikey") ?? SUPABASE_ANON_KEY,
  };
}

function supabaseHeaders(caller: Caller): HeadersInit {
  return {
    apikey: caller.apikey,
    Authorization: caller.token,
    "Content-Type": "application/json",
  };
}

async function fetchAccess(caller: Caller): Promise<Access | null> {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/rpc/qip_my_access`, {
    method: "POST",
    headers: supabaseHeaders(caller),
    body: "{}",
  });
  if (!response.ok) return null;
  return (await response.json()) as Access;
}

interface Denial {
  status: number;
  message: string;
}

/**
 * 실행 권한을 사람이 읽을 수 있는 이유와 함께 확인한다. 통과하면 null.
 * 상한 초과(429)와 권한 없음(403)을 다른 상태로 구분해 화면이 다르게 안내하게 한다.
 */
function denial(access: Access, tier: Tier): Denial | null {
  if (!access.enabled) {
    return { status: 503, message: "정성 평가 실행이 일시 중지되어 있습니다. 관리자에게 문의해 주세요." };
  }
  if (access.max_tier === null) {
    return { status: 403, message: "정성 평가 실행 권한이 없습니다. 관리자에게 문의해 주세요." };
  }
  if (tier === "deep" && access.max_tier !== "deep") {
    return { status: 403, message: "deep 티어 실행 권한이 없습니다. quick으로 실행해 주세요." };
  }
  if (access.daily_limit !== null && access.used_today >= access.daily_limit) {
    return {
      status: 429,
      message: `오늘 실행 한도를 모두 썼습니다. (${access.used_today}/${access.daily_limit}건)`,
    };
  }
  return null;
}

/* ── GitHub ──────────────────────────────────────────────────── */

function githubHeaders(): HeadersInit {
  return {
    Authorization: `Bearer ${GH_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "andys-qip-dispatch",
  };
}

function workflowRunsUrl(): string {
  return `https://github.com/${GH_REPO}/actions/workflows/${WORKFLOW_FILE}`;
}

async function dispatchWorkflow(request: DispatchRequest): Promise<string | null> {
  const response = await fetch(
    `${GITHUB_API}/repos/${GH_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: githubHeaders(),
      body: JSON.stringify({
        ref: WORKFLOW_REF,
        inputs: { ticker: request.ticker, tier: request.tier, provider: request.provider },
      }),
    },
  );
  // 204가 정상이다. 본문이 없으므로 오류일 때만 읽는다.
  if (response.status === 204) return null;
  const detail = await response.text();
  return `GitHub가 실행을 거부했습니다. (${response.status}) ${detail.slice(0, 200)}`;
}

/** 최근 실행 목록. 워크플로 파일 이름으로 좁혀 다른 워크플로가 섞이지 않게 한다. */
async function recentRuns(): Promise<unknown[]> {
  const response = await fetch(
    `${GITHUB_API}/repos/${GH_REPO}/actions/workflows/${WORKFLOW_FILE}/runs?per_page=${RECENT_RUN_LIMIT}`,
    { headers: githubHeaders() },
  );
  if (!response.ok) return [];
  const payload = await response.json();
  return (payload.workflow_runs ?? []).map((run: Record<string, unknown>) => ({
    id: run.id,
    title: run.display_title,
    status: run.status, // queued | in_progress | completed
    conclusion: run.conclusion, // success | failure | cancelled | null
    started_at: run.run_started_at ?? run.created_at,
    html_url: run.html_url,
  }));
}

/* ── 요청 처리 ───────────────────────────────────────────────── */

/** 본문을 신뢰하지 않고 형태를 강제한다. 여기를 통과한 값만 GitHub 입력이 된다. */
function parseRequest(body: unknown): DispatchRequest | string {
  const payload = (body ?? {}) as Record<string, unknown>;
  const ticker = typeof payload.ticker === "string" ? payload.ticker.trim() : "";
  const tier = payload.tier as Tier;
  const provider = payload.provider as Provider;

  if (!TICKER_PATTERN.test(ticker)) {
    return "종목 코드 형식이 올바르지 않습니다. (영문·숫자·점 10자 이내)";
  }
  if (!KOREAN_TICKER_PATTERN.test(ticker)) {
    return "지금은 한국 종목(6자리 숫자)만 웹에서 실행할 수 있습니다. 미국 종목은 Actions 러너 IP가 SEC EDGAR에 차단되어 실패합니다 — 로컬에서 실행해 주세요.";
  }
  if (!TIERS.includes(tier)) return "티어 값이 올바르지 않습니다.";
  if (!PROVIDERS.includes(provider)) return "모델 provider 값이 올바르지 않습니다.";
  return { ticker, tier, provider };
}

/** 요청 이력을 남긴다. 실패하면 그 자체가 권한·상한 위반이다(INSERT 정책이 막은 것). */
async function recordJob(caller: Caller, request: DispatchRequest): Promise<Record<string, unknown> | null> {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/qip_qualitative_jobs`, {
    method: "POST",
    headers: { ...supabaseHeaders(caller), Prefer: "return=representation" },
    body: JSON.stringify([{ ...request, run_url: workflowRunsUrl() }]),
  });
  if (!response.ok) return null;
  const rows = await response.json();
  return rows[0] ?? null;
}

async function handlePost(caller: Caller, body: unknown): Promise<Response> {
  const parsed = parseRequest(body);
  if (typeof parsed === "string") return fail(400, parsed);

  const access = await fetchAccess(caller);
  if (access === null) return fail(401, "로그인이 필요합니다.");

  const refusal = denial(access, parsed.tier);
  if (refusal !== null) return fail(refusal.status, refusal.message);

  // 이력을 먼저 남긴다. 순서를 뒤집으면 워크플로는 돌았는데 기록이 없어 상한을 우회할 수 있다.
  const job = await recordJob(caller, parsed);
  if (job === null) {
    return fail(403, "요청이 거부되었습니다. 권한 또는 실행 한도를 확인해 주세요.");
  }

  const error = await dispatchWorkflow(parsed);
  if (error !== null) return fail(502, error);

  return json({ job, access: { ...access, used_today: access.used_today + 1 } });
}

async function handleGet(caller: Caller): Promise<Response> {
  const access = await fetchAccess(caller);
  if (access === null) return fail(401, "로그인이 필요합니다.");
  return json({ access, runs: await recentRuns() });
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });

  const caller = callerOf(request);
  if (caller.token === "") return fail(401, "로그인이 필요합니다.");
  if (GH_TOKEN === "" || GH_REPO === "") {
    return fail(500, "서버 설정이 끝나지 않았습니다. (GH_DISPATCH_TOKEN / GH_REPO)");
  }

  if (request.method === "GET") return await handleGet(caller);
  if (request.method !== "POST") return fail(405, "지원하지 않는 요청입니다.");

  const body = await request.json().catch(() => null);
  return await handlePost(caller, body);
});
