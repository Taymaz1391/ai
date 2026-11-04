/* رایان — صفحهٔ فرود */
(function () {
  "use strict";
  const { $, $$, request, nf, compact, toast } = window.RAYAN;

  async function loadHealth() {
    try {
      const health = await request("/api/health");
      const status = $("#hero-status");
      let line = health.ok ? "آماده به گفتگو" : "در حال آماده‌سازی…";
      if (health.ok) {
        // نام و اندازهٔ همان مدلی که واقعاً در حال پاسخ‌دادن است، نه جملهٔ کلی
        try {
          const card = await request("/api/model/card");
          const model = (card && card.model) || {};
          const params = Number(model.params || 0);
          if (model.name) {
            line = `مدل ${model.name}` +
              (params ? ` · ${compact(params)} پارامتر` : "") +
              " · آماده";
          }
        } catch { /* کارتِ مدل در دسترس نیست؛ جملهٔ کلی می‌ماند */ }
      }
      if (status) status.textContent = line;
      try {
        const cmp = await request("/api/compare");
        if (cmp && cmp.speed && cmp.speed.median_s) {
          const latency = $("#stat-latency");
          if (latency) latency.textContent = nf(cmp.speed.median_s, 2);
          const row = $("#arena-latency");
          if (row) row.textContent = `${nf(cmp.speed.median_s, 2)} ثانیه (میانه)`;
        }
        if (cmp && cmp.arena && cmp.arena.score) {
          const score = $("#arena-score");
          if (score) score.textContent = `${nf(cmp.arena.score, 0)}٪ از ${nf(cmp.arena.tasks, 0)} پرسش`;
          const note = $("#arena-note");
          if (note) {
            note.textContent = `آزمون فارسی ${nf(cmp.arena.tasks, 0)} پرسشی با ` +
              `${nf(cmp.arena.score, 0)}٪ امتیاز و میانهٔ پاسخ ` +
              `${nf((cmp.speed || {}).median_s || 0, 2)} ثانیه — سنجش واقعی روی همین سرویس.`;
          }
        }
      } catch { /* عدد پیش‌فرض می‌ماند */ }
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
      // فقط پاسخ‌هایی که سرویس خودش تأیید کرده (verified) روی صفحه می‌آیند؛
      // خروجیِ خام و درهمِ مدل هرگز جای نمونهٔ واقعی نمی‌نشیند.
      const examples = (data.examples || []).filter((ex) => ex.verified && ex.text);
      if (!examples.length) return;

      const labels = { chat: "پاسخ دانشی", poem: "شعر", poetry: "شعر",
                       continue: "ادامهٔ متن", health: "سلامت", math: "حساب",
                       code: "کد", translate: "ترجمه", guide: "راهنما" };
      const first = examples[0];
      const answer = $("#preview-answer");
      if (answer && first.text) {
        answer.textContent = first.text;
        const prompt = document.querySelector(".preview-msg.user .bubble");
        if (prompt) prompt.textContent = first.prompt;
      }

      const list = $("#showcase-list");
      if (!list) return;
      list.innerHTML = "";
      examples.slice(0, 3).forEach((ex) => {
        const card = document.createElement("article");
        card.className = "showcase-item";
        const q = document.createElement("span");
        q.className = "q";
        q.textContent = labels[ex.mode] || labels.chat;
        const p = document.createElement("p");
        p.className = "pq";
        p.textContent = ex.prompt || "";
        const a = document.createElement("p");
        a.className = "a";
        a.textContent = ex.text || "";
        const meta = document.createElement("div");
        meta.className = "m";
        const badge = document.createElement("span");
        badge.className = "tag tag-blue";
        badge.textContent = "پاسخ واقعی";
        meta.append(badge);
        if (ex.seconds) {
          const t = document.createElement("span");
          t.textContent = `${nf(ex.seconds, 2)} ثانیه`;
          meta.append(t);
        }
        card.append(q, p, a, meta);
        list.append(card);
      });
      const section = $("#showcase");
      if (section) section.hidden = false;
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
