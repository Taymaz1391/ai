/* رایان — صفحهٔ مدل‌ها: اعداد زنده از API */
(function () {
  "use strict";
  const { $, request, nf } = window.RAYAN;

  async function loadLive() {
    try {
      const [health, model] = await Promise.all([
        request("/api/health"),
        request("/api/model").catch(() => null),
      ]);
      const meta = model?.meta || {};
      const ev = model?.metrics?.best_eval || health.latest_eval;
      if (ev) {
        const cells = document.querySelectorAll("#eval-table tbody tr");
        if (cells[0]) cells[0].children[1].textContent = `${nf(ev.val_loss, 2)} nats/token`;
        if (cells[1]) cells[1].children[1].textContent = nf(ev.ppl, 1);
        if (cells[2] && ev.bits_per_char) cells[2].children[1].textContent = nf(ev.bits_per_char, 2);
        const ppl = $("#m-ppl");
        if (ppl) ppl.textContent = nf(ev.ppl, 1);
      }
      const tokens = health.latest_train?.tokens || meta.tokens_seen;
      if (tokens) {
        const rows = document.querySelectorAll("#eval-table tbody tr");
        const last = rows[rows.length - 1];
        if (last) last.children[1].textContent = nf(tokens);
      }
    } catch { /* نسخهٔ استاتیک: اعداد ثابت می‌مانند */ }
  }

  async function loadBench() {
    try {
      const data = await request("/api/benchmark");
      const acc = data.accuracy || {};
      const fa = (value) => String(value).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
      const set = (key, text) => {
        const cell = document.querySelector(`[data-bench="${key}"]`);
        if (cell) cell.textContent = text;
      };
      if (typeof acc.tools_percent === "number") set("tools_percent", `${fa(acc.tools_percent.toFixed(1))}٪`);
      if (typeof acc.clock_percent === "number") set("clock_percent", `${fa(acc.clock_percent.toFixed(1))}٪`);
      if (typeof acc.normalize_percent === "number") set("normalize_percent", `${fa(acc.normalize_percent.toFixed(1))}٪`);
      if (typeof acc.generation_percent === "number") set("generation_percent", `${fa(acc.generation_percent.toFixed(1))}٪`);
      const lat = data.latency?.generation_p50_s;
      if (typeof lat === "number") set("latency", `${fa(lat.toFixed(2))} ثانیه`);
    } catch { /* نسخهٔ استاتیک */ }
  }

  document.addEventListener("DOMContentLoaded", () => { loadLive(); loadBench(); });
})();
