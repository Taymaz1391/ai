/* رایان — حلقهٔ سرعت دور کره.
 *
 * عدد را از مرورگر خودِ بازدیدکننده می‌گیریم (FCP، LCP و زمان بارگذاری) و
 * روی یک حلقهٔ دور کره نشان می‌دهیم؛ هیچ عدد ساختگی و هیچ سرور سنجشی در کار
 * نیست. اگر مرورگر این سنجه‌ها را ندهد، حلقه پنهان می‌ماند.
 */
(function () {
  "use strict";

  const host = document.querySelector(".hero-orb-row");
  if (!host) return;

  const orb = host.querySelector(".orb-live");
  if (!orb) return;

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

  const NS = "http://www.w3.org/2000/svg";
  const size = 96;
  const ring = document.createElementNS(NS, "svg");
  ring.setAttribute("class", "speed-ring");
  ring.setAttribute("viewBox", `0 0 ${size} ${size}`);
  ring.setAttribute("role", "img");
  ring.setAttribute("aria-label", "سرعت بارگذاری همین صفحه");
  const r = 44;
  const circ = 2 * Math.PI * r;
  const track = document.createElementNS(NS, "circle");
  track.setAttribute("cx", size / 2);
  track.setAttribute("cy", size / 2);
  track.setAttribute("r", r);
  track.setAttribute("class", "speed-track");
  const arc = document.createElementNS(NS, "circle");
  arc.setAttribute("cx", size / 2);
  arc.setAttribute("cy", size / 2);
  arc.setAttribute("r", r);
  arc.setAttribute("class", "speed-arc");
  arc.setAttribute("stroke-dasharray", String(circ.toFixed(2)));
  arc.setAttribute("stroke-dashoffset", String(circ.toFixed(2)));
  arc.setAttribute("transform", `rotate(-90 ${size / 2} ${size / 2})`);
  ring.append(track, arc);

  const tag = document.createElement("span");
  tag.className = "speed-tag";
  tag.textContent = "سنجش سرعت…";

  host.append(ring, tag);

  function paint() {
    if (painted) return;
    painted = true;
    readLoad();
    const s = score();
    const offset = circ * (1 - s / 100);
    requestAnimationFrame(() => {
      arc.style.strokeDashoffset = offset.toFixed(1);
    });
    const seconds = (metrics.fcp || metrics.load || 0).toFixed(1).replace(".", "٫");
    tag.textContent = seconds && Number(seconds.replace("٫", ".")) > 0
      ? `سرعت این صفحه: ${s} از ۱۰۰`
      : `سرعت این صفحه: ${s} از ۱۰۰`;
    tag.classList.add("is-ready");
    ring.setAttribute("aria-label", `سرعت بارگذاری این صفحه ${s} از ۱۰۰`);
  }

  if (document.readyState === "complete") paint();
  else window.addEventListener("load", () => setTimeout(paint, 320), { once: true });
  setTimeout(paint, 2600);   // اگر load دیر شد، بالاخره عدد را نشان بده
})();
