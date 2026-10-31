#!/usr/bin/env python3
"""ساخت نسخهٔ استاتیک رایان برای GitHub Pages.

صفحه‌ها، استایل‌ها و دارایی‌ها را در یک پوشهٔ خروجی می‌ریزد و مسیرهای
مطلق (``/static/...`` و ``/chat``) را به مسیرهای نسبی تبدیل می‌کند تا
سایت روی زیرمسیر ``/ai/`` هم درست کار کند.

    python scripts/export_site.py --out _site
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"

PAGES = {
    "index.html": "index.html",
    "app.html": "chat.html",
    "pricing.html": "pricing.html",
    "models.html": "models.html",
    "about.html": "about.html",
    "docs.html": "docs.html",
    "course.html": "course.html",
    "en-course.html": "en-course.html",
    "offline.html": "offline.html",
    "summary.html": "summary.html",
    "en.html": "en.html",
    "en-docs.html": "en-docs.html",
}

# مسیرهای سرور → فایل‌های استاتیک
ROUTES = {
    "/": "index.html",
    "/chat": "chat.html",
    "/pricing": "pricing.html",
    "/models": "models.html",
    "/about": "about.html",
    "/docs": "docs.html",
    "/course": "course.html",
    "/en/course": "en-course.html",
    "/login": "login.html",
    "/signup": "signup.html",
    "/offline": "offline.html",
    "/summary": "summary.html",
    "/en": "en.html",
    "/en/docs": "en-docs.html",
}

NOT_FOUND_HTML = """<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>۴۰۴ — صفحه پیدا نشد · رایان</title><meta name="robots" content="noindex">
<link rel="icon" href="static/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="static/styles.css">
<style>body{min-height:100dvh;display:grid;place-items:center;padding:32px 20px}
.nf{max-width:520px;text-align:center;background:var(--surface);border:1px solid var(--line);
border-radius:26px;padding:40px 30px;box-shadow:var(--shadow-lg)}
.nf img{height:44px;width:auto;margin:0 auto 18px;display:block}
.nf h1{font-size:22px;margin:0 0 10px}.nf p{color:var(--text-2);font-size:14px;line-height:2;margin:0 0 20px}
.nf .row{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}</style></head>
<body><main class="nf">
<img src="static/assets/brand/wordmark-ink.png" alt="رایان" width="109" height="44">
<h1>این صفحه پیدا نشد</h1>
<p>نشانی اشتباه است یا صفحه جابه‌جا شده. از خانه یا مستندات شروع کن؛ دورهٔ ۵ ساعته هم همان‌جاست.</p>
<div class="row"><a class="btn btn-primary" href="index.html">بازگشت به خانه</a>
<a class="btn btn-ghost" href="course.html">دورهٔ ۵ ساعته</a>
<a class="btn btn-ghost" href="docs.html">مستندات</a></div>
</main></body></html>"""

RUNTIME_CONFIG = """/* ساخته‌شده به‌صورت خودکار برای نسخهٔ استاتیک (GitHub Pages). */
window.RAYAN_CONFIG = {{
  apiBase: "",
  appUrl: "chat.html",
  version: "{version}",
  static: true,
}};
"""


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rewrite_html(html: str) -> str:
    html = html.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    html = html.replace('srcset="/static/', 'srcset="static/')
    html = html.replace('href="/manifest.webmanifest"', 'href="manifest.webmanifest"')
    html = html.replace('href="/favicon.svg"', 'href="static/assets/favicon.svg"')
    html = html.replace('content="/static/', 'content="static/')

    def route(match: re.Match[str]) -> str:
        prefix, value, suffix = match.group(1), match.group(2), match.group(3)
        if value.startswith("/api/") or value.startswith("/static/"):
            return match.group(0)
        path, sep, rest = value.partition("#")
        if not sep:
            path, sep, rest = value.partition("?")
        target = ROUTES.get(path)
        if target is None:
            if not path.startswith("/"):
                return match.group(0)
            target = "index.html"
        return f"{prefix}{target}{sep}{rest}{suffix}"

    html = re.sub(r'(href=")(/[^"]*)(")', route, html)
    return html


def rewrite_js(js: str) -> str:
    js = js.replace('"/static/', '"static/')
    js = js.replace('"/manifest.webmanifest"', '"manifest.webmanifest"')
    js = js.replace('navigator.serviceWorker.register("/sw.js")', 'navigator.serviceWorker.register("sw.js")')
    js = js.replace('"/chat"', '"chat.html"')
    js = js.replace('"/academy"', '"academy.html"')
    js = js.replace('"/login"', '"login.html"')
    js = js.replace('"/signup"', '"signup.html"')
    return js


def build(out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    version = "2.0.0"
    config_src = read(STATIC / "config.js")
    match = re.search(r'version:\s*"([^"]+)"', config_src)
    if match:
        version = match.group(1)

    rendered: dict[str, str] = {}
    pages = 0
    for src_name in PAGES:
        src = STATIC / src_name
        if not src.exists():
            continue
        html = rewrite_html(read(src))
        rendered[src_name] = html
        (out / src_name.replace("app.html", "chat.html")).write_text(html, encoding="utf-8")
        pages += 1

    # ورود/ثبت‌نام هر دو از auth.html ساخته می‌شوند
    auth = read(STATIC / "auth.html")
    for mode, target in (("login", "login.html"), ("signup", "signup.html")):
        html = rewrite_html(auth).replace('data-mode="login"', f'data-mode="{mode}"')
        (out / target).write_text(html, encoding="utf-8")

    # دارایی‌ها
    shutil.copytree(STATIC / "assets", out / "static" / "assets")
    for name in ("styles.css", "pages.css", "landing.css", "chat.css",
                 "ui.js", "landing.js", "app.js", "auth.js", "models.js", "share.js",
                 "studio.js", "ads.js", "theme-boot.js", "offline.js",
                 "pricing.js", "promo.js", "course.js"):
        path = STATIC / name
        if path.exists():
            text = read(path)
            (out / "static" / name).write_text(rewrite_js(text), encoding="utf-8")
    (out / "static" / "config.js").write_text(RUNTIME_CONFIG.format(version=version), encoding="utf-8")

    # سرویس‌ورکر با مسیرهای نسبی
    sw = rewrite_js(read(STATIC / "sw.js"))
    (out / "sw.js").write_text(sw, encoding="utf-8")

    # مانیفست با مسیرهای نسبی
    en_css = STATIC / "en.css"
    if en_css.exists():
        (out / "static" / "en.css").write_text(read(en_css), encoding="utf-8")

    manifest = json.loads(read(STATIC / "manifest.webmanifest"))
    manifest["start_url"] = "chat.html"
    manifest["scope"] = "./"
    for icon in manifest.get("icons", []):
        icon["src"] = icon["src"].lstrip("/")
    (out / "manifest.webmanifest").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "404.html").write_text(NOT_FOUND_HTML, encoding="utf-8")
    rendered["404.html"] = NOT_FOUND_HTML

    return {"pages": pages + 2, "files": sum(1 for _ in out.rglob("*") if _.is_file()), "version": version}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="_site")
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    info = build(out)
    print(f"[rayan] static site → {out} | pages={info['pages']} files={info['files']} version={info['version']}")


if __name__ == "__main__":
    main()
