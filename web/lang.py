"""زبان سایت — تک‌زبانه: فارسی، راست‌چین، پیش‌فرض برای همه.

نسخهٔ انگلیسی حذف شده است؛ نه هدایت خودکار بر پایهٔ IP یا ``Accept-Language``
انجام می‌شود، نه کوکی زبان لازم است. تنها یک زبان، یک جهت، و یک مجموعهٔ دارایی متحرک.
"""
from __future__ import annotations

LANGS = ("fa",)

# دارایی‌های متحرک برند (به‌جای ویدیوی تبلیغاتی؛ سبک، شفاف و بی‌صدا)
MOTION = {
    "fa": {
        "orb": "/static/assets/brand/orb-live.webp",
        "avatar": "/static/assets/brand/orb-live-sm.webp",
        "logo": "/static/assets/brand/logo-motion.webp",
        "logo_dark": "/static/assets/brand/logo-motion-dark.webp",
        "loading": "/static/assets/brand/logo-loading.webp",
    },
}


def detect(request) -> dict:  # noqa: ARG001 - امضای مشترک با فراخوان‌ها
    """همیشه فارسی؛ ``request`` فقط برای سازگاری امضا نگه داشته شده است."""
    return {
        "lang": "fa",
        "dir": "rtl",
        "source": "default",
        "motion": MOTION["fa"],
        "alternate": "/",
    }
