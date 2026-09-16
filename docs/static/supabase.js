/**
 * Supabase(로그인 + REST + Edge Function)를 브라우저에서 직접 부르는 얇은 계층.
 *
 * 관리자 화면(admin/index.html)에서만 쓴다. 공개 페이지는 이 파일을 읽지 않는다.
 *
 * 이 파일만 ES 모듈인 이유 — 나머지 static/*.js(search·install·sw-register)는 페이지를
 * 꾸미는 IIFE 스크립트라 전역 하나 없이 끝나지만, 여기는 접속 정보(config.js)를 import 해야
 * 하고 관리자 화면이 여러 모듈로 나뉜다. window에 전역을 얹는 대신 모듈 경계로 캡슐화한다.
 * 구현 자체는 Andys_PFmanager의 public/supabase.js에서 이 프로젝트가 쓰는 부분만 가져온 것이라,
 * 두 저장소의 인증 코드를 나란히 놓고 비교할 수 있게 모양도 그대로 두었다.
 *
 * 접근 권한은 전적으로 DB의 RLS 정책이 지킨다(supabase/schema_qip3.sql).
 * 여기 실리는 anon(publishable) 키는 공개되어도 되는 값이며, 그 자체로는 아무것도 못 한다.
 */

import { SUPABASE_ANON_KEY, SUPABASE_URL } from "./config.js";

const SESSION_KEY = "qip.session";
const REFRESH_MARGIN_SECONDS = 60; // 만료 직전이면 미리 갱신한다.

/** 원문 오류 메시지를 사용자에게 보여줄 한국어로 바꾼다. */
const MESSAGES = new Map([
  ["invalid login credentials", "이메일 또는 비밀번호가 올바르지 않습니다."],
  ["email not confirmed", "메일 인증이 아직 끝나지 않았습니다. 받은 메일의 링크를 눌러 주세요."],
  ["anonymous sign-ins are disabled", "이메일과 비밀번호를 입력해 주세요."],
]);

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isConfigured() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

/* ── 세션 보관 ───────────────────────────────────────────────── */

function readSession() {
  try {
    return JSON.parse(window.localStorage.getItem(SESSION_KEY) ?? "null");
  } catch {
    return null;
  }
}

function writeSession(session) {
  try {
    if (session === null) window.localStorage.removeItem(SESSION_KEY);
    else window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // 시크릿 모드 등에서 저장이 막히면 이번 탭에서만 로그인 상태가 유지된다.
  }
}

/** GoTrue 응답을 저장 가능한 형태로 줄인다. */
function toSession(payload) {
  return {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    expires_at: payload.expires_at ?? Math.floor(Date.now() / 1000) + (payload.expires_in ?? 3600),
    user: { id: payload.user.id, email: payload.user.email },
  };
}

/* ── 인증 ───────────────────────────────────────────────────── */

/**
 * 로그인. 계정은 Andys_PFmanager와 같은 Supabase 프로젝트를 쓰므로 그쪽 계정이 그대로 통한다.
 * 회원가입 기능은 두지 않는다 — 가입은 PFmanager 쪽 허용 목록이 관리한다.
 */
export async function signIn(email, password) {
  const payload = await authRequest("/auth/v1/token?grant_type=password", { email, password });
  const session = toSession(payload);
  writeSession(session);
  return session.user;
}

export async function signOut() {
  const session = readSession();
  writeSession(null);
  if (session === null) return;
  // 서버 쪽 토큰 폐기가 실패해도 로컬 로그아웃은 이미 끝났다.
  await authRequest("/auth/v1/logout", {}, session.access_token).catch(() => undefined);
}

/** 저장된 세션의 사용자. 없거나 갱신에 실패하면 null. */
export async function currentUser() {
  const session = await freshSession();
  return session?.user ?? null;
}

/** 만료가 임박했으면 갱신한 세션을 돌려준다. */
async function freshSession() {
  const session = readSession();
  if (session === null) return null;
  if (session.expires_at - REFRESH_MARGIN_SECONDS > Date.now() / 1000) return session;

  try {
    const payload = await authRequest("/auth/v1/token?grant_type=refresh_token", {
      refresh_token: session.refresh_token,
    });
    const refreshed = toSession(payload);
    writeSession(refreshed);
    return refreshed;
  } catch (failure) {
    // 네트워크 문제라면 세션을 버리지 않는다. 거부당한 경우에만 로그아웃한다.
    if (failure instanceof ApiError && failure.status !== 0) writeSession(null);
    return null;
  }
}

async function authRequest(path, body, token) {
  return send(path, {
    method: "POST",
    headers: {
      apikey: SUPABASE_ANON_KEY,
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

/* ── 데이터 (PostgREST) ──────────────────────────────────────── */

/** @param {Record<string, string>} query PostgREST 질의 (예: {select: "*", order: "created_at.desc"}) */
export function select(table, query) {
  return rest("GET", table, query);
}

/** 있으면 고치고 없으면 넣는다. onConflict는 유일 제약을 이루는 컬럼이다. */
export function upsert(table, rows, onConflict) {
  return rest(
    "POST",
    table,
    { on_conflict: onConflict },
    rows,
    "resolution=merge-duplicates,return=representation",
  );
}

/** 지운 행을 돌려받는다. 비어 있으면 없거나 권한이 없다는 뜻이다. */
export function remove(table, query) {
  return rest("DELETE", table, query, undefined, "return=representation");
}

async function rest(method, table, query, body, prefer) {
  const session = await freshSession();
  if (session === null) throw new ApiError(401, "로그인이 필요합니다.");

  const search = new URLSearchParams(query).toString();
  return send(`/rest/v1/${table}${search ? `?${search}` : ""}`, {
    method,
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${session.access_token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(prefer ? { Prefer: prefer } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/* ── Edge Function ───────────────────────────────────────────── */

/**
 * Edge Function을 부른다. 함수 URL은 Project URL에서 나오므로 따로 설정하지 않는다.
 * @param {string} name 함수 이름
 * @param {"GET"|"POST"} method
 * @param {unknown} [body]
 */
export async function callFunction(name, method, body) {
  const session = await freshSession();
  if (session === null) throw new ApiError(401, "로그인이 필요합니다.");

  return send(`/functions/v1/${name}`, {
    method,
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${session.access_token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/* ── 공통 요청 처리 ─────────────────────────────────────────── */

async function send(path, options) {
  if (!isConfigured()) {
    throw new ApiError(0, "Supabase 접속 정보가 설정되지 않았습니다. README를 참고해 주세요.");
  }

  let response;
  try {
    response = await fetch(`${SUPABASE_URL}${path}`, options);
  } catch {
    throw new ApiError(0, offlineMessage());
  }

  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, describe(payload, response.status));
  return payload;
}

function offlineMessage() {
  return navigator.onLine
    ? "서버에 연결하지 못했습니다."
    : "오프라인 상태입니다. 연결을 확인해 주세요.";
}

/** GoTrue·PostgREST·Edge Function은 오류 모양이 서로 다르다. 한곳에서 흡수한다. */
function describe(payload, status) {
  const raw =
    payload?.error_description ?? payload?.msg ?? payload?.message ?? payload?.error ?? null;
  if (typeof raw === "string" && raw !== "") {
    return MESSAGES.get(raw.toLowerCase()) ?? raw;
  }
  if (status === 401) return "로그인이 필요합니다.";
  if (status === 403) return "권한이 없습니다.";
  return `요청을 처리하지 못했습니다. (${status})`;
}
