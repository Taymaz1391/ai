/* رایان — بستهٔ اسکرول نرم.
 *
 * سه چیز را با هم می‌آورد و هیچ کتابخانه‌ای لازم ندارد:
 *   ۱) اسکرول نرم برای لینک‌های داخلی (با احترام به prefers-reduced-motion)
 *   ۲) نوار پیشرفت اسکرول در بالای صفحه
 *   ۳) اسکرول‌بار اختصاصی که بعد از توقفِ حرکت محو می‌شود
 */
(function () {
  "use strict";

  const doc = document.documentElement;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;

  /* ------------------------------------------------ نوار پیشرفت اسکرول */
  const bar = document.createElement("div");
  bar.className = "scroll-progress";
  bar.setAttribute("aria-hidden", "true");
  bar.innerHTML = "<i></i>";
  document.body.append(bar);
  const fill = bar.firstElementChild;

  let ticking = false;
  let hideTimer = 0;

  function paint() {
    ticking = false;
    const max = doc.scrollHeight - window.innerHeight;
    const ratio = max > 4 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    fill.style.transform = `scaleX(${ratio.toFixed(4)})`;
    bar.classList.toggle("is-visible", ratio > 0.01);
    // اسکرول‌بار اختصاصی: تا وقتی حرکت ادامه دارد روشن می‌ماند
    root.classList.add("is-scrolling");
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => root.classList.remove("is-scrolling"), 900);
  }

  window.addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(paint);
  }, { passive: true });
  window.addEventListener("resize", paint, { passive: true });
  paint();

  /* ---------------------------------------------------- اسکرول نرم لینک‌ها */
  function smoothTo(target, offset) {
    const top = target.getBoundingClientRect().top + window.scrollY - (offset || 76);
    if (reduce) {
      window.scrollTo(0, top);
      return;
    }
    const start = window.scrollY;
    const delta = top - start;
    const duration = Math.min(900, Math.max(260, Math.abs(delta) * 0.45));
    const t0 = performance.now();
    const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
    function step(now) {
      const t = Math.min(1, (now - t0) / duration);
      window.scrollTo(0, start + delta * ease(t));
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest?.('a[href^="#"]');
    if (!link) return;
    const id = link.getAttribute("href");
    if (!id || id === "#") return;
    const target = document.querySelector(id);
    if (!target) return;
    event.preventDefault();
    smoothTo(target);
    history.replaceState(null, "", id);
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });

  /* ------------------------------- دکمهٔ «برو به بالا» که با اسکرول می‌آید */
  const top = document.createElement("button");
  top.className = "to-top";
  top.type = "button";
  top.setAttribute("aria-label", "رفتن به بالای صفحه");
  top.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 19V5M6 11l6-6 6 6"/></svg>';
  document.body.append(top);
  top.addEventListener("click", () => smoothTo(document.body, 0));

  // واسط عمومی برای بقیهٔ اسکریپت‌ها (مثلاً پرش نرم به پیام تازه)
  window.RAYAN = window.RAYAN || {};
  window.RAYAN.smoothScroll = (target) => {
    const node = typeof target === "string" ? document.querySelector(target) : target;
    if (!node || reduce) return;
    smoothTo(node, 0);
  };
  window.addEventListener("scroll", () => {
    top.classList.toggle("is-visible", window.scrollY > window.innerHeight * 1.4);
  }, { passive: true });
})();
