#!/usr/bin/env python3
"""اتاق فرمان از سمت سازنده: خواندن دستورهای مالک، برداشتن کار و نوشتن پاسخ.

مالک در سایت (/admin → اتاق فرمان) می‌نویسد؛ این ابزار همان صف را می‌خواند.
هیچ دستوری خودکار اجرا نمی‌شود؛ متن دستور فقط داده است.

    python scripts/ops_console.py list                # همهٔ دستورها
    python scripts/ops_console.py pending             # فقط کارهای باز
    python scripts/ops_console.py take op_ab12cd      # علامت «در حال انجام»
    python scripts/ops_console.py reply op_ab12cd "انجام شد: دکمه آبی شد"
    python scripts/ops_console.py skip op_ab12cd "خارج از دسترس این نسخه است"
    python scripts/ops_console.py watch               # پایش پیوسته (هر ۵ ثانیه)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web import ops  # noqa: E402

STATUS_FA = {"pending": "در انتظار", "working": "در حال انجام",
             "done": "انجام شد", "skipped": "رد شد"}


def _print(order: dict) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(order.get("at", 0)))
    print(f"— {order['id']} · {STATUS_FA.get(order['status'], order['status'])} · {stamp}")
    print(f"  {order['text']}")
    for reply in order.get("replies", []):
        print(f"  ↳ {reply['text']}")


def cmd_list(_args) -> int:
    rows = ops.listing(limit=60)
    if not rows:
        print("صف خالی است.")
        return 0
    for order in rows:
        _print(order)
        print()
    stats = ops.stats()
    print(json.dumps(stats, ensure_ascii=False))
    return 0


def cmd_pending(args) -> int:
    rows = ops.pending()
    if not rows:
        print("کار بازی نیست.")
        return 0
    for order in rows:
        _print(order)
        print()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_take(args) -> int:
    ops.reply(args.id, "برداشتم؛ در حال انجام.", status="working")
    print(f"{args.id} → در حال انجام")
    return 0


def cmd_reply(args) -> int:
    ops.reply(args.id, args.text, status="done")
    print(f"{args.id} → انجام شد")
    return 0


def cmd_skip(args) -> int:
    ops.reply(args.id, args.text, status="skipped")
    print(f"{args.id} → رد شد")
    return 0


def cmd_watch(args) -> int:
    """پایش پیوسته: هر دستور تازه را چاپ می‌کند تا وقتی Ctrl+C بزنی."""
    seen: set[str] = set()
    print("پایش صف… (Ctrl+C برای توقف)")
    try:
        while True:
            fresh = [row for row in ops.pending() if row["id"] not in seen]
            for order in fresh:
                seen.add(order["id"])
                print(time.strftime("%H:%M:%S"), end=" ")
                _print(order)
                print(flush=True)
            time.sleep(max(2, args.interval))
    except KeyboardInterrupt:
        print("\nپایان پایش.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="همهٔ دستورها و پاسخ‌ها").set_defaults(func=cmd_list)

    pending = sub.add_parser("pending", help="فقط کارهای باز")
    pending.add_argument("--json", action="store_true")
    pending.set_defaults(func=cmd_pending)

    take = sub.add_parser("take", help="علامت «در حال انجام»")
    take.add_argument("id")
    take.set_defaults(func=cmd_take)

    reply = sub.add_parser("reply", help="ثبت پاسخ و بستن دستور")
    reply.add_argument("id")
    reply.add_argument("text")
    reply.set_defaults(func=cmd_reply)

    skip = sub.add_parser("skip", help="رد کردن با دلیل")
    skip.add_argument("id")
    skip.add_argument("text")
    skip.set_defaults(func=cmd_skip)

    watch = sub.add_parser("watch", help="پایش پیوستهٔ صف")
    watch.add_argument("--interval", type=float, default=5.0)
    watch.set_defaults(func=cmd_watch)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
