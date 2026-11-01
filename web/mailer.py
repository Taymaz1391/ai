"""کد تأیید ایمیل رایان — واقعی، با SMTP؛ هیچ کدی در متن نوشته نمی‌شود.

سه چیز را رعایت می‌کند:

* **کد واقعی** — شش رقم تصادفی با `secrets` ساخته می‌شود و فقط هشِ آن ذخیره
  می‌شود؛ خودِ کد هیچ‌جا در پایگاه‌داده نمی‌ماند.
* **ارسال واقعی** — با هر سرویس SMTP کار می‌کند (Gmail با «گذرواژهٔ برنامه»،
  Brevo، Mailgun، SMTP سرور خودتان). پیکربندی با متغیرهای محیطی است:

      RAYAN_SMTP_HOST=smtp.gmail.com
      RAYAN_SMTP_PORT=587
      RAYAN_SMTP_USER=you@gmail.com
      RAYAN_SMTP_PASS=xxxx xxxx xxxx xxxx      # گذرواژهٔ برنامه، نه گذرواژهٔ حساب
      RAYAN_SMTP_FROM="رایان <you@gmail.com>"
      RAYAN_SMTP_TLS=starttls                    # starttls | ssl | none

* **بدون ادعا** — اگر SMTP تنظیم نشده باشد، سرویس صریح می‌گوید «ارسال ایمیل
  پیکربندی نشده است» و کد را جایی چاپ نمی‌کند؛ در حالت توسعه فقط اگر
  `RAYAN_EMAIL_DEV=1` باشد کد در پاسخ API برمی‌گردد تا آزمون ممکن باشد.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage

CODE_TTL = int(os.environ.get("RAYAN_CODE_TTL", "600"))       # ۱۰ دقیقه
RESEND_SECONDS = int(os.environ.get("RAYAN_CODE_RESEND", "60"))
MAX_TRIES = int(os.environ.get("RAYAN_CODE_TRIES", "6"))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class MailError(RuntimeError):
    """ارسال نشد؛ متن پیام برای نمایش به کاربر مناسب است."""


def valid_address(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))


def normalize(email: str) -> str:
    return (email or "").strip().lower()


# ------------------------------------------------------------------ کد
def new_code() -> str:
    """شش رقم تصادفیِ رمزنگاری‌شده؛ صفرِ ابتدایی حفظ می‌شود."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str, salt: str) -> str:
    return hmac.new(bytes.fromhex(salt), code.encode("utf-8"), hashlib.sha256).hexdigest()


def check_code(stored: dict | None, code: str) -> tuple[bool, str]:
    """(درست؟، پیام) — انقضا و تعداد تلاش هم بررسی می‌شود."""
    if not stored:
        return False, "کدی برای این ایمیل صادر نشده است؛ دوباره درخواست بده."
    if time.time() > float(stored["expires_at"]):
        return False, "کد منقضی شده است؛ کد تازه بگیر."
    if int(stored["tries"]) >= MAX_TRIES:
        return False, "تعداد تلاش‌ها زیاد شد؛ کد تازه بگیر."
    if not hmac.compare_digest(stored["code_hash"], hash_code(code.strip(), stored["salt"])):
        return False, "کد نادرست است."
    return True, ""


def seconds_until_resend(stored: dict | None) -> int:
    if not stored:
        return 0
    left = RESEND_SECONDS - (time.time() - float(stored["sent_at"]))
    return max(0, int(left))


# ------------------------------------------------------------------ ارسال
def _setting(key: str, default: str = "") -> str:
    """پیکربندیِ ذخیره‌شده در پنل مدیریت (متغیر محیطی همیشه اولویت دارد)."""
    try:
        from web import store as store_module
        return store_module.store().setting(f"mail.{key}", default) or default
    except Exception:  # noqa: BLE001 - نبودِ پایگاه‌داده نباید ارسال را بشکند
        return default


