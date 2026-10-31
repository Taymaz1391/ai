#!/usr/bin/env python3
"""پاک‌کردن سهمیهٔ امروز در پایگاه‌دادهٔ توسعه (فقط برای آزمون رابط).

    python scripts/reset_dev_quota.py            # پاک‌سازی کامل رویدادهای چت
    RAYAN_DB=... python scripts/reset_dev_quota.py
"""
from __future__ import annotations

import os
import sqlite3
import sys


def main() -> int:
    path = os.environ.get("RAYAN_DB", "data/rayan.sqlite3")
    if not os.path.exists(path):
        print(f"database not found: {path}")
        return 1
    con = sqlite3.connect(path)
    try:
        cur = con.execute("DELETE FROM events WHERE kind IN ('chat','deep')")
        con.commit()
        print(f"cleared {cur.rowcount} usage events in {path}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
