/* 종목 상세 페이지 차트 — 외부 라이브러리 없이 SVG를 직접 그린다.
   데이터는 페이지에 임베드된 <script id="chart-data">(JSON)에서 읽는다.
   - 주가: 영역(area) 차트 + 기간 토글 + 호버 툴팁 (상승 빨강/하락 파랑, 한국 관례)
   - 실적: 매출·영업이익·순이익 그룹 막대 (실적 섹션을 펼칠 때 애니메이션으로 렌더) */
(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  // 실적 막대 3계열 색 (템플릿 범례 .swatch 색과 일치시킨다)
  var SERIES = [
    { key: "r", color: "#3182f6" }, // 매출
    { key: "o", color: "#12b886" }, // 영업이익
    { key: "n", color: "#7048e8" }, // 순이익
  ];

  function svgEl(name, attrs) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function isKr(market) {
    return !!market && market.charAt(0) === "K";
  }

  function fmtPrice(v, kr) {
    if (v == null) return "—";
    return kr
      ? "₩" + Math.round(v).toLocaleString()
      : "$" + v.toFixed(2);
  }

  function fmtMoney(v, kr) {
    if (v == null) return "—";
    var sign = v < 0 ? "-" : "";
    var a = Math.abs(v);
    if (kr) {
      if (a >= 1e12) return sign + (a / 1e12).toFixed(1) + "조";
      return sign + Math.round(a / 1e8).toLocaleString() + "억";
    }
    if (a >= 1e12) return sign + "$" + (a / 1e12).toFixed(2) + "T";
    if (a >= 1e9) return sign + "$" + (a / 1e9).toFixed(1) + "B";
    if (a >= 1e6) return sign + "$" + (a / 1e6).toFixed(1) + "M";
    return sign + "$" + Math.round(a).toLocaleString();
  }

  // --- 주가 영역 차트 ---

  function renderPrice(root, data) {
    var prices = data.prices;
    if (!prices || !prices.d || prices.d.length < 2) return;
    var kr = isKr(root.dataset.market);
    var canvas = root.querySelector(".chart-canvas");
    var tabs = Array.prototype.slice.call(root.querySelectorAll(".range-tab"));

    var W = 1000;
    var H = 280;
    var padT = 12;
    var padB = 12;

    function startIndexFor(months) {
      var n = prices.d.length;
      if (!months || months <= 0) return 0;
      var last = new Date(prices.d[n - 1]);
      var cutoff = new Date(last);
      cutoff.setMonth(cutoff.getMonth() - months);
      for (var i = 0; i < n; i++) {
        if (new Date(prices.d[i]) >= cutoff) return i;
      }
      return n - 1;
    }

    function draw(months) {
      var start = startIndexFor(months);
      var dates = prices.d.slice(start);
      var closes = prices.c.slice(start);
      var m = closes.length;
      if (m < 2) return;

      var min = Infinity;
      var max = -Infinity;
      for (var i = 0; i < m; i++) {
        if (closes[i] < min) min = closes[i];
        if (closes[i] > max) max = closes[i];
      }
      var span = max - min || 1;
      var plotH = H - padT - padB;
      var color = closes[m - 1] >= closes[0] ? "var(--up)" : "var(--down)";
      var xOf = function (i) {
        return (i / (m - 1)) * W;
      };
      var yOf = function (v) {
        return padT + ((max - v) / span) * plotH;
      };

      var linePts = [];
      for (var j = 0; j < m; j++) linePts.push(xOf(j) + "," + yOf(closes[j]));
      var linePath = "M" + linePts.join("L");
      var areaPath =
        linePath + "L" + W + "," + (H - padB) + "L0," + (H - padB) + "Z";

      canvas.innerHTML = "";
      var svg = svgEl("svg", {
        viewBox: "0 0 " + W + " " + H,
        preserveAspectRatio: "none",
        class: "price-svg",
      });
      var gradId = "grad-" + Math.random().toString(36).slice(2);
      var defs = svgEl("defs", {});
      var grad = svgEl("linearGradient", {
        id: gradId,
        x1: "0",
        y1: "0",
        x2: "0",
        y2: "1",
      });
      grad.appendChild(
        svgEl("stop", { offset: "0", "stop-color": color, "stop-opacity": "0.22" })
      );
      grad.appendChild(
        svgEl("stop", { offset: "1", "stop-color": color, "stop-opacity": "0" })
      );
      defs.appendChild(grad);
      svg.appendChild(defs);
      svg.appendChild(svgEl("path", { d: areaPath, fill: "url(#" + gradId + ")" }));
      svg.appendChild(
        svgEl("path", {
          d: linePath,
          fill: "none",
          stroke: color,
          "stroke-width": "2",
          "stroke-linejoin": "round",
          "vector-effect": "non-scaling-stroke",
        })
      );

      // 호버 요소 (크로스헤어 + 점)
      var crosshair = svgEl("line", {
        class: "chart-crosshair",
        y1: 0,
        y2: H,
        stroke: "var(--border)",
        "stroke-width": "1",
        "vector-effect": "non-scaling-stroke",
        visibility: "hidden",
      });
      var dot = svgEl("circle", {
        class: "chart-dot",
        r: "4",
        fill: color,
        stroke: "var(--page-bg)",
        "stroke-width": "2",
        visibility: "hidden",
      });
      svg.appendChild(crosshair);
      svg.appendChild(dot);
      canvas.appendChild(svg);

      var tip = document.createElement("div");
      tip.className = "chart-tooltip";
      tip.hidden = true;
      canvas.appendChild(tip);

      function onMove(evt) {
        var rect = svg.getBoundingClientRect();
        var clientX =
          evt.touches && evt.touches[0] ? evt.touches[0].clientX : evt.clientX;
        var frac = (clientX - rect.left) / rect.width;
        var idx = Math.round(frac * (m - 1));
        if (idx < 0) idx = 0;
        if (idx > m - 1) idx = m - 1;
        var px = xOf(idx);
        var py = yOf(closes[idx]);
        crosshair.setAttribute("x1", px);
        crosshair.setAttribute("x2", px);
        crosshair.setAttribute("visibility", "visible");
        // 점은 viewBox(비균일 스케일) 대신 실제 픽셀 위치로 배치
        dot.setAttribute("visibility", "hidden");
        tip.hidden = false;
        tip.innerHTML =
          '<span class="tip-date">' +
          dates[idx] +
          '</span><span class="tip-price">' +
          fmtPrice(closes[idx], kr) +
          "</span>";
        var left = (px / W) * rect.width;
        tip.style.left = Math.min(Math.max(left, 4), rect.width - 4) + "px";
        // 점은 HTML 오버레이로(스케일 왜곡 방지)
        placeDot(px, py, rect, color);
      }

      var htmlDot = document.createElement("div");
      htmlDot.className = "chart-hover-dot";
      htmlDot.hidden = true;
      canvas.appendChild(htmlDot);
      function placeDot(px, py, rect, c) {
        htmlDot.hidden = false;
        htmlDot.style.left = (px / W) * rect.width + "px";
        htmlDot.style.top = (py / H) * rect.height + "px";
        htmlDot.style.background = c;
      }

      function onLeave() {
        crosshair.setAttribute("visibility", "hidden");
        tip.hidden = true;
        htmlDot.hidden = true;
      }

      svg.addEventListener("mousemove", onMove);
      svg.addEventListener("mouseleave", onLeave);
      svg.addEventListener("touchmove", onMove, { passive: true });
      svg.addEventListener("touchend", onLeave);
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) {
          t.classList.remove("active");
        });
        tab.classList.add("active");
        draw(parseInt(tab.dataset.range, 10));
      });
    });

    var active = root.querySelector(".range-tab.active") || tabs[tabs.length - 1];
    draw(parseInt(active.dataset.range, 10));
  }

  // --- 실적 그룹 막대 ---

  function renderBars(root, annual) {
    if (!annual || !annual.length) return;
    var kr = isKr(root.dataset.market);
    var W = 1000;
    var H = 260;
    var padT = 14;
    var padB = 30; // 연도 라벨 자리

    var vals = [0];
    annual.forEach(function (y) {
      SERIES.forEach(function (s) {
        if (y[s.key] != null) vals.push(y[s.key]);
      });
    });
    var max = Math.max.apply(null, vals);
    var min = Math.min.apply(null, vals);
    var span = max - min || 1;
    var plotH = H - padT - padB;
    var yOf = function (v) {
      return padT + ((max - v) / span) * plotH;
    };
    var zeroY = yOf(0);

    var groups = annual.length;
    var groupW = W / groups;
    var innerW = groupW * 0.62;
    var barW = innerW / SERIES.length;
    var barGap = barW * 0.16;

    var svg = svgEl("svg", {
      viewBox: "0 0 " + W + " " + H,
      preserveAspectRatio: "xMidYMid meet",
      class: "bar-svg",
    });
    // 0선
    svg.appendChild(
      svgEl("line", {
        x1: 0,
        x2: W,
        y1: zeroY,
        y2: zeroY,
        stroke: "var(--border)",
        "stroke-width": "1",
        "vector-effect": "non-scaling-stroke",
      })
    );

    var bars = [];
    annual.forEach(function (y, g) {
      var groupX = g * groupW + (groupW - innerW) / 2;
      SERIES.forEach(function (s, si) {
        var v = y[s.key];
        if (v == null) return;
        var yv = yOf(v);
        var top = Math.min(yv, zeroY);
        var height = Math.abs(yv - zeroY);
        var x = groupX + si * barW + barGap / 2;
        var rect = svgEl("rect", {
          x: x,
          y: zeroY, // 애니메이션 시작: 0선에서 자란다
          width: barW - barGap,
          height: 0,
          rx: 2,
          fill: s.color,
        });
        svg.appendChild(rect);
        bars.push({ rect: rect, top: top, height: height, delay: g * 60 + si * 20 });
      });
      var label = svgEl("text", {
        x: g * groupW + groupW / 2,
        y: H - 10,
        "text-anchor": "middle",
        class: "bar-year",
      });
      label.textContent = y.p;
      svg.appendChild(label);
    });

    var canvas = root;
    canvas.innerHTML = "";
    canvas.appendChild(svg);

    // "주르륵" 등장: 0선에서 목표 높이로 자라는 rAF 트윈 (계열·연도 순 스태거)
    var duration = 420;
    var startT = null;
    function ease(t) {
      return 1 - Math.pow(1 - t, 3);
    }
    function step(now) {
      if (startT == null) startT = now;
      var elapsed = now - startT;
      var done = true;
      bars.forEach(function (b) {
        var t = (elapsed - b.delay) / duration;
        if (t < 0) t = 0;
        if (t < 1) done = false;
        var k = ease(Math.min(t, 1));
        b.rect.setAttribute("y", zeroY - (zeroY - b.top) * k);
        b.rect.setAttribute("height", b.height * k);
      });
      if (!done) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // --- 초기화 ---

  function init() {
    var dataNode = document.getElementById("chart-data");
    if (!dataNode) return;
    var data;
    try {
      data = JSON.parse(dataNode.textContent);
    } catch (e) {
      return;
    }

    var priceRoot = document.querySelector('.price-chart[data-chart="price"]');
    if (priceRoot && data.prices) renderPrice(priceRoot, data);

    var barRoot = document.querySelector('.bar-chart[data-chart="financials"]');
    if (barRoot && data.annual && data.annual.length) {
      var currentSeries = data.annual;
      var periodTabs = document.querySelector(".bar-period-tabs");
      var tablePanels = Array.prototype.slice.call(
        document.querySelectorAll(".fin-table-panel")
      );

      function showPeriod(period) {
        currentSeries =
          period === "quarterly" && data.quarterly && data.quarterly.length
            ? data.quarterly
            : data.annual;
        renderBars(barRoot, currentSeries);
        tablePanels.forEach(function (panel) {
          panel.hidden = panel.dataset.period !== period;
        });
      }

      if (periodTabs) {
        var periodButtons = Array.prototype.slice.call(
          periodTabs.querySelectorAll(".range-tab")
        );
        periodButtons.forEach(function (tab) {
          tab.addEventListener("click", function () {
            periodButtons.forEach(function (t) {
              t.classList.remove("active");
            });
            tab.classList.add("active");
            showPeriod(tab.dataset.period);
          });
        });
      }

      var details = barRoot.closest("details");
      if (details) {
        var rendered = false;
        details.addEventListener("toggle", function () {
          if (details.open && !rendered) {
            rendered = true;
            renderBars(barRoot, currentSeries);
          }
        });
      } else {
        renderBars(barRoot, currentSeries);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
