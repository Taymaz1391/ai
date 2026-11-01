/* رایان — بستهٔ تقویت سرعت.
 *
 * کارهایی که حس «سریع بودن» می‌سازند، بدون اینکه چیزی الکی بار شود:
 *   ۱) ورق‌زدن صفحه‌ها با prefetch در لحظهٔ اشاره (نه همه‌چیز از اول)
 *   ۲) رفع فوران فونت: صفحه فقط بعد از آمادگی فونت کلاس می‌گیرد
 *   ۳) تصویرهای پایین صفحه با loading=lazy و decoding=async
 *   ۴) نوار راه‌اندازی برند که با اولین رنگ‌آمیزی محو می‌شود
 *   ۵) احترام به Save-Data و prefers-reduced-motion
 */
(function () {
  "use strict";

  const saveData = navigator.connection && navigator.connection.saveData;
  const slow = navigator.connection && /2g/.test(navigator.connection.effectiveType || "");

  /* --------------------------------------------------- پیش‌بارگذاری صفحات */
  const fetched = new Set();
  function prefetch(url) {
    if (!url || fetched.has(url) || saveData) return;
    if (!/^\/(?!\/)/.test(url)) return;
    if (/\.(png|jpe?g|mp4|webm|zip|apk|exe)$/i.test(url)) return;
    fetched.add(url);
    const link = document.createElement("link");
    link.rel = "prefetch";
    link.href = url;
    link.as = "document";
    document.head.append(link);
  }

  document.addEventListener("pointerover", (event) => {
    const link = event.target.closest?.("a[href]");
    if (!link || link.target || link.hasAttribute("download")) return;
    const url = link.getAttribute("href");
    if (url && url.startsWith("/") && !url.startsWith("//")) prefetch(url);
  }, { passive: true });

  document.addEventListener("focusin", (event) => {
    const link = event.target.closest?.("a[href]");
    if (link && link.getAttribute("href")?.startsWith("/")) prefetch(link.getAttribute("href"));
  });

  // سه مسیر پرکاربرد، بعد از آمادگی صفحه و در زمان بیکاری
  const warm = () => {
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1200));
    idle(() => {
      ["/chat", "/pricing", "/compare"].forEach(prefetch);
    });
  };

  /* ------------------------------------------------------------ فونت‌ها */
  const root = document.documentElement;
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => root.classList.add("fonts-ready"));
  } else {
    root.classList.add("fonts-ready");
  }

  /* --------------------------------------------------------- تصویرها */
  function tuneImages() {
    const viewport = window.innerHeight || 800;
    document.querySelectorAll("img").forEach((img) => {
      if (!img.decoding) img.decoding = "async";
      const rect = img.getBoundingClientRect();
      if (rect.top > viewport * 1.6 && !img.loading && !img.closest("picture")) {
        img.loading = "lazy";
      }
    });
  }

  /* --------------------------------------------------- نوار راه‌اندازی */
  function bootScreen() {
    const el = document.createElement("div");
    el.className = "boot-screen";
    el.setAttribute("aria-hidden", "true");
    el.innerHTML = '<div class="boot-inner"><span class="boot-ring"></span>' +
      '<img class="boot-mark boot-mark-light" src="/static/assets/brand/mark-ink.png" alt="" width="1026" height="520">' +
      '<img class="boot-mark boot-mark-dark" src="/static/assets/brand/mark-white.png" alt="" width="1026" height="520">' +
      "</div>";
    document.body.append(el);
    let seen = false;
    try { seen = sessionStorage.getItem("rayan.booted") === "1"; } catch { /* نادیده */ }
    if (seen) el.classList.add("is-quick");
    try { sessionStorage.setItem("rayan.booted", "1"); } catch { /* نادیده */ }
    const done = () => {
      el.classList.add("is-done");
      setTimeout(() => el.remove(), 620);
    };
    // اگر همه‌چیز آماده بود، بدون معطلی برو؛ حداکثر ۱٫۲ ثانیه
    const ready = document.readyState === "complete" ? Promise.resolve() : new Promise((res) => {
      window.addEventListener("load", res, { once: true });
      setTimeout(res, seen ? 220 : 900);
    });
    ready.then(() => requestAnimationFrame(done));
  }

  function init() {
    tuneImages();
    if (!saveData && !slow) warm();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") tuneImages();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bootScreen();
      init();
    }, { once: true });
  } else {
    bootScreen();
    init();
  }

  window.RAYAN_PERF = { prefetch, tuneImages };
})();
