/* رایان — سرویس‌ورکر: دارایی‌های ایستا کش، صفحه‌ها شبکه-اول، آفلاین‌پذیر */
const VERSION = "rayan-v17";
const SHELL = [
  "/static/styles.css",
  "/static/pages.css",
  "/static/chat.css",
  "/static/admin.css",
  "/static/ui.js",
  "/static/app.js",
  "/static/auth.js",
  "/static/admin.js",
  "/static/human.js",
  "/static/config.js",
  "/static/theme-boot.js",
  "/static/offline.js",
  "/static/studio.js",
  "/static/ads.js",
  "/static/voice.js",
  "/static/scroll.js",
  "/static/perf.js",
  "/static/speed.js",
  "/static/support.js",
  "/static/assets/brand/orb-128.png",
  "/static/assets/brand/orb-live-sm.webp",
  "/static/assets/brand/orb-live.webp",
  "/static/assets/brand/logo-motion.webp",
  "/static/assets/brand/logo-motion-dark.webp",
  "/static/assets/brand/logo-loading.webp",
  "/static/assets/brand/mark-ink.png",
  "/static/assets/brand/mark-white.png",
  "/static/assets/brand/logotype-stack-ink.png",
  "/static/assets/brand/logotype-stack-white.png",
  "/static/assets/fonts/Vazirmatn-Regular.woff2",
  "/static/assets/fonts/Vazirmatn-Bold.woff2",
];
const PAGES = ["/", "/chat", "/pricing", "/models", "/about", "/compare", "/support", "/offline"];
const OFFLINE_HTML = `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>رایان — آفلاین</title>
<style>
 body{margin:0;min-height:100dvh;display:grid;place-items:center;background:#f2f6ff;color:#0a1730;
      font-family:Vazirmatn,"Vazir",sans-serif;text-align:center;padding:24px}
 .card{max-width:420px;background:#fff;border:1px solid #dde7f7;border-radius:24px;padding:34px;
       box-shadow:0 30px 80px -50px rgba(12,44,104,.45)}
 img{width:96px;height:96px;margin-bottom:14px}
 h1{font-size:20px;margin:0 0 8px}
 p{color:#3b4f73;font-size:14px;line-height:1.9;margin:0 0 18px}
 button{padding:10px 18px;border-radius:12px;border:0;background:#1a63f0;color:#fff;font:inherit;font-weight:700;cursor:pointer}
 a{color:#1a63f0;font-size:13px;text-decoration:none;display:inline-block;margin-top:14px}
</style></head><body><div class="card">
 <img src="/static/assets/brand/orb-128.png" alt="رایان">
 <h1>فعلاً اتصال برقرار نیست</h1>
 <p>این صفحه بدون اینترنت هم باز می‌شود، اما برای پاسخ‌دادن به سرور نیاز دارد.
    اتصال را بررسی کن؛ گفتگوهای ذخیره‌شده پس از وصل‌شدن برمی‌گردند.</p>
 <button onclick="location.reload()">تلاش دوباره</button>
 <br><a href="/">بازگشت به خانه</a>
</div></body></html>`;

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(VERSION);
    await cache.addAll(SHELL).catch(() => {});
    await Promise.all(PAGES.map(async (page) => {
      try {
        const res = await fetch(page, { cache: "no-cache" });
        if (res.ok) await cache.put(page, res.clone());
      } catch { /* صفحه‌ای که در دسترس نیست بعداً کش می‌شود */ }
    }));
    await cache.put("/offline", new Response(OFFLINE_HTML, {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    }));
  })());
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (event && event.data && event.data.type === "skip-waiting") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/static/")) {
    // دارایی‌ها: شبکه-اول، کش فقط پشتیبانِ آفلاین. این‌طوری نسخهٔ تازهٔ کد
    // هرگز پشتِ کشِ قدیمی نمی‌ماند (دلیلِ کلاسیکِ «سایت کار نمی‌کند»).
    event.respondWith((async () => {
      const cache = await caches.open(VERSION);
      try {
        const res = await fetch(request, { cache: "no-cache" });
        if (res && res.ok) cache.put(request, res.clone());
        return res;
      } catch {
        return (await cache.match(request)) || Response.error();
      }
    })());
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const res = await fetch(request);
        if (res.ok) {
          const cache = await caches.open(VERSION);
          cache.put(request, res.clone());
        }
        return res;
      } catch {
        const cache = await caches.open(VERSION);
        return (await cache.match(request)) || (await cache.match(url.pathname)) ||
          (await cache.match("/offline")) ||
          new Response(OFFLINE_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
      }
    })());
  }
});
