// Detail rows (#53), registered first so a row is visible before the focus handler below
// reaches into it: each item row is followed by a hidden `tr.detail`, so a screen reader's row
// count is the real one. Loading a detail shows its row and marks the item link expanded;
// the card's Close button hides it again and puts focus back on the link. A detail opened from
// a question card is not in a row: its Close is an hx-get that puts the card back (#126).
function detailLink(cell) {
  return document.querySelector('[hx-target="#' + cell.id + '"]');
}
document.addEventListener("htmx:afterSwap", function (e) {
  var cell = e.detail.target;
  var row = cell && cell.closest && cell.closest("tr.detail");
  if (!row) return;
  row.hidden = false;
  var link = detailLink(cell);
  if (link) link.setAttribute("aria-expanded", "true");
});
document.addEventListener("click", function (e) {
  var btn = e.target.closest && e.target.closest("[data-close-detail]");
  if (!btn) return;
  var row = btn.closest("tr.detail");
  if (!row) return;
  var cell = row.querySelector("td");
  var link = detailLink(cell);
  cell.innerHTML = "";
  row.hidden = true;
  if (link) { link.setAttribute("aria-expanded", "false"); link.focus(); }
});

// Small helpers; everything interactive is htmx. After a swap that brings in a [data-focus]
// card -- as the swapped element itself or inside the target -- move focus to its named
// [data-focus-target] (the card heading). Focusing the first input instead raised the phone
// keyboard on every tap and sent screen readers past the card's content.
// An outerHTML swap leaves e.detail.target pointing at the removed element; the event itself
// is dispatched on its replacement, so fall back to e.target when the target is detached.
document.addEventListener("htmx:afterSwap", function (e) {
  var el = e.detail.target && e.detail.target.isConnected ? e.detail.target : e.target;
  if (!el || !el.matches) return;
  var card = el.matches("[data-focus]") ? el : el.querySelector("[data-focus]");
  var f = card && card.querySelector("[data-focus-target]");
  if (f) f.focus();
});

// Announcements (#43): swapped content can carry `data-announce`; its text goes into the one
// polite live region in base.html, so a screen reader hears "Note added" or "12 assignments
// shown" instead of nothing. Cleared first so the same words twice are still read twice.
document.addEventListener("htmx:afterSwap", function (e) {
  var root = e.detail.target && e.detail.target.isConnected ? e.detail.target : e.target;
  var live = document.getElementById("announce");
  if (!root || !root.matches || !live) return;
  var src = root.matches("[data-announce]") ? root : root.querySelector("[data-announce]");
  if (!src) return;
  live.textContent = "";
  setTimeout(function () { live.textContent = src.getAttribute("data-announce"); }, 50);
});

// A request the server refused (a 400 for a reprint of a day with no data, a 404 for a job
// that is no longer kept) used to change nothing on the page (#6). Say so next to what was
// clicked, in the server's own words when it sent a short reason, and read it out.
function errorText(xhr) {
  var text = (xhr && xhr.responseText || "").trim();
  try { var j = JSON.parse(text); if (j && typeof j.detail === "string") text = j.detail; } catch (e) { /* not JSON */ }
  if (!text || text.length > 300 || text.charAt(0) === "<") text = "The app could not do that (error " + (xhr ? xhr.status : "?") + ").";
  return text;
}
// A 409 that comes back as HTML is a card meant to be shown -- the job card saying "Busy: …
// is still running" (#142) -- not a refusal: htmx's default responseHandling swaps no 4xx, and
// errorText would have turned it into "could not do that (error 409)". A 409 with a JSON
// `detail` ("Already in the plan for …") stays an error, said next to the button as above.
document.addEventListener("htmx:beforeSwap", function (e) {
  var xhr = e.detail.xhr;
  if (!xhr || xhr.status !== 409) return;
  if (!/^text\/html/i.test(xhr.getResponseHeader("Content-Type") || "")) return;
  e.detail.shouldSwap = true;
  e.detail.isError = false;
});
document.addEventListener("htmx:responseError", function (e) {
  var near = e.detail.elt && e.detail.elt.isConnected ? e.detail.elt : e.detail.target;
  if (!near || !near.parentNode) return;
  var box = near.nextElementSibling && near.nextElementSibling.classList.contains("request-error")
    ? near.nextElementSibling : document.createElement("p");
  box.className = "request-error warn";
  box.setAttribute("role", "alert");
  box.textContent = errorText(e.detail.xhr);
  if (box !== near.nextElementSibling) near.parentNode.insertBefore(box, near.nextSibling);
});

