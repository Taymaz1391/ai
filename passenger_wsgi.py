"""نقطهٔ ورودِ هاست اشتراکی — cPanel / Plesk / DirectAdmin (Passenger یا mod_wsgi).

روی هاست:

۱. بستهٔ ``rayan-host.zip`` را در پوشهٔ برنامه (Application Root) باز کن.
۲. در cPanel → **Setup Python App** یک برنامه بساز:

   * Application root: همان پوشه‌ای که این فایل در آن است
   * Application URL: دامنه یا زیردامنه (اگر زیرشاخه شد، ``RAYAN_BASE_PATH`` را همان بگذار)
   * Application startup file: ``passenger_wsgi.py``
   * Python version: 3.10 یا بالاتر

۳. در همان صفحه، «Run Pip Install» را با ``requirements.txt`` بزن (یا در ترمینال:
   ``pip install -r requirements.txt``).
۴. متغیرهای محیطی را در همان صفحه اضافه کن (دست‌کم ``RAYAN_OWNER_PASSWORD``).
۵. برنامه را Restart کن؛ سپس ``/api/health`` باید ``{"ok": true}`` بدهد.

هیچ سرویس هوش مصنوعی بیرونی لازم نیست؛ مدل داخل بسته است.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# پیش از هر وارداتِ برنامه: پوشه‌های نوشتنی، حالتِ هاست و پیش‌فرض‌های امن
os.environ.setdefault("RAYAN_HOST", "1")
from web.hosting import prepare_host_env, to_wsgi  # noqa: E402

prepare_host_env(ROOT)

from web.server import app, boot  # noqa: E402

# در Passenger رخدادِ lifespan اجرا نمی‌شود؛ آماده‌سازی را صریح انجام می‌دهیم.
boot()

application = to_wsgi(app)


def app_factory():                     # برای سرورهایی که کارخانهٔ برنامه می‌خواهند
    return application
