/* رایان — صفحهٔ مدل‌ها: اعداد زنده از کارتِ عمومیِ مدلِ فعال */
(function () {
  "use strict";
  const { $, request, nf } = window.RAYAN;
  const FA = "۰۱۲۳۴۵۶۷۸۹";
  const fa = (value) => String(value).replace(/\d/g, (d) => FA[Number(d)]);

  const STAGE = { sft: "تنظیم دستورمحور", dpo: "بهینه‌سازی ترجیح", base: "پیش‌آموزش" };

  function num(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    if (typeof nf === "function") return nf(value, digits || 0);
    return fa(Number(value).toFixed(digits || 0));
  }

  function fact(label, value) {
    const row = document.createElement("div");
    row.className = "model-fact";
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    row.append(dt, dd);
    return row;
  }

  function fillFacts(target, pairs) {
    if (!target) return;
    target.innerHTML = "";
    pairs.filter((pair) => pair[1] && pair[1] !== "—").forEach(([label, value]) => {
      target.append(fact(label, value));
    });
  }

  function renderModel(card) {
    if (!card) return;
    const shape = card.shape || {};
    const metrics = card.metrics || {};
    const name = $("#model-name");
    if (name) name.textContent = card.name || "رایان";
    const badge = $("#model-badge");
    if (badge) badge.textContent = card.stage ? (STAGE[card.stage] || card.stage) : (card.badge || "فعال");
    const desc = $("#model-desc");
    if (desc) desc.textContent = card.desc || "";

    fillFacts($("#model-facts"), [
      ["پارامترها", card.params ? `${num(card.params / 1e6, 1)} میلیون` : "—"],
      ["معماری", shape.layers && shape.heads ? `${num(shape.layers)} لایه · ${num(shape.heads)} سر` : "—"],
      ["بُعد نهان", shape.embed ? num(shape.embed) : "—"],
      ["واژگان", shape.vocab ? num(shape.vocab) : "—"],
      ["پنجرهٔ متن", card.context ? `${num(card.context)} توکن` : "—"],
      ["زمان آموزش", metrics.trained_seconds ? `${num(metrics.trained_seconds / 60, 0)} دقیقه` : "—"],
    ]);

    const set = (key, value) => {
      const cell = document.querySelector(`[data-eval='${key}']`);
      if (cell) cell.textContent = value;
    };
    set("val_loss", num(metrics.val_loss, 3));
    set("ppl", num(metrics.ppl, 1));
    set("bpc", num(metrics.bits_per_char, 3));
    set("tokens", metrics.tokens_seen ? `${num(metrics.tokens_seen / 1e6, 2)} میلیون` : "—");
    set("steps", metrics.steps ? num(metrics.steps) : "—");
    set("context", card.context ? num(card.context) : "—");
  }

  function renderArchive(list) {
    const previous = (list || []).find((m) => m.id === "rayan-1-small") || (list || [])[0];
    if (!previous) return;
    const card = document.querySelector("[data-role='archive']");
    if (card) card.hidden = false;
    const name = $("#archive-name");
    if (name) name.textContent = previous.name || "نسخهٔ قبلی";
    const badge = $("#archive-badge");
    if (badge) badge.textContent = previous.tagline || "قبلی";
    const desc = $("#archive-desc");
    if (desc) desc.textContent = previous.desc || "";
    fillFacts($("#archive-facts"), [
      ["پارامترها", previous.params ? `${num(previous.params / 1e6, 1)} میلیون` : "—"],
      ["پنجرهٔ متن", previous.context ? `${num(previous.context)} توکن` : "—"],
      ["وضعیت", previous.status === "archived" ? "بازنشسته" : "—"],
    ]);
  }

  async function loadCard() {
    try {
      const data = await request("/api/model/card");
      renderModel(data.model);
      renderArchive(data.archive);
    } catch { /* نسخهٔ استاتیک */ }
  }

  async function loadBench() {
    try {
      const data = await request("/api/benchmark");
      const acc = data.accuracy || {};
      const set = (key, text) => {
        const cell = document.querySelector(`[data-bench='${key}']`);
        if (cell) cell.textContent = text;
      };
      if (typeof acc.tools_percent === "number") set("tools_percent", `${fa(acc.tools_percent.toFixed(1))}٪`);
      if (typeof acc.clock_percent === "number") set("clock_percent", `${fa(acc.clock_percent.toFixed(1))}٪`);
      if (typeof acc.normalize_percent === "number") set("normalize_percent", `${fa(acc.normalize_percent.toFixed(1))}٪`);
      if (typeof acc.generation_percent === "number") set("generation_percent", `${fa(acc.generation_percent.toFixed(1))}٪`);
    } catch { /* نسخهٔ استاتیک */ }
  }

  document.addEventListener("DOMContentLoaded", () => { loadCard(); loadBench(); });
})();
