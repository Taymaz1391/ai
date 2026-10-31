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
  window.HTMLMediaElement.prototype.play = () => Promise.resolve();
  window.HTMLMediaElement.prototype.pause = () => {};
  window.HTMLMediaElement.prototype.load = () => {};
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
  check("landing: promo video", !!doc.querySelector("#promo-video"));
  const pv = doc.querySelector("#promo-video");
  check("landing: promo autoplay muted", !!pv && pv.hasAttribute("autoplay") && pv.hasAttribute("muted"));
  check("landing: promo sound button", !!doc.querySelector("#promo-sound"));
  check("landing: no academy", !doc.querySelector('a[href="/academy"]'));
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

  // نوار گفتگوها: یک دکمه باز می‌کند، یک دکمه می‌بندد و نوار کامل ناپدید می‌شود
  const sidebar = doc.querySelector("#sidebar");
  const scrim = doc.querySelector("#sidebar-scrim");
  const toggle = doc.querySelector("#sidebar-open");
  check("chat: sidebar closed by default", !sidebar.classList.contains("is-open"));
  toggle.click();
  check("chat: sidebar opens", sidebar.classList.contains("is-open") && scrim.hidden === false,
    `${sidebar.className}|${scrim.hidden}`);
  check("chat: sidebar aria expanded", toggle.getAttribute("aria-expanded") === "true");
  doc.querySelector("#sidebar-close").click();
  check("chat: sidebar fully hidden", !sidebar.classList.contains("is-open")
    && sidebar.hasAttribute("inert") && sidebar.getAttribute("aria-hidden") === "true",
    `${sidebar.className}|${sidebar.hasAttribute("inert")}`);
  check("chat: scrim removed", scrim.hidden === true);
  check("chat: toggle still reachable", !!toggle && !toggle.hasAttribute("hidden")
    && !toggle.hasAttribute("disabled"));
  toggle.click();
  check("chat: one button restores sidebar", sidebar.classList.contains("is-open") && scrim.hidden === false);
  toggle.click();
  check("chat: same button closes again", !sidebar.classList.contains("is-open") && scrim.hidden === true);

  // ویدیوی معرفی در همان صفحه
  check("chat: promo modal present", doc.querySelector("#promo-modal")?.hidden === true);
  check("chat: promo video source", /promo-fa-16x9\.mp4/.test(
    doc.querySelector("#promo-modal-video source")?.getAttribute("src") || ""));
  doc.querySelector("#promo-open").click();
  check("chat: promo modal opens", doc.querySelector("#promo-modal").hidden === false);
  doc.querySelector("#promo-modal").hidden = true;

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
  await wait(9000);
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

async function testAdminGate() {
  const { window } = await loadPage("/admin");
  const doc = window.document;
  check("admin: login gate", doc.querySelector("#admin-login")?.hidden === false);
  check("admin: shell hidden", doc.querySelector("#admin-shell")?.hidden === true);
  const pw = doc.querySelector("#admin-password");
  // اعتبارسنجی سمت مرورگر؛ عمداً درخواست ورود نمی‌فرستیم تا قفل تلاش‌های ناموفق فعال نشود.
  check("admin: password field constrained", pw.getAttribute("type") === "password"
    && Number(pw.getAttribute("minlength")) >= 6);
  const form = doc.querySelector("#login-form");
  check("admin: form wired", !!form && typeof form.requestSubmit === "function");
}

async function testOfflinePage() {
  const { window } = await loadPage("/offline");
  const doc = window.document;
  check("offline: headline", /بدون اتصال|اتصال/.test(doc.body.textContent));
  check("offline: retry", !!doc.querySelector("#retry"));
  check("offline: noindex", /noindex/.test(doc.querySelector('meta[name="robots"]')?.content || ""));
}

async function testToolChip() {
  const { window } = await loadPage("/chat");
  const doc = window.document;
  const prompt = doc.querySelector("#prompt");
  prompt.value = "۷*۶ چند است؟";
  doc.querySelector("#composer").dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
  await wait(1800);
  const chip = doc.querySelector(".tool-result .tool-badge")?.textContent || "";
  const value = doc.querySelector(".tool-result b")?.textContent || "";
  check("chat: tool chip shown", /ماشین/.test(chip), chip);
  check("chat: tool value 42", value.replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).includes("42"), value);
}

