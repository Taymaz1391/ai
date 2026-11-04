#!/usr/bin/env python3
"""بازرسی خودکار سایت — دارایی‌های گم‌شده، لینک‌های شکسته، خطای JS و API.

    python scripts/audit_site.py --api http://127.0.0.1:8000

هر یافته یک خط است: نوع، محل، و چه چیزی خراب است. خروجی غیرصفر یعنی دست‌کم یک ایراد.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"

HREF = re.compile(r'(?:href|src)\s*=\s*"([^"#]+)"')
CSS_URL = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)')
FETCH = re.compile(r'(?:fetch|request)\(\s*"(/api/[^"?]*)')
ID_REF = re.compile(r'\$\("#([A-Za-z0-9_-]+)"\)')


def get(base: str, path: str, timeout: float = 15.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=timeout) as rsp:
            return rsp.status, rsp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode()


def local_asset(path: str) -> Path | None:
    """مسیر یک نشانیِ ایستا را به فایلِ محلی تبدیل می‌کند."""
    if not path.startswith("/static/"):
        if path.startswith("/") and path.endswith((".js", ".css", ".webmanifest", ".svg", ".png")):
            return STATIC / path.lstrip("/")
        return None
    return STATIC / path[len("/static/"):]


def page_routes() -> dict[str, str]:
    """نامِ فایل → مسیرِ واقعی، از روی `_page("x.html")` در سرور."""
    server = (ROOT / "web" / "server.py").read_text(encoding="utf-8")
    routes: dict[str, str] = {}
    for chunk in server.split("@app.get(")[1:]:
        head = chunk.split(")", 1)[0]
        path = head.strip().strip('"').split('"')[0]
        if not path.startswith("/") or "{" in path:
            continue
        body = chunk.split("@app.get(")[0]
        found = re.search(r'_page\("([^"]+\.html)"', body)
        if found:
            routes.setdefault(found.group(1), path)
    routes.setdefault("index.html", "/")
    return routes


def check_pages(base: str, report: list[str]) -> None:
    routes = page_routes()
    for file_name, path in sorted(routes.items()):
        status, body = get(base, path)
        if status != 200:
            report.append(f"صفحه {path} → {status}")
        text = body.decode("utf-8", "ignore")
        for ref in HREF.findall(text):
            if ref.startswith(("http://", "https://", "mailto:", "data:", "#", "javascript:")):
                continue
            if not ref.startswith("/"):
                continue
            file_path = local_asset(ref.split("?")[0])
            if file_path is None:
                # مسیرهای سروری مثل /api یا /login را با درخواست می‌سنجیم
                code, _ = get(base, ref.split("?")[0], timeout=10)
                if code >= 400:
                    report.append(f"لینک {path} → {ref} = {code}")
                continue
            if not file_path.exists():
                report.append(f"دارایی گم‌شده {path} → {ref}")


def check_css(report: list[str]) -> None:
    for css in STATIC.glob("*.css"):
        text = css.read_text(encoding="utf-8", errors="ignore")
        # data-URIها نشانیِ فایل نیستند
        text = re.sub(r'url\(\s*["\']?data:[^)]*\)', "", text)
        for ref in CSS_URL.findall(text):
            ref = ref.split("?")[0]
            if ref.startswith(("data:", "http:", "https:", "#")):
                continue
            target = local_asset(ref) if ref.startswith("/") else css.parent / ref
            if target is not None and not Path(target).exists():
                report.append(f"دارایی گم‌شده {css.name} → {ref}")


def check_js(report: list[str]) -> None:
    for js in sorted(STATIC.glob("*.js")):
        proc = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        if proc.returncode != 0:
            first = (proc.stderr or "").strip().splitlines()
            report.append(f"خطای نگارشی {js.name}: {first[-1] if first else '?'}")


def check_sw(report: list[str]) -> None:
    """فهرست پیش‌کش سرویس‌ورکر باید فقط فایل‌های موجود را داشته باشد."""
    sw = STATIC / "sw.js"
    if not sw.exists():
        return
    text = sw.read_text(encoding="utf-8", errors="ignore")
    routes = page_routes()
    known = set(routes.values())
    for ref in re.findall(r'"(/[^"]+)"', text):
        if ref.startswith("/api/") or ref in known:
            continue
        target = STATIC / ref.lstrip("/") if not ref.startswith("/static/") else local_asset(ref)
        if target is not None and not Path(target).exists():
            report.append(f"پیش‌کشِ ناموجود sw.js → {ref}")


def check_html_ids(report: list[str]) -> None:
    """هر `$("#id")` که در HTML هیچ صفحه‌ای نباشد، معمولاً باگِ رابط است."""
    ids: set[str] = set()
    for html in STATIC.glob("*.html"):
        ids.update(re.findall(r'id="([^"]+)"', html.read_text(encoding="utf-8", errors="ignore")))
    app = STATIC / "app.html"
    page_ids = set(re.findall(r'id="([^"]+)"', app.read_text(encoding="utf-8"))) if app.exists() else set()
    dynamic_prefixes = ("conv-", "msg-", "toast-", "player", "intro")
    missing: dict[str, set[str]] = {}
    for js in ("app.js", "ui.js", "settings.js", "admin.js", "voice.js", "studio.js"):
        path = STATIC / js
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for ref in ID_REF.findall(text):
            if ref in ids or ref in page_ids:
                continue
            if ref.startswith(dynamic_prefixes):
                continue
            missing.setdefault(js, set()).add(ref)
    for js, refs in missing.items():
        report.append(f"شناسهٔ ناموجود {js}: {', '.join(sorted(refs)[:6])}"
                      + (" …" if len(refs) > 6 else ""))


def check_apis(base: str, report: list[str]) -> None:
    endpoints = [
        "/api/health", "/api/models", "/api/samples", "/api/auth/me", "/api/config",
        "/api/conversations", "/api/usage", "/api/plans", "/api/status",
    ]
    for path in endpoints:
        code, body = get(base, path, timeout=20)
        if code == 0:
            report.append(f"API {path} → بی‌پاسخ ({body[:60].decode('utf-8', 'ignore')})")
        elif code >= 500:
            report.append(f"API {path} → {code}")
        elif code >= 400 and path in ("/api/health", "/api/models", "/api/plans"):
            report.append(f"API {path} → {code}")


def raw_endpoint_calls(report: list[str]) -> None:
    """فراخوانی‌های /api در JS باید در سرور وجود داشته باشند."""
    server = (ROOT / "web" / "server.py").read_text(encoding="utf-8")
    declared = set()
    for method, path in re.findall(r'@app\.(get|post|patch|delete)\("([^"]+)"\)', server):
        declared.add(path)
    for js in STATIC.glob("*.js"):
        text = js.read_text(encoding="utf-8", errors="ignore")
        for path in FETCH.findall(text):
            path = path.split("?")[0]
            if "[" in path or "$" in path or "{" in path:
                continue
            if path in declared:
                continue
            # مسیرهای پارامتری
            if any(part.startswith(":") for part in re.findall(r'@app\.\w+\("([^"]+)"\)', server)):
                pass
            if any(path.startswith(d.split(":")[0]) for d in declared if "{" in d):
                continue
            report.append(f"API ناموجود در JS {js.name}: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report: list[str] = []
    check_js(report)
    check_css(report)
    check_sw(report)
    check_html_ids(report)
    raw_endpoint_calls(report)
    if args.api:
        check_pages(args.api, report)
        check_apis(args.api, report)

    if args.json:
        print(json.dumps({"issues": report}, ensure_ascii=False, indent=2))
    else:
        if not report:
            print("✓ هیچ ایرادی پیدا نشد")
        for line in report:
            print(" ✗", line)
        print(f"\n{len(report)} ایراد")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
