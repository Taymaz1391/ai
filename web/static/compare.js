/* رایان — صفحهٔ میزان: همهٔ عددها از API خود سرویس می‌آید */
(function () {
  "use strict";
  const { $, request, nf } = window.RAYAN;

  function set(id, text) {
    const el = $(`#${id}`);
    if (el) el.textContent = text;
  }

  async function load() {
    try {
      const data = await request("/api/compare");
      const speed = data.speed || {};
      if (typeof speed.median_s === "number") {
        const official = speed.source === "benchmark";
        set("m-latency", official ? `${nf(speed.median_s, 2)}` : nf(speed.median_s, 2));
        set("m-p95", typeof speed.p95_s === "number" ? nf(speed.p95_s, 2) : "—");
        set("m-rate", speed.per_minute === null ? "—" : nf(speed.per_minute, 0));
        set("c-latency", `${nf(speed.median_s, 1)} ثانیه`);
      }
      if (data.uptime_pct) set("m-score", `${nf(data.uptime_pct, 1)}٪`);

      const arena = data.arena || {};
      const table = $("#arena-table tbody");
      if (table && arena.by_category) {
        table.innerHTML = Object.entries(arena.by_category).map(([cat, score]) =>
          `<tr><td>${cat}</td><td><b>${nf(score, 0)}٪</b></td></tr>`).join("");
      }
      if (arena.score) set("m-score", `${nf(arena.score, 0)}٪`);
      if (arena.score) set("suite-note", `${nf(arena.tasks, 0)} پرسش فارسی در شش دسته — امتیاز کل: ${nf(arena.score, 0)}٪`);
      const note = $("#arena-note");
      if (note) note.textContent = arena.note || "";
    } catch {
      const note = $("#arena-note");
      if (note) note.textContent = "آمار زنده در دسترس نیست؛ اعداد پیش‌فرض نمایش داده می‌شود.";
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
