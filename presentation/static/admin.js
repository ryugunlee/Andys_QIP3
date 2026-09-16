/**
 * 관리자 화면 동작: 로그인 → 정성 평가 실행 요청 → 최근 실행 상태 → (관리자) 실행 권한 관리.
 *
 * 이 파일은 아무것도 허가하지 않는다. 버튼을 감추거나 비활성화하는 것은 헛걸음을 줄이기 위한
 * 안내이고, 실제 판정은 Supabase의 RLS 정책과 Edge Function이 한다
 * (supabase/schema_qip3.sql, supabase/functions/qualitative-dispatch/index.ts).
 * 그래서 여기서 막힌 것을 개발자도구로 되살려 눌러도 서버가 같은 이유로 거절한다.
 *
 * ES 모듈인 이유는 supabase.js 파일 머리말 참고.
 */

import {
  ApiError,
  callFunction,
  currentUser,
  isConfigured,
  remove,
  select,
  signIn,
  signOut,
  upsert,
} from "./supabase.js";

const PERMISSIONS_TABLE = "qip_permissions";
/* 실행을 요청해도 GitHub이 러너를 붙잡아 목록에 띄우기까지 몇 초 걸린다.
   그 사이 "최근 실행"이 비어 보이지 않도록 두 번만 다시 읽는다(무한 폴링은 하지 않는다). */
const RUN_REFRESH_DELAYS_MS = [4000, 12000];

const TIER_QUICK = "quick";
const TIER_DEEP = "deep";
const PROVIDER_ANTHROPIC = "anthropic";

const RUN_STATE_LABELS = new Map([
  ["queued", "대기 중"],
  ["in_progress", "진행 중"],
  ["requested", "대기 중"],
  ["waiting", "대기 중"],
  ["success", "성공"],
  ["failure", "실패"],
  ["cancelled", "취소됨"],
  ["skipped", "건너뜀"],
  ["timed_out", "시간 초과"],
]);

const console_ = document.getElementById("admin-console");
if (console_) start();

function start() {
  const functionName = console_.dataset.functionName;
  const costHints = JSON.parse(console_.dataset.costHints ?? "{}");
  const view = collectElements();

  if (!isConfigured()) {
    show(view.unconfigured);
    return;
  }

  bindLogin(view, () => enterConsole(view, functionName, costHints));
  bindCostHint(view, costHints);

  currentUser()
    .then((user) => {
      if (user === null) {
        show(view.login);
        return;
      }
      view.userEmail.textContent = user.email;
      enterConsole(view, functionName, costHints);
    })
    .catch(() => show(view.login));
}

function collectElements() {
  const byId = (id) => document.getElementById(id);
  return {
    unconfigured: byId("admin-unconfigured"),
    login: byId("admin-login"),
    loginForm: byId("admin-login-form"),
    loginMessage: byId("admin-login-message"),
    loginSubmit: byId("admin-login-submit"),
    email: byId("admin-email"),
    password: byId("admin-password"),
    console: console_,
    userEmail: byId("admin-user-email"),
    accessSummary: byId("admin-access-summary"),
    logout: byId("admin-logout"),
    runForm: byId("admin-run-form"),
    runMessage: byId("admin-run-message"),
    runSubmit: byId("admin-run-submit"),
    ticker: byId("admin-ticker"),
    deepLabel: byId("admin-tier-deep-label"),
    providerField: byId("admin-provider-field"),
    costHint: byId("admin-cost-hint"),
    runs: byId("admin-runs"),
    refreshRuns: byId("admin-refresh-runs"),
    permissionsPanel: byId("admin-permissions-panel"),
    grantForm: byId("admin-grant-form"),
    grantEmail: byId("admin-grant-email"),
    grantTier: byId("admin-grant-tier"),
    grantLimit: byId("admin-grant-limit"),
    grantNote: byId("admin-grant-note"),
    grantSubmit: byId("admin-grant-submit"),
    permissionMessage: byId("admin-permission-message"),
    permissionRows: byId("admin-permission-rows"),
  };
}

/* ── 화면 전환 ───────────────────────────────────────────────── */

function show(element) {
  if (element) element.hidden = false;
}

function hide(element) {
  if (element) element.hidden = true;
}

function setMessage(element, text, isError) {
  element.textContent = text;
  element.classList.toggle("admin-message--error", Boolean(isError));
}

function describeFailure(failure) {
  return failure instanceof ApiError ? failure.message : "요청을 처리하지 못했습니다.";
}

/* ── 로그인 ─────────────────────────────────────────────────── */

