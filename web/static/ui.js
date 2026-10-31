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
    if (state.user) {
      const display = state.user.name || state.user.email.split("@")[0];
      $$("[data-user-name]").forEach((el) => { el.textContent = display; });
      $$("[data-user-plan]").forEach((el) => {
        el.textContent = state.user.plan === "pro" ? "حرفه‌ای" : "رایگان";
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
    config: cfg,
    href(path) { return `${apiBase}${path}`; },
  });

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

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    if ((window.RAYAN_CONFIG || {}).static) return;
    if (location.protocol !== "https:" && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => { /* اختیاری */ });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initNav();
    initReveal();
    initFaq();
    applyAuthChrome();
    staticBanner();
    registerServiceWorker();
  });
})();