// Live job progress: a <pre data-sse=URL data-reload=URL> opens an EventSource, appends each
// line, and when the server says done, fetches the finished job partial over htmx.
function attachSse(root) {
  (root.querySelectorAll ? root.querySelectorAll("[data-sse]") : []).forEach(function (pre) {
    if (pre.dataset.attached) return;
    pre.dataset.attached = "1";
    var es = new EventSource(pre.dataset.sse);
    es.onmessage = function (e) { pre.textContent += (pre.textContent ? "\n" : "") + e.data; pre.scrollTop = pre.scrollHeight; };
    es.addEventListener("done", function () { es.close(); htmx.ajax("GET", pre.dataset.reload, { target: "#job", swap: "outerHTML" }); });
    // A dropped connection (the server restarted, the laptop slept) used to leave the log
    // frozen with no sign (#4): say so, then ask for the job card again, which reattaches
    // if the job is still running and shows its result if it is not.
    es.onerror = function () {
      es.close();
      pre.textContent += (pre.textContent ? "\n" : "") + "(connection lost; checking the job again…)";
      setTimeout(function () { htmx.ajax("GET", pre.dataset.reload, { target: "#job", swap: "outerHTML" }); }, 2000);
    };
  });
}
document.addEventListener("DOMContentLoaded", function () { attachSse(document); });
document.addEventListener("htmx:afterSwap", function (e) { attachSse(e.detail.target); });

// Charts: a <div class="chart" data-chart=URL data-kind=lines|weekly> fetches its own JSON and
// draws one uPlot into itself. No data is embedded in the page, so a chart is just a URL.
var CHART_FAILED = '<p class="warn">The chart could not load.</p>';
var CHART_WAIT_MS = 50;
var CHART_MAX_TRIES = 100;              // ~5s, then say so rather than spin forever

