/* رایان — ابزارهای مشترک رابط کاربری */
(function () {
  "use strict";

  const cfg = window.RAYAN_CONFIG || {};
  window.RAYAN = window.RAYAN || {};

  const faNumber = new Intl.NumberFormat("fa-IR");
  const faDigits = (value) =>
    String(value).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);

  const nf = (value, digits) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return "—";
    return digits === undefined ? faNumber.format(num) : num.toLocaleString("fa-IR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  };

  const compact = (value) => {
    const num = Number(value) || 0;
    if (num >= 1e9) return `${nf(num / 1e9, 1)} میلیارد`;
    if (num >= 1e6) return `${nf(num / 1e6, 1)} میلیون`;
    if (num >= 1e3) return `${nf(num / 1e3, 1)} هزار`;
    return nf(num);
  };

  const duration = (seconds) => {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    if (s < 60) return `${nf(s)} ثانیه`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${nf(m)} دقیقه`;
    const h = Math.floor(m / 60);
    return `${nf(h)} ساعت و ${nf(m % 60)} دقیقه`;
  };

  const timeAgo = (epoch) => {
    const s = (Date.now() / 1000) - Number(epoch || 0);
    if (s < 60) return "همین حالا";
    if (s < 3600) return `${nf(Math.floor(s / 60))} دقیقه پیش`;
    if (s < 86400) return `${nf(Math.floor(s / 3600))} ساعت پیش`;
    if (s < 86400 * 7) return `${nf(Math.floor(s / 86400))} روز پیش`;
    try {
      return new Date(epoch * 1000).toLocaleDateString("fa-IR", { day: "numeric", month: "long" });
    } catch {
      return "";
    }
  };

  const apiBase = (cfg.apiBase || "").replace(/\/$/, "");

  async function request(path, options = {}) {
    const url = `${apiBase}${path}`;
    const opts = Object.assign({ credentials: "include", headers: {} }, options);
    if (opts.body && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
      opts.headers["Content-Type"] = "application/json";
    }
    let res;
    try {
      res = await fetch(url, opts);
    } catch (err) {
      const error = new Error("اتصال به سرور برقرار نشد. اینترنت یا آدرس سرور را بررسی کنید.");
      error.offline = true;
      throw error;
    }
    const type = res.headers.get("content-type") || "";
    let data = null;
    if (type.includes("application/json")) {
      try { data = await res.json(); } catch { data = null; }
    }
    if (!res.ok) {
      const detail = data && (data.detail || data.error);
      const message = typeof detail === "string" ? detail
        : Array.isArray(detail) ? detail.map((d) => d.msg).join("، ")
        : `خطای سرور (${res.status})`;
      const error = new Error(message);
      error.status = res.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function toast(message, kind = "") {
    let stack = $(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("role", "status");
      stack.setAttribute("aria-live", "polite");
      document.body.append(stack);
    }
    const el = document.createElement("div");
    el.className = `toast ${kind ? `is-${kind}` : ""}`;
    el.textContent = message;
    stack.append(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(8px)";
      el.style.transition = "0.3s";
      setTimeout(() => el.remove(), 320);
    }, 3800);
  }

  function initNav() {
    const nav = $(".nav");
    if (!nav) return;
    let toggle = $(".nav-toggle", nav);
    if (!toggle) {
      toggle = document.createElement("button");
      toggle.className = "nav-toggle";
      toggle.setAttribute("aria-label", "منو");
      toggle.setAttribute("aria-expanded", "false");
      toggle.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
      const actions = $(".nav-actions", nav) || nav;
      actions.append(toggle);
    }
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    const onScroll = () => nav.classList.toggle("is-scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    $$(".nav-links a").forEach((link) => {
      if (link.getAttribute("href") === location.pathname) link.classList.add("is-active");
    });
  }

  function initReveal() {
    const items = $$(".reveal");
    if (!items.length) return;
    if (!("IntersectionObserver" in window)) {
      items.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -12% 0px", threshold: 0.05 });
    items.forEach((el) => io.observe(el));
  }

  function initFaq() {
    $$(".faq-item").forEach((item) => {
      const q = $(".faq-q", item);
      if (!q) return;
      q.addEventListener("click", () => {
        const isOpen = item.classList.contains("is-open");
        $$(".faq-item").forEach((other) => {
          other.classList.remove("is-open");
          const btn = $(".faq-q", other);
          if (btn) btn.setAttribute("aria-expanded", "false");
        });
        if (!isOpen) {
          item.classList.add("is-open");
          q.setAttribute("aria-expanded", "true");
        }
      });
    });
  }

  let authCache = null;
  async function me(force = false) {
    if (authCache && !force) return authCache;
    try {
      authCache = await request("/api/auth/me");
    } catch {
      authCache = { user: null, plan: "guest", usage: null, offline: true };
    }
    return authCache;
  }

  function initials(name) {
    const clean = (name || "").trim();
    if (!clean) return "؟";
    const parts = clean.split(/\s+/);
    return (parts[0][0] + (parts[1] ? parts[1][0] : "")).toUpperCase();
  }

  async function applyAuthChrome() {
    const state = await me();
    $$("[data-auth='guest']").forEach((el) => { el.hidden = !!state.user; });
    $$("[data-auth='user']").forEach((el) => { el.hidden = !state.user; });
    $$("[data-admin-link]").forEach((node) => {
      node.hidden = !(state.user && state.user.plan === "admin");
    });
    if (state.user) {
      const display = state.user.name || state.user.email.split("@")[0];
      $$("[data-user-name]").forEach((el) => { el.textContent = display; });
      const planLabel = { free: "رایگان", pro: "حرفه‌ای", admin: "مدیر", banned: "مسدود" };
      $$("[data-user-plan]").forEach((el) => {
        el.textContent = planLabel[state.user.plan] || "رایگان";
      });
      $$("[data-user-initials]").forEach((el) => {
        el.textContent = initials(state.user.name || state.user.email);
      });
    }
    return state;
  }

  async function logout() {
    try {
      await request("/api/auth/logout", { method: "POST" });
    } catch { /* بی‌اهمیت */ }
    authCache = null;
    location.href = "/";
  }

  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.getAttribute("data-action");
    if (action === "logout") {
      event.preventDefault();
      logout();
    }
  });

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    try { document.execCommand("copy"); } catch { /* نادیده */ }
    area.remove();
    return Promise.resolve();
  }

  Object.assign(window.RAYAN, {
    apiBase, request, $, $$, toast, nf, faDigits, compact, duration, timeAgo,
    me, logout, applyAuthChrome, copyText, initials,
    applyTheme, toggleTheme, preferredTheme, orbState, icon, hydrateIcons, asset,
    initOrbs,
    config: cfg,
    href(path) { return `${apiBase}${path}`; },
  });


  // ------------------------------------------------------------- تم و برند
  const THEMES = ["light", "dark"];
  function preferredTheme() {
    let saved = null;
    try { saved = localStorage.getItem("rayan.theme"); } catch { /* حالت خصوصی */ }
    if (THEMES.includes(saved)) return saved;
    return "light";   // پیش‌فرض محصول: روشن
  }

  function applyTheme(theme) {
    const value = THEMES.includes(theme) ? theme : "light";
    document.documentElement.dataset.theme = value;
    try { localStorage.setItem("rayan.theme", value); } catch { /* نادیده */ }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", value === "dark" ? "#050b1a" : "#ffffff");
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      btn.setAttribute("aria-pressed", String(value === "dark"));
      btn.setAttribute("title", value === "dark" ? "حالت روشن" : "حالت تیره");
      const sun = btn.querySelector("[data-icon='sun']");
      const moon = btn.querySelector("[data-icon='moon']");
      if (sun) sun.hidden = value === "dark";
      if (moon) moon.hidden = value !== "dark";
    });
    document.dispatchEvent(new CustomEvent("rayan:theme", { detail: { theme: value } }));
  }

  function toggleTheme() {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  }

  function themeButton() {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "icon-btn theme-toggle";
    btn.dataset.themeToggle = "";
    btn.setAttribute("aria-label", "تغییر تم");
    btn.innerHTML =
      '<svg data-icon="sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>' +
      '<svg data-icon="moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" hidden><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8Z"/></svg>';
    btn.addEventListener("click", toggleTheme);
    return btn;
  }

  function initTheme() {
    applyTheme(preferredTheme());
    document.querySelectorAll(".nav-actions, .chat-nav-actions, .topbar-actions").forEach((box) => {
      if (box.querySelector("[data-theme-toggle]")) return;
      box.insertBefore(themeButton(), box.firstChild);
    });
    if (!document.querySelector("[data-theme-toggle]")) {
      const nav = document.querySelector(".nav .nav-inner");
      if (nav) nav.append(themeButton());
    }
  }

  // ------------------------------------------------------------- چشمک orb
  function initOrbs() {
    document.querySelectorAll(".orb-live").forEach((orb) => {
      if (orb.dataset.ready) return;
      orb.dataset.ready = "1";
      orb.setAttribute("role", "img");
      orb.setAttribute("aria-label", "رایان");
      // چشم‌ها در یک لایه جمع می‌شوند تا هنگام «نوشتن» کل چهره بچرخد
      if (!orb.querySelector(".face")) {
        const lids = [...orb.querySelectorAll(".lid")];
        if (lids.length) {
          const face = document.createElement("span");
          face.className = "face";
          lids[0].before(face);
          lids.forEach((lid) => face.append(lid));
        }
      }
      const blink = () => orb.classList.add("is-blinking");
      orb.addEventListener("animationend", () => orb.classList.remove("is-blinking"));
      orb.addEventListener("click", () => {
        orb.classList.remove("is-blinking");
        void orb.offsetWidth;
        orb.classList.add("is-blinking");
        orb.dispatchEvent(new CustomEvent("rayan:orb-wink", { bubbles: true }));
      });
      orb.blinkTimer = setInterval(blink, 6400 + Math.random() * 1400);
    });
  }

  function orbState(state, host) {
    const target = host || document.querySelector(".orb-live");
    if (!target) return;
    target.dataset.state = state || "";
  }

  // ---------------------------------------------------------- اسپلش آغازین
  function initSplash() {
    if (document.documentElement.dataset.noSplash === "1") return;
    const staticMode = (window.RAYAN_CONFIG || {}).static;
    if (staticMode && document.body.dataset.splash === "0") return;
    let seen = false;
    try { seen = sessionStorage.getItem("rayan.splash") === "1"; } catch { /* نادیده */ }
    if (seen) return;
    try { sessionStorage.setItem("rayan.splash", "1"); } catch { /* نادیده */ }
    const splash = document.createElement("div");
    splash.className = "splash";
    splash.innerHTML =
      '<img class="splash-art" src="' + asset("brand/logotype-stack-white.png") + '" alt="رایان" />' +
      '<div class="splash-bar"><i></i></div>';
    document.body.append(splash);
    window.setTimeout(() => splash.classList.add("is-out"), 1250);
    window.setTimeout(() => splash.remove(), 1900);
  }

  function asset(path) {
    const base = (document.body.dataset.assetBase || "/static/assets/").replace(/\/?$/, "/");
    return base + String(path).replace(/^\//, "");
  }

  // --------------------------------------------------------------- آیکون‌ها
  const ICON_PATHS = {
    send: '<path d="M4.5 12h15M13 5.5 19.5 12 13 18.5"/>',
    stop: '<rect x="7" y="7" width="10" height="10" rx="2.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M15 6.5A2.5 2.5 0 0 0 12.5 4h-6A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15"/>',
    download: '<path d="M12 4v11m0 0 4-4m-4 4-4-4M5 19h14"/>',
    share: '<circle cx="17.5" cy="6.5" r="2.5"/><circle cx="6.5" cy="12" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/><path d="m9 10.8 6-3.1M9 13.2l6 3.1"/>',
    trash: '<path d="M5 7h14M10 7V5.5A1.5 1.5 0 0 1 11.5 4h1A1.5 1.5 0 0 1 14 5.5V7m-7 0 .8 11a2 2 0 0 0 2 1.9h4.4a2 2 0 0 0 2-1.9L17 7"/>',
    pin: '<path d="M9 4h6l-1 6 3 3H7l3-3-1-6ZM12 13v7"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.7 8.6a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    sparkle: '<path d="M12 3.5 13.7 9l5.5 1.7-5.5 1.7L12 18l-1.7-5.6L4.8 10.7 10.3 9 12 3.5Z"/><path d="M18.5 4v3M17 5.5h3"/>',
    image: '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="8.8" cy="9.6" r="1.6"/><path d="m4.5 17 4.6-4.4a2 2 0 0 1 2.7 0l3 2.9m0 0 2-1.9a2 2 0 0 1 2.7 0l2 1.9"/>',
    code: '<path d="m9 8-4 4 4 4M15 8l4 4-4 4"/>',
    file: '<path d="M14 4H7.5A1.5 1.5 0 0 0 6 5.5v13A1.5 1.5 0 0 0 7.5 20h9a1.5 1.5 0 0 0 1.5-1.5V8l-4-4Z"/><path d="M14 4v4h4"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.3 3.6 5.3 3.6 8.5s-1.2 6.2-3.6 8.5c-2.4-2.3-3.6-5.3-3.6-8.5S9.6 5.8 12 3.5Z"/>',
    mic: '<rect x="9" y="3.5" width="6" height="10" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    arrow: '<path d="M19 12H5m0 0 6-6m-6 6 6 6"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    shield: '<path d="M12 3.5 5 6v6c0 4 3 7 7 8.5 4-1.5 7-4.5 7-8.5V6l-7-2.5Z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
    users: '<circle cx="9" cy="8.5" r="3.5"/><path d="M3.5 20c0-3 2.5-5.5 5.5-5.5s5.5 2.5 5.5 5.5"/><path d="M16 5.2a3.5 3.5 0 0 1 0 6.6M17.5 14.8c1.8.7 3 2.5 3 5.2"/>',
    chart: '<path d="M4 20V4m0 16h16"/><path d="M8 16v-5M12.5 16V7M17 16v-3"/>',
    megaphone: '<path d="M4 10.5v3a2 2 0 0 0 2 2h1.5l7 4V4.5l-7 4H6a2 2 0 0 0-2 2Z"/><path d="M18 8.5a4.5 4.5 0 0 1 0 7"/>',
    gift: '<rect x="3.5" y="8.5" width="17" height="12" rx="2.5"/><path d="M3.5 12.5h17M12 8.5V20"/><path d="M12 8.5C10 8.5 7 8 7 5.8A2.3 2.3 0 0 1 9.3 3.5C11.5 3.5 12 6.5 12 8.5Zm0 0c2 0 5-.5 5-2.7a2.3 2.3 0 0 0-2.3-2.3C12.5 3.5 12 6.5 12 8.5Z"/>',
  };

  function icon(name, size = 20, extra = "") {
    const body = ICON_PATHS[name];
    if (!body) return "";
    return `<svg class="rayan-icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" ` +
      `stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" ` +
      `aria-hidden="true" ${extra}>${body}</svg>`;
  }

  function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach((el) => {
      const name = el.dataset.icon;
      if (!ICON_PATHS[name] || el.dataset.hydrated === "1") return;
      el.dataset.hydrated = "1";
      el.innerHTML = icon(name, Number(el.dataset.size || 20));
      el.classList.add("icon-slot");
    });
  }

  function staticBanner() {
    const cfg = window.RAYAN_CONFIG || {};
    if (!cfg.static || document.getElementById("static-banner")) return;
    const bar = document.createElement("div");
    bar.id = "static-banner";
    bar.className = "static-banner";
    bar.innerHTML = 'نسخهٔ نمایشی روی GitHub Pages — گفتگو به سرور نیاز دارد. ' +
      '<a href="https://github.com/Taymaz1391/ai#%D8%B4%D8%B1%D9%88%D8%B9-%D8%B3%D8%B1%DB%8C%D8%B9" rel="noopener">اجرا در چند دقیقه</a>';
    document.body.prepend(bar);
  }

  async function initStatus() {
    let data;
    try {
      data = await (await fetch("/api/status", { credentials: "include" })).json();
    } catch {
      return;
    }
    window.RAYAN.status = data;
    if (data.maintenance) {
      const banner = document.createElement("div");
      banner.className = "notice is-warn maintenance-bar";
      banner.innerHTML = "🛠 سرویس در حال به‌روزرسانی است؛ ممکن است گفتگو موقتاً پاسخ ندهد.";
      document.body.prepend(banner);
    } else if (data.announcement) {
      const banner = document.createElement("div");
      banner.className = "notice is-ok announce-bar";
      banner.innerHTML = '<span>' + String(data.announcement).replace(/[<>&]/g, "") + "</span>" +
        '<button type="button" class="icon-btn" style="width:26px;height:26px;margin-inline-start:auto" aria-label="بستن">✕</button>';
      banner.querySelector("button").addEventListener("click", () => banner.remove());
      document.body.prepend(banner);
    }
    const pill = document.querySelector("[data-model-status]");
    if (pill) {
      pill.textContent = data.model_loaded ? "مدل فعال" : "مدل در دسترس نیست";
      pill.className = "pill " + (data.model_loaded ? "is-ok" : "is-warn");
    }
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    if ((window.RAYAN_CONFIG || {}).static) return;
    if (location.protocol !== "https:" && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => { /* اختیاری */ });
    });
  }

  // تم پیش از رندر اعمال می‌شود تا پرش رنگ نداشته باشیم
  try { applyTheme(preferredTheme()); } catch { /* نادیده */ }

  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    hydrateIcons();
    initNav();
    initReveal();
    initFaq();
    applyAuthChrome();
    initOrbs();
    initSplash();
    initStatus();
    staticBanner();
    registerServiceWorker();
  });
})();
