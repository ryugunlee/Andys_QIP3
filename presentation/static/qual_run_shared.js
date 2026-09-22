/**
 * 정성 평가 "실행 요청" 화면 두 곳(관리자 콘솔 admin.js, 종목 상세 페이지 위젯
 * qual_run_widget.js)이 함께 쓰는 계산 로직.
 *
 * DOM을 직접 만들지 않는다 — 두 화면의 마크업이 서로 달라서(admin은 티커 입력칸과
 * 권한 관리 표까지 있고, 위젯은 이 페이지의 티커로 고정된 실행 폼뿐이다) 여기서는
 * "같은 값이면 같은 결과가 나와야 하는" 순수 계산만 모은다. 실제 권한 판정은 어차피
 * Supabase RLS가 다시 하므로(admin.js 머리말 참고), 여기 로직은 편의를 위한 것이다.
 */

export const TIER_QUICK = "quick";
export const TIER_DEEP = "deep";
export const PROVIDER_ANTHROPIC = "anthropic";

export function selectedValue(form, name) {
  return form.querySelector(`input[name="${name}"]:checked`)?.value ?? "";
}

/** deep 권한이 없으면 고를 수 없게 한다. 서버(RLS)도 같은 판단을 다시 한다 — 여긴 안내일 뿐. */
export function applyDeepGating(form, deepLabel, deepAllowed) {
  const deepInput = deepLabel.querySelector("input");
  deepInput.disabled = !deepAllowed;
  deepLabel.classList.toggle("admin-choice--disabled", !deepAllowed);
  if (!deepAllowed && deepInput.checked) {
    form.querySelector(`input[name="tier"][value="${TIER_QUICK}"]`).checked = true;
  }
}

export function costHintFor(costHints, tier, provider) {
  return costHints[`${tier}:${provider}`];
}

export function costHintText(cost) {
  return cost === undefined
    ? ""
    : `예상 비용 약 ${cost.toLocaleString("ko-KR")}원 (원문 분량에 따라 달라집니다)`;
}

export function confirmRunPrompt(ticker, tier, cost) {
  const price = cost === undefined ? "" : ` 약 ${cost.toLocaleString("ko-KR")}원이 듭니다.`;
  return `${ticker} 종목을 ${tier} 티어로 채점합니다.${price}\n실행할까요?`;
}

export function quotaText(access) {
  return access.daily_limit === null
    ? `오늘 ${access.used_today}건 실행 (상한 없음)`
    : `오늘 ${access.used_today} / ${access.daily_limit}건`;
}