// uPlot's `width` is the *content* box it draws into. `.chart` is border-box with 8px of
// padding, so clientWidth includes that padding; subtract it or the plot draws 16px too wide.
//
// `height`, by contrast, is NOT the holder's box -- uPlot draws a title and a legend table as
// *siblings* of the sized plot, adding their height on top of whatever we pass. A holder sized
// to the plot alone is too short for the furniture uPlot puts around it, and the legend prints
// on top of whatever follows the chart in the page. So `height` is a per-chart constant from
// `data-height` (set by `_chart.html`), and `.chart` has no fixed height of its own (see
// app.css) -- the holder grows to fit title + plot + legend, so nothing can overflow it.
function chartWidth(el) {
  var cs = window.getComputedStyle(el);
  function px(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  return Math.max(1, Math.round(el.clientWidth - px(cs.paddingLeft) - px(cs.paddingRight)));
}

// Every chart drawn on the page, so one resize listener can walk them all instead of each
// chart installing its own -- bounded at one listener no matter how many charts a page has.
var CHARTS = [];

// An htmx swap replaces DOM nodes; the uPlot instance built on a replaced `.chart` is not on
// the page any more but is still in `CHARTS`, still holding its canvas and its own document
// listeners. Dropping the entry is not enough -- `destroy()` is what releases them. This used
// to happen only inside the resize handler's filter, and only as far as dropping the entry:
// on a page nobody ever resizes (a phone), a swapped-away chart leaked for the life of the
// page. Called from `attachCharts`, which htmx fires after *every* swap, so it runs whether or
// not the incoming content has a chart of its own.
function pruneCharts() {
  CHARTS = CHARTS.filter(function (c) {
    if (document.contains(c.el)) return true;
    try { c.u.destroy(); } catch (e) { /* already gone; the entry goes either way */ }
    return false;
  });
}

function drawChart(el) {
  if (el.dataset.drawn) return;
  el.dataset.drawn = "1";
  var plotHeight = Math.max(1, parseInt(el.dataset.height, 10) || 220);
  fetch(el.dataset.chart, { headers: { Accept: "application/json" } })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      // An htmx swap during the fetch may have removed this holder (and pruned already):
      // drawing into it now would leave a detached uPlot in CHARTS that nothing destroys.
      if (!document.contains(el)) return;
      var opts, series, width = chartWidth(el);
      if (el.dataset.kind === "weekly") {
        // `Date.parse` on a date-only string ("2026-08-24") parses as UTC midnight per spec;
        // uPlot's default tick formatting uses local getters, so in America/New_York that
        // timestamp draws as ~8pm the day before -- disagreeing with the week the table below
        // prints for the same row. Build local midnight by hand instead. Do not "simplify"
        // this back to Date.parse: that reintroduces the off-by-one-day mismatch.
        var xs = data.weeks.map(function (w) {
          var ymd = w.split("-");
          return new Date(Number(ymd[0]), Number(ymd[1]) - 1, Number(ymd[2])).getTime() / 1000;
        });
        // One line per count `/trends/weekly.json` sends and the table beside the chart shows --
        // "On paper" was once left out here, so the chart and its table disagreed (#150).
        series = [xs, data.not_done, data.unknown, data.late, data.done_offline, data.on_time];
        opts = { title: el.dataset.title, width: width, height: plotHeight,
                 series: [{}, { label: "Not done", stroke: "#b3261e" }, { label: "Unknown", stroke: "#8a6d3b" },
                          { label: "Late", stroke: "#b8860b" }, { label: "On paper", stroke: "#1f5fa8" },
                          { label: "On time", stroke: "#2e7d32" }] };
      } else {
        if (!data.series.length) { el.innerHTML = '<p class="muted">No grades recorded yet.</p>'; return; }
        var times = {};
        data.series.forEach(function (s) { s.points.forEach(function (p) { times[p[0]] = 1; }); });
        var xs2 = Object.keys(times).map(Number).sort(function (a, b) { return a - b; });
        series = [xs2].concat(data.series.map(function (s) {
          var by = {}; s.points.forEach(function (p) { by[p[0]] = p[1]; });
          var last = null;
          return xs2.map(function (t) { if (by[t] !== undefined) last = by[t]; return last; });
        }));
        var colors = ["#1f5fa8", "#b3261e", "#2e7d32", "#6b3fa0", "#b8860b", "#00707f"];
        opts = { title: el.dataset.title, width: width, height: plotHeight,
                 series: [{}].concat(data.series.map(function (s, i) {
                   return { label: s.label, stroke: colors[i % colors.length] };
                 })) };
      }
      el.innerHTML = "";
      pruneCharts();
      CHARTS.push({ el: el, u: new uPlot(opts, series, el) });
      ensureResizeListener();
    })
    .catch(function () { el.innerHTML = CHART_FAILED; });
}

// One shared resize listener for every chart on the page, debounced -- a resize fires
// continuously during a drag, and `setSize` redraws the canvas each time it is called. Only
// the width follows the holder; the plot height is the constant it was constructed with, so a
// resize never reopens the overflow this file exists to fix. Stale entries (an element that's
// no longer on the page, e.g. after an htmx swap replaced it) are destroyed as they're found.
//
// Installed lazily, at most once, the first time a chart actually draws -- same reasoning as
// `attachCharts` below: a page with no chart should end up with no chart-related listener.
var resizeTimer = null;
var resizeInstalled = false;
function ensureResizeListener() {
  if (resizeInstalled) return;
  resizeInstalled = true;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      pruneCharts();
      CHARTS.forEach(function (c) {
        var w = chartWidth(c.el);
        if (w !== c.u.width) c.u.setSize({ width: w, height: c.u.height });
      });
    }, 150);
  });
}

