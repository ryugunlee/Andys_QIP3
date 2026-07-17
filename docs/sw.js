/* Andy's QIP 서비스워커 — 앱 셸 오프라인 캐시 + PWA 설치 조건(fetch 핸들러) 충족.
   search.js/charts.js와 같이 외부 라이브러리 없는 바닐라 자체구현.

   이 파일은 build_site.py가 생성한다. 직접 고치지 말고
   presentation/templates/sw.js.jinja를 고칠 것.

   캐싱 전략 — 분석 결과가 매일 갱신되므로 "낡은 데이터를 보여주지 않는 것"이 최우선이다.
   - 페이지 이동:  네트워크 우선 → 실패 시 캐시 → 그래도 없으면 offline.html로 이동
   - data/*.json: 네트워크 우선 → 실패 시 캐시 (검색 인덱스도 최신이어야 한다)
   - static/*, 매니페스트: 캐시 우선
     (버전이 캐시 이름에 있어 빌드 때 통째로 무효화되므로 낡을 일이 없다)
   그 외 요청은 건드리지 않고 브라우저에 맡긴다. */

(function () {
  "use strict";

  var CACHE_NAME = "qip-907c699d4ef9";
  /* 이 워커는 사이트 루트에 있으므로 self.location이 곧 사이트 루트다. */
  var OFFLINE_HREF = new URL("./offline.html", self.location.href).href;
  var MANIFEST_HREF = new URL("./manifest.webmanifest", self.location.href).href;

  /* 앱 셸: 설치 직후 오프라인으로도 열려야 하는 최소 집합.
     종목 상세는 수천 개라 미리 받지 않고, 방문한 것만 위 전략에 따라 캐시된다. */
  var PRECACHE_URLS = [
    "./index.html",
    "./offline.html",
    "./stocks/index.html",
    "./sectors/index.html",
    "./manifest.webmanifest",
    "./static/charts.js",
    "./static/icons/apple-touch-icon.png",
    "./static/icons/icon-192.png",
    "./static/icons/icon-512.png",
    "./static/icons/icon-maskable-512.png",
    "./static/install.js",
    "./static/search.js",
    "./static/style.css",
    "./static/sw-register.js",
    "./data/search-index.json"
  ];

  function putInCache(request, response) {
    var copy = response.clone();
    caches.open(CACHE_NAME).then(function (cache) {
      cache.put(request, copy);
    });
  }

  function networkFirst(request) {
    return fetch(request)
      .then(function (response) {
        if (response && response.ok) putInCache(request, response);
        return response;
      })
      .catch(function () {
        return caches.match(request);
      });
  }

  function cacheFirst(request) {
    return caches.match(request).then(function (cached) {
      if (cached) return cached;
      return fetch(request).then(function (response) {
        if (response && response.ok) putInCache(request, response);
        return response;
      });
    });
  }

  self.addEventListener("install", function (event) {
    event.waitUntil(
      caches
        .open(CACHE_NAME)
        .then(function (cache) {
          return cache.addAll(PRECACHE_URLS);
        })
        .then(function () {
          return self.skipWaiting();
        })
    );
  });

  self.addEventListener("activate", function (event) {
    /* 버전이 바뀌면 옛 캐시를 통째로 버린다 — 낡은 CSS/JS가 남지 않게. */
    event.waitUntil(
      caches
        .keys()
        .then(function (names) {
          return Promise.all(
            names
              .filter(function (name) {
                return name !== CACHE_NAME;
              })
              .map(function (name) {
                return caches.delete(name);
              })
          );
        })
        .then(function () {
          return self.clients.claim();
        })
    );
  });

  self.addEventListener("fetch", function (event) {
    var request = event.request;
    if (request.method !== "GET") return;

    var url = new URL(request.url);
    if (url.origin !== self.location.origin) return;

    if (request.mode === "navigate") {
      event.respondWith(
        networkFirst(request).then(function (response) {
          if (response) return response;
          /* 오프라인 안내는 "본문을 대신 돌려주기"가 아니라 "이동시키기"다.
             본문만 돌려주면 주소는 원래 페이지(예: /stocks/NVDA.html)로 남아
             offline.html 안의 상대경로 자산(../static/...)이 전부 어긋난다. */
          if (request.url === OFFLINE_HREF) return Response.error(); // 리다이렉트 루프 방지
          return Response.redirect(OFFLINE_HREF, 302);
        })
      );
      return;
    }

    if (url.pathname.indexOf("/data/") >= 0) {
      event.respondWith(networkFirst(request));
      return;
    }

    /* 매니페스트는 루트에 있어 /static/ 규칙에 걸리지 않으므로 따로 잡아준다 —
       빠지면 오프라인에서 매니페스트만 못 읽어 설치된 앱의 정보가 비어 보인다. */
    if (url.pathname.indexOf("/static/") >= 0 || request.url === MANIFEST_HREF) {
      event.respondWith(cacheFirst(request));
    }
  });
})();