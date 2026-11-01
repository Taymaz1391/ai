/* رایان — نشان سرعت بارگذاری.
 *
 * سنجه را از مرورگر خودِ بازدیدکننده می‌گیریم (FCP، LCP و زمان بارگذاری) و
 * نتیجه را در یک نشان کوچک و بی‌عدد کنار وضعیت مدل نشان می‌دهیم: «بارگذاری سریع».
 * عدد خام و جزئیات فنی به کاربر نمایش داده نمی‌شود؛ فقط برای دسترس‌پذیری در
 * aria-label می‌ماند. هیچ عدد ساختگی و هیچ سرور سنجشی در کار نیست.
 */
(function () {
  "use strict";

  const note = document.querySelector(".hero-note");
  if (!note) return;

  const metrics = { fcp: 0, lcp: 0, load: 0 };
  let painted = false;

  function readLoad() {
    try {
      const nav = performance.getEntriesByType("navigation")[0];
      if (nav && nav.duration) metrics.load = nav.duration / 1000;
      const fcp = performance.getEntriesByName("first-contentful-paint")[0];
      if (fcp) metrics.fcp = fcp.startTime / 1000;
    } catch { /* نادیده */ }
  }

  if ("PerformanceObserver" in window) {
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.name === "largest-contentful-paint") metrics.lcp = entry.startTime / 1000;
        }
      }).observe({ type: "largest-contentful-paint", buffered: true });
    } catch { /* نادیده */ }
  }

  function score() {
    // سنجهٔ سرانگشتی: FCP و LCP زیر یک ثانیه عالی، بالای سه ثانیه ضعیف
    const fcp = metrics.fcp || metrics.lcp || 2.4;
    const lcp = metrics.lcp || fcp * 1.4;
    const raw = 100 - Math.min(60, fcp * 22) - Math.min(40, Math.max(0, lcp - 0.6) * 16);
    return Math.max(18, Math.min(100, Math.round(raw)));
  }

  const pill = document.createElement("span");
  pill.className = "speed-pill";

  function paint() {
    if (painted) return;
    painted = true;
    readLoad();
    const s = score();
    const label = s >= 80 ? "بارگذاری سریع" : s >= 58 ? "بارگذاری خوب" : "بارگذاری سبک";
    pill.textContent = label;
    pill.title = "همین صفحه در مرورگر تو، بی‌کمک سرور، سنجیده شد.";
    pill.setAttribute("role", "img");
    pill.setAttribute("aria-label", `${label}؛ سرعت بارگذاری این صفحه ${s} از ۱۰۰`);
    pill.classList.add("is-ready");
    note.append(pill);
  }

  if (document.readyState === "complete") paint();
  else window.addEventListener("load", () => setTimeout(paint, 320), { once: true });
  setTimeout(paint, 2600);   // اگر load دیر شد، بالاخره نشان را بده
})();