// Look for charts *before* waiting on uPlot. `app.js` is deferred on every page but
// `uplot.min.js` is loaded only on Trends and the course page, so checking the global first
// left a permanent 20 Hz timer running on the Dashboard, Kid, Reconcile, Runs, Settings,
// Diagnostics and 404 pages -- and htmx:afterSwap started another independent one on every
// filter change, note save and flag toggle, none of which ever stopped. A page with no chart
// now returns immediately; a page with charts waits a bounded five seconds and then says the
// chart could not load, the same sentence a failed fetch puts there.
function attachCharts(root, tries) {
  pruneCharts();                          // whatever this swap replaced, before anything new
  var els = root.querySelectorAll ? root.querySelectorAll(".chart[data-chart]") : [];
  if (!els.length) return;
  if (typeof uPlot === "undefined") {
    if ((tries || 0) >= CHART_MAX_TRIES) {
      Array.prototype.forEach.call(els, function (el) { el.innerHTML = CHART_FAILED; });
      return;
    }
    setTimeout(function () { attachCharts(root, (tries || 0) + 1); }, CHART_WAIT_MS);
    return;
  }
  Array.prototype.forEach.call(els, drawChart);
}
document.addEventListener("DOMContentLoaded", function () { attachCharts(document); });
document.addEventListener("htmx:afterSwap", function (e) { attachCharts(e.detail.target); });

// Config charts: `charts.chart_config()`'s output, inlined as JSON next to a `<canvas>` by
// `_chart_canvas.html`. Unlike Trends' uPlot charts, such a chart has no URL of its own -- a
// builder preview is an unsaved definition with no report id to fetch by -- so the config
// travels with the page rather than being fetched. Every page that draws one includes
// `_chart_scripts.html` on its own initial page load, before any htmx swap can bring in a
// chart-bearing partial, so there is no "library not loaded yet" race to poll for here (unlike
// attachCharts' wait loop, which exists for the first draw on page load itself).
//
// Same lifecycle rule as `pruneCharts` above: Chart.js keeps every instance in its own
// registry (and a ResizeObserver on the canvas's parent) until `destroy()`. The builder's
// Preview replaces `#preview` wholesale on every click, so without this each click drew a new
// chart and kept the old one for the life of the page (tests/test_web_report_chart_lifecycle.py).
var REPORT_CHARTS = [];

function pruneReportCharts() {
  REPORT_CHARTS = REPORT_CHARTS.filter(function (chart) {
    if (document.contains(chart.canvas)) return true;
    try { chart.destroy(); } catch (e) { /* already gone; the entry goes either way */ }
    return false;
  });
}

function attachReportCharts(root) {
  pruneReportCharts();                    // whatever this swap replaced, before anything new
  var els = root.querySelectorAll ? root.querySelectorAll("[data-chart-canvas]") : [];
  Array.prototype.forEach.call(els, function (canvas) {
    if (canvas.dataset.drawn) return;
    var script = canvas.parentNode.querySelector("[data-chart-config]");
    if (!script) return;
    canvas.dataset.drawn = "1";
    try {
      REPORT_CHARTS.push(new Chart(canvas.getContext("2d"), JSON.parse(script.textContent)));
    } catch (e) {
      canvas.parentNode.innerHTML = '<p class="warn">The chart could not load.</p>';
    }
  });
}
document.addEventListener("DOMContentLoaded", function () { attachReportCharts(document); });
document.addEventListener("htmx:afterSwap", function (e) { attachReportCharts(e.detail.target); });

// Printing is explicit: opening a saved plan or report view never starts a print job on its own.
document.addEventListener("click", function (event) {
  if (event.target.closest("[data-print-plan], [data-print]")) window.print();
});

// The one form that deletes asks first; nothing else on these pages needs a dialog.
document.addEventListener("submit", function (event) {
  var form = event.target.closest("form[data-confirm]");
  if (form && !window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
});

// Graphical config editors (Settings: late-rules, no-print-days): rows are added, removed and
// reordered entirely client-side -- the file is one form with one Save, so nothing here needs
// a round trip until that button is pressed.
document.addEventListener("click", function (event) {
  var add = event.target.closest("[data-add-row]");
  if (add) {
    var tmpl = document.getElementById(add.getAttribute("data-add-row"));
    document.getElementById(add.getAttribute("data-add-target")).appendChild(tmpl.content.cloneNode(true));
    return;
  }
  if (event.target.closest("[data-remove-row]")) { event.target.closest(".row").remove(); return; }
  var move = event.target.closest("[data-move-row]");
  if (move) {
    var row = move.closest(".row");
    if (move.getAttribute("data-move-row") === "up" && row.previousElementSibling) {
      row.parentNode.insertBefore(row, row.previousElementSibling);
    } else if (move.getAttribute("data-move-row") === "down" && row.nextElementSibling) {
      row.parentNode.insertBefore(row.nextElementSibling, row);
    }
  }
});
