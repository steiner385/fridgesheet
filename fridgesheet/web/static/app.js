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

// Charts: `charts.chart_config()`'s output, inlined as JSON next to a `<canvas>` by
// `_chart_canvas.html` (Trends, the course page, the report builder and view). The config
// travels with the page rather than being fetched: a builder preview is an unsaved definition
// with no URL to fetch by, and a page that already holds the rows should not ask for them
// twice. Every page that draws a chart includes `_chart_scripts.html` on its own initial load,
// before any htmx swap can bring in a chart-bearing partial, so there is no "library not
// loaded yet" race here.
//
// Chart.js keeps every instance in its own registry (and a ResizeObserver on the canvas's
// parent) until `destroy()`. An htmx swap replaces the canvas; the chart drawn on it must be
// destroyed, not kept, or each Preview click leaks one (tests/test_web_report_chart_lifecycle.py).
var CHARTS = [];

function pruneCharts() {
  CHARTS = CHARTS.filter(function (chart) {
    if (document.contains(chart.canvas)) return true;
    try { chart.destroy(); } catch (e) { /* already gone; the entry goes either way */ }
    return false;
  });
}

function attachCharts(root) {
  pruneCharts();                    // whatever this swap replaced, before anything new
  var els = root.querySelectorAll ? root.querySelectorAll("[data-chart-canvas]") : [];
  Array.prototype.forEach.call(els, function (canvas) {
    if (canvas.dataset.drawn) return;
    var script = canvas.parentNode.querySelector("[data-chart-config]");
    if (!script) return;
    canvas.dataset.drawn = "1";
    try {
      CHARTS.push(new Chart(canvas.getContext("2d"), JSON.parse(script.textContent)));
    } catch (e) {
      canvas.parentNode.innerHTML = '<p class="warn">The chart could not load.</p>';
    }
  });
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