function bindLogin(view, onSuccess) {
  view.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setMessage(view.loginMessage, "");
    view.loginSubmit.disabled = true;
    try {
      const user = await signIn(view.email.value.trim(), view.password.value);
      view.userEmail.textContent = user.email;
      hide(view.login);
      onSuccess();
    } catch (failure) {
      setMessage(view.loginMessage, describeFailure(failure), true);
    } finally {
      view.loginSubmit.disabled = false;
    }
  });

  view.logout.addEventListener("click", async () => {
    await signOut();
    window.location.reload();
  });
}

/* ── 콘솔 ───────────────────────────────────────────────────── */

function enterConsole(view, functionName, costHints) {
  hide(view.login);
  show(view.console);

  view.refreshRuns.addEventListener("click", () => refresh(view, functionName));
  bindRunForm(view, functionName, costHints);
  refresh(view, functionName);
}

/** Edge Function 한 번으로 권한 상태와 최근 실행 목록을 모두 받아 온다. */
async function refresh(view, functionName) {
  try {
    const payload = await callFunction(functionName, "GET");
    applyAccess(view, payload.access);
    renderRuns(view, payload.runs);
  } catch (failure) {
    view.runs.replaceChildren(hintItem(describeFailure(failure)));
  }
}

function applyAccess(view, access) {
  const quota =
    access.daily_limit === null
      ? `오늘 ${access.used_today}건 실행 (상한 없음)`
      : `오늘 ${access.used_today} / ${access.daily_limit}건`;

  if (access.max_tier === null) {
    setMessage(view.accessSummary, "실행 권한이 없습니다. 관리자에게 문의해 주세요.", true);
    view.runSubmit.disabled = true;
  } else {
    const role = access.is_admin ? "관리자" : `${access.max_tier} 권한`;
    setMessage(view.accessSummary, `${role} · ${quota}`);
    view.runSubmit.disabled = false;
  }

  if (!access.enabled) {
    setMessage(view.runMessage, "정성 평가 실행이 일시 중지되어 있습니다.", true);
    view.runSubmit.disabled = true;
  }

  // deep 권한이 없으면 고를 수 없게 한다. 서버도 같은 판단을 다시 한다.
  const deepInput = view.deepLabel.querySelector("input");
  const deepAllowed = access.max_tier === TIER_DEEP;
  deepInput.disabled = !deepAllowed;
  view.deepLabel.classList.toggle("admin-choice--disabled", !deepAllowed);
  if (!deepAllowed && deepInput.checked) {
    view.runForm.querySelector(`input[name="tier"][value="${TIER_QUICK}"]`).checked = true;
  }

  if (access.is_admin) {
    show(view.permissionsPanel);
    bindPermissions(view);
    loadPermissions(view);
  }
}

/* ── 실행 ───────────────────────────────────────────────────── */

function selectedValue(form, name) {
  return form.querySelector(`input[name="${name}"]:checked`)?.value ?? "";
}

function bindCostHint(view, costHints) {
  const update = () => {
    const tier = selectedValue(view.runForm, "tier");
    // deep은 Opus로 재무·주석까지 읽는 티어라 저가 엔드포인트를 섞지 않는다.
    const isDeep = tier === TIER_DEEP;
    if (isDeep) {
      view.runForm.querySelector(`input[name="provider"][value="${PROVIDER_ANTHROPIC}"]`).checked = true;
    }
    view.providerField.disabled = isDeep;
    view.providerField.classList.toggle("admin-choice--disabled", isDeep);
    const provider = selectedValue(view.runForm, "provider");
    const cost = costHints[`${tier}:${provider}`];
    view.costHint.textContent =
      cost === undefined
        ? ""
        : `예상 비용 약 ${cost.toLocaleString("ko-KR")}원 (원문 분량에 따라 달라집니다)`;
  };
  view.runForm.addEventListener("change", update);
  update();
}

function bindRunForm(view, functionName, costHints) {
  view.runForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const ticker = view.ticker.value.trim();
    const tier = selectedValue(view.runForm, "tier");
    const provider = selectedValue(view.runForm, "provider");
    const cost = costHints[`${tier}:${provider}`];
    const price = cost === undefined ? "" : ` 약 ${cost.toLocaleString("ko-KR")}원이 듭니다.`;

    if (!window.confirm(`${ticker} 종목을 ${tier} 티어로 채점합니다.${price}\n실행할까요?`)) return;

    setMessage(view.runMessage, "실행을 요청하는 중…");
    view.runSubmit.disabled = true;
    try {
      const payload = await callFunction(functionName, "POST", { ticker, tier, provider });
      applyAccess(view, payload.access);
      setMessage(view.runMessage, `${ticker} 실행을 요청했습니다. 아래 목록에서 진행 상태를 볼 수 있습니다.`);
      for (const delay of RUN_REFRESH_DELAYS_MS) {
        window.setTimeout(() => refresh(view, functionName), delay);
      }
    } catch (failure) {
      setMessage(view.runMessage, describeFailure(failure), true);
    } finally {
      view.runSubmit.disabled = false;
    }
  });
}

