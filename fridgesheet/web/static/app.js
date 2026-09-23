// Detail rows (#53), registered first so a row is visible before the focus handler below
// reaches into it: each item row is followed by a hidden `tr.detail`, so a screen reader's row
// count is the real one. Loading a detail shows its row and marks the item link expanded;
// the card's Close button hides it again and puts focus back on the link.
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
