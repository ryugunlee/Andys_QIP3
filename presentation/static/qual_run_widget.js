/**
 * 종목 상세 페이지에서 정성 평가를 바로 실행하는 위젯 (한국 종목 페이지에만 실린다 —
 * builders/detail_pages.py + environment.py의 is_kr_market 게이트, 템플릿은
 * partials/_qualitative_run_panel.html).
 *
 * 로그인 안 한 방문자에게는 이 위젯을 아예 보여주지 않는다. "숨긴다"는 편의일 뿐이고,
 * 실제 판정은 관리자 화면과 똑같이 Supabase RLS가 한다(supabase/schema_qip3.sql).
 * 계산 로직(티어 게이팅·비용 안내)은 admin.js와 qual_run_shared.js를 함께 쓴다 —
 * 같은 규칙을 두 곳에 따로 구현하지 않기 위해서다.
 */

import { ApiError, callFunction, currentUser, isConfigured } from "./supabase.js";
import {
  PROVIDER_ANTHROPIC,
  TIER_DEEP,
  applyDeepGating,
  confirmRunPrompt,
  costHintFor,
  costHintText,
  quotaText,
  selectedValue,
} from "./qual_run_shared.js";

const panel = document.getElementById("qual-run-panel");
if (panel) start();

function start() {
  if (!isConfigured()) return; // 접속 정보가 없는 사이트에서는 조용히 아무것도 하지 않는다.

  const ticker = panel.dataset.ticker;
  const functionName = panel.dataset.functionName;
  const costHints = JSON.parse(panel.dataset.costHints ?? "{}");
  const view = collectElements();

  bindCostHint(view, costHints);
  bindRunForm(view, functionName, costHints, ticker);

  currentUser()
    .then((user) => {
      if (user === null) return; // 로그인 안 했으면 위젯을 보여줄 이유가 없다.
      return refreshAccess(view, functionName);
    })
    .catch(() => undefined);
}

function collectElements() {
  const byId = (id) => document.getElementById(id);
  return {
    panel,
    denied: byId("qualrun-denied"),
    form: byId("qualrun-form"),
    quota: byId("qualrun-quota"),
    deepLabel: byId("qualrun-tier-deep-label"),
    providerField: byId("qualrun-provider-field"),
    costHint: byId("qualrun-cost-hint"),
    message: byId("qualrun-message"),
    submit: byId("qualrun-submit"),
  };
}

function describeFailure(failure) {
  return failure instanceof ApiError ? failure.message : "요청을 처리하지 못했습니다.";
}

function setMessage(element, text, isError) {
  element.textContent = text;
  element.classList.toggle("admin-message--error", Boolean(isError));
}

async function refreshAccess(view, functionName) {
  try {
    const payload = await callFunction(functionName, "GET");
    applyAccess(view, payload.access);
  } catch {
    // 조용히 포기한다 — 실행 버튼이 안 나타날 뿐, 이 페이지 본래 목적(분석 열람)에는
    // 지장이 없어야 한다.
  }
}

function applyAccess(view, access) {
  view.panel.hidden = false;

  if (access.max_tier === null) {
    view.denied.hidden = false;
    view.form.hidden = true;
    return;
  }

  view.denied.hidden = true;
  view.form.hidden = false;
  view.quota.textContent = quotaText(access);
  applyDeepGating(view.form, view.deepLabel, access.max_tier === TIER_DEEP);

  if (!access.enabled) {
    setMessage(view.message, "정성 평가 실행이 일시 중지되어 있습니다.", true);
    view.submit.disabled = true;
  } else {
    view.submit.disabled = false;
  }
}

function bindCostHint(view, costHints) {
  const update = () => {
    const tier = selectedValue(view.form, "tier");
    // deep은 Opus로 재무·주석까지 읽는 티어라 저가 엔드포인트를 섞지 않는다.
    const isDeep = tier === TIER_DEEP;
    if (isDeep) {
      view.form.querySelector(`input[name="provider"][value="${PROVIDER_ANTHROPIC}"]`).checked = true;
    }
    view.providerField.disabled = isDeep;
    view.providerField.classList.toggle("admin-choice--disabled", isDeep);
    const provider = selectedValue(view.form, "provider");
    view.costHint.textContent = costHintText(costHintFor(costHints, tier, provider));
  };
  view.form.addEventListener("change", update);
  update();
}

function bindRunForm(view, functionName, costHints, ticker) {
  view.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const tier = selectedValue(view.form, "tier");
    const provider = selectedValue(view.form, "provider");
    const cost = costHintFor(costHints, tier, provider);

    if (!window.confirm(confirmRunPrompt(ticker, tier, cost))) return;

    setMessage(view.message, "실행을 요청하는 중…");
    view.submit.disabled = true;
    try {
      const payload = await callFunction(functionName, "POST", { ticker, tier, provider });
      applyAccess(view, payload.access);
      setMessage(view.message, "실행을 요청했습니다. 진행 상태는 관리자 화면의 '최근 실행'에서 볼 수 있습니다.");
    } catch (failure) {
      setMessage(view.message, describeFailure(failure), true);
    } finally {
      view.submit.disabled = false;
    }
  });
}