def config() -> dict:
    """پیکربندیِ مؤثر: متغیر محیطی ← سپس ذخیره‌شده در پنل."""
    def pick(env: str, key: str, default: str = "") -> str:
        return os.environ.get(env) or _setting(key, default)

    return {
        "host": pick("RAYAN_SMTP_HOST", "host"),
        "port": pick("RAYAN_SMTP_PORT", "port", "587"),
        "user": pick("RAYAN_SMTP_USER", "user"),
        "password": pick("RAYAN_SMTP_PASS", "pass"),
        "sender": pick("RAYAN_SMTP_FROM", "from"),
        "mode": pick("RAYAN_SMTP_TLS", "tls", "starttls").lower(),
    }


def configured() -> bool:
    cfg = config()
    return bool(cfg["host"] and cfg["sender"])


def _message(to: str, code: str, purpose: str, sender: str = "") -> EmailMessage:
    subject = "کد تأیید رایان" if purpose != "reset" else "بازیابی گذرواژهٔ رایان"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender or "رایان <no-reply@rayan.local>"
    msg["To"] = to
    msg.set_content(
        f"کد تأیید شما: {code}\n\n"
        f"این کد تا {CODE_TTL // 60} دقیقه معتبر است. اگر شما درخواست نداده‌اید، "
        f"این ایمیل را نادیده بگیرید.\n\nرایان — هوش مصنوعی فارسی"
    )
    msg.add_alternative(
        f"""<!doctype html><html dir="rtl" lang="fa"><body style="font-family:Tahoma,Arial,sans-serif;
background:#f4f7ff;padding:24px;color:#0a1730">
<div style="max-width:420px;margin:auto;background:#fff;border-radius:18px;padding:26px;
box-shadow:0 24px 60px -40px rgba(12,44,104,.5)">
<div style="font-size:15px;color:#4b5c7a">کد تأیید رایان</div>
<div style="font-size:34px;letter-spacing:10px;font-weight:800;margin:16px 0;color:#1b6bff">{code}</div>
<div style="font-size:13px;color:#4b5c7a;line-height:1.9">
این کد تا {CODE_TTL // 60} دقیقه معتبر است.<br>اگر شما درخواست نداده‌اید، این ایمیل را نادیده بگیرید.
</div></div></body></html>""",
        subtype="html",
    )
    return msg


def send(to: str, code: str, purpose: str = "signup") -> None:
    """ارسال واقعی ایمیل؛ در نبودِ پیکربندی، صریح خطا می‌دهد (نه موفقیت قلابی)."""
    if not configured():
        raise MailError("ارسال ایمیل هنوز پیکربندی نشده است؛ با پشتیبانی تماس بگیر.")
    cfg = config()
    host = cfg["host"]
    try:
        port = int(cfg["port"] or 587)
    except ValueError:
        port = 587
    user = cfg["user"]
    password = cfg["password"]
    mode = cfg["mode"]
    msg = _message(to, code, purpose, sender=cfg["sender"])
    try:
        if mode == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if mode == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise MailError("ارسال ایمیل ناموفق بود؛ چند لحظه بعد دوباره تلاش کن.") from exc


def dev_mode() -> bool:
    """فقط برای آزمون محلی: کد در پاسخ API برمی‌گردد و ایمیلی ارسال نمی‌شود."""
    return os.environ.get("RAYAN_EMAIL_DEV", "0") == "1"


def status() -> dict:
    cfg = config()
    return {"configured": configured(), "dev": dev_mode(),
            "host": cfg["host"], "mode": cfg["mode"], "sender": cfg["sender"],
            "has_password": bool(cfg["password"]),
            "ttl": CODE_TTL, "resend": RESEND_SECONDS}


def send_test(to: str) -> None:
    """ارسالِ ایمیلِ آزمایشی به همان مسیرِ کد؛ برای دکمهٔ پنل مدیریت."""
    send(to, new_code(), "test")
