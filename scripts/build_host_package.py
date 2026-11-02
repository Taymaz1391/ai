#!/usr/bin/env python3
"""ساختِ بستهٔ آپلود روی هاست اشتراکی.

    python scripts/build_host_package.py                 # release/rayan-host.zip
    python scripts/build_host_package.py --with-index    # همراه با ایندکسِ شاهد
    python scripts/build_host_package.py --out /tmp/pkg  # پوشهٔ خروجیِ دیگر

بسته فقط چیزهایی را دارد که در اجرا لازم است: کد، مدل، دانشنامه، استاتیک و
فایل‌های راه‌اندازی هاست. تست‌ها، مخزنِ گیت، محیطِ مجازی و پایگاه‌داده‌های محلی
داخل بسته نمی‌روند.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# پوشه‌هایی که کامل می‌روند
DIRS = ("web", "rayan", "tokenizer", "configs", "deploy")
# فایل‌های تک
FILES = (
    "passenger_wsgi.py", "requirements.txt", "requirements-host.txt", "README-HOST.md",
    "LICENSE", "NOTICE.md", "docs/HOSTING.md",
)
# داده‌های خواندنی (پایگاه‌داده‌ها و ایندکس‌های محلی عمداً نیستند)
DATA_FILES = ("knowledge.jsonl", "knowledge-pack.jsonl", "corpus_stats.json",
              "benchmark.jsonl", "chat_seed.jsonl")
CHECKPOINT = "checkpoints/rayan-1-small.npz"
SKIP_SUFFIX = (".pyc", ".pyo", ".log", ".tmp", ".bak", ".sqlite3", ".sqlite3-wal",
               ".sqlite3-shm", ".npz", ".zip")
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache", "var",
             "reports", "logs", "assets_src", "tests", ".github"}


def iter_dir(folder: Path):
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIX:
            continue
        yield path


def build_index(work: Path) -> Path | None:
    """ایندکسِ شاهد از دانشنامه؛ بدونِ پیکرهٔ آموزشیِ ۲۴۰ مگابایتی."""
    sys.path.insert(0, str(ROOT))
    from web import retrieval  # noqa: PLC0415

    sources = [("دانشنامهٔ پروژه", str(ROOT / "data" / name))
               for name in ("knowledge.jsonl", "knowledge-pack.jsonl")
               if (ROOT / "data" / name).exists()]
    if not sources:
        return None
    out = work / "index.sqlite3"
    info = retrieval.build_index(sources, out_path=str(out))
    print(f"  ایندکس: {info.get('documents', 0)} سند / {info.get('passages', 0)} قطعه "
          f"({out.stat().st_size / 1e6:.1f} مگابایت)")
    return out


def manifest(entries: list[str]) -> str:
    lines = [
        "رایان — بستهٔ میزبانی",
        f"ساخته‌شده: {time.strftime('%Y-%m-%d %H:%M')}",
        f"تعداد فایل: {len(entries)}",
        "",
        "راهنمای نصب: README-HOST.md",
        "پس از آپلود: python deploy/host_check.py",
        "",
        "فایل‌های کلیدی (sha256):",
    ]
    for name in ("passenger_wsgi.py", "web/server.py", "web/hosting.py",
                 "checkpoints/rayan-1-small.npz", "data/knowledge-pack.jsonl"):
        path = ROOT / name
        if path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            lines.append(f"  {digest}  {name}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "release"))
    parser.add_argument("--name", default="rayan-host")
    parser.add_argument("--with-index", action="store_true",
                        help="ایندکسِ شاهد از دانشنامه هم ساخته و اضافه شود")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{args.name}.zip"
    work = out_dir / f".{args.name}-work"
    work.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[str, Path]] = []
    for folder in DIRS:
        base = ROOT / folder
        if base.is_dir():
            for path in iter_dir(base):
                entries.append((str(path.relative_to(ROOT)), path))
    for name in FILES:
        path = ROOT / name
        if path.is_file():
            entries.append((name, path))
    for name in DATA_FILES:
        path = ROOT / "data" / name
        if path.is_file():
            entries.append((f"data/{name}", path))
    checkpoint = ROOT / CHECKPOINT
    if not checkpoint.exists():
        print("✗ checkpoint/rayan-1-small.npz پیدا نشد.", file=sys.stderr)
        return 2
    entries.append((CHECKPOINT, checkpoint))

    index_path = build_index(work) if args.with_index else None
    if index_path:
        entries.append(("data/index.sqlite3", index_path))

    entries = [(name, path) for name, path in entries if not name.startswith("dist")]
    names = [name for name, _ in entries]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for name, path in entries:
            zf.write(path, arcname=name)
        zf.writestr("MANIFEST.txt", manifest(names))
        zf.writestr("htaccess.sample", (ROOT / "deploy" / "apache.rules.conf").read_text(
            encoding="utf-8"))

    if index_path:
        index_path.unlink(missing_ok=True)
    try:
        work.rmdir()
    except OSError:
        pass

    info = {
        "package": str(zip_path),
        "size_mb": round(zip_path.stat().st_size / 1e6, 1),
        "files": len(entries) + 2,
        "index": bool(index_path),
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print("\nحالا فایل zip را در پوشهٔ برنامهٔ هاست آپلود و «Extract» کن، "
          "سپس README-HOST.md را بخوان.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
