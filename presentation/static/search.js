/* 종목 검색: 이 사이트의 유일한 JS.
   첫 입력 시에만 검색 인덱스(data/search-index.json)를 내려받아(지연 로드)
   티커/종목명 부분일치 상위 20개를 드롭다운으로 보여준다. */

(function () {
  "use strict";

  var RESULT_LIMIT = 20;

  var box = document.querySelector(".search-box");
  var input = document.getElementById("stock-search");
  var resultList = document.getElementById("search-results");
  if (!box || !input || !resultList) return;

  var root = box.getAttribute("data-root") || ".";
  var stocks = null; // 인덱스 로드 전 null
  var loading = false;

  function loadIndex() {
    if (stocks !== null || loading) return;
    loading = true;
    fetch(root + "/data/search-index.json")
      .then(function (res) { return res.json(); })
      .then(function (data) {
        stocks = data.stocks || [];
        render(input.value);
      })
      .catch(function () {
        stocks = [];
      });
  }

  function matchScore(stock, query) {
    /* 접두 일치 > 부분 일치, 같은 등급에서는 시가총액 큰 순. */
    var ticker = (stock.t || "").toLowerCase();
    var name = (stock.n || "").toLowerCase();
    if (ticker.indexOf(query) === 0 || name.indexOf(query) === 0) return 2;
    if (ticker.indexOf(query) >= 0 || name.indexOf(query) >= 0) return 1;
    return 0;
  }

  function render(rawQuery) {
    var query = rawQuery.trim().toLowerCase();
    if (query === "" || stocks === null) {
      resultList.hidden = true;
      resultList.innerHTML = "";
      return;
    }

    var matched = [];
    for (var i = 0; i < stocks.length; i++) {
      var score = matchScore(stocks[i], query);
      if (score > 0) matched.push({ stock: stocks[i], score: score });
    }
    matched.sort(function (a, b) {
      if (b.score !== a.score) return b.score - a.score;
      return (b.stock.c || 0) - (a.stock.c || 0);
    });
    matched = matched.slice(0, RESULT_LIMIT);

    resultList.innerHTML = "";
    if (matched.length === 0) {
      var empty = document.createElement("li");
      empty.className = "no-result";
      empty.textContent = "검색 결과가 없습니다";
      resultList.appendChild(empty);
    }
    matched.forEach(function (item) {
      var stock = item.stock;
      var li = document.createElement("li");
      var link = document.createElement("a");
      link.href = root + "/stocks/" + encodeURIComponent(stock.t) + ".html";

      var name = document.createElement("span");
      name.className = "result-name";
      name.textContent = stock.n || stock.t;
      link.appendChild(name);

      var meta = document.createElement("span");
      meta.className = "result-meta";
      meta.textContent = stock.t + " · " + (stock.m || "");
      link.appendChild(meta);

      li.appendChild(link);
      resultList.appendChild(li);
    });
    resultList.hidden = false;
  }

  input.addEventListener("focus", loadIndex);
  input.addEventListener("input", function () {
    loadIndex();
    render(input.value);
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      resultList.hidden = true;
      input.blur();
    }
  });
  document.addEventListener("click", function (event) {
    if (!box.contains(event.target)) resultList.hidden = true;
  });
})();
