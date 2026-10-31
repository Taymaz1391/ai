/* رایان — استودیو: ساخت تصویر، پوستر و کارت به‌صورت محلی (SVG، بدون سرویس بیرونی) */
(function () {
  "use strict";
  const R = window.RAYAN || {};
  const { $, $$, toast, nf } = R;

  // ------------------------------------------------------------ پالت‌ها
  const PALETTES = [
    { id: "ocean", name: "اقیانوس", from: "#3ad2ff", to: "#1a63f0", ink: "#ffffff", soft: "#e8f4ff" },
    { id: "night", name: "شب", from: "#5b6cff", to: "#0b1b3f", ink: "#ffffff", soft: "#e9ecff" },
    { id: "mint", name: "نعنایی", from: "#5eead4", to: "#0f9d8a", ink: "#04231e", soft: "#e6fbf6" },
    { id: "sunset", name: "غروب", from: "#ffb26b", to: "#e0447c", ink: "#ffffff", soft: "#fff0ea" },
    { id: "violet", name: "بنفش", from: "#b18cff", to: "#5b2ee0", ink: "#ffffff", soft: "#f1ecff" },
    { id: "sand", name: "شنی", from: "#f5e3c3", to: "#c9a066", ink: "#2b1e0c", soft: "#fdf6ea" },
    { id: "graphite", name: "گرافیتی", from: "#4b5563", to: "#0f172a", ink: "#ffffff", soft: "#eef1f5" },
    { id: "rose", name: "گلی", from: "#ffd1dc", to: "#e35d7a", ink: "#3a0d18", soft: "#fff1f4" },
  ];

  const THEMES = {
    poster: { w: 1080, h: 1350, label: "پوستر" },
    card: { w: 1200, h: 630, label: "کارت شبکه" },
    banner: { w: 1440, h: 480, label: "بنر" },
    square: { w: 1080, h: 1080, label: "مربع" },
    story: { w: 1080, h: 1920, label: "استوری" },
  };

  const KEYWORDS = [
    { words: ["اقیانوس", "دریا", "آب", "موج", "blue", "ocean"], palette: "ocean", motif: "waves" },
    { words: ["شب", "ستاره", "فضا", "کهکشان", "night", "space"], palette: "night", motif: "stars" },
    { words: ["طبیعت", "برگ", "جنگل", "سبز", "گیاه"], palette: "mint", motif: "blob" },
    { words: ["غروب", "خورشید", "آفتاب", "گرم"], palette: "sunset", motif: "sun" },
    { words: ["بنفش", "رویا", "خیال"], palette: "violet", motif: "blob" },
    { words: ["کویر", "شنی", "قدیمی", "کاغذ"], palette: "sand", motif: "grain" },
    { words: ["مینیمال", "ساده", "خاکستری", "تیره"], palette: "graphite", motif: "grid" },
    { words: ["گل", "عشق", "قلب", "رمانتیک"], palette: "rose", motif: "blob" },
    { words: ["هوش مصنوعی", "فناوری", "تکنولوژی", "مدل", "ai"], palette: "ocean", motif: "circuit" },
    { words: ["شعر", "ادبیات", "کتاب"], palette: "sand", motif: "lines" },
  ];

  const MOTIFS = ["waves", "stars", "circuit", "blob", "grid", "sun", "lines", "grain"];

  function hash(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function rngFrom(seed) {
    let s = seed || 1;
    return () => {
      s ^= s << 13; s ^= s >>> 17; s ^= s << 5;
      return ((s >>> 0) % 100000) / 100000;
    };
  }

  function choosePalette(prompt) {
    const lower = prompt.toLowerCase();
    for (const rule of KEYWORDS) {
      if (rule.words.some((w) => lower.includes(w))) {
        return PALETTES.find((p) => p.id === rule.palette) || PALETTES[0];
      }
    }
    return PALETTES[hash(prompt) % PALETTES.length];
  }

  function chooseMotif(prompt) {
    const lower = prompt.toLowerCase();
    for (const rule of KEYWORDS) {
      if (rule.words.some((w) => lower.includes(w))) return rule.motif;
    }
    return MOTIFS[hash(prompt + "m") % MOTIFS.length];
  }

  function esc(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function wrap(text, maxChars) {
    const words = String(text).split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    words.forEach((word) => {
      if ((line + " " + word).trim().length <= maxChars) {
        line = (line + " " + word).trim();
      } else {
        if (line) lines.push(line);
        line = word;
      }
    });
    if (line) lines.push(line);
    return lines.slice(0, 5);
  }

  function motifSvg(motif, w, h, color, rand) {
    const out = [];
    if (motif === "waves") {
      for (let i = 0; i < 5; i += 1) {
        const y = h * (0.55 + i * 0.09);
        const amp = 26 + rand() * 42;
        out.push(`<path d="M0 ${y} C ${w * 0.25} ${y - amp}, ${w * 0.5} ${y + amp}, ${w} ${y - amp * 0.4}" fill="none" stroke="${color}" stroke-opacity="${0.34 - i * 0.05}" stroke-width="${3 + i}"/>`);
      }
    } else if (motif === "stars") {
      for (let i = 0; i < 90; i += 1) {
        const x = rand() * w;
        const y = rand() * h * 0.7;
        const r = rand() * 2.6 + 0.4;
        out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(2)}" fill="${color}" opacity="${(0.25 + rand() * 0.6).toFixed(2)}"/>`);
      }
      out.push(`<circle cx="${w * 0.82}" cy="${h * 0.16}" r="${h * 0.09}" fill="${color}" opacity="0.16"/>`);
    } else if (motif === "circuit") {
      for (let i = 0; i < 14; i += 1) {
        const x1 = rand() * w;
        const y1 = rand() * h;
        const len = 60 + rand() * 220;
        const vertical = rand() > 0.5;
        out.push(`<path d="M${x1} ${y1} ${vertical ? "v" : "h"}${len}" stroke="${color}" stroke-opacity="0.22" stroke-width="2" fill="none"/>`);
        out.push(`<circle cx="${x1}" cy="${y1}" r="4" fill="${color}" opacity="0.35"/>`);
      }
    } else if (motif === "blob") {
      for (let i = 0; i < 3; i += 1) {
        const cx = w * (0.2 + rand() * 0.6);
        const cy = h * (0.2 + rand() * 0.5);
        const r = Math.min(w, h) * (0.22 + rand() * 0.22);
        out.push(`<circle cx="${cx.toFixed(0)}" cy="${cy.toFixed(0)}" r="${r.toFixed(0)}" fill="${color}" opacity="0.14"/>`);
      }
    } else if (motif === "grid") {
      for (let x = 0; x < w; x += 56) out.push(`<path d="M${x} 0V${h}" stroke="${color}" stroke-opacity="0.10" stroke-width="1"/>`);
      for (let y = 0; y < h; y += 56) out.push(`<path d="M0 ${y}H${w}" stroke="${color}" stroke-opacity="0.10" stroke-width="1"/>`);
    } else if (motif === "sun") {
      out.push(`<circle cx="${w * 0.5}" cy="${h * 0.42}" r="${Math.min(w, h) * 0.26}" fill="${color}" opacity="0.22"/>`);
      out.push(`<circle cx="${w * 0.5}" cy="${h * 0.42}" r="${Math.min(w, h) * 0.34}" fill="none" stroke="${color}" stroke-opacity="0.18" stroke-width="2"/>`);
    } else if (motif === "lines") {
      for (let i = 0; i < 12; i += 1) {
        const y = h * 0.62 + i * 12;
        out.push(`<path d="M${w * 0.08} ${y} H${w * (0.5 + rand() * 0.42)}" stroke="${color}" stroke-opacity="0.16" stroke-width="2"/>`);
      }
    } else {
      for (let i = 0; i < 700; i += 1) {
        out.push(`<circle cx="${(rand() * w).toFixed(0)}" cy="${(rand() * h).toFixed(0)}" r="1" fill="${color}" opacity="${(rand() * 0.2).toFixed(2)}"/>`);
      }
    }
    return out.join("");
  }

  // لوگوتایپ برند به‌صورت data URI تا داخل SVG بماند و بوم «آلوده» نشود
  let BRAND_MARK = "";
  function preloadBrandMark() {
    if (BRAND_MARK || !window.fetch) return;
    fetch("/static/assets/brand/mark-white.png")
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (!blob) return;
        const reader = new FileReader();
        reader.onload = () => { BRAND_MARK = String(reader.result || ""); };
        reader.readAsDataURL(blob);
      })
      .catch(() => { /* بدون لوگو هم پوستر ساخته می‌شود */ });
  }

  /** ساخت SVG پوستر/کارت از متن — قطعی، آفلاین و بدون هیچ سرویس بیرونی */
  function makeArt(prompt, options = {}) {
    const kind = options.kind && THEMES[options.kind] ? options.kind : "poster";
    const size = THEMES[kind];
    const palette = options.palette ? PALETTES.find((p) => p.id === options.palette) || choosePalette(prompt) : choosePalette(prompt);
    const motif = options.motif || chooseMotif(prompt);
    const seed = hash(prompt + kind + palette.id);
    const rand = rngFrom(seed);
    const title = (options.title || prompt || "پوستر تازه").trim().slice(0, 90);
    const tagline = (options.tagline || "هوش مصنوعی، به زبان فارسی").trim().slice(0, 120);
    const w = size.w;
    const h = size.h;
    const isWide = w > h * 1.4;
    const pad = Math.round(Math.min(w, h) * 0.085);
    const titleSize = isWide ? Math.round(h * 0.13) : Math.round(w * 0.095);
    const lines = wrap(title, isWide ? 26 : 18);
    const lineH = titleSize * 1.32;
    const blockTop = isWide ? h * 0.30 : h * 0.36;

    const textParts = lines.map((line, i) => (
      `<text x="${w - pad}" y="${(blockTop + i * lineH).toFixed(0)}" text-anchor="end" ` +
      `font-family="Vazirmatn, Tahoma" font-size="${titleSize}" font-weight="800" fill="${palette.ink}">${esc(line)}</text>`
    )).join("");

    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(title)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${palette.from}"/>
      <stop offset="1" stop-color="${palette.to}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.1" r="0.9">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.32"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="${w}" height="${h}" fill="url(#bg)"/>
  <rect width="${w}" height="${h}" fill="url(#glow)"/>
  <g>${motifSvg(motif, w, h, palette.ink, rand)}</g>
  <g>${textParts}</g>
  <text x="${w - pad}" y="${(blockTop + lines.length * lineH + titleSize * 0.55).toFixed(0)}" text-anchor="end"
        font-family="Vazirmatn, Tahoma" font-size="${Math.round(titleSize * 0.34)}" fill="${palette.ink}" opacity="0.82">${esc(tagline)}</text>
  <g opacity="0.95">
    <defs>
      <radialGradient id="orbGrad" cx="0.36" cy="0.28" r="0.78">
        <stop offset="0" stop-color="#7df0ff"/>
        <stop offset="0.45" stop-color="#2e8bff"/>
        <stop offset="1" stop-color="#0b47e8"/>
      </radialGradient>
    </defs>
    <circle cx="${pad + titleSize * 0.52}" cy="${h - pad - titleSize * 0.52}" r="${titleSize * 0.44}" fill="url(#orbGrad)"/>
    <circle cx="${pad + titleSize * 0.42}" cy="${h - pad - titleSize * 0.55}" r="${titleSize * 0.075}" fill="#ffffff"/>
    <circle cx="${pad + titleSize * 0.62}" cy="${h - pad - titleSize * 0.55}" r="${titleSize * 0.075}" fill="#ffffff"/>
    ${BRAND_MARK ? `<image href="${BRAND_MARK}" x="${pad + titleSize * 1.02}" y="${h - pad - titleSize * 0.62}"
           width="${titleSize * 2.4}" height="${titleSize * 2.4 * 64 / 122}" opacity="0.92"
           preserveAspectRatio="xMinYMid meet"/>` : ""}
  </g>
</svg>`;
    return { svg, palette, motif, kind, width: w, height: h, title };
  }

  function svgUrl(svg) {
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  }

  function download(name, content, type) {
    const blob = content instanceof Blob ? content : new Blob([content], { type: type || "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  async function svgToPng(svg, width, height, scale = 2) {
    const img = new Image();
    img.crossOrigin = "anonymous";
    const url = svgUrl(svg);
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  }

  /** ساخت فایل از پاسخ مدل: تشخیص بلوک کد و نوع فایل */
  function extractArtifacts(text) {
    const out = [];
    const fence = /```([a-zA-Z0-9+#-]*)\n([\s\S]*?)```/g;
    let match;
    while ((match = fence.exec(text)) !== null) {
      const lang = (match[1] || "").toLowerCase();
      const code = match[2].trimEnd();
      if (!code) continue;
      out.push({ lang, code, ext: extFor(lang, code), kind: extFor(lang, code) === "html" ? "html" : "code" });
    }
    // SVG inline بدون بلوک کد
    if (!out.length) {
      const svg = /<svg[\s\S]*?<\/svg>/i.exec(text);
      if (svg) out.push({ lang: "svg", code: svg[0], ext: "svg", kind: "svg" });
    }
    return out;
  }

  const EXT = {
    python: "py", py: "py", javascript: "js", js: "js", typescript: "ts", ts: "ts",
    html: "html", css: "css", json: "json", bash: "sh", sh: "sh", shell: "sh",
    sql: "sql", markdown: "md", md: "md", svg: "svg", yaml: "yml", yml: "yml",
    csv: "csv", java: "java", c: "c", cpp: "cpp", go: "go", rust: "rs", php: "php",
  };

  function extFor(lang, code) {
    if (EXT[lang]) return EXT[lang];
    if (/^\s*<svg/i.test(code)) return "svg";
    if (/^\s*<!doctype html|<html/i.test(code)) return "html";
    return "txt";
  }

  // -------------------------------------------------------- پنل آرتیفکت
  let panel;
  let current = null;

  function ensurePanel() {
    if (panel) return panel;
    panel = document.createElement("aside");
    panel.className = "artifact-panel";
    panel.id = "artifact-panel";
    panel.hidden = true;
    panel.innerHTML =
      '<header class="artifact-head">' +
      '<div class="artifact-tabs" role="tablist"></div>' +
      '<div class="artifact-actions">' +
      '<button type="button" class="icon-btn" data-art="download" title="دانلود">' + (R.icon ? R.icon("download", 18) : "⬇") + "</button>" +
      '<button type="button" class="icon-btn" data-art="copy" title="کپی">' + (R.icon ? R.icon("copy", 18) : "⧉") + "</button>" +
      '<button type="button" class="icon-btn" data-art="close" title="بستن">' + (R.icon ? R.icon("close", 18) : "✕") + "</button>" +
      "</div></header>" +
      '<div class="artifact-body"><div class="artifact-preview" id="artifact-preview"></div>' +
      '<pre class="artifact-code"><code id="artifact-code"></code></pre></div>' +
      '<footer class="artifact-foot" id="artifact-foot"></footer>';
    document.body.append(panel);
    panel.querySelector("[data-art='close']").addEventListener("click", closePanel);
    panel.querySelector("[data-art='download']").addEventListener("click", () => {
      if (!current) return;
      if (current.kind === "image") {
        svgToPng(current.svg, current.width, current.height, 2).then((blob) => {
          if (blob) download(`${current.name}.png`, blob);
          else toast("مرورگر از خروجی PNG پشتیبانی نکرد؛ SVG را دانلود کنید.", "error");
        });
      } else {
        download(`${current.name}.${current.ext}`, current.code, "text/plain;charset=utf-8");
      }
    });
    panel.querySelector("[data-art='copy']").addEventListener("click", () => {
      if (!current) return;
      const text = current.kind === "image" ? current.svg : current.code;
      (R.copyText ? R.copyText(text) : Promise.resolve()).then(() => toast("کپی شد.", "ok"));
    });
    return panel;
  }

  function closePanel() {
    if (!panel) return;
    panel.classList.remove("is-open");
    setTimeout(() => { panel.hidden = true; }, 240);
  }

  function openArtifact(art) {
    ensurePanel();
    current = art;
    panel.hidden = false;
    requestAnimationFrame(() => panel.classList.add("is-open"));
    const preview = panel.querySelector("#artifact-preview");
    const codeEl = panel.querySelector("#artifact-code");
    const foot = panel.querySelector("#artifact-foot");
    preview.innerHTML = "";
    if (art.kind === "image") {
      preview.innerHTML = `<img src="${svgUrl(art.svg)}" alt="${esc(art.title || "تصویر ساخته‌شده")}" width="${art.width}" height="${art.height}">`;
      codeEl.parentElement.hidden = true;
      foot.textContent = `${nf(art.width)} × ${nf(art.height)} · ${art.palette ? art.palette.name : ""} · SVG محلی`;
      return;
    }
    codeEl.parentElement.hidden = false;
    codeEl.textContent = art.code;
    if (art.ext === "html" || art.ext === "svg") {
      preview.innerHTML = art.ext === "svg"
        ? `<img src="${svgUrl(art.code)}" alt="پیش‌نمایش SVG">`
        : `<iframe sandbox="allow-scripts" srcdoc="${esc(art.code)}" title="پیش‌نمایش"></iframe>`;
    } else {
      preview.innerHTML = "";
    }
    foot.textContent = `${art.lang || "متن"} · ${art.ext.toUpperCase()} · ${nf(art.code.length)} نویسه`;
  }

  // --------------------------------------------------- ابزار دکمه‌های چت
  function attachToChat() {
    const host = document.querySelector(".composer-left");
    if (!host || host.querySelector("#studio-btn")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tool-btn";
    btn.id = "studio-btn";
    btn.title = "ساخت تصویر، پوستر و کارت به‌صورت محلی";
    btn.innerHTML = (R.icon ? R.icon("image", 15) : "") + "<span>تصویر بساز</span>";
    btn.addEventListener("click", () => openStudio());
    host.prepend(btn);
  }

  function openStudio(prefill) {
    let modal = document.getElementById("studio-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.className = "modal";
      modal.id = "studio-modal";
      modal.hidden = true;
      modal.innerHTML = `
        <div class="modal-card studio-card" role="dialog" aria-modal="true" aria-labelledby="studio-title">
          <header class="modal-head">
            <h3 id="studio-title">استودیو تصویر</h3>
            <button type="button" class="icon-btn" data-studio="close">${R.icon ? R.icon("close", 18) : "✕"}</button>
          </header>
          <div class="studio-grid">
            <div class="studio-form">
              <label class="field"><span>چه تصویری بسازم؟</span>
                <input id="studio-prompt" type="text" maxlength="120" placeholder="مثلاً: پوستر «شب‌های تهران» با حال‌وهوای غروب">
              </label>
              <div class="field-row">
                <label class="field"><span>قالب</span>
                  <select id="studio-kind">${Object.entries(THEMES).map(([k, v]) => `<option value="${k}">${v.label} — ${v.w}×${v.h}</option>`).join("")}</select>
                </label>
                <label class="field"><span>پالت</span>
                  <select id="studio-palette"><option value="">خودکار</option>${PALETTES.map((p) => `<option value="${p.id}">${p.name}</option>`).join("")}</select>
                </label>
              </div>
              <label class="field"><span>زیرنویس</span>
                <input id="studio-tagline" type="text" maxlength="100" value="هوش مصنوعی، به زبان فارسی">
              </label>
              <div class="studio-actions">
                <button type="button" class="btn btn-primary" data-studio="make">بساز</button>
                <button type="button" class="btn" data-studio="png">دانلود PNG</button>
                <button type="button" class="btn" data-studio="svg">دانلود SVG</button>
              </div>
              <p class="hint">همه‌چیز محلی و آفلاین ساخته می‌شود؛ هیچ درخواستی به سرویس تصویر بیرونی نمی‌رود.</p>
            </div>
            <div class="studio-stage" id="studio-stage"></div>
          </div>
        </div>`;
      document.body.append(modal);
      modal.addEventListener("click", (event) => {
        if (event.target === modal) closeStudio();
        const action = event.target.closest("[data-studio]")?.dataset.studio;
        if (action === "close") closeStudio();
        if (action === "make") renderStudio();
        if (action === "png") {
          if (!modal._art) return;
          svgToPng(modal._art.svg, modal._art.width, modal._art.height, 2)
            .then((blob) => blob && download(`rayan-${Date.now()}.png`, blob));
        }
        if (action === "svg") {
          if (!modal._art) return;
          download(`rayan-${Date.now()}.svg`, modal._art.svg, "image/svg+xml;charset=utf-8");
        }
      });
      modal.querySelector("#studio-prompt").addEventListener("input", () => renderStudio());
      modal.querySelector("#studio-kind").addEventListener("change", () => renderStudio());
      modal.querySelector("#studio-palette").addEventListener("change", () => renderStudio());
      modal.querySelector("#studio-tagline").addEventListener("input", () => renderStudio());
    }
    modal.hidden = false;
    const input = modal.querySelector("#studio-prompt");
    if (prefill) input.value = prefill;
    if (!input.value) input.value = "پوستر — هوش مصنوعی فارسی";
    renderStudio();
    input.focus();
  }

  function closeStudio() {
    const modal = document.getElementById("studio-modal");
    if (modal) modal.hidden = true;
  }

  function renderStudio() {
    const modal = document.getElementById("studio-modal");
    if (!modal) return;
    const prompt = modal.querySelector("#studio-prompt").value.trim() || "پوستر — هوش مصنوعی فارسی";
    const kind = modal.querySelector("#studio-kind").value;
    const palette = modal.querySelector("#studio-palette").value;
    const tagline = modal.querySelector("#studio-tagline").value;
    const art = makeArt(prompt, { kind, palette: palette || undefined, tagline });
    modal._art = art;
    const stage = modal.querySelector("#studio-stage");
    stage.innerHTML = `<img src="${svgUrl(art.svg)}" alt="پیش‌نمایش ${esc(prompt)}" width="${art.width}" height="${art.height}">` +
      `<div class="studio-meta"><span class="pill">${THEMES[kind].label}</span><span class="pill">${art.palette.name}</span>` +
      `<span class="pill">${nf(art.width)}×${nf(art.height)}</span></div>`;
  }

  window.RAYAN_STUDIO = { makeArt, svgUrl, download, svgToPng, extractArtifacts, openArtifact, closePanel, openStudio, PALETTES, THEMES };

  document.addEventListener("DOMContentLoaded", () => {
    preloadBrandMark();
    attachToChat();
    // جایگاه‌های تبلیغ
    if (window.RAYAN_ADS) window.RAYAN_ADS.loadAll();
  });
})();
