// Fridge Sheet's service worker. One job: when the home computer cannot be reached -- the
// phone is at school, the laptop is asleep -- show the offline page instead of the browser's
// own error. Nothing a route renders is ever cached: every page is a live answer about
// tonight's work. Only the offline page and the mark are stored, under a cache named for
// the build, so a new build drops the old copy at its first start.
var CACHE = "fridgesheet-__VERSION__";
var OFFLINE = "/offline";
var KEEP = [OFFLINE, "/static/mark.svg"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(KEEP); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  // Pages go to the network, always; the offline page only when the network is not there.
  // Everything else (htmx partials, the stylesheet, the PDF of a plan) is left to the browser.
  if (e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request).catch(function () {
    return caches.open(CACHE).then(function (c) { return c.match(OFFLINE); });
  }));
});
