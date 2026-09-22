// Small helpers; everything interactive is htmx. Keep the expanded row open after a swap.
document.addEventListener("htmx:afterSwap", function (e) {
  var el = e.detail.target;
  if (el && el.matches && el.matches("[data-focus]")) { var f = el.querySelector("textarea, input"); if (f) f.focus(); }
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
    es.onerror = function () { es.close(); };
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
        series = [xs, data.not_done, data.unknown, data.late, data.on_time];
        opts = { title: el.dataset.title, width: width, height: plotHeight,
                 series: [{}, { label: "Not done", stroke: "#b3261e" }, { label: "Unknown", stroke: "#8a6d3b" },
                          { label: "Late", stroke: "#b8860b" }, { label: "On time", stroke: "#2e7d32" }] };
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

// Printing is explicit: opening a saved plan or report view never starts a print job on its own.
document.addEventListener("click", function (event) {
  if (event.target.closest("[data-print-plan], [data-print]")) window.print();
});

// The one form that deletes asks first; nothing else on these pages needs a dialog.
document.addEventListener("submit", function (event) {
  var form = event.target.closest("form[data-confirm]");
  if (form && !window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
});
