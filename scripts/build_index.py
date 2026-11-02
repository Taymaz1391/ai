#!/usr/bin/env python3
"""ساخت索引 بازیابی محلی (FTS5) از پیکرهٔ آموزش.

    python scripts/build_index.py            # پیکرهٔ کامل
    python scripts/build_index.py --quick    # نمونهٔ کوچک برای آزمون

خروجی ``data/index.sqlite3`` است؛ سرور با آن برای هر سؤال شاهد پیدا می‌کند.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from web import retrieval  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default=os.path.join(ROOT, "data", "train.txt"))
    parser.add_argument("--out", default=os.path.join(ROOT, "data", "index.sqlite3"))
    parser.add_argument("--quick", type=int, default=0, help="فقط N مگابایت اول پیکره")
    parser.add_argument("--knowledge", default=os.path.join(ROOT, "data", "knowledge.jsonl"))
    args = parser.parse_args()

    sources: list[tuple[str, str]] = []
    train_path = args.train
    if args.quick:
        sample = os.path.join(ROOT, "data", f"index-sample-{args.quick}m.txt")
        with open(args.train, encoding="utf-8") as src, open(sample, "w", encoding="utf-8") as dst:
            remaining = args.quick * 1_000_000
            while remaining > 0:
                block = src.read(min(1_000_000, remaining))
                if not block:
                    break
                dst.write(block)
                remaining -= len(block)
        train_path = sample
    sources.append(("پیکرهٔ فارسی رایان", train_path))

    if os.path.exists(args.knowledge):
        sources.append(("دانشنامهٔ پروژه", args.knowledge))

    info = retrieval.build_index(sources, out_path=args.out)
    info["sources"] = [name for name, _ in sources]
    print(json.dumps(info, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
