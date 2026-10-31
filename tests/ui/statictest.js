const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const BASE = "http://127.0.0.1:8078";
const pages = ["/index.html", "/chat.html", "/login.html", "/signup.html", "/pricing.html", "/models.html", "/about.html", "/docs.html", "/course.html", "/download.html"];
(async () => {
  const errors = [];
  for (const p of pages) {
    const html = await (await fetch(BASE + p)).text();
    const vc = new VirtualConsole();
    vc.on("jsdomError", (e) => errors.push(`${p}: ${e.message}`));
    vc.on("error", (m) => errors.push(`${p}: console.error ${m}`));
    vc.on("warn", () => {});
    const dom = new JSDOM(html, { url: BASE + p, runScripts: "outside-only", pretendToBeVisual: true, virtualConsole: vc });
    const { window } = dom;
    window.matchMedia = window.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
    window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
    window.TextDecoder = TextDecoder; window.TextEncoder = TextEncoder;
    window.HTMLMediaElement.prototype.play = () => Promise.resolve();
    window.HTMLMediaElement.prototype.pause = () => {};
    window.HTMLMediaElement.prototype.load = () => {};
    window.fetch = async (url) => { throw new Error("offline static"); };
    const scripts = [...window.document.querySelectorAll("script[src]")].map((s) => s.getAttribute("src"));
    for (const src of scripts) {
      const file = "/tmp/site/" + src.replace(/^\.?\//, "");
      if (!fs.existsSync(file)) { errors.push(`${p}: missing ${src}`); continue; }
      try { window.eval(fs.readFileSync(file, "utf8")); } catch (e) { errors.push(`${p}: eval ${src}: ${e.message}`); }
    }
    window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
    await new Promise((r) => setTimeout(r, 120));
    const banner = window.document.getElementById("static-banner");
    const disabled = window.document.getElementById("prompt")?.disabled;
    console.log(p, "banner:", !!banner, p === "/chat.html" ? `composer disabled: ${disabled}` : "");
    dom.window.close();
  }
  console.log("ERRORS:", errors.length ? errors : "none");
})();
