/* آزمون رابط رایان با jsdom: بارگذاری صفحه‌ها، اجرای اسکریپت‌ها، تعامل واقعی */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const { ReadableStream } = require("stream/web");

const BASE = process.env.BASE || "http://localhost:8000";
const ROOT = process.env.RAYAN_ROOT || path.resolve(__dirname, "..", "..");

const results = [];
const errors = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  if (!ok) errors.push(`${name} ${detail}`);
}

async function loadPage(pagePath, { runScripts = true } = {}) {
  const res = await fetch(`${BASE}${pagePath}`, { headers: { accept: "text/html" } });
  let html = await res.text();
  const cookie = res.headers.get("set-cookie") || "";
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push(`jsdomError[${pagePath}]: ${e.message}`));
  vc.on("error", (m) => errors.push(`console.error[${pagePath}]: ${m}`));
  const dom = new JSDOM(html, {
    url: `${BASE}${pagePath}`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const { window } = dom;

  // سبد کوکی ساده (jsdom کوکی fetch را نگه نمی‌دارد)
  const jar = new Map();
  const cookieHeader = () => [...jar.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
  window.fetch = async (url, opts = {}) => {
    const absolute = url.startsWith("http") ? url : `${BASE}${url}`;
    const headers = Object.assign({}, opts.headers || {});
    if (jar.size) headers.cookie = cookieHeader();
    const response = await fetch(absolute, { ...opts, headers });
    const setCookies = typeof response.headers.getSetCookie === "function"
      ? response.headers.getSetCookie()
      : (response.headers.get("set-cookie") ? [response.headers.get("set-cookie")] : []);
    setCookies.forEach((raw) => {
      const [pair] = raw.split(";");
      const idx = pair.indexOf("=");
      if (idx > 0) jar.set(pair.slice(0, idx).trim(), pair.slice(idx + 1).trim());
    });
    const text = await response.text();
    const body = ReadableStream
      ? new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(text));
            controller.close();
          },
        })
      : null;
    return {
      ok: response.ok,
      status: response.status,
      headers: response.headers,
      text: async () => text,
      json: async () => JSON.parse(text),
      body: body,
    };
  };
  window.AbortController = AbortController;
  window.TextDecoder = TextDecoder;
  window.TextEncoder = TextEncoder;
  window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
  window.matchMedia = window.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.HTMLElement.prototype.scrollTo = () => {};
  window.IntersectionObserver = class {
    constructor(cb) { this.cb = cb; }
    observe(el) { this.cb([{ isIntersecting: true, target: el }]); }
    unobserve() {}
    disconnect() {}
  };
  window.localStorage.clear();
  window.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, {
    get: (t, k) => {
      if (k === "canvas") return { width: 600, height: 200 };
      if (k === "measureText") return () => ({ width: 20 });
      if (k === "createLinearGradient") return () => ({ addColorStop() {} });
      return () => {};
    },
    set: () => true,
  });

  if (runScripts) {
    const scripts = [...window.document.querySelectorAll("script[src]")].map((s) => s.getAttribute("src"));
    for (const src of scripts) {
      const file = path.join(ROOT, "web", src.replace(/^\//, "").replace(/^static\//, "static/"));
      const rel = path.join(ROOT, "web", src.replace(/^\//, ""));
      const target = fs.existsSync(rel) ? rel : file;
      if (!fs.existsSync(target)) { errors.push(`missing script ${src}`); continue; }
      try {
        window.eval(fs.readFileSync(target, "utf8"));
      } catch (err) {
        errors.push(`script ${src}: ${err.message}`);
      }
    }
    window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  }
  await new Promise((r) => setTimeout(r, 350));
  return { dom, window };
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function testLanding() {
  const { window } = await loadPage("/");
  const doc = window.document;
  check("landing: title", /رایان/.test(doc.title), doc.title);
  check("landing: hero h1", /فارسی/.test(doc.querySelector(".hero-title")?.textContent || ""));
  check("landing: features", doc.querySelectorAll(".feature").length >= 6);
  check("landing: plans", doc.querySelectorAll(".plan").length === 3);
  check("landing: faq", doc.querySelectorAll(".faq-item").length >= 5);
  check("landing: showcase rendered", doc.querySelectorAll("#showcase-list .showcase-item").length >= 3,
    String(doc.querySelectorAll("#showcase-list .showcase-item").length));
  check("landing: hero status", /مدل|گام|آموزش/.test(doc.querySelector("#hero-status")?.textContent || ""),
    doc.querySelector("#hero-status")?.textContent);
  const answers = doc.querySelector("#live-answers")?.textContent || "";
  check("landing: stats populated", /[\d۰-۹—]/.test(answers.trim()), answers);
  const stats = [...doc.querySelectorAll(".hero-stat b")].map((n) => n.textContent).join(" | ");
  console.log("HERO STATS:", stats);
  return { window };
}

async function testAuth() {
  const { window } = await loadPage("/signup");
  const doc = window.document;
  check("signup: title", /ساخت حساب/.test(doc.querySelector("#auth-title")?.textContent || ""), doc.querySelector("#auth-title")?.textContent);
  check("signup: name field visible", doc.querySelector("#name-field")?.hidden === false);
  // ارسال فرم با اعتبارنامهٔ نامعتبر
  doc.querySelector("#email").value = "bad-email";
  doc.querySelector("#password").value = "123";
  doc.querySelector("#auth-form").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await wait(120);
  check("signup: validation error", /معتبر|۸/.test(doc.querySelector("#auth-error")?.textContent || ""),
    doc.querySelector("#auth-error")?.textContent);
  return { window };
}

async function testChat() {
  const { window } = await loadPage("/chat");
  const doc = window.document;
  const R = window.RAYAN;
  check("chat: empty state", doc.querySelector("#empty-state")?.hidden === false);
  check("chat: suggestions", doc.querySelectorAll("#suggestions .suggestion").length >= 4,
    String(doc.querySelectorAll("#suggestions .suggestion").length));
  check("chat: models loaded", doc.querySelector("#model-label")?.textContent?.includes("رایان") === true,
    doc.querySelector("#model-label")?.textContent);

  // نام کاربر (مهمان)
  const uname = doc.querySelector("[data-user-name]")?.textContent;
  check("chat: account chrome", uname === "مهمان", uname);

  // ارسال پیام واقعی (جریان)
  const prompt = doc.querySelector("#prompt");
  prompt.value = "سلام! خودت را معرفی کن";
  doc.querySelector("#composer").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await wait(2500);
  const bubbles = [...doc.querySelectorAll(".msg.bot .bubble")].map((b) => b.textContent.trim());
  const answer = bubbles[bubbles.length - 1] || "";
  check("chat: answer streamed", answer.length > 3, JSON.stringify(answer.slice(0, 60)));
  const userBubble = doc.querySelector(".msg.user .bubble")?.textContent || "";
  check("chat: user bubble", userBubble.includes("خودت"), userBubble);
  const convs = doc.querySelectorAll(".conv-item").length;
  check("chat: conversation created", convs >= 1, String(convs));
  const usage = doc.querySelector("#usage-count")?.textContent || "";
  const usedMatch = usage.match(/[۰-۹0-9]+/);
  const usedNum = usedMatch ? Number(usedMatch[0].replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d))) : 0;
  check("chat: usage updated", usedNum > 0, usage);
  console.log("CHAT ANSWER:", JSON.stringify(answer.slice(0, 80)));
  console.log("CONVERSATIONS:", convs, "| USAGE:", usage);

  // اندیشهٔ ژرف
  doc.querySelector("#deep-toggle").click();
  check("chat: deep toggled", doc.querySelector("#deep-toggle").getAttribute("aria-pressed") === "true");
  prompt.value = "اسمت چیست؟";
  doc.querySelector("#composer").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await wait(3500);
  check("chat: deep trace shown", doc.querySelectorAll(".trace").length >= 1,
    String(doc.querySelectorAll(".trace").length));
  const traceText = doc.querySelector(".trace summary")?.textContent || "";
  check("chat: trace rationale", traceText.includes("مسیر"), traceText.slice(0, 60));
  console.log("TRACE:", traceText.slice(0, 90));

  // مدال تنظیمات
  doc.querySelector("#settings-btn").click();
  check("chat: settings modal", doc.querySelector("#settings-modal")?.hidden === false);
  doc.querySelector("#set-temp").value = "1.1";
  doc.querySelector("#set-temp").dispatchEvent(new window.Event("input", { bubbles: true }));
  check("chat: temp label", doc.querySelector("#temp-value")?.textContent?.includes("۱") === true,
    doc.querySelector("#temp-value")?.textContent);
  doc.querySelector("#settings-modal").hidden = true;

  // اشتراک‌گذاری
  doc.querySelector("#share-btn").click();
  await wait(600);
  const link = doc.querySelector("#share-link")?.value || "";
  check("chat: share link", link.includes("/s/"), link);
  doc.querySelector("#share-modal").hidden = true;

  // گفتگوی تازه
  doc.querySelector("#new-chat").click();
  await wait(200);
  check("chat: new chat clears", doc.querySelectorAll(".msg").length === 0);
  check("chat: empty visible again", doc.querySelector("#empty-state")?.hidden === false);
  return { window };
}

async function testPages() {
  for (const page of ["/pricing", "/models", "/about"]) {
    const { window } = await loadPage(page);
    const doc = window.document;
    check(`${page}: title`, /رایان/.test(doc.title), doc.title);
    check(`${page}: nav`, doc.querySelectorAll(".nav-links a").length >= 5);
    if (page === "/models") {
      check("models: cards", doc.querySelectorAll(".model-card").length === 3);
      check("models: eval table", doc.querySelectorAll("#eval-table tbody tr").length >= 6);
    }
    if (page === "/pricing") check("pricing: plans", doc.querySelectorAll(".plan").length === 3);
    if (page === "/about") check("about: sections", doc.querySelectorAll(".prose h2").length >= 5);
  }
}

(async () => {
  try {
    await testLanding();
    await testAuth();
    await testChat();
    await testPages();
  } catch (err) {
    errors.push(`FATAL: ${err.stack}`);
  }
  console.log("\n---- RESULT ----");
  results.forEach((r) => console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name}${r.ok ? "" : " :: " + r.detail}`));
  console.log(`\n${results.filter((r) => r.ok).length}/${results.length} passed`);
  console.log("ERRORS:", errors.length ? errors.slice(0, 12).join("\n") : "none");
  process.exit(errors.length || results.some((r) => !r.ok) ? 1 : 0);
})();
