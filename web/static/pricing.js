/* رایان — تعرفهٔ پویا: قیمت و وضعیت پرداخت از تنظیمات مدیر خوانده می‌شود */
(function () {
  "use strict";
  function fa(n) {
    return String(n).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
  }
  function money(n) {
    return fa(Number(n).toLocaleString("en-US"));
  }
  async function load() {
    let data;
    try {
      const res = await fetch("/api/plans", { headers: { accept: "application/json" } });
      if (!res.ok) return;
      data = await res.json();
    } catch { return; }
    const plans = (data.plans || []).reduce((acc, p) => { acc[p.id] = p; return acc; }, {});
    const pro = plans.pro;
    if (!pro) return;
    const price = document.querySelector("[data-plan-price='pro']");
    const tag = document.querySelector("[data-plan-tag='pro']");
    const cta = document.querySelector("[data-plan-cta='pro']");
    const currency = data.currency || "تومان";
    if (pro.price > 0) {
      if (price) price.innerHTML = `${money(pro.price)} <small>${currency} / ${pro.period}</small>`;
      if (tag) tag.textContent = pro.for_sale ? "فعال" : "به‌زودی";
    } else if (price) {
      price.innerHTML = "توافقی <small>قرارداد سازمانی</small>";
    }
    if (cta) {
      const pay = data.payments || {};
      if (pro.for_sale && pay.link) {
        cta.textContent = "خرید پلن حرفه‌ای";
        cta.href = pay.link;
        cta.rel = "noopener";
      } else if (pro.price > 0) {
        cta.textContent = "پرداخت به‌زودی";
        cta.href = "/docs";
      }
    }
    const note = document.querySelector("[data-payments-note]");
    const pay = data.payments || {};
    if (note) {
      const text = pay.note || (pay.enabled ? "" : "پرداخت فعلاً غیرفعال است؛ همه‌چیز رایگان.");
      note.textContent = text;
      note.hidden = !text;
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
  window.RAYAN_PRICING = { load };
})();
