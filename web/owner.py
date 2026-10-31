"""هویت مالک (مدیر کل) — ورود با نام کاربری فارسی، بدون افشای گذرواژه در مخزن.

گذرواژه هرگز در کد یا Git ذخیره نمی‌شود؛ فقط هش scrypt در ``data/owner.json``
(که در ``.gitignore`` است) می‌ماند. مقدار اولیه از متغیر محیطی
``RAYAN_OWNER_PASSWORD`` خوانده می‌شود. برای اینکه نصب تازه بدون تنظیم اولیه
قفل نشود، در محیط توسعه (``RAYAN_ENV`` برابر ``prod`` نباشد) اگر متغیری وجود
نداشت، همان گذرواژهٔ درخواستی مالک به‌عنوان مقدار پیش‌فرض ساخته می‌شود و
پنل مدیریت هشدار «گذرواژهٔ پیش‌فرض را عوض کن» نشان می‌دهد.

اگر این فایل از بین برود، با اجرای دوبارهٔ سرور و همان متغیر محیطی بازسازی
می‌شود؛ برای چرخش گذرواژه از ``scripts/set_owner.py`` استفاده کن.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_FILE = os.environ.get("RAYAN_OWNER_FILE") or os.path.join(ROOT, "data", "owner.json")

DEFAULT_NAME = "تایماز جلیلی"
DEV_DEFAULT_PASSWORD = "13911391"
MIN_LENGTH = 8

# نویسه‌هایی که در تایپ فارسی/عربی جابه‌جا می‌شوند
_FOLD = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا"})


def display_name() -> str:
    return (os.environ.get("RAYAN_OWNER_NAME") or DEFAULT_NAME).strip()


def normalize(value: str) -> str:
    """نام کاربری را برای مقایسه یکسان می‌کند: نیم‌فاصله، فاصلهٔ اضافی، ی/ک عربی."""
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    text = text.translate(_FOLD)
    text = " ".join(text.split())
    return text.casefold()


def matches_username(value: str) -> bool:
    candidate = normalize(value)
    if not candidate:
        return False
    names = {normalize(display_name())}
    for extra in (os.environ.get("RAYAN_OWNER_ALIASES") or "").split(","):
        if extra.strip():
            names.add(normalize(extra))
    return any(candidate == name for name in names)


def _hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                          n=2 ** 14, r=8, p=1, dklen=32).hex()


def _is_prod() -> bool:
    return os.environ.get("RAYAN_ENV", "").lower() in ("prod", "production")


def _read() -> dict | None:
    try:
        with open(OWNER_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("pw_hash") and data.get("pw_salt"):
            return data
    except (OSError, ValueError):
        return None
    return None


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(OWNER_FILE) or ".", exist_ok=True)
    tmp = f"{OWNER_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, OWNER_FILE)


def set_password(password: str, *, generated: bool = False) -> dict:
    if len(password or "") < MIN_LENGTH:
        raise ValueError(f"گذرواژهٔ مالک باید حداقل {MIN_LENGTH} نویسه باشد.")
    salt = secrets.token_hex(16)
    data = {
        "name": display_name(),
        "pw_hash": _hash(password, salt),
        "pw_salt": salt,
        "generated": bool(generated),
        "updated_at": time.time(),
    }
    _write(data)
    return {"name": data["name"], "generated": data["generated"]}


def credentials() -> dict | None:
    """اطلاعات مالک را می‌خواند و در صورت نبود، از محیط می‌سازد."""
    data = _read()
    if data:
        return data
    env_password = os.environ.get("RAYAN_OWNER_PASSWORD", "")
    if env_password:
        set_password(env_password)
        return _read()
    if _is_prod():
        # در محیط تولید بدون گذرواژهٔ صریح، حساب مالک ساخته نمی‌شود.
        return None
    set_password(DEV_DEFAULT_PASSWORD, generated=True)
    return _read()


def verify(password: str) -> bool:
    data = credentials()
    if not data:
        return False
    candidate = _hash(password or "", data["pw_salt"])
    return hmac.compare_digest(candidate, data["pw_hash"])


def using_default_password() -> bool:
    """آیا گذرواژهٔ پیش‌فرض توسعه فعال است؟ (برای هشدار در پنل)"""
    data = credentials()
    if not data:
        return False
    salt = data["pw_salt"]
    return hmac.compare_digest(_hash(DEV_DEFAULT_PASSWORD, salt), data["pw_hash"])


def status() -> dict:
    data = credentials()
    return {
        "configured": bool(data),
        "name": (data or {}).get("name") or display_name(),
        "default_password": using_default_password(),
        "updated_at": (data or {}).get("updated_at"),
    }
