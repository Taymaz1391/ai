/* رایان — صفحهٔ فرود */
(function () {
  "use strict";
  const { $, $$, request, nf, compact, toast } = window.RAYAN;

  async function loadHealth() {
    try {
      const health = await request("/api/health");
      const status = $("#hero-status");
      if (status) {
        const step = health.latest_train?.step || health.model?.step;
        status.textContent = health.ok
          ? `مدل آماده است · گام ${nf(step)} آموزش · ${health.training_active ? "در حال آموزش" : "پایدار"}`
          : "مدل در حال بارگذاری است…";
      }
      if (health.model?.params) {
        const params = $("#stat-params");
        if (params) params.textContent = `${nf(health.model.params / 1e6, 2)} میلیون`;
        const loss = $("#stat-loss");
        if (loss && health.model.val_loss) loss.textContent = nf(health.model.val_loss, 2);
      }
      const tokens = health.latest_train?.tokens;
      if (tokens) {
        const el = $("#stat-tokens");
        if (el) el.textContent = `${nf(tokens / 1e6, 1)} میلیون`;
      }
    } catch {
      const banner = $("#demo-banner");
      if (banner) banner.hidden = false;
      const status = $("#hero-status");
      if (status) status.textContent = "نمایش استاتیک · سرور در دسترس نیست";
    }
  }

  async function loadStats() {
    try {
      const data = await request("/api/stats");
      const s = data.stats || {};
      const set = (id, value) => { const el = $(id); if (el) el.textContent = value; };
      // صفر را به خط تیره تبدیل می‌کنیم تا استقرار تازه «خالی» به نظر نرسد
      const count = (value) => (Number(value) > 0 ? compact(value) : "—");
      set("#live-answers", count(s.answers));
      set("#live-users", count(s.users));
      set("#live-convs", count(s.conversations));
      const up = Number(data.uptime_s || 0);
      const days = up / 86400;
      set("#live-uptime", days >= 1 ? `${nf(days, 1)} روز` : `${nf(up / 3600, 1)} ساعت`);
    } catch { /* صفحهٔ استاتیک */ }
  }

  async function loadShowcase() {
    try {
      const data = await request("/api/showcase");
      const examples = (data.examples || []).slice(0, 3);
      if (!examples.length) return;
      const list = $("#showcase-list");
      if (!list) return;
      const labels = { chat: "گفتگو", poetry: "شعر", continue: "ادامهٔ متن" };
      list.innerHTML = "";
      examples.forEach((ex) => {
        const card = document.createElement("article");
        card.className = "showcase-item";
        const q = document.createElement("span");
        q.className = "q";
        q.textContent = `${labels[ex.mode] || ex.mode} · «${ex.prompt || "—"}»`;
        const a = document.createElement("p");
        a.className = "a";
        a.textContent = ex.text || "—";
        const meta = document.createElement("div");
        meta.className = "m";
        const t = document.createElement("span");
        t.textContent = `${nf(ex.tokens || 0)} توکن`;
        meta.append(t);
        if (ex.deep) {
          const badge = document.createElement("span");
          badge.className = "tag tag-blue";
          badge.textContent = "اندیشهٔ ژرف";
          meta.append(badge);
        }
        card.append(q, a, meta);
        list.append(card);
      });
      const first = examples.find((e) => e.mode === "chat" && (e.text || "").length > 30);
      if (first) {
        const answer = $("#preview-answer");
        if (answer) answer.textContent = first.text;
      }
    } catch { /* نسخهٔ استاتیک */ }
  }

  function initCta() {
    $$("a[href='/chat']").forEach((link) => {
      link.addEventListener("click", () => { /* عبور عادی */ });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    loadHealth();
    loadStats();
    loadShowcase();
    initCta();
    const params = new URLSearchParams(location.search);
    if (params.get("welcome") === "1") {
      toast("خوش آمدی! حسابت ساخته شد.", "ok");
      history.replaceState({}, "", "/");
    }
    if (params.get("loggedout") === "1") {
      toast("از حساب خارج شدی.", "");
      history.replaceState({}, "", "/");
    }
  });
})();
