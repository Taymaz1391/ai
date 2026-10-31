#!/usr/bin/env python3
"""ساخت پیکرهٔ بزرگ فارسی برای آموزش در مقیاس میلیارد نویسه.

    python scripts/scale_corpus.py --sources corpora/news corpora/poems \
        --target-chars 1000000000 --out data/train.txt

ورودی‌ها می‌توانند پوشه، فایل ``.txt``، ``.txt.gz`` یا ``.jsonl`` با کلید
``text`` باشند. کارها:

* نرمال‌سازی با همان تابعی که مدل در زمان اجرا استفاده می‌کند
* حذف تکراری‌ها با اثر انگشت SHA-1 (دقیق، نه احتمالی)
* نوشتن جریانی و قابل ادامه: اگر قطع شد، از همان‌جا ادامه می‌دهد
* نگه‌داشتن ۰٬۵٪ برای اعتبارسنجی به‌صورت قطعی و تکرارپذیر

حافظهٔ لازم تقریباً ثابت است (چند ده مگابایت) چون هیچ‌وقت کل پیکره در RAM
جمع نمی‌شود. برای ۱ میلیارد نویسه حدود ۲ گیگابایت متن خام و چند ساعت I/O
لازم است؛ عدد دقیق را خودِ ابزار گزارش می‌دهد.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rayan.text import normalize  # noqa: E402

STATE = ROOT / "data" / ".scale_state.json"
SPLIT_RE = re.compile(r"\n{2,}")


def iter_lines(path: Path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as fh:
            yield from fh
    elif path.suffix == ".jsonl":
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                text = row.get("text") or row.get("content") or row.get("body") or ""
                if text:
                    yield text
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            yield from fh


def iter_source(source: str):
    if source.startswith(("http://", "https://")):
        req = Request(source, headers={"User-Agent": "rayan-corpus/1.0"})
        with urlopen(req, timeout=60) as res:  # noqa: S310 - آدرس را خودِ کاربر می‌دهد
            for line in res:
                yield line.decode("utf-8", errors="ignore")
        return
    path = Path(source)
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix in (".txt", ".gz", ".jsonl"):
                yield from iter_lines(child)
    elif path.exists():
        yield from iter_lines(path)
    else:
        print(f"[skip] پیدا نشد: {source}", file=sys.stderr)


def fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description="ساخت پیکرهٔ مقیاس‌پذیر فارسی")
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--target-chars", type=float, default=1_000_000_000)
    ap.add_argument("--out", default="data/train.txt")
    ap.add_argument("--val-out", default="data/val.txt")
    ap.add_argument("--val-ratio", type=float, default=0.005)
    ap.add_argument("--min-chars", type=int, default=12)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--fresh", action="store_true", help="از صفر شروع کن")
    args = ap.parse_args()

    out = Path(args.out)
    val = Path(args.val_out)
    if args.fresh:
        for path in (out, val, STATE):
            path.unlink(missing_ok=True)

    state = {"chars": 0, "docs": 0, "seen": 0, "dupes": 0, "sources": args.sources,
             "started": time.time()}
    if STATE.exists() and args.resume:
        try:
            state.update(json.loads(STATE.read_text(encoding="utf-8")))
            state["sources"] = args.sources
        except ValueError:
            pass

    seen: set[str] = set()
    seen_path = ROOT / "data" / ".scale_seen.txt"
    if seen_path.exists() and args.resume:
        with open(seen_path, "r", encoding="utf-8") as fh:
            seen = {line.strip() for line in fh if line.strip()}

    out.parent.mkdir(parents=True, exist_ok=True)
    target = int(args.target_chars)
    started = time.time()
    last_report = started

    mode_out = "a" if out.exists() and args.resume else "w"
    mode_val = "a" if val.exists() and args.resume else "w"
    seen_mode = "a" if seen and args.resume else "w"

    with open(out, mode_out, encoding="utf-8") as fo, \
            open(val, mode_val, encoding="utf-8") as fv, \
            open(seen_path, seen_mode, encoding="utf-8") as fs:
        for source in args.sources:
            print(f"[read] {source}", flush=True)
            buffer: list[str] = []
            for raw in iter_source(source):
                state["seen"] += 1
                text = normalize(raw).strip()
                if len(text) < args.min_chars:
                    continue
                fp = fingerprint(text)
                if fp in seen:
                    state["dupes"] += 1
                    continue
                seen.add(fp)
                fs.write(fp + "\n")
                buffer.append(text)
                if len(buffer) >= 512:
                    chunk = "\n\n".join(buffer)
                    buffer.clear()
                    state["docs"] += len(chunk.split("\n\n"))
                    state["chars"] += len(chunk)
                    to_val = (state["docs"] % max(1, int(1 / max(args.val_ratio, 0.0001)))) == 0
                    (fv if to_val else fo).write(chunk + "\n\n")
                    if state["chars"] >= target:
                        break
                now = time.time()
                if now - last_report > 15:
                    last_report = now
                    pct = 100 * state["chars"] / target
                    rate = state["chars"] / max(now - started, 1)
                    print(f"[corpus] {state['chars']:,} نویسه ({pct:.1f}%) · "
                          f"{rate:,.0f} نویسه/ثانیه · تکراری {state['dupes']:,}", flush=True)
                    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            if buffer:
                chunk = "\n\n".join(buffer)
                state["docs"] += len(buffer)
                state["chars"] += len(chunk)
                fo.write(chunk + "\n\n")
            if state["chars"] >= target:
                break

    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    stats = {
        "target_chars": target,
        "chars": state["chars"],
        "docs": state["docs"],
        "duplicates": state["dupes"],
        "seconds": round(time.time() - started, 1),
        "complete": state["chars"] >= target * 0.999,
    }
    stats_path = ROOT / "data" / "scale_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if stats["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
