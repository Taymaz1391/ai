/* رایان — پنل تنظیمات */
(function () {
  "use strict";
  const R = window.RAYAN;
  const { $, $$, request, toast, faDigits } = R;

  const KEY = {
    temp: "rayan.set.temp",
    tokens: "rayan.set.tokens",
    topp: "rayan.set.topp",
    enter: "rayan.set.enter",
    web: "rayan.set.web",
    reduce: "rayan.set.reduce",
    font: "rayan.set.font",
  };
  const DEFAULTS = { temp: 0.82, tokens: 110, topp: 0.9, enter: true, web: false, reduce: false, font: 100 };

  const read = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch { return fallback; }
  };
  const write = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* نادیده */ }
  };

  let state = { user: null, verified: false, mailReady: false };

  // ---------------------------------------------------------------- بخش‌ها
  function initTabs() {
    $$(".panel-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        const name = tab.dataset.panel;
        $$(".panel-tab").forEach((t) => t.classList.toggle("is-active", t === tab));
        $$(".panel-pane").forEach((pane) => {
          pane.classList.toggle("is-active", pane.dataset.pane === name);
        });
        if (history.replaceState) history.replaceState(null, "", `#${name}`);
      });
    });
    const hash = (location.hash || "").replace("#", "");
    if (hash) {
      const tab = $(`.panel-tab[data-panel="${hash}"]`);
      if (tab && !tab.hidden) tab.click();
    }
  }

  // ---------------------------------------------------------------- حساب
  async function loadMe(force = false) {
    let data;
    try {
      data = await R.me(force);
    } catch {
      data = { user: null };
    }
    state.user = data && data.user ? data.user : null;
    renderAccount();
    renderEmail();
    return data;
  }

  function renderAccount() {
    const user = state.user;
    const nameInput = $("#profile-name");
    const emailInput = $("#profile-email");
    const loggedIn = !!(user && user.id);
    if (nameInput) {
      nameInput.value = user ? (user.name || "") : "";
      nameInput.disabled = !loggedIn;
    }
    if (emailInput) emailInput.value = user ? (user.email || "") : "";
    $("#save-profile").disabled = !loggedIn;
    $("#logout-btn").hidden = !loggedIn;
    const note = $("[data-user-plan-note]");
    if (note) {
      const label = { free: "حساب رایگان", pro: "اشتراک حرفه‌ای", admin: "مدیر", owner: "مالک سرویس" };
      note.textContent = loggedIn
        ? `${label[user.plan] || "حساب رایگان"}${user.verified ? " · ایمیل تأییدشده" : " · ایمیل تأییدنشده"}`
        : "هنوز وارد نشده‌ای";
    }
  }

  function initProfile() {
    const form = $("#profile-form");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = ($("#profile-name").value || "").trim();
        if (!value) { toast("نام نمایشی را بنویس.", "warn"); return; }
        try {
          const res = await request("/api/auth/me", { method: "PATCH", body: { name: value } });
          state.user = res.user;
          R.me(true);
          renderAccount();
          toast("نام ذخیره شد.", "ok");
        } catch (err) {
          toast(err.message || "ذخیره نشد.", "error");
        }
      });
    }

    const pw = $("#password-form");
    if (pw) {
      pw.addEventListener("submit", async (event) => {
        event.preventDefault();
        const current = $("#pw-current").value;
        const next = $("#pw-new").value;
        const note = $("#pw-note");
        if (next.length < 8) { note.textContent = "گذرواژهٔ تازه کوتاه است."; return; }
        try {
          await request("/api/auth/password", { method: "POST", body: { current, new: next } });
          pw.reset();
          note.textContent = "گذرواژه تغییر کرد.";
          toast("گذرواژهٔ تازه فعال شد.", "ok");
        } catch (err) {
          note.textContent = err.message || "تغییر نکرد.";
        }
      });
    }

    const out = $("#logout-btn");
    if (out) {
      out.addEventListener("click", async () => {
        try { await R.logout(); } catch { /* نادیده */ }
        location.href = "/";
      });
    }
  }

  // ---------------------------------------------------------------- ایمیل
  function renderEmail() {
    const user = state.user;
    $("#verify-email").textContent = user ? (user.email || "—") : "—";
    const badge = $("#verify-badge");
    const send = $("#send-code");
    const form = $("#verify-form");
    const note = $("#verify-note");
    const service = $("#mail-service");
    if (!user) {
      badge.className = "badge";
      badge.textContent = "وارد نشده‌ای";
      send.disabled = true;
      return;
    }
    if (user.verified) {
      badge.className = "badge ok";
      badge.textContent = "تأییدشده";
      send.disabled = true;
      form.querySelectorAll("input,button").forEach((el) => { el.disabled = true; });
      note.textContent = "ایمیلت تأیید شده است.";
    } else {
      badge.className = "badge warn";
      badge.textContent = "تأییدنشده";
      send.disabled = false;
    }
    if (service) {
      service.textContent = state.mailReady
        ? "سرویس ارسال ایمیل فعال است؛ اگر پیام در صندوق ورودی نبود، پوشهٔ هرزنامه را هم ببین."
        : "ارسال ایمیل هنوز روی این سرور پیکربندی نشده؛ تا آن زمان کد ارسال نمی‌شود.";
    }
  }

  async function loadVerification() {
    try {
      const data = await request("/api/auth/verification");
      state.mailReady = !!(data.service && data.service.configured);
      state.verified = !!data.verified;
      if (state.user) state.user.verified = state.verified ? 1 : 0;
    } catch { /* سرویس در دسترس نیست */ }
    renderEmail();
  }

  function initEmail() {
    const send = $("#send-code");
    if (send) {
      send.addEventListener("click", async () => {
        const note = $("#verify-note");
        send.disabled = true;
        note.textContent = "در حال ارسال…";
        try {
          const res = await request("/api/auth/verification/send", { method: "POST", body: {} });
          if (res.already) {
            note.textContent = "ایمیلت از قبل تأیید شده است.";
            send.disabled = true;
            return;
          }
          note.textContent = res.dev_code
            ? `کد آزمایشی: ${faDigits(res.dev_code)}`
            : "کد به ایمیلت فرستاده شد.";
          startCooldown(send, 60);
        } catch (err) {
          note.textContent = err.message || "ارسال نشد.";
          send.disabled = false;
        }
      });
    }

    const form = $("#verify-form");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const code = ($("#verify-code").value || "").replace(/\D/g, "");
        const note = $("#verify-note");
        if (code.length !== 6) { note.textContent = "کد شش‌رقمی را کامل بنویس."; return; }
        try {
          await request("/api/auth/verification/confirm", { method: "POST", body: { code } });
          state.verified = true;
          if (state.user) state.user.verified = 1;
          R.me(true);
          renderEmail();
          note.textContent = "ایمیل تأیید شد.";
          toast("حسابت تأیید شد.", "ok");
          const badge = $("[data-verified]");
          if (badge) badge.hidden = false;
        } catch (err) {
          note.textContent = err.message || "کد پذیرفته نشد.";
        }
      });
    }
  }

  function startCooldown(button, seconds) {
    const original = "ارسال کد تأیید";
    let left = seconds;
    button.textContent = `${faDigits(left)} ثانیه`;
    const timer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(timer);
        button.textContent = original;
        button.disabled = false;
        return;
      }
      button.textContent = `${faDigits(left)} ثانیه`;
    }, 1000);
  }

  // ---------------------------------------------------------------- گفتگو
  function paintChat() {
    const temp = read(KEY.temp, DEFAULTS.temp);
    const tokens = read(KEY.tokens, DEFAULTS.tokens);
    const topp = read(KEY.topp, DEFAULTS.topp);
    $("#set-temp").value = temp;
    $("#set-tokens").value = tokens;
    $("#set-topp").value = topp;
    $("#temp-value").textContent = faDigits(Number(temp).toFixed(2).replace(".", "٫"));
    $("#tokens-value").textContent = `${faDigits(tokens)} توکن`;
    $("#topp-value").textContent = faDigits(Number(topp).toFixed(2).replace(".", "٫"));
    $("#set-enter").checked = read(KEY.enter, DEFAULTS.enter);
    $("#set-web").checked = read(KEY.web, DEFAULTS.web);
  }

  function initChatSettings() {
    const bind = (id, key, label, format) => {
      const el = $(id);
      if (!el) return;
      el.addEventListener("input", () => {
        const value = Number(el.value);
        write(key, value);
        const out = $(label);
        if (out) out.textContent = format(value);
      });
    };
    bind("#set-temp", KEY.temp, "#temp-value", (v) => faDigits(v.toFixed(2).replace(".", "٫")));
    bind("#set-tokens", KEY.tokens, "#tokens-value", (v) => `${faDigits(v)} توکن`);
    bind("#set-topp", KEY.topp, "#topp-value", (v) => faDigits(v.toFixed(2).replace(".", "٫")));

    [["#set-enter", KEY.enter], ["#set-web", KEY.web]].forEach(([id, key]) => {
      const el = $(id);
      if (!el) return;
      el.addEventListener("change", () => { write(key, el.checked); toast("ذخیره شد.", "ok"); });
    });

    const reset = $("#reset-chat");
    if (reset) {
      reset.addEventListener("click", () => {
        Object.entries({ temp: KEY.temp, tokens: KEY.tokens, topp: KEY.topp, enter: KEY.enter, web: KEY.web })
          .forEach(([k, key]) => write(key, DEFAULTS[k]));
        paintChat();
        toast("به پیش‌فرض برگشت.", "ok");
      });
    }
  }

  // ---------------------------------------------------------------- ظاهر
  function applyLook() {
    const reduce = read(KEY.reduce, DEFAULTS.reduce);
    const font = read(KEY.font, DEFAULTS.font);
    document.documentElement.classList.toggle("reduce-motion", !!reduce);
    document.documentElement.style.setProperty("--font-scale", String(Number(font) / 100));
    $("#set-reduce").checked = !!reduce;
    $("#set-font").value = font;
    $("#font-value").textContent = `${faDigits(font)}٪`;
  }

  function initLook() {
    $("#set-reduce").addEventListener("change", (event) => {
      write(KEY.reduce, event.target.checked);
      applyLook();
    });
    $("#set-font").addEventListener("input", (event) => {
      write(KEY.font, Number(event.target.value));
      applyLook();
    });
    $("#reset-look").addEventListener("click", () => {
      write(KEY.reduce, DEFAULTS.reduce);
      write(KEY.font, DEFAULTS.font);
      applyLook();
    });
  }

  // ---------------------------------------------------------------- داده
  function initData() {
    const exp = $("#export-btn");
    if (exp) {
      exp.addEventListener("click", async () => {
        const note = $("#data-note");
        exp.disabled = true;
        note.textContent = "در حال گردآوری…";
        try {
          const list = await request("/api/conversations");
          const items = (list.conversations || list.items || []).slice(0, 100);
          const full = [];
          for (const conv of items) {
            try {
              full.push(await request(`/api/conversations/${conv.id}`));
            } catch { /* یک گفتگو رد شد */ }
          }
          const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), conversations: full }, null, 2)],
            { type: "application/json" });
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "rayan-conversations.json";
          a.click();
          setTimeout(() => URL.revokeObjectURL(a.href), 4000);
          note.textContent = `${faDigits(full.length)} گفتگو در فایل ذخیره شد.`;
        } catch (err) {
          note.textContent = err.message || "خروجی گرفته نشد.";
        } finally {
          exp.disabled = false;
        }
      });
    }

    const del = $("#delete-convs");
    if (del) {
      let armed = false;
      del.addEventListener("click", async () => {
        const note = $("#data-note");
        if (!armed) {
          armed = true;
          del.textContent = "مطمئنی؟ دوباره بزن";
          setTimeout(() => { armed = false; del.textContent = "پاک‌کردن همهٔ گفتگوها"; }, 5000);
          return;
        }
        try {
          await request("/api/conversations", { method: "DELETE" });
          note.textContent = "همهٔ گفتگوها پاک شد.";
          toast("گفتگوها پاک شدند.", "ok");
        } catch (err) {
          note.textContent = err.message || "پاک نشد.";
        }
        armed = false;
        del.textContent = "پاک‌کردن همهٔ گفتگوها";
      });
    }
  }

  // ---------------------------------------------------------------- راه‌اندازی
  document.addEventListener("DOMContentLoaded", async () => {
    initTabs();
    initProfile();
    initEmail();
    initChatSettings();
    initLook();
    initData();
    paintChat();
    applyLook();

    const data = await loadMe(true);
    await loadVerification();

    const isAdmin = !!(data && (data.plan === "admin" ||
      (data.user && (data.user.role === "owner" || data.user.plan === "admin"))));
    const tab = $("#tab-admin");
    if (tab) tab.hidden = !isAdmin;
    if (isAdmin) {
      const pane = $('.panel-pane[data-pane="admin"]');
      if (pane) pane.hidden = false;
    } else {
      const pane = $('.panel-pane[data-pane="admin"]');
      if (pane) pane.hidden = true;
    }

    // کاربری که وارد نشده، پیام روشن می‌بیند نه فرم بی‌اثر
    if (!state.user) {
      const lead = $("#email-lead");
      if (lead) {
        lead.innerHTML = 'برای استفاده از ایمیل و تأیید حساب، ابتدا <a href="chat.html">وارد شو یا حساب بساز</a>.';
      }
      $("#verify-form").querySelectorAll("input,button").forEach((el) => { el.disabled = true; });
    }
  });
})();
