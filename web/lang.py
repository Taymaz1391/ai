"""زبان سایت — تک‌زبانه: فارسی، راست‌چین، پیش‌فرض برای همه.

نسخهٔ انگلیسی حذف شده است؛ نه هدایت خودکار بر پایهٔ IP یا ``Accept-Language``
انجام می‌شود، نه کوکی زبان لازم است. تنها یک زبان، یک جهت، و یک مجموعهٔ ویدیو.
"""
from __future__ import annotations

LANGS = ("fa",)

# نسخه‌های ویدیوی تبلیغاتی
VIDEOS = {
    "fa": {
        "landscape": "/static/assets/video/promo-fa-16x9.mp4",
        "vertical": "/static/assets/video/promo-fa-9x16.mp4",
        "square": "/static/assets/video/promo-fa-1x1.mp4",
        "poster": "/static/assets/video/promo-fa-poster.jpg",
    },
}


def detect(request) -> dict:  # noqa: ARG001 - امضای مشترک با فراخوان‌ها
    """همیشه فارسی؛ ``request`` فقط برای سازگاری امضا نگه داشته شده است."""
    return {
        "lang": "fa",
        "dir": "rtl",
        "source": "default",
        "videos": VIDEOS["fa"],
        "alternate": "/",
    }
