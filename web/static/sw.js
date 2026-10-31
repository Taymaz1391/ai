/* رایان — سرویس‌ورکر: دارایی‌های ایستا کش، صفحه‌ها شبکه-اول */
const VERSION = "rayan-v2";
const SHELL = [
  "/static/styles.css",
  "/static/ui.js",
  "/static/config.js",
  "/static/assets/brand/orb-128.png",
  "/static/assets/fonts/Vazirmatn-Regular.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((cache) => cache.put(request, copy)).catch(() => {});
        return res;
      }).catch(() => hit))
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((cache) => cache.put(request, copy)).catch(() => {});
        return res;
      }).catch(() => caches.match(request).then((hit) => hit || caches.match("/")))
    );
  }
});
