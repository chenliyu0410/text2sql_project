(function () {
  "use strict";

  var byId = function (id) { return document.getElementById(id); };
  var conversation = byId("conversation");
  var form = byId("queryForm");
  var input = byId("queryInput");
  var sendButton = byId("sendButton");
  var activeController = null;
  var composing = false;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function api(path, options) {
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { throw new Error("伺服器回傳非 JSON 內容"); })
        .then(function (payload) {
          if (!response.ok) throw new Error(payload.detail || "HTTP " + response.status);
          return payload;
        });
    });
  }

  function announce(message, urgent) {
    var target = byId(urgent ? "srAlert" : "srStatus");
    target.textContent = "";
    window.setTimeout(function () { target.textContent = message; }, 20);
  }

  function scrollLatest() {
    window.requestAnimationFrame(function () {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
    });
  }

  function setProcessing(on) {
    sendButton.disabled = on;
    sendButton.textContent = on ? "分析中" : "查詢";
    document.querySelectorAll(".example-chip").forEach(function (button) { button.disabled = on; });
    if (!on) input.focus();
  }

  function addUserMessage(question) {
    conversation.appendChild(element("article", "message user", question));
  }

  function progressCard() {
    var card = element("article", "message progress-card");
    card.setAttribute("aria-label", "查詢進度");
    card.appendChild(element("strong", "", "正在處理您的查詢"));
    var list = element("ol");
    var labels = ["解析問題與實體", "套用安全與語意規則", "產生並執行查詢", "整理結果與圖表"];
    var items = labels.map(function (label, index) {
      var item = element("li", index === 0 ? "active" : "", label);
      if (index === 0) item.setAttribute("aria-current", "step");
      list.appendChild(item);
      return item;
    });
    card.appendChild(list);
    var cancel = element("button", "suggestion", "取消查詢");
    cancel.type = "button";
    cancel.addEventListener("click", function () {
      if (activeController) activeController.abort();
    });
    card.appendChild(cancel);
    conversation.appendChild(card);
    var timers = items.slice(1).map(function (item, index) {
      return window.setTimeout(function () {
        items[index].className = "done";
        items[index].removeAttribute("aria-current");
        item.className = "active";
        item.setAttribute("aria-current", "step");
      }, 450 + index * 650);
    });
    return {
      finish: function () {
        timers.forEach(window.clearTimeout);
        items.forEach(function (item) {
          item.className = "done";
          item.removeAttribute("aria-current");
        });
      },
      remove: function () {
        timers.forEach(window.clearTimeout);
        card.remove();
      }
    };
  }

  function valueText(value) {
    if (value == null || value === "") return "—";
    if (typeof value === "number") return new Intl.NumberFormat("zh-Hant-TW", { maximumFractionDigits: 3 }).format(value);
    return String(value);
  }

  function renderChart(spec) {
    if (!spec || ["line", "bar", "scatter"].indexOf(spec.kind) < 0 || !Array.isArray(spec.data)) return null;
    var wrap = element("figure", "chart");
    wrap.setAttribute("aria-label", (spec.layout && spec.layout.title && spec.layout.title.text) || "查詢結果圖表");
    var cleanData = spec.data.map(function (trace) {
      var clean = {
        type: spec.kind === "bar" ? "bar" : "scatter",
        mode: spec.kind === "line" ? "lines+markers" : spec.kind === "scatter" ? "markers" : undefined,
        name: String(trace.name || ""),
        x: Array.isArray(trace.x) ? trace.x.slice() : [],
        y: Array.isArray(trace.y) ? trace.y.slice() : []
      };
      if (Array.isArray(trace.text)) clean.text = trace.text.map(String);
      return clean;
    });
    var cleanLayout = {
      title: { text: String(spec.layout && spec.layout.title && spec.layout.title.text || "查詢結果") },
      xaxis: { title: { text: String(spec.layout && spec.layout.xaxis && spec.layout.xaxis.title && spec.layout.xaxis.title.text || "") } },
      yaxis: { title: { text: String(spec.layout && spec.layout.yaxis && spec.layout.yaxis.title && spec.layout.yaxis.title.text || "") } },
      margin: { t: 52, r: 24, b: 56, l: 68 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "system-ui, sans-serif", color: "#263547" }
    };
    if (window.Plotly && typeof window.Plotly.newPlot === "function") {
      var plot = element("div", "plotly-chart");
      wrap.appendChild(plot);
      window.setTimeout(function () {
        window.Plotly.newPlot(plot, cleanData, cleanLayout, {
          responsive: true,
          displaylogo: false,
          modeBarButtonsToRemove: ["sendDataToCloud", "lasso2d", "select2d"]
        });
      }, 30);
      return wrap;
    }
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 720 260");
    var allY = [];
    cleanData.forEach(function (trace) {
      (trace.y || []).forEach(function (value) { if (typeof value === "number") allY.push(value); });
    });
    if (!allY.length) return null;
    var min = Math.min.apply(null, allY);
    var max = Math.max.apply(null, allY);
    var span = max - min || 1;
    var colors = ["#1a5fb4", "#c25e00", "#2e7d32", "#7b4ab5"];
    var axis = document.createElementNS(ns, "path");
    axis.setAttribute("d", "M52 18 V220 H700");
    axis.setAttribute("fill", "none");
    axis.setAttribute("stroke", "#9dabbc");
    svg.appendChild(axis);
    cleanData.forEach(function (trace, traceIndex) {
      var ys = trace.y || [];
      var color = colors[traceIndex % colors.length];
      if (spec.kind === "bar") {
        var width = Math.max(8, Math.min(42, 600 / Math.max(ys.length, 1) - 5));
        ys.forEach(function (value, index) {
          var height = ((Number(value) - Math.min(0, min)) / (Math.max(max, 0) - Math.min(0, min) || 1)) * 180;
          var rect = document.createElementNS(ns, "rect");
          rect.setAttribute("x", String(65 + index * (610 / Math.max(ys.length, 1))));
          rect.setAttribute("y", String(220 - height));
          rect.setAttribute("width", String(width));
          rect.setAttribute("height", String(Math.max(1, height)));
          rect.setAttribute("fill", color);
          svg.appendChild(rect);
        });
      } else {
        var points = ys.map(function (value, index) {
          var xValues = trace.x || [];
          var x = spec.kind === "scatter" && typeof xValues[index] === "number"
            ? 65 + ((xValues[index] - Math.min.apply(null, xValues)) / (Math.max.apply(null, xValues) - Math.min.apply(null, xValues) || 1)) * 620
            : 65 + index * (620 / Math.max(ys.length - 1, 1));
          var y = 210 - ((Number(value) - min) / span) * 175;
          return [x, y];
        });
        if (spec.kind === "line") {
          var line = document.createElementNS(ns, "polyline");
          line.setAttribute("points", points.map(function (point) { return point.join(","); }).join(" "));
          line.setAttribute("fill", "none");
          line.setAttribute("stroke", color);
          line.setAttribute("stroke-width", "2.5");
          svg.appendChild(line);
        }
        points.forEach(function (point) {
          var circle = document.createElementNS(ns, "circle");
          circle.setAttribute("cx", String(point[0]));
          circle.setAttribute("cy", String(point[1]));
          circle.setAttribute("r", "3.5");
          circle.setAttribute("fill", color);
          svg.appendChild(circle);
        });
      }
    });
    wrap.appendChild(svg);
    return wrap;
  }

  function renderTable(columns, rows) {
    var wrap = element("div", "table-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("aria-label", "查詢結果，可左右捲動");
    var table = element("table");
    var head = element("thead");
    var headRow = element("tr");
    columns.forEach(function (column) { headRow.appendChild(element("th", "", column)); });
    head.appendChild(headRow);
    table.appendChild(head);
    var body = element("tbody");
    rows.forEach(function (row) {
      var tr = element("tr");
      columns.forEach(function (_column, index) { tr.appendChild(element("td", "", valueText(row[index]))); });
      body.appendChild(tr);
    });
    table.appendChild(body);
    wrap.appendChild(table);
    return wrap;
  }

  function renderResult(data) {
    var card = element("article", "message result-card");
    var head = element("header", "result-head");
    head.appendChild(element("h3", "", "查詢結果"));
    head.appendChild(element("span", "meta", String(data.record_count || 0) + " 筆"));
    card.appendChild(head);
    card.appendChild(element("p", "explanation", data.explanation || "查詢完成。"));
    (data.disclosures || []).forEach(function (disclosure) {
      card.appendChild(element("div", "callout", disclosure.reason));
    });
    var kpis = element("div", "kpis");
    var count = element("div", "kpi");
    count.appendChild(element("span", "", "結果筆數"));
    count.appendChild(element("strong", "", data.record_count || 0));
    kpis.appendChild(count);
    var numericEntries = Object.entries(data.statistics || {}).filter(function (entry) { return entry[1] && typeof entry[1] === "object"; });
    numericEntries.slice(0, 2).forEach(function (entry) {
      var kpi = element("div", "kpi");
      kpi.appendChild(element("span", "", entry[0] + "平均"));
      kpi.appendChild(element("strong", "", valueText(entry[1].average)));
      kpis.appendChild(kpi);
    });
    card.appendChild(kpis);
    var chart = renderChart(data.chart_spec);
    if (chart) card.appendChild(chart);
    card.appendChild(renderTable(data.columns || [], data.rows || []));
    var details = element("details");
    details.appendChild(element("summary", "", "查看執行 SQL"));
    details.appendChild(element("pre", "", data.sql || ""));
    card.appendChild(details);
    conversation.appendChild(card);
  }

  function renderError(payload) {
    var card = element("article", "message error-card");
    var severity = payload.severity === "clarify" ? "需要補充條件" : payload.severity === "refuse" ? "這個問題不能直接計算" : "查詢未完成";
    card.appendChild(element("h3", "", severity));
    card.appendChild(element("p", "", payload.error || "系統目前無法完成查詢。"));
    if (payload.error_code) card.appendChild(element("div", "meta", "錯誤碼：" + payload.error_code));
    var actions = element("div", "suggestions");
    (payload.suggestions || []).forEach(function (suggestion) {
      var button = element("button", "suggestion", suggestion);
      button.type = "button";
      button.addEventListener("click", function () { input.value = suggestion; input.focus(); });
      actions.appendChild(button);
    });
    if (actions.childNodes.length) card.appendChild(actions);
    conversation.appendChild(card);
  }

  function submitQuestion(question) {
    if (!question || activeController) return;
    addUserMessage(question);
    input.value = "";
    input.style.height = "auto";
    setProcessing(true);
    var progress = progressCard();
    activeController = new AbortController();
    scrollLatest();
    api("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question }),
      signal: activeController.signal
    }).then(function (payload) {
      progress.finish();
      window.setTimeout(progress.remove, 120);
      if (payload.success) {
        renderResult(payload.data);
        announce("查詢完成，共 " + payload.data.record_count + " 筆結果", false);
      } else {
        renderError(payload);
        announce(payload.error || "查詢未完成", true);
      }
    }).catch(function (error) {
      progress.remove();
      renderError({ error: error.name === "AbortError" ? "已取消這次查詢。伺服器端的處理仍會完成，但結果不會顯示。" : error.message, severity: "error" });
      announce(error.name === "AbortError" ? "查詢已取消" : "連線或伺服器錯誤", true);
    }).finally(function () {
      activeController = null;
      setProcessing(false);
      scrollLatest();
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!composing) submitQuestion(input.value.trim());
  });
  input.addEventListener("compositionstart", function () { composing = true; });
  input.addEventListener("compositionend", function () { composing = false; });
  input.addEventListener("keydown", function (event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitQuestion(input.value.trim());
    }
  });
  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 150) + "px";
  });

  function closeSidebar() {
    byId("sidebar").classList.remove("open");
    byId("sidebarBackdrop").hidden = true;
    byId("navToggle").setAttribute("aria-expanded", "false");
  }
  byId("navToggle").addEventListener("click", function () {
    var open = !byId("sidebar").classList.contains("open");
    byId("sidebar").classList.toggle("open", open);
    byId("sidebarBackdrop").hidden = !open;
    byId("navToggle").setAttribute("aria-expanded", String(open));
    if (open) byId("sidebar").focus();
  });
  byId("sidebarBackdrop").addEventListener("click", closeSidebar);

  Promise.all([api("/api/health"), api("/api/stats"), api("/api/examples")])
    .then(function (results) {
      var health = results[0];
      var stats = results[1].data;
      byId("statusDot").classList.add("connected");
      byId("statusText").textContent = health.demo ? "離線規則模式已就緒" : "AI 分析引擎已就緒";
      byId("demoBanner").hidden = !health.demo;
      byId("totalRecords").textContent = valueText(stats.total_records) + " 筆";
      byId("totalUnits").textContent = valueText(stats.total_units) + " 台";
      byId("outageRecords").textContent = valueText(stats.outage_records) + " 筆";
      byId("dateRange").textContent = stats.date_range;
      results[2].data.forEach(function (question) {
        var button = element("button", "example-chip", question);
        button.type = "button";
        button.addEventListener("click", function () { closeSidebar(); submitQuestion(question); });
        byId("examples").appendChild(button);
      });
    }).catch(function (error) {
      byId("statusDot").classList.add("failed");
      byId("statusText").textContent = "服務尚未就緒";
      announce(error.message, true);
    });
}());
