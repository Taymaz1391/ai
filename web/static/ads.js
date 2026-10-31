/* رایان — جایگاه‌های تبلیغ: بارگذاری، شمارش نمایش و کلیک */
(function () {
  "use strict";
  const R = window.RAYAN || {};
  const { $, $$ } = R;

  const SLOTS = ["home-top", "home-mid", "chat-empty", "chat-inline", "share-bottom", "docs-top"];

  function esc(text) {
    return String(text || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function fetchAd(slot) {
    try {
      const res = await fetch(`/api/ads?slot=${encodeURIComponent(slot)}`, { credentials: "include" });
      if (!res.ok) return null;
      const data = await res.json();
      return (data.ads && data.ads[0]) || null;
    } catch {
      return null;
    }
  }

  function render(node, ad) {
    node.hidden = false;
    node.innerHTML =
      '<span class="ad-tag">تبلیغ</span>' +
      '<div class="ad-body"><b>' + esc(ad.title) + "</b>" +
      (ad.body ? "<p>" + esc(ad.body) + "</p>" : "") + "</div>" +
      '<a class="ad-cta" href="' + esc(ad.url) + '" rel="sponsored noopener nofollow" data-ad-id="' + ad.id + '">' +
      esc(ad.cta || "بیشتر بدانید") + "</a>";
    node.querySelector("a.ad-cta").addEventListener("click", () => {
      try {
        navigator.sendBeacon(`/api/ads/${ad.id}/click`);
      } catch { /* نادیده */ }
    });
  }

  async function loadAll() {
    const nodes = $$("[data-ad-slot]");
    if (!nodes.length) return;
    let flags = {};
    try {
      const res = await fetch("/api/flags", { credentials: "include" });
      flags = (await res.json()).flags || {};
    } catch { /* نادیده */ }
    if (flags.ads_enabled === false) return;
    for (const node of nodes) {
      const slot = node.dataset.adSlot;
      if (!SLOTS.includes(slot) && !slot) continue;
      const ad = await fetchAd(slot);
      if (ad) render(node, ad);
      else node.hidden = true;
    }
  }

  window.RAYAN_ADS = { loadAll, render, SLOTS };
})();