/* ── 최근 실행 ──────────────────────────────────────────────── */

function hintItem(text) {
  const item = document.createElement("li");
  item.className = "admin-hint";
  item.textContent = text;
  return item;
}

function runStateLabel(run) {
  const key = run.status === "completed" ? run.conclusion : run.status;
  return RUN_STATE_LABELS.get(key) ?? key ?? "알 수 없음";
}

function renderRuns(view, runs) {
  if (!runs || runs.length === 0) {
    view.runs.replaceChildren(hintItem("아직 실행 기록이 없습니다."));
    return;
  }

  view.runs.replaceChildren(
    ...runs.map((run) => {
      const item = document.createElement("li");
      item.className = "admin-run";

      const title = document.createElement("span");
      title.className = "admin-run__title";
      title.textContent = run.title ?? "정성 평가";

      const state = document.createElement("span");
      state.className = `admin-run__state admin-run__state--${run.conclusion ?? run.status}`;
      state.textContent = runStateLabel(run);

      const time = document.createElement("time");
      time.className = "admin-run__time";
      time.textContent = formatTime(run.started_at);

      const link = document.createElement("a");
      link.className = "admin-run__link";
      link.href = run.html_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "실행 기록";

      item.append(title, state, time, link);
      return item;
    }),
  );
}

function formatTime(value) {
  if (!value) return "";
  const when = new Date(value);
  return Number.isNaN(when.getTime()) ? "" : when.toLocaleString("ko-KR");
}

/* ── 실행 권한 관리 (관리자 전용) ───────────────────────────── */

function bindPermissions(view) {
  if (view.grantForm.dataset.bound === "true") return; // refresh()가 여러 번 불려도 한 번만 건다.
  view.grantForm.dataset.bound = "true";

  view.grantForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setMessage(view.permissionMessage, "");
    const note = view.grantNote.value.trim();
    const row = {
      email: view.grantEmail.value.trim().toLowerCase(),
      max_tier: view.grantTier.value,
      daily_limit: Number(view.grantLimit.value),
      note: note === "" ? null : note,
    };
    view.grantSubmit.disabled = true;
    try {
      await upsert(PERMISSIONS_TABLE, [row], "email");
      view.grantForm.reset();
      setMessage(view.permissionMessage, `${row.email} 권한을 저장했습니다.`);
      loadPermissions(view);
    } catch (failure) {
      setMessage(view.permissionMessage, describeFailure(failure), true);
    } finally {
      view.grantSubmit.disabled = false;
    }
  });
}

async function loadPermissions(view) {
  try {
    const rows = await select(PERMISSIONS_TABLE, { select: "*", order: "created_at.desc" });
    renderPermissions(view, rows);
  } catch (failure) {
    setMessage(view.permissionMessage, describeFailure(failure), true);
  }
}

function renderPermissions(view, rows) {
  if (rows.length === 0) {
    const empty = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "admin-hint";
    cell.textContent = "등록된 사람이 없습니다. 관리자는 등록 없이도 실행할 수 있습니다.";
    empty.append(cell);
    view.permissionRows.replaceChildren(empty);
    return;
  }

  view.permissionRows.replaceChildren(
    ...rows.map((row) => {
      const tr = document.createElement("tr");
      for (const value of [row.email, row.max_tier, `${row.daily_limit}건/일`, row.note ?? "—"]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        tr.append(cell);
      }

      const actionCell = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "admin-button admin-button--quiet";
      button.textContent = "해제";
      button.addEventListener("click", async () => {
        if (!window.confirm(`${row.email}의 실행 권한을 해제할까요?`)) return;
        try {
          await remove(PERMISSIONS_TABLE, { email: `eq.${row.email}` });
          setMessage(view.permissionMessage, `${row.email} 권한을 해제했습니다.`);
          loadPermissions(view);
        } catch (failure) {
          setMessage(view.permissionMessage, describeFailure(failure), true);
        }
      });
      actionCell.append(button);
      tr.append(actionCell);
      return tr;
    }),
  );
}
