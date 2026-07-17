/* 앱 설치 유도 UI: 설치 가능한 환경에서만 헤더에 "앱 설치" 버튼을 띄운다.
   - 안드로이드·데스크톱 크롬 계열: beforeinstallprompt를 붙잡아 두고, 버튼을 누르면
     브라우저 기본 설치창을 연다.
   - iOS 사파리: 설치 API가 없어 "공유 → 홈 화면에 추가" 수동 안내를 대신 띄운다.
   이미 설치해 standalone으로 열린 경우에는 어느 쪽도 띄우지 않는다. */

(function () {
  "use strict";

  var cta = document.querySelector(".install-cta");
  if (!cta) return;

  var button = cta.querySelector(".install-button");
  var guide = cta.querySelector(".install-guide");
  var closeButton = cta.querySelector(".install-guide-close");
  if (!button || !guide || !closeButton) return;

  var deferredPrompt = null; // beforeinstallprompt 이벤트 (한 번만 쓸 수 있다)

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function isIos() {
    if (/iPhone|iPad|iPod/i.test(window.navigator.userAgent)) return true;
    /* iPadOS 13+는 데스크톱 사파리로 위장하므로 터치 지원 여부로 가려낸다. */
    return (
      window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1
    );
  }

  function toggleGuide(open) {
    guide.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function onButtonClick() {
    if (!deferredPrompt) {
      /* 안내만 가능한 환경(iOS). 여기 오는 경우는 iOS뿐이다 — 아래 노출 조건 참고. */
      toggleGuide(guide.hidden);
      return;
    }
    var prompt = deferredPrompt;
    deferredPrompt = null; // 한 번 쓴 이벤트는 재사용할 수 없다
    prompt.prompt();
    /* 설치하든 거절하든 이번 방문에는 더 띄울 수 없으므로 버튼을 내린다.
       거절한 경우 브라우저가 다음 방문에서 이벤트를 다시 준다. */
    prompt.userChoice.then(function () {
      cta.hidden = true;
    });
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault(); // 브라우저 기본 배너 대신 헤더 버튼으로 유도
    deferredPrompt = event;
    cta.hidden = false;
  });

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    cta.hidden = true;
  });

  button.addEventListener("click", onButtonClick);
  closeButton.addEventListener("click", function () {
    toggleGuide(false);
  });

  document.addEventListener("click", function (event) {
    if (!cta.contains(event.target)) toggleGuide(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") toggleGuide(false);
  });

  /* iOS는 beforeinstallprompt가 없으므로 안내 버튼을 직접 띄운다. */
  if (isIos() && !isStandalone()) cta.hidden = false;
})();
