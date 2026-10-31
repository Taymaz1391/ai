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

  document.addEventListener("DOMContentLoaded", loadLive);
})();
