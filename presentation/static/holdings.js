/* 보유 판단 페이지(holdings/index.html): 시장 전환 + 정렬 기준(필터) 전환.
   등수는 빌드 때 행의 data-rank-{기준}에 미리 계산돼 있다 — 여기서는 줄 순서와
   등수 칸만 바꾼다. JS가 없으면 모든 시장 표가 종합 점수 순으로 그대로 보인다. */

(function () {
  "use strict";

  var board = document.querySelector("[data-holding-board]");
  if (!board) return;

  var markets = board.querySelectorAll("[data-market]");
  var marketButtons = board.querySelectorAll("[data-market-button]");
  var sortButtons = board.querySelectorAll("[data-sort-button]");
  var sortNotes = board.querySelectorAll("[data-sort-note-for]");

  function activate(buttons, active) {
    buttons.forEach(function (button) {
      var on = button === active;
      button.classList.toggle("is-active", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function showMarket(market) {
    markets.forEach(function (section) {
      section.hidden = section.getAttribute("data-market") !== market;
    });
  }

  function rankOf(row, key) {
    var rank = row.getAttribute("data-rank-" + key);
    return rank ? Number(rank) : Infinity; // 점수 없는 종목은 맨 뒤
  }

  function sortTable(tbody, key) {
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      return rankOf(a, key) - rankOf(b, key) || rankOf(a, "total") - rankOf(b, "total");
    });
    rows.forEach(function (row) {
      var cell = row.querySelector("[data-rank-cell]");
      var rank = row.getAttribute("data-rank-" + key);
      cell.firstChild.nodeValue = rank || "—";
      tbody.appendChild(row);
    });
  }

  function sortBy(key) {
    board.querySelectorAll(".holding-table").forEach(function (table) {
      sortTable(table.tBodies[0], key);
      table.querySelectorAll("[data-col]").forEach(function (cell) {
        cell.classList.toggle("is-sorted", cell.getAttribute("data-col") === key);
      });
    });
    sortNotes.forEach(function (note) {
      note.hidden = note.getAttribute("data-sort-note-for") !== key;
    });
  }

  marketButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      activate(marketButtons, button);
      showMarket(button.getAttribute("data-market-button"));
    });
  });
  sortButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      activate(sortButtons, button);
      sortBy(button.getAttribute("data-sort-button"));
    });
  });

  if (marketButtons.length) showMarket(marketButtons[0].getAttribute("data-market-button"));
  sortBy("total");
})();
