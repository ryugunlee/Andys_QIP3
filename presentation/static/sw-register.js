/* 서비스워커 등록. sw.js는 사이트 루트에 있어야 스코프가 전 페이지를 덮으므로,
   페이지 깊이에 따라 달라지는 data-root(body)를 기준으로 경로를 만든다.
   등록에 실패해도 사이트는 그대로 동작한다 — 오프라인 캐시와 설치 기능만 빠진다. */

(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  var root = document.body.getAttribute("data-root") || ".";
  window.addEventListener("load", function () {
    navigator.serviceWorker.register(root + "/sw.js").catch(function () {
      /* 사설 인증서·비HTTPS 등 등록이 막히는 환경에서도 조용히 넘어간다. */
    });
  });
})();
