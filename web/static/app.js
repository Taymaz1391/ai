/* ============================================================
   پارسیا — منطق رابط کاربری
   بدون هیچ کتابخانه؛ گفتگوی جریانی، اندیشه‌نامه و نمودارهای واقعی
   ============================================================ */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const faFormatter = new Intl.NumberFormat("fa-IR");
  const fa = (n, digits = 0) => {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
    return new Intl.NumberFormat("fa-IR", { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(Number(n));
  };
  const pct = (x) => `${fa(Math.round((x || 0) * 100))}٪`;
  const compact = (n) => {
    if (!n && n !== 0) return "—";
    if (n >= 1e9) return `${fa(n / 1e9, 2)} میلیارد`;
    if (n >= 1e6) return `${fa(n / 1e6, 2)} میلیون`;
    if (n >= 1e3) return `${fa(n / 1e3, 1)} هزار`;
    return fa(n);
  };
  const duration = (sec) => {
    if (!Number.isFinite(sec) || sec < 0) return "—";
    if (sec < 60) return `${fa(Math.round(sec))} ثانیه`;
    if (sec < 3600) return `${fa(Math.round(sec / 60))} دقیقه`;
    const h = Math.floor(sec / 3600);
    const m = Math.round((sec % 3600) / 60);
    return `${fa(h)} ساعت${m ? ` و ${fa(m)} دقیقه` : ""}`;
  };
  const timeAgo = (ts) => {
    if (!ts) return "—";
    const diff = Math.max(0, Date.now() / 1000 - ts);
    if (diff < 60) return `${fa(Math.round(diff))} ثانیه پیش`;
    if (diff < 3600) return `${fa(Math.round(diff / 60))} دقیقه پیش`;
    return `${fa(Math.round(diff / 3600))} ساعت پیش`;
  };
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const debounce = (fn, ms) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  };
  const lrFmt = (lr) => (lr === undefined || lr === null ? "—" : fa(lr, 5));

  const store = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* حافظهٔ خصوصی */ }
    },
  };

  const state = {
    view: "chat",
    mode: "chat",
    sessionId: store.get("parsia.session", null) || makeId(),
    messages: store.get("parsia.history", []),
    deep: store.get("parsia.deep", false),
    temperature: store.get("parsia.temperature", 0.82),
    samples: [],
    health: null,
    metrics: null,
    model: null,
    streaming: false,
    abort: null,
    chartPoints: null,
  };
  store.set("parsia.session", state.sessionId);

  function makeId() {
    try { return crypto.randomUUID(); }
    catch { return `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`; }
  }

  /* ---------------------------------------------------------- کوچک‌ها */
  let toastTimer;
  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-visible"), 2600);
  }

  async function getJSON(url) {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error((await safeDetail(res)) || `HTTP ${res.status}`);
    return res.json();
  }

  async function safeDetail(res) {
    try {
      const data = await res.json();
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("، ");
      return null;
    } catch { return null; }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("در حافظه کپی شد");
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.append(area);
      area.select();
      try { document.execCommand("copy"); toast("کپی شد"); } catch { toast("کپی ممکن نشد"); }
      area.remove();
    }
  }

  const STAR = `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="15" y="15" width="34" height="34" rx="8" fill="none" stroke="currentColor" stroke-width="2" transform="rotate(45 32 32)"/><circle cx="32" cy="32" r="3" fill="currentColor"/></svg>`;

  /* ---------------------------------------------------------- ناوبری */
  function setView(view, push = true) {
    if (!["chat", "model", "training", "about"].includes(view)) view = "chat";
    state.view = view;
    $$(".view").forEach((section) => section.classList.toggle("is-active", section.id === `view-${view}`));
    $$(".nav-link").forEach((btn) => btn.classList.toggle("is-active", btn.dataset.view === view));
    if (push) history.replaceState(null, "", `#${view}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (view === "training") { refreshMetrics(); drawMainChart(); }
    if (view === "model") refreshModel();
  }

  $$(".nav-link").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-view-link]");
    if (link) setView(link.dataset.viewLink);
  });
  window.addEventListener("hashchange", () => setView(location.hash.replace("#", "") || "chat", false));

  /* ---------------------------------------------------------- وضعیت */
  function setStatus(kind, text) {
    const pill = $("#status-pill");
    pill.classList.remove("is-ready", "is-training", "is-offline");
    if (kind) pill.classList.add(kind);
    $("#status-text").textContent = text;
  }

  function applyHealth(h) {
    state.health = h;
    if (!h.ok) {
      setStatus("is-offline", "مدل بارگذاری نشده");
    } else if (h.training_active) {
      const step = h.latest_train?.step ?? h.latest_eval?.step ?? h.model?.step;
      setStatus("is-training", `در حال آموزش${step ? ` · گام ${fa(step)}` : ""}`);
    } else {
      setStatus("is-ready", "آماده · محلی");
    }
    if (h.model?.params) {
      $$("[data-model-params]").forEach((el) => (el.textContent = compact(h.model.params)));
      $$("[data-about-params]").forEach((el) => (el.textContent = compact(h.model.params)));
    }
  }

  async function refreshHealth() {
    try {
      const h = await getJSON("/api/health");
      applyHealth(h);
    } catch {
      setStatus("is-offline", "ارتباط قطع است");
    }
  }

  /* ---------------------------------------------------------- داده‌های مدل */
  async function refreshModel() {
    if (!state.model) {
      try { state.model = await getJSON("/api/model"); } catch { return; }
    }
    const m = state.model;
    const params = m.params;
    $$("[data-spec='params']").forEach((el) => (el.textContent = fa(params)));
    $$("[data-model-params]").forEach((el) => (el.textContent = compact(params)));
    $$("[data-about-params]").forEach((el) => (el.textContent = compact(params)));
    const vocab = m.config?.vocab_size ?? m.tokenizer?.vocab_size;
    $$("[data-model-vocab]").forEach((el) => (el.textContent = fa(vocab)));
    const best = m.metrics?.best_eval;
    if (best?.bits_per_char) {
      const el = $("#spec-data");
      if (el) el.textContent = `${compact(m.meta?.tokens_seen)} توکن · bpc ${fa(best.bits_per_char, 3)}`;
    }
  }

  function renderSpecs() {
    if (!state.model) return;
    const tokenizer = state.model.tokenizer || {};
    const cfg = state.model.config || {};
    const table = {
      params: state.model.params,
      vocab: cfg.vocab_size || tokenizer.vocab_size,
    };
    $$("[data-spec]").forEach((el) => {
      const key = el.dataset.spec;
      if (table[key] !== undefined) el.textContent = fa(table[key]);
    });
  }

  $("#copy-config")?.addEventListener("click", () => {
    if (!state.model) return;
    copyText(JSON.stringify({
      name: state.model.name,
      params: state.model.params,
      config: state.model.config,
      tokenizer: state.model.tokenizer,
      training: state.model.meta,
    }, null, 2));
  });

  /* ---------------------------------------------------------- گفتگو */
  const chatLog = $("#chat-log");
  const input = $("#input");
  const sendBtn = $("#send");
  const stopBtn = $("#stop");
  let welcomeTemplate = $("#welcome")?.outerHTML || "";

  function scrollToBottom(force = false) {
    const gap = chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight;
    if (force || gap < 140) chatLog.scrollTop = chatLog.scrollHeight;
  }

  function clearWelcome() {
    const welcome = $("#welcome");
    if (welcome) welcome.remove();
  }

  function renderSuggestions() {
    const holder = $("#suggestions");
    if (!holder) return;
    const list = state.samples.length ? state.samples : [
      { mode: "chat", title: "خودت را معرفی کن", text: "تو کی هستی؟" },
      { mode: "chat", title: "یک شعر", text: "یک شعر بگو" },
      { mode: "continue", title: "ادامهٔ متن", text: "در دل کویر، شب‌ها آسمان پر از ستاره است و" },
      { mode: "poetry", title: "بیت‌سازی", text: "" },
    ];
    const ordered = [...list].sort((a, b) => (b.mode === state.mode) - (a.mode === state.mode)).slice(0, 4);
    holder.innerHTML = "";
    ordered.forEach((sample) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "suggestion";
      const title = document.createElement("b");
      title.textContent = sample.title;
      const preview = document.createElement("span");
      preview.textContent = sample.text ? sample.text.slice(0, 62) : "یک شعر تازه بساز";
      btn.append(title, preview);
      btn.addEventListener("click", () => {
        state.mode = sample.mode;
        syncModeTabs();
        if (!sample.text) {
          sendMessage(null, { mode: sample.mode });
        } else {
          input.value = sample.text;
          autosize();
          input.focus();
        }
      });
      holder.append(btn);
    });
  }

  function addMessage(role, text, opts = {}) {
    clearWelcome();
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${role}`;
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    if (role === "user") avatar.textContent = "ش";
    else avatar.innerHTML = STAR;

    const bubbleWrap = document.createElement("div");
    bubbleWrap.className = "bubble-wrap";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (opts.streaming) bubble.classList.add("streaming");
    if (opts.error) bubble.classList.add("is-error");
    bubble.textContent = text || "";
    bubbleWrap.append(bubble);

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.hidden = !opts.metaText;
    if (opts.metaText) meta.textContent = opts.metaText;
    bubbleWrap.append(meta);

    let traceEl = null;
    if (opts.trace) {
      traceEl = buildTrace(opts.trace);
      bubbleWrap.append(traceEl);
    }

    wrapper.append(avatar, bubbleWrap);
    chatLog.append(wrapper);
    scrollToBottom(true);
    return { wrapper, bubble, meta, traceEl };
  }

  function setMeta(entry, text, extra = null) {
    entry.meta.hidden = false;
    entry.meta.textContent = text;
    if (extra) {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.textContent = "کپی";
      copy.addEventListener("click", () => copyText(entry.bubble.textContent));
      const sep = document.createElement("span");
      sep.className = "dot-sep";
      entry.meta.append(sep, copy);
    }
  }

  function buildTrace(trace) {
    const details = document.createElement("details");
    details.className = "trace";
    const summary = document.createElement("summary");
    const label = document.createElement("span");
    label.textContent = `اندیشه‌نامه · ${fa(trace.candidates?.length || 0)} مسیر`;
    const show = document.createElement("b");
    show.textContent = "نمایش";
    summary.append(label, show);

    const body = document.createElement("div");
    body.className = "trace-body";
    const note = document.createElement("p");
    note.className = "trace-note";
    note.textContent = trace.rationale || "";
    body.append(note);

    const candidates = trace.candidates || [];
    if (candidates.length) {
      const scores = candidates.map((c) => c.score);
      const lo = Math.min(...scores);
      const hi = Math.max(...scores);
      candidates.forEach((cand) => {
        const row = document.createElement("div");
        row.className = "candidate" + (cand.index === trace.chosen ? " is-chosen" : "");
        const idx = document.createElement("span");
        idx.className = "idx";
        idx.textContent = fa(cand.index);
        const info = document.createElement("div");
        const title = document.createElement("div");
        title.textContent = cand.preview || cand.text?.slice(0, 80) || "";
        title.className = "preview";
        const bar = document.createElement("div");
        bar.className = "bar";
        const fill = document.createElement("i");
        fill.style.width = `${hi === lo ? 100 : 12 + ((cand.score - lo) / (hi - lo)) * 88}%`;
        bar.append(fill);
        info.append(title, bar);
        const score = document.createElement("span");
        score.className = "score";
        score.textContent = cand.index === trace.chosen ? "برگزیده" : fa(cand.score, 2);
        score.title = `اطمینان ${pct(cand.confidence)} · تکرار ${pct(cand.repetition)}`;
        row.append(idx, info, score);
        body.append(row);
      });
      const foot = document.createElement("p");
      foot.className = "trace-note";
      foot.textContent = "امتیاز = اطمینان مدل − جریمهٔ تکرار + پاداش فارسی‌بودن و پایان جمله.";
      body.append(foot);
    }
    details.append(summary, body);
    return details;
  }

  function autosize() {
    input.style.height = "auto";
    input.style.height = `${Math.min(150, Math.max(40, input.scrollHeight))}px`;
  }

  function setBusy(busy) {
    state.streaming = busy;
    sendBtn.disabled = busy;
    stopBtn.hidden = !busy;
    input.disabled = false;
  }

  function syncModeTabs() {
    $$(".mode-tab").forEach((tab) => {
      const active = tab.dataset.mode === state.mode;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    input.placeholder = state.mode === "chat"
      ? "به فارسی بنویس…"
      : state.mode === "continue"
        ? "متن آغازین را بنویس تا ادامه بدهم…"
        : "موضوع یا مصرعِ آغازین (اختیاری)…";
  }

  function saveHistory() {
    store.set("parsia.history", state.messages.slice(-20));
  }

  function buildHistory(messages) {
    const turns = [];
    messages.forEach((msg) => {
      if (msg.role === "user") turns.push({ user: msg.text || "", assistant: "" });
      else if (turns.length) turns[turns.length - 1].assistant = msg.text || "";
    });
    return turns.filter((t) => t.user && t.assistant).slice(-2);
  }

  async function sendMessage(textOverride, opts = {}) {
    if (state.streaming) return;
    const mode = opts.mode || state.mode;
    let raw = textOverride !== null && textOverride !== undefined ? textOverride : input.value;
    let text = (raw || "").trim();
    if (!text && mode !== "poetry") return;
    if (text.length > 2000) text = text.slice(0, 2000);
    const displayText = text || "یک شعر بگو";

    input.value = "";
    autosize();
    addMessage("user", displayText, { metaText: mode === "chat" ? "شما" : mode === "continue" ? "متن آغازین" : "درخواست شعر" });
    state.messages.push({ role: "user", text: displayText, mode });
    saveHistory();

    const payload = {
      message: text,
      session_id: state.sessionId,
      mode,
      deep: state.deep,
      candidates: 4,
      temperature: Number(state.temperature),
      max_new_tokens: state.deep ? 90 : 110,
      history: buildHistory(state.messages.slice(0, -1)),
    };

    const controller = new AbortController();
    state.abort = controller;
    setBusy(true);

    try {
      if (state.deep) {
        await runDeep(payload, controller);
      } else {
        await runStream(payload, controller);
      }
    } catch (err) {
      if (err.name === "AbortError") {
        const streaming = $(".bubble.streaming");
        if (streaming) {
          streaming.classList.remove("streaming");
          const partial = streaming.textContent.trim();
          if (partial) {
            const meta = streaming.parentElement.querySelector(".msg-meta");
            if (meta) { meta.hidden = false; meta.textContent = "متوقف شد"; }
            state.messages.push({ role: "assistant", text: partial });
            saveHistory();
          }
        } else {
          const thinking = $(".bubble .thinking");
          if (thinking) { thinking.closest(".bubble").textContent = "تولید متوقف شد."; }
        }
        return;
      }
      const stale = $(".bubble.streaming");
      if (stale) stale.closest(".msg")?.remove();
      const thinking = $(".bubble .thinking");
      if (thinking) thinking.closest(".msg")?.remove();
      const entry = addMessage("assistant", err.message || "خطایی رخ داد.", { error: true, metaText: "خطا" });
      state.messages.push({ role: "assistant", text: entry.bubble.textContent, error: true });
      saveHistory();
    } finally {
      state.abort = null;
      setBusy(false);
    }
  }

  async function runStream(payload, controller) {
    const entry = addMessage("assistant", "", { streaming: true, metaText: "در حال نوشتن…" });
    const started = performance.now();
    let answer = "";
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error((await safeDetail(res)) || "سرور پاسخ نداد.");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let done = false;
    while (!done) {
      const chunk = await reader.read();
      done = chunk.done;
      buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !done });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        let event;
        try { event = JSON.parse(line); } catch { continue; }
        if (event.type === "token") {
          answer += event.text || "";
          entry.bubble.textContent = answer;
          scrollToBottom();
        } else if (event.type === "done") {
          answer = event.answer || answer;
          entry.bubble.textContent = answer;
          entry.bubble.classList.remove("streaming");
          const s = event.stats || {};
          const seconds = (performance.now() - started) / 1000;
          setMeta(entry,
            `${duration(s.seconds ?? seconds)} · ${fa(s.tokens || 0)} توکن · اطمینان ${pct(s.confidence || 0)}`,
            { entry: { payload } });
          state.messages.push({ role: "assistant", text: answer, mode: payload.mode });
          saveHistory();
        } else if (event.type === "error") {
          throw new Error(event.error || "خطا در تولید");
        }
      }
    }
    entry.bubble.classList.remove("streaming");
    if (!answer) {
      entry.bubble.textContent = "پاسخی ساخته نشد؛ دوباره تلاش کن.";
      entry.bubble.classList.add("is-error");
    }
  }

  async function runDeep(payload, controller) {
    const entry = addMessage("assistant", "", { metaText: "اندیشهٔ ژرف در حال کار است…" });
    entry.bubble.innerHTML = `<div class="thinking"><span class="thinking-dots"><i></i><i></i><i></i></span><span class="thinking-text">پیام را می‌خوانم…</span></div>`;
    const thinkingText = $(".thinking-text", entry.bubble);
    const phases = [
      "پیام را می‌خوانم…",
      "چند مسیر موازی می‌سازم…",
      "مسیرها را امتیاز می‌دهم…",
      "بهترین مسیر را انتخاب می‌کنم…",
    ];
    let phase = 0;
    const started = performance.now();
    const timer = setInterval(() => {
      phase = (phase + 1) % phases.length;
      if (thinkingText) thinkingText.textContent = `${phases[phase]} (${Math.round((performance.now() - started) / 1000)} ثانیه)`;
    }, 1600);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error((await safeDetail(res)) || "سرور پاسخ نداد.");
      const data = await res.json();
      entry.bubble.textContent = data.answer || "…";
      const s = data.stats || {};
      const chosen = data.trace?.candidates?.find((c) => c.index === data.trace?.chosen);
      setMeta(entry,
        `${fa(data.trace?.candidates?.length || 0)} مسیر · ${duration(data.latency_s)} · امتیاز ${fa(chosen?.score ?? 0, 2)}`,
        { entry: { payload } });
      if (data.trace) {
        const traceEl = buildTrace(data.trace);
        entry.meta.before(traceEl);
        store.set("parsia.lastTrace", data.trace);
      }
      state.messages.push({ role: "assistant", text: data.answer, trace: data.trace });
      saveHistory();
    } finally {
      clearInterval(timer);
    }
  }

  $(".mode-tab")?.parentElement?.addEventListener("click", (event) => {
    const tab = event.target.closest(".mode-tab");
    if (!tab) return;
    state.mode = tab.dataset.mode;
    syncModeTabs();
    input.focus();
  });

  $("#composer").addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  input.addEventListener("input", autosize);

  stopBtn.addEventListener("click", () => {
    state.abort?.abort();
    toast("تولید متوقف شد");
  });

  $("#export-chat").addEventListener("click", () => {
    if (!state.messages.length) { toast("گفتگویی برای دانلود نیست"); return; }
    if (!window.URL?.createObjectURL) { toast("مرورگر از دانلود پشتیبانی نمی‌کند"); return; }
    try {
      const lines = state.messages.map((m) => `${m.role === "user" ? "شما" : "پارسیا"}: ${m.text}`);
      const blob = new Blob([`گفتگوی پارسیا\n\n${lines.join("\n\n")}\n`], { type: "text/plain;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "parsia-chat.txt";
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 2000);
      toast("گفتگو دانلود شد");
    } catch { toast("دانلود ممکن نشد"); }
  });

  $("#new-chat").addEventListener("click", async () => {
    const old = state.sessionId;
    state.sessionId = makeId();
    store.set("parsia.session", state.sessionId);
    state.messages = [];
    saveHistory();
    chatLog.innerHTML = welcomeTemplate;
    renderSuggestions();
    fetch(`/api/session/${encodeURIComponent(old)}`, { method: "DELETE" }).catch(() => {});
    scrollToBottom(true);
    input.focus();
  });

  const deepToggle = $("#deep-toggle");
  deepToggle.checked = !!state.deep;
  deepToggle.addEventListener("change", () => {
    state.deep = deepToggle.checked;
    store.set("parsia.deep", state.deep);
    toast(state.deep ? "اندیشهٔ ژرف روشن شد؛ پاسخ کمی دیرتر می‌آید." : "اندیشهٔ ژرف خاموش شد.");
  });

  const tempSlider = $("#temp");
  tempSlider.value = String(state.temperature);
  const tempOut = $("#temp-out");
  const renderTemp = () => { tempOut.textContent = fa(Number(tempSlider.value), 2); };
  renderTemp();
  tempSlider.addEventListener("input", () => {
    state.temperature = Number(tempSlider.value);
    renderTemp();
    store.set("parsia.temperature", state.temperature);
  });

  /* ---------------------------------------------------------- بازسازی تاریخچه */
  function restoreHistory() {
    if (!Array.isArray(state.messages) || !state.messages.length) return;
    state.messages.forEach((msg) => {
      if (msg.role === "user") {
        addMessage("user", msg.text, { metaText: "شما" });
      } else {
        const entry = addMessage("assistant", msg.text, {
          metaText: msg.error ? "خطا" : undefined,
          trace: msg.trace || null,
        });
        if (!msg.error) setMeta(entry, "از گفتگوی پیشین", { entry: null });
        entry.wrapper.dataset.restored = "1";
      }
    });
    scrollToBottom(true);
  }

  /* ---------------------------------------------------------- نمودارها */
  function fitCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, width: rect.width, height: rect.height };
  }

  function drawMainChart() {
    const canvas = $("#loss-chart");
    if (!canvas || state.view !== "training" || !state.metrics) return;
    const fit = fitCanvas(canvas);
    if (!fit) return;
    const { ctx, width: W, height: H } = fit;
    ctx.clearRect(0, 0, W, H);
    const train = state.metrics.train || [];
    const evals = state.metrics.eval || [];
    const run = state.metrics.run || {};
    const total = run.steps || Math.max(...train.map((r) => r.step || 0), ...evals.map((r) => r.step || 0), 100);
    const pad = { top: 20, right: 46, bottom: 34, left: 16 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;
    if (plotW <= 20 || plotH <= 20) return;

    const values = [...train.map((r) => r.loss), ...evals.map((r) => r.val_loss)].filter((v) => Number.isFinite(v));
    let lo = Math.min(...values, 2.5);
    let hi = Math.max(...values, 9.5);
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi - lo < 0.5) { lo = 2; hi = 10; }
    const padY = (hi - lo) * 0.12;
    lo -= padY; hi += padY;

    const X = (step) => pad.left + (clamp(step, 0, total) / total) * plotW;
    const Y = (loss) => pad.top + (1 - (loss - lo) / (hi - lo)) * plotH;

    // شبکه
    ctx.strokeStyle = "rgba(148,180,220,0.10)";
    ctx.lineWidth = 1;
    ctx.font = '10px "Vazirmatn", Tahoma, sans-serif';
    ctx.fillStyle = "rgba(148,180,220,0.65)";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    const yTicks = 5;
    for (let i = 0; i <= yTicks; i++) {
      const v = lo + ((hi - lo) * i) / yTicks;
      const y = Y(v);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(W - pad.right, y);
      ctx.stroke();
      ctx.fillText(fa(v, 1), W - pad.right + 8, y);
    }
    const xTicks = 6;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let i = 0; i <= xTicks; i++) {
      const step = (total * i) / xTicks;
      const x = X(step);
      ctx.beginPath();
      ctx.strokeStyle = "rgba(148,180,220,0.07)";
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, H - pad.bottom);
      ctx.stroke();
      ctx.fillStyle = "rgba(148,180,220,0.6)";
      ctx.fillText(fa(Math.round(step)), x, H - pad.bottom + 10);
    }

    // خط آموزش
    if (train.length > 1) {
      const gradient = ctx.createLinearGradient(0, pad.top, 0, H - pad.bottom);
      gradient.addColorStop(0, "rgba(125,211,252,0.22)");
      gradient.addColorStop(1, "rgba(125,211,252,0)");
      ctx.beginPath();
      train.forEach((point, i) => {
        const x = X(point.step), y = Y(point.loss);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "rgba(125,211,252,0.85)";
      ctx.lineWidth = 1.8;
      ctx.lineJoin = "round";
      ctx.stroke();
      ctx.lineTo(X(train[train.length - 1].step), H - pad.bottom);
      ctx.lineTo(X(train[0].step), H - pad.bottom);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();
    }

    // خط اعتبارسنجی
    if (evals.length) {
      ctx.beginPath();
      evals.forEach((point, i) => {
        const x = X(point.step), y = Y(point.val_loss);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "#f5b74a";
      ctx.lineWidth = 2;
      ctx.stroke();
      evals.forEach((point) => {
        const x = X(point.step), y = Y(point.val_loss);
        ctx.beginPath();
        ctx.arc(x, y, 3.4, 0, Math.PI * 2);
        ctx.fillStyle = "#0b1422";
        ctx.fill();
        ctx.strokeStyle = "#f5b74a";
        ctx.lineWidth = 1.6;
        ctx.stroke();
      });
      const last = evals[evals.length - 1];
      ctx.beginPath();
      ctx.arc(X(last.step), Y(last.val_loss), 8, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(245,183,74,0.14)";
      ctx.fill();
      ctx.fillStyle = "rgba(245,183,74,0.9)";
      ctx.font = '10px "Vazirmatn", Tahoma, sans-serif';
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      ctx.fillText(fa(last.val_loss, 2), X(last.step) - 10, Y(last.val_loss) - 10);
    }

    canvas._map = { X, Y, pad, total, W, H, train, evals };
    const note = $("#chart-note");
    if (note) {
      const last = train[train.length - 1];
      note.textContent = last ? `آخرین خطای آموزش: ${fa(last.loss, 3)} · گام ${fa(last.step)}` : "در انتظار داده…";
    }
  }

  function drawMiniChart() {
    const canvas = $("#mini-chart");
    if (!canvas) return;
    const fit = fitCanvas(canvas);
    if (!fit) return;
    const { ctx, width: W, height: H } = fit;
    ctx.clearRect(0, 0, W, H);
    const evals = state.metrics?.eval || [];
    if (evals.length < 2) {
      ctx.strokeStyle = "rgba(148,180,220,0.18)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, H * 0.6);
      ctx.lineTo(W, H * 0.6);
      ctx.stroke();
      return;
    }
    const losses = evals.map((e) => e.val_loss);
    const lo = Math.min(...losses), hi = Math.max(...losses);
    const X = (i) => 2 + (i / (evals.length - 1)) * (W - 4);
    const Y = (v) => 4 + (1 - (v - lo) / Math.max(1e-6, hi - lo)) * (H - 8);
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, "rgba(94,234,212,0.28)");
    grad.addColorStop(1, "rgba(94,234,212,0)");
    ctx.beginPath();
    evals.forEach((e, i) => { const x = X(i), y = Y(e.val_loss); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.strokeStyle = "#5eead4";
    ctx.lineWidth = 1.6;
    ctx.stroke();
    ctx.lineTo(X(evals.length - 1), H);
    ctx.lineTo(X(0), H);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
    const last = evals[evals.length - 1];
    ctx.beginPath();
    ctx.arc(X(evals.length - 1), Y(last.val_loss), 2.6, 0, Math.PI * 2);
    ctx.fillStyle = "#f5b74a";
    ctx.fill();
  }

  const chartWrap = $(".chart-wrap");
  if (chartWrap) {
    chartWrap.addEventListener("mousemove", (event) => {
      const canvas = $("#loss-chart");
      const map = canvas?._map;
      const tip = $("#chart-tip");
      if (!map || !tip) return;
      const rect = canvas.getBoundingClientRect();
      const mx = event.clientX - rect.left;
      const my = event.clientY - rect.top;
      let best = null;
      let bestDist = 22;
      (map.train || []).forEach((p) => {
        const d = Math.abs(map.X(p.step) - mx);
        if (d < bestDist) { bestDist = d; best = { ...p, kind: "train" }; }
      });
      (map.evals || []).forEach((p) => {
        const d = Math.abs(map.X(p.step) - mx);
        if (d < bestDist) { bestDist = d; best = { ...p, kind: "eval" }; }
      });
      if (!best) { tip.hidden = true; return; }
      tip.hidden = false;
      tip.style.left = `${clamp(map.X(best.step), 60, map.W - 60)}px`;
      tip.style.top = `${clamp(map.Y(best.kind === "eval" ? best.val_loss : best.loss), 30, map.H - 20)}px`;
      tip.innerHTML = best.kind === "eval"
        ? `گام ${fa(best.step)}<br>اعتبارسنجی: <b>${fa(best.val_loss, 3)}</b> · ppl ${fa(best.ppl, 1)}`
        : `گام ${fa(best.step)}<br>آموزش: <b>${fa(best.loss, 3)}</b> · lr ${lrFmt(best.lr)}`;
    });
    chartWrap.addEventListener("mouseleave", () => { const tip = $("#chart-tip"); if (tip) tip.hidden = true; });
  }

  new ResizeObserver(debounce(() => { drawMainChart(); drawMiniChart(); }, 120)).observe(chatLog.parentElement || document.body);
  window.addEventListener("resize", debounce(() => { drawMainChart(); drawMiniChart(); }, 160));

  /* ---------------------------------------------------------- متریک‌ها */
  function latestStats() {
    const m = state.metrics || {};
    const run = m.run || {};
    const lastTrain = m.latest_train || (m.train || [])[m.train.length - 1] || {};
    const lastEval = m.latest_eval || (m.eval || [])[m.eval.length - 1] || {};
    const totalSteps = run.steps || 1800;
    const tokensPerStep = run.tokens_per_step || 6144;
    const targetTokens = run.target_tokens || totalSteps * tokensPerStep;
    const tokens = lastTrain.tokens || lastEval.tokens || 0;
    const step = lastTrain.step || lastEval.step || 0;
    const tps = lastTrain.tok_s || null;
    const elapsed = lastTrain.elapsed_s || lastEval.elapsed_s || 0;
    let eta = null;
    if (m.active) {
      if (tps) eta = (targetTokens - tokens) / tps;
      else if (step && elapsed) eta = ((totalSteps - step) * elapsed) / step;
    }
    return { m, run, lastTrain, lastEval, totalSteps, targetTokens, tokens, step, tps, elapsed, eta };
  }

  function applyMetrics() {
    const s = latestStats();
    const { lastEval, lastTrain, run } = s;
    if (lastEval?.val_loss !== undefined) {
      $("#stat-loss").textContent = fa(lastEval.val_loss, 3);
      $$("[data-model-loss]").forEach((el) => (el.textContent = fa(lastEval.val_loss, 3)));
      const ppl = lastEval.ppl ?? Math.exp(lastEval.val_loss);
      $("#stat-ppl").textContent = fa(ppl, 1);
      const frac = clamp((9.2 - lastEval.val_loss) / (9.2 - 2.8), 0.02, 0.99);
      const ring = $("#ring-value");
      if (ring) ring.style.strokeDashoffset = String(314.16 * (1 - frac));
      $("#stat-bpc").textContent = fa(lastEval.bits_per_char, 2);
    }
    if (lastTrain) {
      $("#stat-step").textContent = `گام ${fa(lastTrain.step)}`;
      $("#stat-tokens").textContent = compact(lastTrain.tokens);
      $("#stat-tps").textContent = fa(lastTrain.tok_s || 0);
    }
    const trainTokens = run.dataset?.train_tokens || 3944980;
    const epochs = s.tokens ? s.tokens / trainTokens : 0;
    $("#m-step").textContent = fa(s.step);
    $("#m-step-sub").textContent = `از ${fa(s.totalSteps)} گام`;
    $("#m-tokens").textContent = compact(s.tokens);
    $("#m-epoch").textContent = epochs ? `${fa(epochs, 1)} دوره از پیکره` : "—";
    $("#m-tps").textContent = s.tps ? fa(s.tps) : "—";
    $("#m-eta").textContent = s.m.active ? (s.eta ? duration(s.eta) : "—") : "پایان";
    $("#m-elapsed").textContent = s.elapsed ? `${duration(s.elapsed)} گذشته` : "—";
    const progress = clamp((s.step / s.totalSteps) * 100, 0, 100);
    const bar = $("#train-progress-bar");
    if (bar) bar.style.width = `${progress}%`;
    $("#train-step-label").textContent = `${fa(s.step)} / ${fa(s.totalSteps)}`;
    $("#train-eta").textContent = s.m.active ? (s.eta ? `${duration(s.eta)} مانده` : "در حال محاسبه") : "پایان آموزش";
    const badge = $("#train-badge");
    const badge2 = $("#train-badge-2");
    [badge, badge2].forEach((el) => el?.classList.toggle("is-off", !s.m.active));
    if (badge) badge.innerHTML = `<span></span>${s.m.active ? "زنده" : "پایان"}`;
    if (badge2) badge2.innerHTML = `<span></span>${s.m.active ? "در حال آموزش" : "آموزش پایان یافته"}`;
    const miniText = $("#train-mini-text");
    if (miniText) {
      miniText.textContent = s.m.active
        ? `گام ${fa(s.step)} از ${fa(s.totalSteps)}؛ خطای آموزش ${lastTrain?.loss !== undefined ? fa(lastTrain.loss, 3) : "—"}.`
        : `آخرین وضعیت: گام ${fa(s.step)}؛ خطای اعتبارسنجی ${fa(lastEval?.val_loss, 3)}.`;
    }
    const heroLive = $("#hero-live-text");
    if (heroLive) {
      heroLive.textContent = s.m.active
        ? `گام ${fa(s.step)} از ${fa(s.totalSteps)} · توکن ${compact(s.tokens)} · خطا ${fa(lastEval?.val_loss, 3)}`
        : `آخرین آموزش در گام ${fa(s.step)} تمام شد · خطای اعتبارسنجی ${fa(lastEval?.val_loss, 3)}`;
    }
    const updated = $("#train-updated");
    if (updated) updated.textContent = state.metrics?.metrics_mtime ? `آخرین به‌روزرسانی: ${timeAgo(state.metrics.metrics_mtime)}` : "—";
    const logCount = $("#log-count");
    if (logCount) logCount.textContent = fa((state.metrics?.train || []).length);

    // جدول گزارش‌ها
    const tbody = $("#log-body");
    if (tbody) {
      const rows = (state.metrics?.train || []).slice(-12).reverse();
      tbody.innerHTML = "";
      if (!rows.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 5; td.className = "muted"; td.textContent = "در انتظار داده…";
        tr.append(td); tbody.append(tr);
      } else {
        rows.forEach((row) => {
          const tr = document.createElement("tr");
          const cells = [fa(row.step), fa(row.loss, 3), lrFmt(row.lr), fa(row.grad_norm, 2), fa(row.tok_s)];
          cells.forEach((value, idx) => {
            const td = document.createElement("td");
            td.textContent = value;
            if (idx === 1) td.className = "loss-cell";
            tr.append(td);
          });
          tbody.append(tr);
        });
      }
    }
    const config = $("#train-config");
    if (config && run.layers) {
      config.textContent = `مدل: ${fa(run.layers)} لایه · ${fa(run.heads)} سر · ${fa(run.embed)} بُعد · زمینهٔ ${fa(run.block_size)} · batch ${fa(run.batch_size)} · ${run.hardware || "CPU"}`;
    }
    drawMainChart();
    drawMiniChart();
  }

  async function refreshMetrics() {
    try {
      state.metrics = await getJSON("/api/metrics");
      applyMetrics();
    } catch { /* سرور در دسترس نیست */ }
  }

  function applyCorpusStats() {
    if (!state.model?.corpus) return;
    const c = state.model.corpus;
    const news = c.news_chars || 0;
    const poetry = c.poetry_chars || 0;
    const chat = c.chat_chars || 0;
    const total = news + poetry + chat;
    if (!total) return;
    $$(".mix").forEach((el) => {
      if (el.classList.contains("news")) el.style.width = `${(news / total) * 100}%`;
      if (el.classList.contains("poetry")) el.style.width = `${(poetry / total) * 100}%`;
      if (el.classList.contains("chat")) el.style.width = `${Math.max(1, (chat / total) * 100)}%`;
    });
    if ($("#mix-news")) $("#mix-news").textContent = `${fa(news / 1e6, 1)} میلیون نویسه`;
    if ($("#mix-poetry")) $("#mix-poetry").textContent = `${fa(poetry / 1e6, 1)} میلیون نویسه`;
  }

  async function loadShowcase() {
    try {
      const data = await getJSON("/api/showcase");
      const examples = (data.examples || []).slice(0, 3);
      if (!examples.length) return;
      const holder = $("#showcase-list");
      const section = $("#showcase");
      if (!holder || !section) return;
      holder.innerHTML = "";
      const modeLabel = { chat: "گفتگو", continue: "ادامهٔ متن", poetry: "شعر" };
      examples.forEach((example) => {
        const item = document.createElement("div");
        item.className = "showcase-item";
        const prompt = document.createElement("span");
        prompt.className = "prompt";
        prompt.textContent = `ورودی: ${example.prompt || "—"}`;
        const text = document.createElement("p");
        text.textContent = example.text || "—";
        const foot = document.createElement("div");
        foot.className = "foot";
        foot.textContent = `${modeLabel[example.mode] || example.mode} · ${fa(example.tokens || 0)} توکن · ${fa(example.tok_s || 0)} توکن/ث`;
        item.append(prompt, text, foot);
        holder.append(item);
      });
      section.hidden = false;
    } catch { /* بدون نمونه */ }
  }

  async function loadStatic() {
    try {
      const [model, samples] = await Promise.all([getJSON("/api/model"), getJSON("/api/samples")]);
      state.model = model;
      state.samples = samples.samples || [];
      renderSpecs();
      renderSuggestions();
      applyCorpusStats();
      loadShowcase();
      const params = model.params;
      $$("[data-spec='params']").forEach((el) => (el.textContent = fa(params)));
      $$("[data-model-params]").forEach((el) => (el.textContent = compact(params)));
      $$("[data-about-params]").forEach((el) => (el.textContent = compact(params)));
      const vocabSize = model.config?.vocab_size || model.tokenizer?.vocab_size;
      $$("[data-model-vocab]").forEach((el) => (el.textContent = fa(vocabSize)));
      const step = model.meta?.step;
      if (step) $("#stat-step").textContent = `گام ${fa(step)}`;
      const loss = model.meta?.val_loss;
      if (loss) {
        $("#stat-loss").textContent = fa(loss, 3);
        $$("[data-model-loss]").forEach((el) => (el.textContent = fa(loss, 3)));
      }
    } catch { /* بعداً تلاش می‌کنیم */ }
  }

  /* ---------------------------------------------------------- راه‌اندازی */
  async function boot() {
    setView(location.hash.replace("#", "") || "chat", false);
    syncModeTabs();
    renderSuggestions();
    restoreHistory();
    await Promise.all([refreshHealth(), refreshMetrics(), loadStatic()]);
    applyMetrics();
    drawMainChart();
    drawMiniChart();

    setInterval(async () => {
      if (document.hidden) return;
      await refreshHealth();
      await refreshMetrics();
    }, 7000);

    if (document.fonts?.ready) {
      document.fonts.ready.then(() => { drawMainChart(); drawMiniChart(); }).catch(() => {});
    }
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) { refreshHealth(); refreshMetrics(); }
    });

    if (!state.messages.length) {
      setTimeout(() => input.focus(), 500);
    }
  }

  boot();
})();
