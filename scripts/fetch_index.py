"""دریافت ایندکس‌های آماده (پیکره و دانشنامه) روی سروری که دیسک دارد.

ایندکس‌ها در مخزن گیت نگه داشته نمی‌شوند (۲۸۴ و ۵۸۱ مگابایت). یک‌بار جایی
منتشرشان کن (مثلاً GitHub Release) و بعد روی سرور:

    RAYAN_INDEX_URL=https://…/index.sqlite3 \\
    RAYAN_WIKI_URL=https://…/wiki.sqlite3 \\
    python scripts/fetch_index.py

یا برای یک نشانی:

    python scripts/fetch_index.py --url https://…/wiki.sqlite3 --out data/wiki.sqlite3

اگر متغیرها خالی باشند، فرمان فقط وضعیت فعلی را نشان می‌دهد.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = [
    ("RAYAN_INDEX_URL", os.path.join("data", "index.sqlite3")),
    ("RAYAN_WIKI_URL", os.path.join("data", "wiki.sqlite3")),
]


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def download(url: str, out: str, force: bool = False) -> dict:
    path = os.path.join(ROOT, out) if not os.path.isabs(out) else out
    if os.path.exists(path) and not force:
        return {"ok": True, "skipped": True, "path": path,
                "bytes": os.path.getsize(path)}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".part"
    started = time.time()
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "rayan-index-fetch/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, open(temp, "wb") as fh:  # noqa: S310
        total = int(response.headers.get("content-length") or 0)
        read = 0
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            digest.update(chunk)
            read += len(chunk)
            if total:
                print(f"\r  {os.path.basename(path)}: {read * 100 // total}% "
                      f"({_human(read)} از {_human(total)})", end="", flush=True)
    print()
    shutil.move(temp, path)
    return {"ok": True, "path": path, "bytes": os.path.getsize(path),
            "sha256": digest.hexdigest(), "seconds": round(time.time() - started, 1)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.url:
        if not args.out:
            print("--out لازم است", file=sys.stderr)
            return 2
        print(json.dumps(download(args.url, args.out, args.force), ensure_ascii=False))
        return 0

    results = []
    for env, default_out in DEFAULT:
        url = os.environ.get(env, "").strip()
        if not url:
            path = os.path.join(ROOT, default_out)
            results.append({"env": env, "configured": False,
                            "exists": os.path.exists(path),
                            "bytes": os.path.getsize(path) if os.path.exists(path) else 0})
            continue
        results.append({"env": env, **download(url, default_out, args.force)})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
