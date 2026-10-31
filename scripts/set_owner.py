#!/usr/bin/env python3
"""تعیین/چرخش گذرواژهٔ مالک رایان (ورود با نام کاربری).

    python scripts/set_owner.py                      # پرسش تعاملی
    python scripts/set_owner.py --password '...'      # غیرتعاملی
    RAYAN_OWNER_PASSWORD=... python scripts/set_owner.py --from-env

گذرواژه فقط به‌صورت هش scrypt در `data/owner.json` ذخیره می‌شود.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web import owner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", default="")
    parser.add_argument("--from-env", action="store_true")
    args = parser.parse_args()

    password = ""
    if args.from_env:
        password = os.environ.get("RAYAN_OWNER_PASSWORD", "")
    elif args.password:
        password = args.password
    else:
        first = getpass.getpass("گذرواژهٔ تازهٔ مالک: ")
        second = getpass.getpass("تکرار گذرواژه: ")
        if first != second:
            print("گذرواژه‌ها یکسان نیستند.")
            return 1
        password = first

    if not password:
        print("گذرواژه‌ای داده نشد.")
        return 1
    if password == owner.DEV_DEFAULT_PASSWORD:
        print("گذرواژهٔ پیش‌فرض پذیرفته نیست؛ یک گذرواژهٔ تازه انتخاب کن.")
        return 1
    try:
        info = owner.set_password(password)
    except ValueError as exc:
        print(exc)
        return 1
    print(f"گذرواژهٔ مالک برای «{info['name']}» ذخیره شد: {owner.OWNER_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
