"""حالت شبکهٔ ملی: سایت بدون اینترنت بین‌المللی هم کامل کار می‌کند.

هیچ دارایی صفحه (فونت، تصویر، CSS، JS) از بیرون نمی‌آید؛ تنها چیزی که به بیرون
نگاه می‌کند «جست‌وجوی وب» و «یادگیری آنلاین» است. در قطعیِ بین‌المللی این دو
خودبه‌خود بی‌فایده‌اند و فقط وقت کاربر را می‌گیرند. این ماژول یک کلید واحد
می‌دهد:

* ``RAYAN_NETWORK=national`` — همیشه خروج به اینترنت را می‌بندد.
* ``RAYAN_NETWORK=auto`` (پیش‌فرض) — اولین شکست شبکه، حالت ملی را برای چند
  دقیقه فعال می‌کند و دوباره امتحان می‌کند؛ عدد جادویی و ادعای بی‌سنجه ندارد.
* ``RAYAN_NETWORK=global`` — همیشه باز (برای سرورهای خارج از ایران).

    from web import network
    if network.allow_outbound(): ...
    network.report_failure("timeout")   # خودکار به حالت ملی می‌رود
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = Path(os.environ.get("RAYAN_NETWORK_STATE", ROOT / "data" / "network.json"))
MODE = (os.environ.get("RAYAN_NETWORK") or "auto").strip().lower()
COOLDOWN = float(os.environ.get("RAYAN_NETWORK_COOLDOWN", "180"))

_state = {"mode": MODE, "offline_until": 0.0, "failures": 0, "last_error": "",
          "last_success": 0.0}


def _load() -> None:
    """حالتی که مدیر از پنل انتخاب کرده بعد از ری‌استارت هم می‌ماند."""
    if (os.environ.get("RAYAN_NETWORK") or "").strip():
        return
    try:
        saved = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    value = str(saved.get("mode", "")).strip().lower()
    if value in ("auto", "national", "global"):
        _state["mode"] = value


def _save() -> None:
    try:
        target = Path(STATE_FILE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"mode": _state["mode"], "at": time.time()}),
                          encoding="utf-8")
    except OSError:
        pass


_load()


def mode() -> str:
    return _state["mode"]


def allow_outbound() -> bool:
    """آیا الان اجازهٔ تماس با اینترنت بین‌المللی داریم؟"""
    if _state["mode"] in ("national", "offline", "local"):
        return False
    if _state["mode"] == "global":
        return True
    return time.time() >= _state["offline_until"]


def report_failure(reason: str = "") -> None:
    """شکست شبکه را ثبت می‌کند و در حالت auto مدتی خروج را می‌بندد."""
    _state["failures"] += 1
    _state["last_error"] = (reason or "")[:160]
    if _state["mode"] == "auto":
        _state["offline_until"] = time.time() + COOLDOWN


def report_success() -> None:
    _state["last_success"] = time.time()
    if _state["mode"] == "auto":
        _state["offline_until"] = 0.0


def set_mode(value: str) -> str:
    value = (value or "").strip().lower()
    if value not in ("auto", "national", "global"):
        raise ValueError("حالت شبکه باید auto، national یا global باشد")
    _state["mode"] = value
    _state["offline_until"] = 0.0
    _state["last_error"] = ""
    _save()
    return value


def stats() -> dict:
    now = time.time()
    return {
        "mode": _state["mode"],
        "allow_outbound": allow_outbound(),
        "blocked_for_s": max(0, round(_state["offline_until"] - now, 1)),
        "failures": _state["failures"],
        "last_success_s": (round(now - _state["last_success"]) if _state["last_success"] else None),
        "last_error": _state["last_error"],
        "assets_local": True,
        "note": "همهٔ فونت‌ها، تصاویر و اسکریپت‌ها از همین سرور می‌آیند؛ "
                "در حالت ملی فقط جست‌وجو و یادگیری وب خاموش است.",
    }
