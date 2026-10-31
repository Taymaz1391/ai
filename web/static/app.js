/* رایان — کلاینت گفتگو */
(function () {
  "use strict";
  const R = window.RAYAN;
  const { $, $$, request, toast, nf, timeAgo, copyText, initials } = R;

  const STORE_KEY = "rayan.settings.v2";
  const DEFAULTS = { temperature: 0.82, top_p: 0.9, max_new_tokens: 110, candidates: 4 };
  const MODE_LABELS = { chat: "گفتگو", continue: "ادامهٔ متن", poetry: "شعر" };

  const state = {
    user: null,
    plan: "guest",
    usage: null,
    conversations: [],
    currentId: null,
    messages: [],
    models: [],
    model: "rayan-1-small",
    deep: false,
    web: localStorage.getItem("rayan.web") === "1",
    mode: "chat",
    settings: loadSettings(),
    sending: false,
    controller: null,
    query: "",
    dragging: false,
  };

  function loadSettings() {
    try {
      return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(STORE_KEY) || "{}"));
    } catch {
      return Object.assign({}, DEFAULTS);
    }
  }
  function saveSettings() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state.settings)); } catch { /* حالت خصوصی */ }
  }

  // ------------------------------------------------------------- مارک‌داون
  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function inline(text) {
    let out = escapeHtml(text);
    out = out.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    out = out.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return out;
  }

  function renderMarkdown(raw) {
    const lines = String(raw || "").replace(/\r/g, "").split("\n");
    const html = [];
    let inCode = false;
    let list = null;
    let paragraph = [];

    const flushParagraph = () => {
      if (paragraph.length) {
        html.push(`<p>${inline(paragraph.join(" "))}</p>`);
        paragraph = [];
      }
    };
    const closeList = () => {
      if (list) {
        html.push(`</${list}>`);
        list = null;
      }
    };

    for (const line of lines) {
      if (/^```/.test(line)) {
        flushParagraph();
        closeList();
        if (inCode) { html.push("</code></pre>"); inCode = false; }
        else { html.push("<pre><code>"); inCode = true; }
        continue;
      }
      if (inCode) { html.push(escapeHtml(line)); continue; }
      const trimmed = line.trim();
      if (!trimmed) { flushParagraph(); closeList(); continue; }
      const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushParagraph(); closeList();
        const level = Math.min(4, heading[1].length + 2);
        html.push(`<h${level}>${inline(heading[2])}</h${level}>`);
        continue;
      }
      if (/^([-*•]|\d+\.)\s+/.test(trimmed)) {
        flushParagraph();
        const ordered = /^\d+\./.test(trimmed);
        const kind = ordered ? "ol" : "ul";
        if (list !== kind) { closeList(); html.push(`<${kind}>`); list = kind; }
        html.push(`<li>${inline(trimmed.replace(/^([-*•]|\d+\.)\s+/, ""))}</li>`);
        continue;
      }
      if (/^>\s?/.test(trimmed)) {
        flushParagraph(); closeList();
        html.push(`<blockquote>${inline(trimmed.replace(/^>\s?/, ""))}</blockquote>`);
        continue;
      }
      if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
        flushParagraph(); closeList(); html.push("<hr>"); continue;
      }
      closeList();
      paragraph.push(trimmed);
    }
    flushParagraph();
    closeList();
    if (inCode) html.push("</code></pre>");
    return html.join("");
  }

  // ---------------------------------------------------------------- عناصر
  const el = {
    scroll: $("#chat-scroll"),
    messages: $("#messages"),
    empty: $("#empty-state"),
    suggestions: $("#suggestions"),
    composer: $("#composer"),
    prompt: $("#prompt"),
    send: $("#send-btn"),
    stop: $("#stop-btn"),
    deep: $("#deep-toggle"),
    web: $("#web-toggle"),
    mode: $("#mode-select"),
    hint: $("#composer-hint"),
    convList: $("#conv-list"),
    convEmpty: $("#conv-empty"),
    search: $("#conv-search"),
    usagePlan: $("#usage-plan"),
    usageCount: $("#usage-count"),
    usageFill: $("#usage-fill"),
    usageCta: $("#usage-cta"),
    modelBtn: $("#model-btn"),
    modelMenu: $("#model-menu"),
    modelLabel: $("#model-label"),
    modelTag: $("#model-tag"),
    sidebar: $("#sidebar"),
    scrim: $("#sidebar-scrim"),
    accountMenu: $("#account-menu"),
  };

  // --------------------------------------------------------------- مودال‌ها
  function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.hidden = false;
  }
  function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.hidden = true;
  }
  $$(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) backdrop.hidden = true;
    });
  });
  $$("[data-close]").forEach((btn) => {
    btn.addEventListener("click", () => closeModal(btn.getAttribute("data-close")));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      $$(".modal-backdrop").forEach((m) => { m.hidden = true; });
      el.accountMenu.hidden = true;
      el.modelMenu.hidden = true;
      closeSidebar({ restoreFocus: true });
    }
  });

  // نوار گفتگوها: پیش‌فرض بسته، با یک دکمه باز/بسته می‌شود و کامل ناپدید می‌گردد.
  const sidebarToggle = $("#sidebar-open");
  const sidebarClose = $("#sidebar-close");
  const canHover = window.matchMedia("(hover: hover) and (pointer: fine)");

  function sidebarIsOpen() {
    return el.sidebar.classList.contains("is-open");
  }

  function setSidebar(open, opts) {
    const wasOpen = sidebarIsOpen();
    el.sidebar.classList.toggle("is-open", open);
    el.sidebar.toggleAttribute("inert", !open);
    el.sidebar.setAttribute("aria-hidden", open ? "false" : "true");
    el.scrim.hidden = !open;
    document.body.classList.toggle("sidebar-visible", open);
    if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && !(opts && opts.silent)) {
      const target = canHover.matches ? $("#conv-search") : sidebarClose;
      if (target) requestAnimationFrame(() => target.focus({ preventScroll: true }));
    } else if (wasOpen && (opts && opts.restoreFocus) && sidebarToggle) {
      sidebarToggle.focus({ preventScroll: true });
    }
  }

  function openSidebar() { setSidebar(true); }
  function closeSidebar(opts) {
    if (!sidebarIsOpen()) return;
    const inside = el.sidebar.contains(document.activeElement);
    setSidebar(false, { restoreFocus: inside || (opts && opts.restoreFocus) });
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      if (sidebarIsOpen()) { closeSidebar({ restoreFocus: true }); rememberSidebar(false); }
      else { openSidebar(); rememberSidebar(true); }
    });
  }

  // روی نمایشگر بزرگ، نوار گفتگوها پیش‌فرض باز است تا فضای صفحه هدر نرود؛
  // انتخاب کاربر (باز یا بسته) برای دفعهٔ بعد یادش می‌ماند.
  const wideScreen = window.matchMedia("(min-width: 1080px)");
  function rememberSidebar(open) {
    try { localStorage.setItem("rayan.sidebar", open ? "open" : "closed"); } catch { /* حالت خصوصی */ }
  }
  function restoreSidebar() {
    let saved = null;
    try { saved = localStorage.getItem("rayan.sidebar"); } catch { /* حالت خصوصی */ }
    if (saved === "open" || (saved === null && wideScreen.matches)) setSidebar(true, { silent: true });
  }
  if (sidebarClose) sidebarClose.addEventListener("click", () => closeSidebar({ restoreFocus: true }));
  el.scrim.addEventListener("click", () => closeSidebar());
  // بستن با کلیک بیرون
  document.addEventListener("pointerdown", (event) => {
    if (!sidebarIsOpen()) return;
    if (el.sidebar.contains(event.target) || (sidebarToggle && sidebarToggle.contains(event.target))) return;
    closeSidebar();
  });
  // در حالت بسته، فوکوس داخل نوار نماند
  el.sidebar.toggleAttribute("inert", !sidebarIsOpen());
  el.sidebar.setAttribute("aria-hidden", sidebarIsOpen() ? "false" : "true");

  // ---------------------------------------------------------- وضعیت کاربر
  function planLabel(plan) {
    return { guest: "مهمان", free: "رایگان", pro: "حرفه‌ای" }[plan] || "مهمان";
  }

  function applyUser(stateAuth) {
    state.user = stateAuth.user;
    state.plan = stateAuth.plan || "guest";
    state.usage = stateAuth.usage;
    const name = state.user ? (state.user.name || state.user.email.split("@")[0]) : "مهمان";
    $$("[data-user-name]").forEach((n) => { n.textContent = name; });
    const plan = planLabel(state.plan);
    $$("[data-user-plan]").forEach((n) => {
      n.textContent = plan;
      n.hidden = plan === name;   // «مهمان» را دو بار پشت هم ننویس
    });
    $$("[data-user-initials]").forEach((n) => { n.textContent = initials(name); });
    $$("[data-auth='guest']").forEach((n) => { n.hidden = !!state.user; });
    $$("[data-auth='user']").forEach((n) => { n.hidden = !state.user; });
    if (el.usageCta) el.usageCta.hidden = !!state.user;
    renderUsage();
  }

  function renderUsage() {
    const usage = state.usage || {};
    const chat = usage.chat || { used: 0, limit: 25 };
    el.usagePlan.textContent = "سهمیهٔ امروز";
    el.usageCount.textContent = `${nf(chat.used || 0)} / ${nf(chat.limit || 0)}`;
    const pct = Math.min(100, ((chat.used || 0) / Math.max(1, chat.limit || 1)) * 100);
    el.usageFill.style.width = `${pct}%`;
    el.usageFill.style.background = pct > 86 ? "linear-gradient(135deg,#ff7a8a,#f5b74a)" : "";
  }

  async function refreshAuth() {
    try {
      const auth = await request("/api/auth/me");
      applyUser(auth);
    } catch { /* آفلاین */ }
  }

  // نام برند همیشه تصویر است: پیشوند «رایان» از دادهٔ سرور جدا و با لوگوتایپ
  // نمایش داده می‌شود، بقیهٔ نام (مثلاً «۱ — کوچک») متن می‌ماند.
  const MODEL_LOGO = (
    '<img class="wm-inline model-logo wordmark-for-light" src="/static/assets/brand/mark-ink.png" alt="رایان" width="1026" height="520" decoding="async">' +
    '<img class="wm-inline model-logo wordmark-for-dark" src="/static/assets/brand/mark-white.png" alt="رایان" width="1026" height="520" decoding="async">'
  );
  function modelNameCore(name) {
    return String(name || "").replace(/^\s*(رایان|Rayan)\s*/u, "").trim();
  }
  function modelNameHtml(name) {
    return `${MODEL_LOGO} ${escapeHtml(modelNameCore(name))}`;
  }

  // ------------------------------------------------------------ مدل‌ها
  async function loadModels() {
    try {
      const data = await request("/api/models");
      state.models = data.models || [];
      renderModelMenu();
      const active = state.models.find((m) => m.id === state.model) || state.models[0];
      if (active) {
        el.modelLabel.innerHTML = modelNameHtml(active.name);
        el.modelTag.textContent = active.badge;
      }
    } catch { /* از پیش‌فرض استفاده می‌کنیم */ }
  }

  function renderModelMenu() {
    el.modelMenu.innerHTML = "";
    const list = state.models.length ? state.models : [{
      id: "rayan-1-small", name: "۱ — کوچک", tagline: "مدل فعال", status: "ready",
      desc: "مدل ۶٫۵۷ میلیون پارامتری روی CPU", context: 256,
    }];
    list.forEach((model) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `model-item${model.id === state.model ? " is-active" : ""}`;
      item.setAttribute("role", "option");
      item.setAttribute("aria-disabled", model.status === "ready" ? "false" : "true");
      item.innerHTML = `
        <span class="mi-body">
          <b>${modelNameHtml(model.name)}</b>
          <small>${escapeHtml(model.tagline || "")} · ${model.context ? nf(model.context) + " توکن زمینه" : "—"}</small>
        </span>
        <span class="mi-side"><span class="tag ${model.status === "ready" ? "tag-blue" : ""}">${escapeHtml(model.badge || "")}</span></span>`;
      item.addEventListener("click", () => {
        if (model.status !== "ready") {
          toast("این مدل هنوز آموزش ندیده است. در نقشهٔ راه ماست.", "");
          return;
        }
        state.model = model.id;
        el.modelLabel.innerHTML = modelNameHtml(model.name);
        el.modelTag.textContent = model.badge;
        el.modelMenu.hidden = true;
        renderModelMenu();
        toast(`مدل از این به بعد: ${modelNameCore(model.name)}`, "ok");
      });
      el.modelMenu.append(item);
    });
  }

  el.modelBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = el.modelMenu.hidden;
    el.modelMenu.hidden = !open;
    el.modelBtn.setAttribute("aria-expanded", String(open));
  });

  // --------------------------------------------------------------- گفتگوها
  function groupConversations(list) {
    const now = Date.now() / 1000;
    const groups = [["سنجاق‌شده", []], ["امروز", []], ["۷ روز گذشته", []], ["قدیمی‌تر", []]];
    list.forEach((conv) => {
      if (conv.pinned) groups[0][1].push(conv);
      else if (now - conv.updated_at < 86400) groups[1][1].push(conv);
      else if (now - conv.updated_at < 86400 * 7) groups[2][1].push(conv);
      else groups[3][1].push(conv);
    });
    return groups.filter(([, items]) => items.length);
  }

  function renderConversations() {
    const query = state.query.trim().toLowerCase();
    const list = state.conversations.filter((c) => !query || (c.title || "").toLowerCase().includes(query));
    el.convList.querySelectorAll(".conv-item, .conv-group-label").forEach((n) => n.remove());
    el.convEmpty.hidden = list.length > 0;
    if (!list.length) {
      el.convEmpty.querySelector("span").textContent = query ? "چیزی پیدا نشد." : "هنوز گفتگویی نیست.";
      el.convEmpty.querySelector("small").textContent = query ? "عبارت دیگری را امتحان کن." : "اولین پیام را بفرست تا اینجا ذخیره شود.";
      return;
    }
    groupConversations(list).forEach(([label, items]) => {
      const groupLabel = document.createElement("div");
      groupLabel.className = "conv-group-label";
      groupLabel.textContent = label;
      el.convList.append(groupLabel);
      items.forEach((conv) => {
        const row = document.createElement("div");
        row.className = `conv-item${conv.id === state.currentId ? " is-active" : ""}`;
        row.dataset.id = conv.id;
        row.tabIndex = 0;
        row.innerHTML = `
          <span class="title">${escapeHtml(conv.title || "گفتگوی تازه")}</span>
          ${conv.pinned ? '<span class="pin">★</span>' : ""}
          <button class="more" aria-label="گزینه‌ها" title="گزینه‌ها">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><circle cx="6" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="18" cy="12" r="1.8"/></svg>
          </button>`;
        const open = () => openConversation(conv.id);
        row.addEventListener("click", (event) => {
          if (event.target.closest(".more")) return;
          open();
        });
        row.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
        });
        row.querySelector(".more").addEventListener("click", (event) => {
          event.stopPropagation();
          showConvMenu(row, conv);
        });
        el.convList.append(row);
      });
    });
  }

  function showConvMenu(row, conv) {
    $$(".conv-menu").forEach((n) => n.remove());
    const menu = document.createElement("div");
    menu.className = "account-menu conv-menu";
    menu.style.cssText = "position:absolute;inset-block-start:auto;inset-block-end:auto;min-width:170px;z-index:70;padding:6px;border-radius:12px;border:1px solid var(--line-strong);background:var(--surface-solid);box-shadow:var(--shadow-lg)";
    const rect = row.getBoundingClientRect();
    menu.style.position = "fixed";
    menu.style.top = `${Math.min(rect.bottom + 6, window.innerHeight - 220)}px`;
    menu.style.insetInlineStart = "auto";
    menu.style.left = `${Math.max(10, rect.right - 180)}px`;
    const items = [
      ["تغییر نام", () => renameConversation(conv)],
      [conv.pinned ? "برداشتن سنجاق" : "سنجاق کردن", () => togglePin(conv)],
      ["اشتراک‌گذاری", () => shareConversation(conv)],
      ["حذف", () => confirmDelete(conv), "danger"],
    ];
    items.forEach(([label, action, kind]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      if (kind === "danger") btn.style.color = "#ffb3bd";
      btn.addEventListener("click", () => {
        menu.remove();
        action();
      });
      menu.append(btn);
    });
    document.body.append(menu);
    setTimeout(() => {
      document.addEventListener("click", function onDoc(event) {
        if (!menu.contains(event.target)) {
          menu.remove();
          document.removeEventListener("click", onDoc);
        }
      });
    }, 0);
  }

  async function loadConversations() {
    try {
      const data = await request("/api/conversations");
      state.conversations = data.conversations || [];
      renderConversations();
    } catch { /* آفلاین */ }
  }

  async function openConversation(id, pushState = true) {
    closeSidebar();
    try {
      const data = await request(`/api/conversations/${id}`);
      const conv = data.conversation;
      state.currentId = conv.id;
      state.messages = (conv.messages || []).map((m) => ({
        id: m.id, role: m.role, content: m.content, meta: m.meta || {},
      }));
      renderAllMessages();
      closeSidebar();
      updateEmptyState();
      renderConversations();
      if (pushState) history.replaceState({}, "", `/chat?c=${id}`);
    } catch (err) {
      toast(err.message, "error");
      state.currentId = null;
      state.messages = [];
      renderAllMessages();
    }
  }

  function newChat() {
    closeSidebar();
    state.currentId = null;
    state.messages = [];
    renderAllMessages();
    updateEmptyState();
    renderConversations();
    history.replaceState({}, "", "/chat");
    el.prompt.focus();
    closeSidebar();
  }

  async function renameConversation(conv) {
    const next = window.prompt("نام تازهٔ گفتگو:", conv.title || "گفتگوی تازه");
    if (!next || next.trim() === conv.title) return;
    try {
      await request(`/api/conversations/${conv.id}`, { method: "PATCH", body: { title: next.trim() } });
      conv.title = next.trim();
      renderConversations();
      toast("نام گفتگو تغییر کرد.", "ok");
    } catch (err) { toast(err.message, "error"); }
  }

  async function togglePin(conv) {
    try {
      const next = !conv.pinned;
      await request(`/api/conversations/${conv.id}`, { method: "PATCH", body: { pinned: next } });
      conv.pinned = next;
      await loadConversations();
      toast(next ? "سنجاق شد." : "سنجاق برداشته شد.", "ok");
    } catch (err) { toast(err.message, "error"); }
  }

  let pendingDelete = null;
  function confirmDelete(conv) {
    pendingDelete = conv;
    $("#confirm-text").textContent = `«${conv.title || "گفتگوی تازه"}» برای همیشه حذف می‌شود. این کار برگشت‌پذیر نیست.`;
    openModal("confirm-modal");
  }
  $("#confirm-yes").addEventListener("click", async () => {
    if (!pendingDelete) return;
    try {
      await request(`/api/conversations/${pendingDelete.id}`, { method: "DELETE" });
      if (state.currentId === pendingDelete.id) newChat();
      await loadConversations();
      closeModal("confirm-modal");
      toast("گفتگو حذف شد.", "ok");
    } catch (err) { toast(err.message, "error"); }
    pendingDelete = null;
  });

  // --------------------------------------------------------------- اشتراک
  async function shareConversation(conv) {
    const id = conv ? conv.id : state.currentId;
    if (!id) { toast("اول یک گفتگو بساز.", ""); return; }
    try {
      const data = await request(`/api/conversations/${id}/share`, { method: "POST" });
      const url = `${location.origin}/s/${data.token}`;
      $("#share-link").value = url;
      $("#share-open").onclick = () => window.open(url, "_blank", "noopener");
      $("#share-revoke").onclick = async () => {
        await request(`/api/conversations/${id}/share`, { method: "DELETE" }).catch(() => {});
        closeModal("share-modal");
        toast("اشتراک لغو شد.", "ok");
      };
      openModal("share-modal");
    } catch (err) { toast(err.message, "error"); }
  }
  $("#share-copy").addEventListener("click", async () => {
    await copyText($("#share-link").value);
    toast("لینک کپی شد.", "ok");
  });
  $("#share-btn").addEventListener("click", () => shareConversation(null));

  // --------------------------------------------------------------- پیام‌ها
  function updateEmptyState() {
    const empty = !state.messages.length;
    el.empty.hidden = !empty;
    el.messages.hidden = empty;
  }

  function renderAllMessages() {
    el.messages.innerHTML = "";
    state.messages.forEach((msg) => el.messages.append(buildMessage(msg)));
    scrollToBottom(false);
  }

  // اسکرول و رندر استریم هر دو در یک فریم جمع می‌شوند؛ توکن‌های پشت‌سرهم
  // دیگر باعث بازسازی چندبارهٔ DOM نمی‌شوند.
  let scrollQueued = false;
  let scrollSmooth = true;
  function scrollToBottom(smooth = true) {
    scrollSmooth = smooth;
    if (scrollQueued) return;
    scrollQueued = true;
    requestAnimationFrame(() => {
      scrollQueued = false;
      el.scroll.scrollTo({ top: el.scroll.scrollHeight, behavior: scrollSmooth ? "smooth" : "auto" });
    });
  }

  // آیا متن تا اینجا نشانهٔ مارک‌داون دارد؟ اگر نه، مسیر سریع متن ساده.
  const MD_HINT = /(^|\n)(#{1,6} |[-*+] |\d+\. |> |```|\|)|`[^`]+`|\*\*[^*]+\*\*/;
  function paintStreaming(bubble, text, done) {
    if (!done && !MD_HINT.test(text)) {
      bubble.textContent = text;
      return;
    }
    bubble.innerHTML = renderMarkdown(text);
  }

  function buildMessage(msg) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${msg.role === "user" ? "user" : "bot"}`;
    wrap.dataset.id = msg.id || "";

    const who = document.createElement("div");
    who.className = "who";
    if (msg.role === "user") {
      who.textContent = initials(state.user ? (state.user.name || state.user.email) : "م");
    } else {
      const orb = document.createElement("span");
      orb.className = "orb-live who-orb";
      orb.style.width = "32px";
      orb.style.height = "32px";
      const img = document.createElement("img");
      img.src = "/static/assets/brand/orb-live-sm.webp";
      img.alt = "رایان";
      img.width = 32;
      img.height = 32;
      const face = document.createElement("span"); face.className = "face";
      const l = document.createElement("i"); l.className = "lid l";
      const r = document.createElement("i"); r.className = "lid r";
      face.append(l, r);
      orb.append(img, face);
      who.append(orb);
      if (window.RAYAN && window.RAYAN.initOrbs) window.RAYAN.initOrbs(who);
    }

    const body = document.createElement("div");
    body.className = "msg-body";

    if (msg.role === "user") {
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = msg.content;
      body.append(bubble, toolsFor(msg));
    } else {
      if (msg.meta && msg.meta.trace) body.append(traceEl(msg.meta.trace));
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.innerHTML = renderMarkdown(msg.content);
      body.append(bubble);
      if (msg.meta && msg.meta.tool) body.append(toolEl(msg.meta.tool));
      if (msg.meta && msg.meta.stats) body.append(statsEl(msg.meta.stats, msg.meta.deep));
      if (!msg.streaming) body.append(toolsFor(msg));
    }
    wrap.append(who, body);
    return wrap;
  }

  function toolEl(tool) {
    const box = document.createElement("div");
    box.className = "tool-result";
    const labels = { calc: "ماشین‌حساب", now: "تاریخ و ساعت", convert: "تبدیل یکا", text: "آمار متن" };
    const name = labels[tool.tool] || tool.tool;
    let value = "";
    if (tool.tool === "calc") value = `${nf(tool.value)}`;
    else if (tool.tool === "now") value = tool.jalali_long || tool.iso;
    else if (tool.tool === "convert") value = `${nf(tool.value)} ${tool.to}`;
    else if (tool.tool === "text") value = `${nf(tool.words)} واژه · ${nf(tool.chars)} نویسه`;
    box.innerHTML = `<span class="tool-badge">${name}</span><b>${value}</b>`;
    return box;
  }

  // فقط چیزی که به کار کاربر می‌آید؛ شمار توکن و اطمینان داخلی را نشان نمی‌دهیم
  function statsEl(stats, deep) {
    const elx = document.createElement("div");
    elx.className = "msg-stats";
    const bits = [];
    const secs = Number(stats?.seconds || 0);
    if (secs > 0) bits.push(`پاسخ در ${nf(secs, 1)} ثانیه`);
    if (deep) bits.push("اندیشهٔ ژرف · چهار مسیر");
    if (!bits.length) bits.push("پاسخ آماده");
    elx.textContent = bits.join(" · ");
    return elx;
  }

  function sourcesEl(sources) {
    const box = document.createElement("div");
    box.className = "msg-sources";
    const head = document.createElement("div");
    head.className = "sources-head";
    head.innerHTML = `<span class="sources-badge">وب</span><span>${nf(sources.length)} منبع</span>`;
    const list = document.createElement("div");
    list.className = "sources-list";
    sources.forEach((item, index) => {
      const card = document.createElement("a");
      card.className = "source-card";
      card.href = item.url;
      card.target = "_blank";
      card.rel = "noopener noreferrer nofollow";
      card.innerHTML = `<span class="source-index">${nf(index + 1)}</span>
        <span class="source-body"><b>${escapeHtml(item.title || "منبع")}</b>
        <em>${escapeHtml(item.domain || "")}</em></span>`;
      list.append(card);
    });
    box.append(head, list);
    return box;
  }

  function traceEl(trace) {
    const details = document.createElement("details");
    details.className = "trace";
    const summary = document.createElement("summary");
    summary.textContent = `اندیشهٔ ژرف — ${trace.rationale || "بهترین مسیر انتخاب شد"}`;
    const body = document.createElement("div");
    body.className = "trace-body";
    if (Array.isArray(trace.candidates)) {
      const ul = document.createElement("ul");
      trace.candidates.forEach((c) => {
        const li = document.createElement("li");
        li.innerHTML = `<b>مسیر ${nf(c.index)}</b><span>${escapeHtml((c.preview || "").slice(0, 70))}</span>
          <span class="score">${nf(c.score, 2)}</span>`;
        ul.append(li);
      });
      body.append(ul);
    }
    details.append(summary, body);
    return details;
  }

  function toolsFor(msg) {
    const bar = document.createElement("div");
    bar.className = "msg-tools";
    const mk = (label, icon, handler, title) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tool-mini";
      btn.title = title || label;
      btn.setAttribute("aria-label", label);
      btn.innerHTML = icon;
      btn.addEventListener("click", handler);
      return btn;
    };
    const copyIcon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="9" y="9" width="12" height="12" rx="2.4"/><path d="M15 5.5A2.5 2.5 0 0 0 12.5 3h-7A2.5 2.5 0 0 0 3 5.5v7A2.5 2.5 0 0 0 5.5 15"/></svg>';
    const redoIcon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/></svg>';
    const upIcon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M7 14l5-5 5 5"/></svg>';
    const downIcon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M7 10l5 5 5-5"/></svg>';

    bar.append(mk("کپی پاسخ", copyIcon, async () => {
      await copyText(msg.content);
      toast("متن کپی شد.", "ok");
    }));
    if (msg.role === "assistant") {
      const studio = window.RAYAN_STUDIO;
      if (studio && msg.content) {
        const arts = studio.extractArtifacts(msg.content);
        if (arts.length) {
          const fileIcon = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M14 3v5h5"/><path d="M6 3h8l5 5v13H6z"/></svg>';
          arts.forEach((art, index) => {
            bar.append(mk(arts.length > 1 ? `پیش‌نمایش ${index + 1}` : "پیش‌نمایش فایل", fileIcon, () => {
              studio.openArtifact(Object.assign({ name: `rayan-${Date.now()}` }, art));
            }));
          });
        }
      }
      bar.append(mk("تولید دوباره", redoIcon, () => regenerate(msg)));
      bar.append(mk("پاسخ خوب بود", upIcon, () => sendFeedback(msg, 1)));
      bar.append(mk("پاسخ بد بود", downIcon, () => sendFeedback(msg, -1)));
    }
    return bar;
  }

  // هر پاسخ کامل، یک رویداد می‌شود تا حالت صوتی بتواند بلند بخواند
  function announceAnswer(text) {
    if (!text) return;
    document.dispatchEvent(new CustomEvent("rayan:answer", { detail: { text } }));
  }

  async function sendFeedback(msg, value) {
    try {
      await request("/api/feedback", { method: "POST", body: { message_id: msg.id || null, value } });
      toast(value > 0 ? "ممنون از بازخوردت." : "ثبت شد؛ روی بهبود کار می‌کنیم.", value > 0 ? "ok" : "");
    } catch { /* اختیاری */ }
  }

  // ------------------------------------------------------------ تولید
  function appendUserMessage(text) {
    const msg = { role: "user", content: text };
    state.messages.push(msg);
    el.messages.append(buildMessage(msg));
  }

  function appendBotShell() {
    const msg = { role: "assistant", content: "", streaming: true };
    state.messages.push(msg);
    state.streamOrb = null;
    const node = buildMessage(msg);
    const bubble = node.querySelector(".bubble");
    bubble.classList.add("streaming");
    bubble.innerHTML = '<span class="typing" aria-label="در حال نوشتن"><i></i><i></i><i></i></span>';
    state.streamOrb = node.querySelector(".who-orb");
    if (state.streamOrb) state.streamOrb.dataset.state = "writing";
    setOrbState("thinking");
    el.messages.append(node);
    scrollToBottom();
    return { msg, node, bubble };
  }

  function historyPayload() {
    const turns = [];
    let pendingUser = null;
    state.messages.slice(0, -1).forEach((msg) => {
      if (msg.role === "user") pendingUser = msg.content;
      else if (pendingUser) {
        turns.push({ user: pendingUser, assistant: msg.content });
        pendingUser = null;
      }
    });
    return turns.slice(-2);
  }

  function setOrbState(next) {
    // اول کرهٔ پیامِ در حال پخش، بعد آخرین کرهٔ گفتگو، و فقط در گفتگوی خالی کرهٔ خوش‌آمد
    const orbs = [...document.querySelectorAll(".who-orb")];
    let orb = state.streamOrb && state.streamOrb.isConnected ? state.streamOrb : null;
    if (!orb) orb = orbs[orbs.length - 1] || document.querySelector(".empty-orb .orb-live");
    if (orb) orb.dataset.state = next || "";
    orbs.forEach((node) => {
      if (node !== orb) node.dataset.state = "";
    });
  }

  function setBusy(busy) {
    state.sending = busy;
    if (busy) setOrbState("writing");
    if (!busy) setOrbState("happy");
    if (!busy) setTimeout(() => setOrbState(""), 1200);
    el.send.hidden = busy;
    el.stop.hidden = !busy;
    el.composer.classList.toggle("is-busy", busy);
    updateHint();
  }

  function updateHint() {
    if (state.sending) { el.hint.textContent = "دستیار در حال نوشتن است…"; return; }
    const usage = state.usage || {};
    const chat = usage.chat || {};
    if (chat.limit) {
      const remaining = Math.max(0, chat.limit - (chat.used || 0));
      el.hint.textContent = `${nf(remaining)} پیام باقی‌مانده امروز`;
    } else {
      el.hint.textContent = "برای ارسال Enter · برای خط تازه Shift+Enter";
    }
  }

  async function send() {
    if (state.sending) return;
    const text = el.prompt.value.trim();
    if (!text) return;
    if (state.mode === "chat" && !text) return;

    el.prompt.value = "";
    resizePrompt();
    appendUserMessage(text);
    updateEmptyState();
    scrollToBottom();
    setBusy(true);

    const wantsDeep = state.deep && state.mode === "chat";
    const wantsWeb = state.web && state.mode === "chat" && !wantsDeep;
    if (wantsDeep || wantsWeb) {
      const { msg, bubble } = appendBotShell();
      try {
        const data = await request("/api/chat", {
          method: "POST",
          body: {
            message: text,
            conversation_id: state.currentId,
            model: state.model,
            mode: state.mode,
            deep: wantsDeep,
            web: wantsWeb,
            candidates: state.settings.candidates,
            temperature: state.settings.temperature,
            top_p: state.settings.top_p,
            max_new_tokens: state.settings.max_new_tokens,
            history: historyPayload(),
          },
        });
        msg.content = data.answer || "…";
        msg.meta = { stats: data.stats, trace: data.trace, deep: wantsDeep, tool: data.tool, sources: data.sources };
        msg.streaming = false;
        msg.id = data.message_id;
        bubble.classList.remove("streaming");
        bubble.innerHTML = renderMarkdown(msg.content);
        const body = bubble.parentElement;
        body.querySelector(".msg-stats")?.remove();
        if (msg.meta.stats && wantsDeep) body.append(statsEl(msg.meta.stats, true));
        body.querySelector(".msg-sources")?.remove();
        if (data.sources && data.sources.length) body.append(sourcesEl(data.sources));
        body.querySelector(".msg-tools")?.remove();
        body.append(toolsFor(msg));
        if (data.trace) body.prepend(traceEl(data.trace));
        if (data.tool) body.prepend(toolEl(data.tool));
        if (data.usage) { state.usage = Object.assign({}, state.usage, { chat: data.usage }); renderUsage(); }
        announceAnswer(msg.content);
        await afterTurn(data);
      } catch (err) {
        failShell(bubble, err);
      } finally {
        setBusy(false);
      }
      return;
    }

    const { msg, bubble } = appendBotShell();
    const controller = new AbortController();
    state.controller = controller;
    let answer = "";
    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        credentials: "include",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          conversation_id: state.currentId,
          model: state.model,
          mode: state.mode,
          temperature: state.settings.temperature,
          top_p: state.settings.top_p,
          max_new_tokens: state.settings.max_new_tokens,
          history: historyPayload(),
        }),
      });
      if (!response.ok) {
        let detail = `خطای سرور (${response.status})`;
        try {
          const data = await response.json();
          if (typeof data.detail === "string") detail = data.detail;
        } catch { /* بدنهٔ غیر JSON */ }
        throw new Error(detail);
      }
      bubble.innerHTML = "";
      const reader = response.body.getReader();
      const Decoder = window.TextDecoder || TextDecoder;
      const decoder = new Decoder();
      let buffer = "";
      let first = true;
      let paintQueued = false;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          let event;
          try { event = JSON.parse(line); } catch { continue; }
          if (event.type === "token") {
            answer += event.text;
            if (first) { bubble.classList.add("streaming"); first = false; }
            if (!paintQueued) {
              paintQueued = true;
              requestAnimationFrame(() => {
                paintQueued = false;
                if (!msg.streaming) return;          // «done» زودتر آمده؛ نقاشی نهایی کافی است
                paintStreaming(bubble, answer, false);
                scrollToBottom(false);
              });
            }
          } else if (event.type === "done") {
            msg.content = event.answer || answer;
            msg.id = event.message_id;
            msg.meta = { stats: event.stats, tool: event.tool, deep: false, sources: event.sources || [] };
            msg.streaming = false;
            bubble.classList.remove("streaming");
            if (state.streamOrb) { state.streamOrb.dataset.state = "happy"; state.streamOrb = null; }
            paintStreaming(bubble, msg.content, true);
            if (event.tool) bubble.parentElement.append(toolEl(event.tool));
            if (event.sources && event.sources.length) bubble.parentElement.append(sourcesEl(event.sources));
            if (event.stats) bubble.parentElement.append(statsEl(event.stats, false));
            bubble.parentElement.append(toolsFor(msg));
            if (event.usage) { state.usage = Object.assign({}, state.usage, { chat: event.usage }); renderUsage(); }
            announceAnswer(msg.content);
            await afterTurn(event);
          } else if (event.type === "error") {
            throw new Error(event.error || "تولید پاسخ متوقف شد.");
          }
        }
      }
      if (msg.streaming) {
        msg.content = answer;
        msg.streaming = false;
        bubble.classList.remove("streaming");
        if (state.streamOrb) { state.streamOrb.dataset.state = ""; state.streamOrb = null; }
        bubble.innerHTML = renderMarkdown(answer || "…");
      }
    } catch (err) {
      if (err.name === "AbortError") {
        msg.content = answer;
        msg.streaming = false;
        bubble.classList.remove("streaming");
        bubble.innerHTML = renderMarkdown(answer || "تولید متوقف شد.");
        toast("تولید متوقف شد.", "");
      } else {
        failShell(bubble, err, answer);
      }
    } finally {
      state.controller = null;
      setBusy(false);
    }
  }

  function failShell(bubble, err, partial = "") {
    bubble.classList.remove("streaming");
    if (state.streamOrb) { state.streamOrb.dataset.state = ""; state.streamOrb = null; }
    bubble.innerHTML = renderMarkdown(partial) || "";
    const alert = document.createElement("div");
    alert.className = "form-alert";
    alert.style.marginTop = "10px";
    alert.textContent = err.message;
    if (err.status === 429) {
      const link = document.createElement("a");
      link.href = "/signup";
      link.style.marginInlineStart = "8px";
      link.style.color = "var(--blue-2)";
      link.textContent = "ساخت حساب رایگان";
      alert.append(link);
    }
    bubble.parentElement.append(alert);
    toast(err.message, "error");
  }

  async function afterTurn(data) {
    if (data.conversation_id) {
      const isNew = !state.currentId;
      state.currentId = data.conversation_id;
      history.replaceState({}, "", `/chat?c=${state.currentId}`);
      await loadConversations();
      if (isNew) renderConversations();
    }
    await refreshAuth();
  }

  async function regenerate(msg) {
    const index = state.messages.indexOf(msg);
    if (index < 1) return;
    const previousUser = [...state.messages.slice(0, index)].reverse().find((m) => m.role === "user");
    if (!previousUser) return;
    state.messages = state.messages.slice(0, index);
    el.messages.innerHTML = "";
    state.messages.forEach((m) => el.messages.append(buildMessage(m)));
    el.prompt.value = previousUser.content;
    await send();
  }

  // ------------------------------------------------------------- تنظیمات
  function syncSettingsUI() {
    const s = state.settings;
    $("#set-temp").value = s.temperature;
    $("#set-topp").value = s.top_p;
    $("#set-tokens").value = s.max_new_tokens;
    $("#set-candidates").value = s.candidates;
    $("#temp-value").textContent = nf(s.temperature, 2);
    $("#topp-value").textContent = nf(s.top_p, 2);
    const tokens = $("#tokens-value");
    if (tokens) tokens.textContent = nf(s.max_new_tokens) + " توکن";
    const cand = $("#cand-value");
    if (cand) cand.textContent = nf(s.candidates);
  }
  $("#settings-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    syncSettingsUI();
    const pop = $("#settings-modal");
    pop.hidden = !pop.hidden;
  });
  document.addEventListener("pointerdown", (event) => {
    const pop = $("#settings-modal");
    if (!pop || pop.hidden) return;
    if (pop.contains(event.target) || $("#settings-btn").contains(event.target)) return;
    pop.hidden = true;
    saveSettings();
  });
  $("#set-temp").addEventListener("input", (e) => {
    state.settings.temperature = Number(e.target.value);
    $("#temp-value").textContent = nf(state.settings.temperature, 2);
  });
  $("#set-topp").addEventListener("input", (e) => {
    state.settings.top_p = Number(e.target.value);
    $("#topp-value").textContent = nf(state.settings.top_p, 2);
  });
  $("#set-tokens").addEventListener("input", (e) => {
    state.settings.max_new_tokens = Math.max(40, Math.min(220, Number(e.target.value) || 110));
    $("#tokens-value").textContent = nf(state.settings.max_new_tokens) + " توکن";
  });
  $("#set-candidates").addEventListener("input", (e) => {
    state.settings.candidates = Math.max(2, Math.min(6, Number(e.target.value) || 4));
    $("#cand-value").textContent = nf(state.settings.candidates);
  });
  $("#reset-settings").addEventListener("click", () => {
    state.settings = Object.assign({}, DEFAULTS);
    syncSettingsUI();
    saveSettings();
    toast("تنظیمات بازنشانی شد.", "ok");
  });
  document.querySelectorAll("[data-close='settings-modal']").forEach((btn) => {
    btn.addEventListener("click", saveSettings);
  });

  // --------------------------------------------------------------- خروجی
  function download(filename, content, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  $("#export-btn").addEventListener("click", () => {
    if (!state.messages.length) { toast("گفتگویی برای خروجی نیست.", ""); return; }
    const title = state.conversations.find((c) => c.id === state.currentId)?.title || "گفتگوی من";
    const markdown = [`# ${title}`, "", `_مدل ۱ — کوچک · ${new Date().toLocaleString("fa-IR")}_`, ""];
    state.messages.forEach((m) => {
      markdown.push(m.role === "user" ? "## تو" : "## دستیار");
      markdown.push(m.content, "");
    });
    download(`rayan-${Date.now()}.md`, markdown.join("\n"), "text/markdown;charset=utf-8");
    toast("خروجی Markdown ذخیره شد.", "ok");
  });

  // --------------------------------------------------------- سرورها/فرم
  // پل کوچک برای حالت صوتی: پر کردن کادر و ارسال همان مسیر معمول
  window.RAYAN_CHAT = {
    setPrompt(text) {
      el.prompt.value = text;
      el.prompt.dispatchEvent(new Event("input", { bubbles: true }));
      el.prompt.focus({ preventScroll: true });
    },
    submit() {
      el.composer.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    },
    say(text) {
      el.prompt.value = text;
      el.prompt.dispatchEvent(new Event("input", { bubbles: true }));
      el.composer.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    },
    isBusy() {
      return !!state.controller;
    },
  };

  // منوی «+» ابزارها؛ مثل دستیارهای بزرگ، ابزارها تا لحظهٔ نیاز پنهان‌اند
  const toolsBtn = $("#tools-btn");
  const toolsMenu = $("#composer-tools");
  function setTools(open) {
    if (!toolsBtn || !toolsMenu) return;
    toolsMenu.hidden = !open;
    toolsBtn.setAttribute("aria-expanded", String(open));
    toolsBtn.classList.toggle("is-open", open);
  }
  if (toolsBtn && toolsMenu) {
    toolsBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      setTools(toolsMenu.hidden);
    });
    document.addEventListener("click", (event) => {
      if (!toolsMenu.hidden && !event.target.closest("#composer-tools, #tools-btn")) setTools(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setTools(false);
    });
  }

  el.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    send();
  });
  el.prompt.addEventListener("input", resizePrompt);
  function resizePrompt() {
    el.prompt.style.height = "auto";
    el.prompt.style.height = `${Math.min(el.prompt.scrollHeight, 210)}px`;
  }
  el.prompt.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send();
    }
  });
  el.stop.addEventListener("click", () => {
    if (state.controller) state.controller.abort();
  });
  if (el.web) {
    el.web.setAttribute("aria-pressed", String(state.web));
    el.web.addEventListener("click", () => {
      state.web = !state.web;
      el.web.setAttribute("aria-pressed", String(state.web));
      localStorage.setItem("rayan.web", state.web ? "1" : "0");
      updateHint();
      toast(state.web ? "جست‌وجوی وب روشن شد؛ پاسخ با منبع و لینک می‌آید." : "جست‌وجوی وب خاموش شد.", "");
    });
  }
  el.deep.addEventListener("click", () => {
    state.deep = !state.deep;
    el.deep.setAttribute("aria-pressed", String(state.deep));
    toast(state.deep ? "اندیشهٔ ژرف روشن شد؛ هر پاسخ چند مسیر را بررسی می‌کند." : "اندیشهٔ ژرف خاموش شد.", "");
  });
  el.mode.addEventListener("change", () => {
    state.mode = el.mode.value;
    el.prompt.placeholder = state.mode === "continue" ? "متن را بنویس تا ادامه‌اش را بسازم…"
      : state.mode === "poetry" ? "موضوع بیت را بنویس (یا خالی بگذار)…"
      : "پیامت را بنویس…";
    if (state.mode !== "chat" && state.deep) {
      state.deep = false;
      el.deep.setAttribute("aria-pressed", "false");
    }
  });
  $("#new-chat").addEventListener("click", newChat);

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      newChat();
    }
    if ((event.ctrlKey || event.metaKey) && event.key === "/") {
      event.preventDefault();
      $("#settings-btn").click();
    }
  });

  el.search.addEventListener("input", () => {
    state.query = el.search.value;
    renderConversations();
  });

  $("#account-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    const open = el.accountMenu.hidden;
    el.accountMenu.hidden = !open;
    $("#account-btn").setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", () => {
    el.accountMenu.hidden = true;
    el.modelMenu.hidden = true;
  });

  $$(".chip[data-scroll]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const target = chip.getAttribute("data-scroll");
      const prompts = {
        models: "مدل زبانی چیست و چطور یاد می‌گیرد؟",
        pricing: "سهمیهٔ من امروز چقدر است؟",
        honest: "چه چیزهایی را نمی‌توانی انجام دهی؟",
      };
      el.prompt.value = prompts[target] || "";
      el.prompt.focus();
      resizePrompt();
    });
  });

  // ------------------------------------------------------------ پیشنهادها
  async function loadSuggestions() {
    try {
      const data = await request("/api/samples");
      renderSuggestions(data.samples || []);
    } catch {
      renderSuggestions([
        { mode: "chat", title: "خودت را معرفی کن", text: "خودت را معرفی کن" },
        { mode: "chat", title: "یک شعر", text: "یک شعر بگو" },
        { mode: "chat", title: "دربارهٔ ایران", text: "دربارهٔ ایران برایم بگو" },
        { mode: "continue", title: "ادامهٔ متن", text: "در دل کویر، شب‌ها آسمان پر از ستاره است و" },
      ]);
    }
  }

  function renderSuggestions(list) {
    el.suggestions.innerHTML = "";
    list.slice(0, 4).forEach((sample) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "suggestion";
      btn.innerHTML = `<b>${escapeHtml(sample.title || sample.text)}</b>
        <span>${escapeHtml(sample.text ? sample.text.slice(0, 64) : MODE_LABELS[sample.mode] || "")}</span>`;
      btn.addEventListener("click", () => {
        if (sample.mode === "poetry") {
          state.mode = "poetry";
          el.mode.value = "poetry";
          el.prompt.value = sample.text || "";
        } else if (sample.mode === "continue") {
          state.mode = "continue";
          el.mode.value = "continue";
          el.prompt.value = sample.text;
        } else {
          state.mode = "chat";
          el.mode.value = "chat";
          el.prompt.value = sample.text || sample.title;
        }
        el.prompt.focus();
        resizePrompt();
      });
      el.suggestions.append(btn);
    });
  }

  // ---------------------------------------------------------------- آغاز
  async function init() {
    syncSettingsUI();
    updateHint();
    updateEmptyState();
    resizePrompt();
    if (!state.settings) state.settings = Object.assign({}, DEFAULTS);

    const params = new URLSearchParams(location.search);
    restoreSidebar();
    loadModels();
    loadSuggestions();
    loadConversations();

    try {
      const auth = await request("/api/auth/me");
      applyUser(auth);
    } catch {
      applyUser({ user: null, plan: "guest", usage: null });
    }

    const target = params.get("c");
    if (target) {
      await openConversation(target, false);
    } else {
      updateEmptyState();
    }

    if (params.get("prompt")) {
      el.prompt.value = params.get("prompt").slice(0, 800);
      resizePrompt();
      el.prompt.focus();
    }
    if (window.RAYAN.config.static) {
      el.prompt.disabled = true;
      el.prompt.placeholder = "نسخهٔ نمایشی روی GitHub Pages — برای گفتگو سرور را اجرا کنید.";
      const send = $("#send-btn");
      if (send) send.disabled = true;
      const hint = $("#composer-hint");
      if (hint) hint.textContent = "این نسخه فقط برای نمایش رابط است.";
      el.composer.classList.add("is-static");
    } else if (window.RAYAN.config.offline) {
      toast("سرور در دسترس نیست؛ حالت نمایشی.", "error");
    }
  }

  init();
})();
