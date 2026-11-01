/* رایان — کلاینت پنل مدیریت */
(function () {
  "use strict";
  const R = window.RAYAN || {};
  const { $, $$, nf, faDigits, timeAgo, toast } = R;
  const CSRF_KEY = "x-rayan-csrf";

  const state = { csrf: "", user: null, tab: "orders", overview: null, users: [], ads: [],
                  audit: [], orders: [] };

  async function api(path, options = {}) {
    const opts = Object.assign({ credentials: "include", headers: {} }, options);
    if (opts.body && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
      opts.headers["Content-Type"] = "application/json";
    }
    if (state.csrf && opts.method && opts.method !== "GET") {
      opts.headers[CSRF_KEY] = state.csrf;
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch { data = null; }
    if (!res.ok) {
      const message = (data && (data.detail || data.error)) || `خطای ${res.status}`;
      const err = new Error(typeof message === "string" ? message : "خطا");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data || {};
  }

  function setTheme() {
    if (R.applyTheme) R.applyTheme(R.preferredTheme ? R.preferredTheme() : "light");
  }

  // ------------------------------------------------------------- ورود
  async function boot() {
    setTheme();
    if (R.hydrateIcons) R.hydrateIcons();
    try {
      const info = await api("/api/admin/session");
      if (info.authenticated) {
        state.csrf = info.csrf;
        state.user = info.user;
        state.sessionInfo = info;
        enterPanel();
        return;
      }
    } catch { /* ورود لازم است */ }
    $("#admin-login").hidden = false;
  }

  function applyOwner(info) {
    state.owner = (info && info.owner) || null;
    const warn = document.getElementById("owner-warning");
    if (warn) warn.hidden = !(state.owner && state.owner.default_password);
    const who = document.getElementById("admin-user");
    if (who && state.user) who.textContent = state.user.name || state.user.email;
    const ownerName = document.getElementById("owner-name");
    if (ownerName && state.owner) ownerName.textContent = state.owner.name || "";
  }

  function enterPanel() {
    $("#admin-login").hidden = true;
    $("#admin-shell").hidden = false;
    applyOwner(state.sessionInfo || { owner: state.owner });
    loadOrders();
    loadOverview();
    loadSelfTest();
    healthLoop();
  }

  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const btn = $("#login-btn");
    const error = $("#login-error");
    error.hidden = true;
    btn.disabled = true;
    btn.textContent = "در حال بررسی…";
    try {
      const data = await api("/api/admin/login", {
        method: "POST", body: { password: $("#admin-password").value },
      });
      state.csrf = data.csrf;
      const info = await api("/api/admin/session");
      state.user = info.user;
      state.sessionInfo = info;
      enterPanel();
      toast("خوش آمدید.", "ok");
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = "ورود امن";
    }
  });

  const ownerBtn = document.getElementById("owner-change-pw");
  if (ownerBtn) ownerBtn.addEventListener("click", () => {
    const tab = document.querySelector('[data-tab="settings"]');
    if (tab) tab.click();
    const input = document.getElementById("owner-new-password");
    if (input) input.focus({ preventScroll: false });
    const warn = document.getElementById("owner-warning");
    if (warn) warn.hidden = true;
  });

  const saveOwner = document.getElementById("save-owner-password");
  if (saveOwner) saveOwner.addEventListener("click", async () => {
    const value = document.getElementById("owner-new-password").value;
    if (value.length < 8) { toast("حداقل ۸ نویسه لازم است.", "error"); return; }
    try {
      const res = await api("/api/admin/owner-password", { method: "POST", body: { password: value } });
      document.getElementById("owner-new-password").value = "";
      state.owner = res.owner;
      const warn = document.getElementById("owner-warning");
      if (warn) warn.hidden = !(res.owner && res.owner.default_password);
      toast("گذرواژهٔ مالک ذخیره شد.", "ok");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  $("#logout-btn").addEventListener("click", async () => {
    try { await api("/api/admin/logout", { method: "POST" }); } catch { /* نادیده */ }
    location.reload();
  });

  // ------------------------------------------------------------- تب‌ها
  const TITLES = {
    orders: ["اتاق فرمان", "دستور بده؛ سازنده اجرا می‌کند و همین‌جا پاسخ می‌دهد"],
    overview: ["نمای کلی", "وضعیت زندهٔ سایت، بدون نیاز به کار روزمره"],
    users: ["کاربران", "جست‌وجو، تغییر پلن، مسدودسازی"],
    ads: ["تبلیغات", "جایگاه، نمایش، کلیک و وزن"],
    settings: ["تنظیمات", "پرچم‌های قابلیت، اعلان و گذرواژه"],
    guard: ["سد تهاجم", "فیلتر درخواست‌های ناامن و بستن موقت مهاجم"],
    audit: ["لاگ حسابرسی", "هر کار مدیر با زمان و IP ثبت می‌شود"],
    system: ["سامانه", "نگهداری، بکاپ و مشخصات سرور"],
  };

  $("#admin-nav").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-tab]");
    if (!btn) return;
    switchTab(btn.dataset.tab);
  });

  function switchTab(tab) {
    state.tab = tab;
    $$("#admin-nav button").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === tab));
    $$(".admin-tab").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === tab));
    const [title, sub] = TITLES[tab] || ["", ""];
    $("#tab-title").textContent = title;
    $("#tab-sub").textContent = sub;
    if (tab === "orders") loadOrders();
    if (tab === "users") loadUsers();
    if (tab === "ads") loadAds();
    if (tab === "audit") loadAudit();
    if (tab === "guard") loadGuard();
    if (tab === "settings") loadSettings();
    if (tab === "system") { loadSystem(); loadNetwork(); loadCapacity(); }
  }

  // ------------------------------------------------------- اتاق فرمان
  function opsRow(order) {
    const row = document.createElement("article");
    row.className = "ops-row";
    const statusText = { pending: "در انتظار", working: "در حال انجام",
                         done: "انجام شد", skipped: "رد شد" }[order.status] || order.status;
    const head = document.createElement("header");
    const badge = document.createElement("span");
    badge.className = `pill ops-${order.status}`;
    badge.textContent = statusText;
    const when = document.createElement("time");
    when.textContent = timeAgo ? timeAgo(order.at) : "";
    head.append(badge, when);
    const body = document.createElement("p");
    body.textContent = order.text;
    row.append(head, body);
    (order.replies || []).forEach((rep) => {
      const answer = document.createElement("p");
      answer.className = "ops-reply";
      answer.textContent = rep.text || "—";
      row.append(answer);
    });
    return row;
  }

  async function loadOrders() {
    const list = $("\#ops-list");
    try {
      const data = await api("/api/admin/ops");
      state.orders = data.orders || [];
      const pending = (data.stats || {}).pending || 0;
      const pill = $("\#ops-pending");
      if (pill) {
        pill.textContent = pending ? `${nf(pending, 0)} دستور در انتظار اجرا` : "همه اجرا شده";
        pill.classList.toggle("is-warn", pending > 0);
      }
      if (!list) return;
      list.innerHTML = "";
      if (!state.orders.length) {
        list.innerHTML = '<p class="hint">هنوز دستوری ثبت نشده.</p>';
        return;
      }
      state.orders.forEach((order) => list.append(opsRow(order)));
    } catch (err) {
      if (list) list.innerHTML = `<p class="hint">${err.message}</p>`;
    }
  }

  document.addEventListener("click", async (event) => {
    const target = event.target.closest("\#ops-refresh, \#ops-reload, \#ops-restart");
    if (!target) return;
    const label = target.textContent;
    target.disabled = true;
    target.textContent = "…";
    try {
      if (target.id === "ops-refresh") {
        await loadOrders();
      } else if (target.id === "ops-reload") {
        const info = await api("/api/admin/reload", { method: "POST" });
        toast(`مدل دوباره بارگذاری شد (${info.seconds}s)`, "ok");
      } else {
        const info = await api("/api/admin/restart", { method: "POST" });
        toast(info.signalled ? "کارگرها بی‌وقفه نو می‌شوند" : (info.reason || "انجام نشد"), "ok");
      }
    } catch (err) {
      toast(err.message, "error");
    } finally {
      target.disabled = false;
      target.textContent = label;
    }
  });

  const opsForm = $("\#ops-form");
  if (opsForm) {
    opsForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const box = $("\#ops-text");
      const ok = $("\#ops-ok");
      const text = (box.value || "").trim();
      if (text.length < 2) { toast("دستور خیلی کوتاه است", "error"); return; }
      const btn = $("\#ops-send");
      btn.disabled = true;
      try {
        await api("/api/admin/ops", { method: "POST", body: { text, kind: "order" } });
        box.value = "";
        if (ok) {
          ok.hidden = false;
          ok.textContent = "ثبت شد. در نشست بعدی سازنده اجرا می‌شود.";
        }
        await loadOrders();
      } catch (err) {
        toast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ------------------------------------------------------------- کلی
  function pct(part, total) {
    if (!total) return "۰٪";
    return `${nf((part / total) * 100, 1)}٪`;
  }

  async function loadOverview() {
    try {
      const data = await api("/api/admin/overview?days=14");
      state.overview = data;
      const s = data.stats;
      renderKpis(s);
      renderChart(s.daily || []);
      renderFlags(data.flags || {});
      const ann = (data.settings || {}).announcement || "";
      $("#announcement").value = ann;
    } catch (err) {
      if (err.status === 401) location.reload();
      else toast(err.message, "error");
    }
  }

  function renderKpis(s) {
    const items = [
      ["کاربران", nf(s.users), `+${nf(s.users_today)} امروز · +${nf(s.users_week)} هفته`],
      ["گفتگوها", nf(s.conversations), `${nf(s.chats_today)} پیام امروز`],
      ["پاسخ‌ها", nf(s.answers), `${nf(s.guest_chats)} از مهمان`],
      ["بازخورد مثبت", nf(s.feedback_up), `منفی: ${nf(s.feedback_down)}`],
      ["بازدید لینک اشتراک", nf(s.share_views), "رشد ارگانیک"],
      ["حجم پایگاه‌داده", `${nf(Math.round((s.db_bytes || 0) / 1024))} KB`, "SQLite محلی"],
    ];
    $("#kpi-grid").innerHTML = items.map(([label, value, note]) => (
      `<div class="kpi"><span>${label}</span><b>${value}</b><small>${note}</small></div>`
    )).join("");
  }

  function renderChart(daily) {
    const max = Math.max(1, ...daily.map((d) => d.chats + d.signups));
    $("#activity-chart").innerHTML = daily.map((d) => {
      const total = d.chats + d.signups;
      const h = Math.max(4, Math.round((total / max) * 100));
      const label = `${faDigits(new Date(d.day * 1000).toLocaleDateString("fa-IR", { day: "numeric", month: "short" }))}`;
      return `<div class="bar" style="height:${h}%" title="${label} · ${nf(d.chats)} گفتگو · ${nf(d.signups)} ثبت‌نام"><span>${nf(total)}</span></div>`;
    }).join("");
  }

  async function loadSelfTest() {
    try {
      const res = await fetch("/api/selftest", { credentials: "include" });
      const data = await res.json();
      $("#selftest-list").innerHTML = (data.checks || []).map((c) => (
        `<div class="check-row"><span>${c.name}</span>` +
        `<span class="${c.ok ? "ok" : "bad"}">${c.ok ? "سالم" : "خطا"}</span></div>`
      )).join("");
      $("#health-pill").textContent = data.ok ? "سامانه سالم" : "نیازمند بررسی";
      $("#health-pill").className = `pill ${data.ok ? "is-ok" : "is-bad"}`;
    } catch {
      $("#health-pill").textContent = "بی‌پاسخ";
      $("#health-pill").className = "pill is-bad";
    }
  }

  function healthLoop() {
    setInterval(async () => {
      try {
        const res = await fetch("/api/status", { credentials: "include" });
        const data = await res.json();
        $("#health-pill").textContent = data.model_loaded ? "مدل فعال" : "مدل خاموش";
        $("#health-pill").className = `pill ${data.model_loaded ? "is-ok" : "is-warn"}`;
      } catch { /* نادیده */ }
    }, 30000);
  }

  // ------------------------------------------------------------- کاربران
  async function loadUsers() {
    try {
      const q = $("#user-search").value.trim();
      const data = await api(`/api/admin/users?q=${encodeURIComponent(q)}`);
      state.users = data.users || [];
      $("#users-table tbody").innerHTML = state.users.map((u) => {
        const planClass = u.plan === "admin" ? "is-ok" : u.plan === "banned" ? "is-bad" : "";
        const planLabel = { free: "رایگان", pro: "حرفه‌ای", admin: "مدیر", banned: "مسدود", guest: "مهمان" }[u.plan] || u.plan;
        return `<tr>
          <td>${nf(u.id)}</td>
          <td dir="ltr">${u.email}</td>
          <td>${u.name || "—"}</td>
          <td><span class="pill ${planClass}">${planLabel}</span></td>
          <td>${nf(u.conversations)}</td>
          <td>${timeAgo(u.created_at)}</td>
          <td>${u.last_seen ? timeAgo(u.last_seen) : "—"}</td>
          <td class="actions">
            <button class="mini-btn" data-user="${u.id}" data-act="plan" data-plan="free">رایگان</button>
            <button class="mini-btn" data-user="${u.id}" data-act="plan" data-plan="pro">حرفه‌ای</button>
            <button class="mini-btn danger" data-user="${u.id}" data-act="ban">مسدود</button>
          </td>
        </tr>`;
      }).join("") || '<tr><td colspan="8" class="hint">کاربری پیدا نشد.</td></tr>';
    } catch (err) {
      toast(err.message, "error");
    }
  }

  $("#user-refresh").addEventListener("click", loadUsers);
  $("#user-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); loadUsers(); }
  });
  $("#users-table").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-user]");
    if (!btn) return;
    const id = btn.dataset.user;
    try {
      if (btn.dataset.act === "ban") {
        await api(`/api/admin/users/${id}/action`, { method: "POST", body: { action: "ban" } });
        toast("کاربر مسدود شد.", "ok");
      } else {
        await api(`/api/admin/users/${id}/action`, {
          method: "POST", body: { action: "plan", plan: btn.dataset.plan },
        });
        toast("پلن تغییر کرد.", "ok");
      }
      loadUsers();
      loadOverview();
    } catch (err) {
      toast(err.message, "error");
    }
  });

  // ------------------------------------------------------------- تبلیغات
  async function loadAds() {
    try {
      const data = await api("/api/admin/ads");
      state.ads = data.ads || [];
      const totalViews = state.ads.reduce((sum, a) => sum + Number(a.views || 0), 0);
      const totalClicks = state.ads.reduce((sum, a) => sum + Number(a.clicks || 0), 0);
      $("#ads-summary").textContent = `${nf(state.ads.length)} تبلیغ · ${nf(totalViews)} نمایش · ${nf(totalClicks)} کلیک`;
      $("#ads-table tbody").innerHTML = state.ads.map((ad) => (
        `<tr>
          <td>${nf(ad.id)}</td>
          <td dir="ltr">${ad.slot}</td>
          <td>${ad.title}</td>
          <td>${nf(ad.weight)}</td>
          <td>${nf(ad.views)}</td>
          <td>${nf(ad.clicks)}</td>
          <td>${pct(ad.clicks, ad.views)}</td>
          <td><span class="pill ${ad.active ? "is-ok" : ""}">${ad.active ? "فعال" : "خاموش"}</span></td>
          <td class="actions">
            <button class="mini-btn" data-ad="${ad.id}" data-act="toggle">${ad.active ? "خاموش" : "روشن"}</button>
            <button class="mini-btn danger" data-ad="${ad.id}" data-act="delete">حذف</button>
          </td>
        </tr>`
      )).join("") || '<tr><td colspan="9" class="hint">هنوز تبلیغی ساخته نشده است.</td></tr>';
    } catch (err) {
      toast(err.message, "error");
    }
  }

  $("#ad-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const payload = {
      slot: form.slot.value,
      title: form.title.value.trim(),
      body: form.body.value.trim(),
      cta: form.cta.value.trim() || "بیشتر بدانید",
      url: form.url.value.trim(),
      weight: Number(form.weight.value) || 1,
      active: true,
    };
    try {
      await api("/api/admin/ads", { method: "POST", body: payload });
      toast("تبلیغ اضافه شد.", "ok");
      form.reset();
      form.cta.value = "بیشتر بدانید";
      form.weight.value = 5;
      loadAds();
    } catch (err) {
      toast(err.message, "error");
    }
  });

  $("#ads-table").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-ad]");
    if (!btn) return;
    const ad = state.ads.find((a) => String(a.id) === btn.dataset.ad);
    try {
      if (btn.dataset.act === "delete") {
        await api(`/api/admin/ads/${btn.dataset.ad}`, { method: "DELETE" });
        toast("حذف شد.", "ok");
      } else if (ad) {
        await api(`/api/admin/ads/${ad.id}`, {
          method: "PATCH",
          body: {
            slot: ad.slot, title: ad.title, body: ad.body, cta: ad.cta, url: ad.url,
            weight: ad.weight, active: !ad.active, starts_at: ad.starts_at, ends_at: ad.ends_at,
          },
        });
      }
      loadAds();
    } catch (err) {
      toast(err.message, "error");
    }
  });

  // ------------------------------------------------------------- تنظیمات
  const FLAGS = [
    ["ads_enabled", "تبلیغات فعال"],
    ["signup_open", "ثبت‌نام باز"],
    ["guest_chat", "گفتگوی مهمان"],
    ["deep_enabled", "اندیشهٔ ژرف"],
    ["studio_enabled", "استودیو تصویر"],
    ["web_search", "جست‌وجوی وب"],
    ["auto_learn", "یادگیری خودکار از وب"],
    ["maintenance", "حالت نگهداری"],
  ];

  function renderFlags(flags) {
    $("#flag-list").innerHTML = FLAGS.map(([key, label]) => (
      `<label class="flag"><span>${label}</span>
        <span class="switch"><input type="checkbox" data-flag="${key}" ${flags[key] ? "checked" : ""}><i></i></span>
      </label>`
    )).join("");
  }

  async function loadSettings() {
    try {
      const data = await api("/api/admin/settings");
      renderFlags(data.flags || {});
      const conf = data.settings || {};
      $("#announcement").value = conf.announcement || "";
      $("#plan-price").value = conf.plan_pro_price || "0";
      $("#plan-days").value = conf.plan_pro_days || "30";
      $("#pay-provider").value = conf.payment_provider || "";
      $("#pay-link").value = conf.payment_link || "";
      $("#pay-note").value = conf.payment_note || "";
      $("#pay-enabled").checked = conf.payments_enabled === "1";
    } catch (err) {
      toast(err.message, "error");
    }
  }

  $("#save-flags").addEventListener("click", async () => {
    const values = {};
    $$("[data-flag]").forEach((input) => { values[input.dataset.flag] = input.checked ? "1" : "0"; });
    try {
      await api("/api/admin/settings", { method: "POST", body: { values } });
      toast("پرچم‌ها ذخیره شد.", "ok");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  $("#save-announcement").addEventListener("click", async () => {
    try {
      await api("/api/admin/settings", {
        method: "POST", body: { values: { announcement: $("#announcement").value.trim() } },
      });
      toast("اعلان ذخیره شد.", "ok");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  $("#save-monetization").addEventListener("click", async () => {
    const price = Math.max(0, Number($("#plan-price").value || 0));
    const days = Math.min(3650, Math.max(1, Number($("#plan-days").value || 30)));
    const link = $("#pay-link").value.trim();
    if (link && !/^(https?:\/\/|\/)/.test(link)) {
      toast("نشانی پرداخت باید با http(s):// یا / شروع شود.", "error");
      return;
    }
    const values = {
      plan_pro_price: String(Math.round(price)),
      plan_pro_days: String(Math.round(days)),
      payment_provider: $("#pay-provider").value.trim(),
      payment_link: link,
      payment_note: $("#pay-note").value.trim(),
      payments_enabled: $("#pay-enabled").checked ? "1" : "0",
    };
    try {
      await api("/api/admin/settings", { method: "POST", body: { values } });
      toast(price > 0 && values.payments_enabled === "1"
        ? "تعرفه ذخیره شد؛ پرداخت فعال است."
        : "تعرفه ذخیره شد.", "ok");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  $("#save-password").addEventListener("click", async () => {
    const value = $("#new-password").value;
    if (value.length < 10) { toast("حداقل ۱۰ نویسه لازم است.", "error"); return; }
    try {
      await api("/api/admin/password", { method: "POST", body: { password: value } });
      $("#new-password").value = "";
      toast("گذرواژه تغییر کرد.", "ok");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  // ------------------------------------------------------------- لاگ
  async function loadAudit() {
    try {
      const data = await api("/api/admin/audit?limit=120");
      state.audit = data.entries || [];
      $("#audit-table tbody").innerHTML = state.audit.map((e) => (
        `<tr><td>${timeAgo(e.created_at)}</td><td dir="ltr">${e.action}</td><td>${e.target || "—"}</td>
         <td>${e.detail || "—"}</td><td dir="ltr">${e.ip || "—"}</td></tr>`
      )).join("") || '<tr><td colspan="5" class="hint">خالی است.</td></tr>';
    } catch (err) {
      toast(err.message, "error");
    }
  }
  $("#audit-refresh").addEventListener("click", loadAudit);

  // ------------------------------------------------------------ سد تهاجم
  async function loadGuard() {
    try {
      const data = await api("/api/admin/security");
      const rules = Object.entries(data.by_rule || {});
      const bans = Object.entries(data.bans || {});
      $("#guard-stats").innerHTML = [
        ["رویدادهای اخیر", nf(data.total_today || 0)],
        ["قاعده‌های فعال", nf((data.rules || []).length)],
        ["IPهای بسته‌شده", nf(bans.length)],
        ["انسان‌سنجی", data.human_checks?.bound_to_browser ? "امضاشده + شواهد" : "ساده"],
      ].map(([k, v]) => `<div class="guard-cell"><span>${k}</span><b>${v}</b></div>`).join("");
      const recent = (data.recent || []);
      $("#guard-table tbody").innerHTML = recent.map((e) => (
        `<tr><td>${timeAgo(e.t)}</td><td dir="ltr">${e.rule || "—"}</td><td>${e.label || "—"}</td>
         <td dir="ltr">${(e.method || "")} ${e.path || ""}</td><td dir="ltr">${e.ip || "—"}</td></tr>`
      )).join("") || '<tr><td colspan="5" class="hint">هنوز حمله‌ای دیده نشده.</td></tr>';
    } catch (err) {
      toast(err.message, "error");
    }
  }
  $("#guard-refresh").addEventListener("click", loadGuard);

  // ------------------------------------------------------------- سامانه
  // -------------------------------------------------- شبکه و ظرفیت
  async function loadNetwork() {
    try {
      const data = await api("/api/admin/network");
      $$("#network-mode button").forEach((btn) => {
        btn.classList.toggle("is-active", btn.dataset.mode === data.mode);
      });
      $("#network-info").innerHTML = Object.entries({
        "حالت فعلی": { auto: "خودکار", national: "فقط ملی", global: "بین‌المللی" }[data.mode] || data.mode,
        "تماس بیرونی": data.outbound_allowed ? "آزاد" : "بسته",
        "آخرین موفقیت": data.last_success_s ? `${nf(Math.round(data.last_success_s))} ثانیه پیش` : "—",
        "آخرین خطا": data.last_error || "—",
        "فایل‌های سایت": data.assets_local ? "همه محلی" : "بیرونی",
      }).map(([k, v]) => `<div class="check-row"><span>${k}</span><span class="hint">${v ?? "—"}</span></div>`).join("");
    } catch (err) {
      $("#network-info").textContent = err.message;
    }
  }

  async function loadCapacity() {
    try {
      const data = await api("/api/admin/capacity");
      const hw = data.hardware || {};
      $("#capacity-info").innerHTML = Object.entries({
        "کارگرهای فعال": nf(data.workers, 0),
        "صف فعلی": nf(data.queue_depth, 0),
        "سقف هم‌زمانی": nf(data.concurrency_limit, 0),
        "کش پاسخ": `${nf(data.cache_used, 0)} از ${nf(data.cache_size, 0)}`,
        "درخواست این نشست": nf(data.requests_served, 0),
        "پردازنده": hw.cpu || "—",
        "هسته‌ها": nf(hw.cores, 0),
        "حافظه": hw.memory_gb ? `${nf(hw.memory_gb, 1)} گیگابایت` : "—",
        "پایگاه کاربران": `${nf((data.database || {}).users_db_bytes, 0)} بایت`,
        "دانش نمایه‌شده": `${nf(Math.round(((data.database || {}).index_bytes || 0) / 1048576), 0)} مگابایت`,
      }).map(([k, v]) => `<div class="check-row"><span>${k}</span><span class="hint">${v ?? "—"}</span></div>`).join("");
      $("#capacity-note").textContent = data.honest_note || "";
    } catch (err) {
      $("#capacity-info").textContent = err.message;
    }
  }

  document.addEventListener("click", async (event) => {
    const btn = event.target.closest("#network-mode button");
    if (!btn || !state.csrf) return;
    try {
      const data = await api("/api/admin/network", { method: "POST", body: { mode: btn.dataset.mode } });
      $("#network-result").textContent = data.outbound_allowed
        ? "حالت ذخیره شد؛ تماس بیرونی آزاد است."
        : "حالت ذخیره شد؛ سایت کاملاً ملی کار می‌کند.";
      loadNetwork();
    } catch (err) {
      $("#network-result").textContent = err.message;
    }
  });

  async function loadSystem() {
    try {
      const data = await api("/api/admin/overview?days=3");
      const sys = data.system || {};
      $("#system-info").innerHTML = Object.entries({
        "نسخهٔ پایتون": sys.python,
        "سیستم": sys.platform,
        "هسته‌های CPU": sys.cpu,
        "زمان فعالیت": `${nf(Math.round((sys.uptime_s || 0) / 60))} دقیقه`,
        "شناسهٔ فرایند": sys.pid,
        "ایمیل مدیر": sys.admin_email,
      }).map(([k, v]) => `<div class="check-row"><span>${k}</span><span class="hint" dir="ltr">${v ?? "—"}</span></div>`).join("");
    } catch (err) {
      toast(err.message, "error");
    }
  }

  $$("[data-task]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const data = await api(`/api/admin/maintenance?task=${btn.dataset.task}`, { method: "POST" });
        $("#system-result").textContent = JSON.stringify(data, null, 1).slice(0, 300);
        toast("انجام شد.", "ok");
      } catch (err) {
        toast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
  });

  document.addEventListener("DOMContentLoaded", boot);
})();