async function testThemeToggle() {
  const { window } = await loadPage("/");
  const doc = window.document;
  const html = doc.documentElement;
  check("theme: light by default", html.getAttribute("data-theme") !== "dark", html.getAttribute("data-theme") || "light");
  const toggle = doc.querySelector("[data-theme-toggle]");
  check("theme: toggle present", !!toggle);
  if (toggle) {
    toggle.click();
    await wait(120);
    check("theme: switches to dark", html.getAttribute("data-theme") === "dark", html.getAttribute("data-theme"));
    toggle.click();
    await wait(120);
    check("theme: switches back", html.getAttribute("data-theme") === "light", html.getAttribute("data-theme"));
  }
}

async function testCourse() {
  const { window } = await loadPage("/course");
  const doc = window.document;
  check("course: title", /۵ ساعته/.test(doc.title), doc.title);
  const lessons = [...doc.querySelectorAll("[data-lesson]")];
  check("course: ten lessons", lessons.length === 10, String(lessons.length));
  const minutes = lessons.reduce((n, el) => n + Number(el.getAttribute("data-min") || 0), 0);
  check("course: five hours", minutes === 300, String(minutes));
  check("course: content", doc.body.textContent.length > 15000, String(doc.body.textContent.length));
  check("course: progress bar", !!doc.getElementById("course-bar-fill"));
  check("course: read aloud buttons", doc.querySelectorAll("[data-read]").length === 10);
  const first = doc.querySelector("[data-done]");
  first.click();
  await wait(60);
  check("course: progress updates", /۱۰٪/.test(doc.getElementById("course-percent").textContent),
    doc.getElementById("course-percent").textContent);
  check("course: progress stored", /rayan.course/.test(JSON.stringify(Object.keys(window.localStorage)))
    || !!window.localStorage.getItem("rayan.course.v1"));
  check("course: toc", doc.querySelectorAll(".course-toc a").length >= 10);
}

async function testEnglishAndSummary() {
  const en = await loadPage("/en");
  const enDoc = en.window.document;
  check("en: title", /Rayan/.test(enDoc.title), enDoc.title);
  check("en: html lang", enDoc.documentElement.lang === "en", enDoc.documentElement.lang);
  check("en: dir ltr", enDoc.documentElement.dir === "ltr", enDoc.documentElement.dir);
  check("en: features", enDoc.querySelectorAll(".feature").length >= 4,
    String(enDoc.querySelectorAll(".feature").length));
  check("en: video", !!enDoc.querySelector("#promo-video source"));
  check("en: autoplay muted", enDoc.getElementById("promo-video")?.hasAttribute("muted") === true
    && enDoc.getElementById("promo-video")?.hasAttribute("autoplay") === true);
  check("en: wordmark", enDoc.querySelectorAll(".brand-wordmark").length >= 2);

  const enCourse = await loadPage("/en/course");
  const enCourseDoc = enCourse.window.document;
  check("en course: syllabus", enCourseDoc.querySelectorAll(".lesson").length >= 10,
    String(enCourseDoc.querySelectorAll(".lesson").length));
  check("en course: fa switch", !!enCourseDoc.querySelector('a[href="/course"]'));

  const docs = await loadPage("/en/docs");
  check("en docs: sections", docs.window.document.querySelectorAll(".prose h2").length >= 5,
    String(docs.window.document.querySelectorAll(".prose h2").length));

  const sum = await loadPage("/summary");
  const sumDoc = sum.window.document;
  check("summary: title", /خلاصه/.test(sumDoc.title), sumDoc.title);
  check("summary: cards", sumDoc.querySelectorAll(".sum-card").length >= 5,
    String(sumDoc.querySelectorAll(".sum-card").length));
  check("summary: limits mentioned", /یک میلیارد/.test(sumDoc.body.textContent));
}

(async () => {
  try {
    await testLanding();
    await testAuth();
    await testChat();
    await testPages();
    await testAdminGate();
    await testOfflinePage();
    await testToolChip();
    await testThemeToggle();
    await testCourse();
    await testEnglishAndSummary();
  } catch (err) {
    errors.push(`FATAL: ${err.stack}`);
  }
  console.log("\n---- RESULT ----");
  results.forEach((r) => console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name}${r.ok ? "" : " :: " + r.detail}`));
  console.log(`\n${results.filter((r) => r.ok).length}/${results.length} passed`);
  console.log("ERRORS:", errors.length ? errors.slice(0, 12).join("\n") : "none");
  process.exit(errors.length || results.some((r) => !r.ok) ? 1 : 0);
})();
