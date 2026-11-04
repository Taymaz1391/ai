#!/usr/bin/env python3
"""صفرکردنِ سهمیهٔ سنجش در دیتابیسِ آزمایشی (نه دیتابیسِ سایتِ زنده).

سنجشِ کیفیت با ۴۰ پیام از سهمیهٔ مهمان (۲۵) می‌گذرد و بقیهٔ درخواست‌ها با
۴۲۹ رد می‌شوند؛ آن‌وقت عددِ سنجش بی‌معنی می‌شود. این اسکریپت فقط رویدادهای
مصرف را در دیتابیسِ داده‌شده پاک می‌کند و هیچ دادهٔ کاربر را دست نمی‌زند.

    python scripts/reset_probe_quota.py --db /tmp/smoke.sqlite3
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("RAYAN_DB", "/tmp/smoke.sqlite3"))
    parser.add_argument("--kind", default="", help="فقط همین نوع (chat/deep)؛ خالی = همه")
    args = parser.parse_args()
    if not os.path.exists(args.db):
        sys.exit(f"دیتابیس پیدا نشد: {args.db}")
    if "smoke" not in os.path.basename(args.db):
        sys.exit("این اسکریپت فقط برای دیتابیسِ آزمایشی است (نامِ فایل باید smoke داشته باشد)")
    conn = sqlite3.connect(args.db)
    if args.kind:
        cur = conn.execute("DELETE FROM events WHERE kind=? AND user_id IS NULL", (args.kind,))
    else:
        cur = conn.execute("DELETE FROM events WHERE user_id IS NULL")
    conn.commit()
    print(f"پاک شد: {cur.rowcount} رویدادِ مصرف از {args.db}")
    conn.close()


if __name__ == "__main__":
    main()
