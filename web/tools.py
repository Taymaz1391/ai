"""ابزارهای محلی رایان — بدون هیچ API بیرونی.

هر ابزار تابعی است که ورودی JSON می‌گیرد و خروجی JSON می‌دهد؛ مدل یا رابط
کاربری می‌تواند پیش از پاسخ، این ابزارها را صدا بزند. همه‌چیز آفلاین اجرا
می‌شود، از جمله تقویم شمسی که پیاده‌سازی مستقل دارد.
"""
from __future__ import annotations

import ast
import math
import operator
import re
import time
from datetime import datetime, timedelta, timezone

TEHRAN = timezone(timedelta(hours=3, minutes=30))


# ------------------------------------------------------------- تقویم شمسی
def _div(a: int, b: int) -> int:
    return a // b


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + _div(gy2 + 3, 4) - _div(gy2 + 99, 100) + _div(gy2 + 399, 400)
    g_day_no += g_d_m[gm2] + gd2
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np = _div(j_day_no, 12053)
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * _div(j_day_no, 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += _div(j_day_no - 1, 365)
        j_day_no = (j_day_no - 1) % 365
    jm = 1
    for i in range(11):
        if j_day_no < (31 if i < 6 else 30):
            jm = i + 1
            break
        j_day_no -= 31 if i < 6 else 30
    else:
        jm = 12
    jd = j_day_no + 1
    return jy, jm, jd


MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def now_tool(_args: dict | None = None) -> dict:
    moment = datetime.now(TEHRAN)
    jy, jm, jd = gregorian_to_jalali(moment.year, moment.month, moment.day)
    return {
        "ok": True,
        "iso": moment.isoformat(timespec="seconds"),
        "jalali": f"{jy}/{jm:02d}/{jd:02d}",
        "jalali_long": f"{WEEKDAYS[moment.weekday()]} {jd} {MONTHS[jm - 1]} {jy}",
        "weekday": WEEKDAYS[moment.weekday()],
        "time": moment.strftime("%H:%M"),
        "timezone": "ایران (UTC+3:30)",
        "unix": int(time.time()),
    }


# --------------------------------------------------------------- ماشین‌حساب
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
    "log": math.log, "log10": math.log10, "exp": math.exp,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "floor": math.floor, "ceil": math.ceil,
}
CONSTS = {"pi": math.pi, "e": math.e}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in CONSTS:
        return CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_safe_eval(arg) for arg in node.args])
    raise ValueError("عبارت مجاز نیست.")


def calc_tool(args: dict) -> dict:
    expr = normalize_math(str(args.get("expression", ""))).strip()
    if not expr or len(expr) > 200:
        return {"ok": False, "error": "عبارت خالی یا بیش از حد بلند است."}
    if not re.fullmatch(r"[0-9+\-*/%^(). a-zA-Z_]+", expr):
        return {"ok": False, "error": "فقط عدد، عملگر و توابع ساده مجازند."}
    try:
        value = _safe_eval(ast.parse(expr.replace("^", "**"), mode="eval"))
    except Exception as exc:
        return {"ok": False, "error": f"محاسبه نشد: {exc}"}
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return {"ok": False, "error": "نتیجهٔ عددی معتبر نیست."}
    return {"ok": True, "expression": expr, "value": round(value, 10) if isinstance(value, float) else value}


# ----------------------------------------------------------- تبدیل یکاها
UNITS = {
    "length": {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "mile": 1609.344,
               "ft": 0.3048, "inch": 0.0254, "فرسنگ": 6000.0},
    "mass": {"g": 1.0, "kg": 1000.0, "mg": 0.001, "ton": 1_000_000.0, "lb": 453.592,
             "oz": 28.3495, "مثقال": 4.6083},
    "time": {"s": 1.0, "min": 60.0, "h": 3600.0, "day": 86400.0, "week": 604800.0},
    "data": {"byte": 1.0, "kb": 1024.0, "mb": 1024.0 ** 2, "gb": 1024.0 ** 3,
             "tb": 1024.0 ** 4},
}


def convert_tool(args: dict) -> dict:
    try:
        value = float(args.get("value", 0))
        src = str(args.get("from", "")).strip()
        dst = str(args.get("to", "")).strip()
    except (TypeError, ValueError):
        return {"ok": False, "error": "مقدار عددی لازم است."}
    for group in UNITS.values():
        if src in group and dst in group:
            result = value * group[src] / group[dst]
            return {"ok": True, "value": round(result, 6), "from": src, "to": dst}
    if src in ("c", "celsius") and dst in ("f", "fahrenheit"):
        return {"ok": True, "value": round(value * 9 / 5 + 32, 3), "from": "°C", "to": "°F"}
    if src in ("f", "fahrenheit") and dst in ("c", "celsius"):
        return {"ok": True, "value": round((value - 32) * 5 / 9, 3), "from": "°F", "to": "°C"}
    return {"ok": False, "error": "این دو یکا هم‌گروه نیستند."}


# --------------------------------------------------------------- آمار متن
def text_tool(args: dict) -> dict:
    text = str(args.get("text", ""))[:20000]
    words = re.findall(r"[^\s]+", text)
    persian = len(re.findall(r"[آ-ی]", text))
    sentences = [s for s in re.split(r"[.!?؟!\n]+", text) if s.strip()]
    letters = [c for c in text if c.isalpha()]
    return {
        "ok": True,
        "chars": len(text),
        "chars_no_space": len(re.sub(r"\s", "", text)),
        "words": len(words),
        "unique_words": len(set(words)),
        "sentences": len(sentences),
        "persian_ratio": round(persian / max(len(letters), 1), 3),
        "avg_word_len": round(sum(len(w) for w in words) / max(len(words), 1), 2),
        "read_minutes": round(len(words) / 200, 1),
    }


# ------------------------------------------------------------ ابزارها
CATALOG = [
    {"name": "now", "fn": now_tool, "desc": "تاریخ و ساعت ایران (شمسی و میلادی)", "args": {}},
    {"name": "calc", "fn": calc_tool, "desc": "ماشین‌حساب امن", "args": {"expression": "۲+۲"}},
    {"name": "convert", "fn": convert_tool, "desc": "تبدیل یکاها", "args": {"value": 1, "from": "km", "to": "m"}},
    {"name": "text", "fn": text_tool, "desc": "آمار متن فارسی", "args": {"text": "..."}},
]
_INDEX = {item["name"]: item for item in CATALOG}


def catalog() -> list[dict]:
    return [{"name": item["name"], "desc": item["desc"], "example": item["args"]} for item in CATALOG]


def phrase(result: dict) -> str:
    """نتیجهٔ ابزار را به یک جملهٔ فارسیِ آمادهٔ نمایش تبدیل می‌کند."""
    if not result or not result.get("ok"):
        return ""
    fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    tool = result.get("tool")
    if tool == "calc":
        value = result.get("value")
        if isinstance(value, float) and value == int(value):
            value = int(value)
        expr = str(result.get("expression") or "").replace("*", "×").replace("/", "÷")
        line = f"{expr} = **{value}**".translate(fa)
        pair = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([+\-*/×÷])\s*(-?\d+(?:\.\d+)?)", expr.strip())
        check = ""
        if pair and value not in (0, None):
            left, op, right = float(pair.group(1)), pair.group(2), float(pair.group(3))
            if op in ("+",):
                check = f"{left + right:g} − {right:g} = {left:g}"
            elif op in ("-", "−"):
                check = f"{left:g} + {right:g} = {left + right:g}"
            elif op in ("×", "*"):
                check = f"{value:g} ÷ {right:g} = {left:g}"
            elif op in ("÷", "/"):
                check = f"{value:g} × {right:g} = {left:g}"
        return line + ((f"\nبازبینی: {check}".translate(fa)) if check else "")
    if tool == "now":
        parts = [str(result.get(k)) for k in ("weekday", "jalali", "time") if result.get(k)]
        return " — ".join(parts).translate(fa) if parts else ""
    return ""


def run(name: str, args: dict) -> dict:
    if name not in _INDEX:
        return {"ok": False, "error": f"ابزار ناشناخته: {name}"}
    try:
        result = _INDEX[name]["fn"](args or {})
    except Exception as exc:  # pragma: no cover - ورودی بد
        return {"ok": False, "error": str(exc)}
    result["tool"] = name
    return result


_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩×÷−–٫",
    "01234567890123456789*/-.-",
)
_MATH_WORDS = [
    (r"\s*(?:ضربدر|ضرب در|×|✕)\s*", "*"),
    (r"\s*(?:تقسیم بر|تقسیمدر|÷)\s*", "/"),
    (r"\s*(?:به\s*علاوهٔ?|بهعلاوه|بعلاوه|جمع)\s*", "+"),
    (r"\s*(?:منهای|منها|تفریق)\s*", "-"),
    (r"\s*(?:به\s*توان|توان)\s*", "^"),
]


def normalize_math(text: str) -> str:
    """ارقام فارسی/عربی و عملگرهای فارسی را به شکل محاسبه‌پذیر تبدیل می‌کند."""
    t = text.translate(_DIGITS)
    for pattern, repl in _MATH_WORDS:
        t = re.sub(pattern, repl, t)
    return t


_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:٪|%|درصد)\s*(?:از|از مبلغ|از عدد)?\s*(\d+(?:\.\d+)?)")


def detect(text: str) -> dict | None:
    """تشخیص خودکار ابزار از متن کاربر (بدون هزینه و بدون مدل)."""
    raw = text.strip()
    # درصد: «۲۵ ٪ از ۸۰» یا «۲۵ درصد ۸۰»
    pct = _PERCENT.search(raw.translate(_DIGITS))
    if pct:
        part, whole = float(pct.group(1)), float(pct.group(2))
        value = part * whole / 100
        return {"ok": True, "tool": "calc",
                "expression": f"{part:g}% * {whole:g}",
                "value": round(value, 10) if value != int(value) else int(value)}
    t = normalize_math(raw)
    # عبارت ریاضی می‌تواند داخل جمله هم باشد: «۱۲*۳ چند است؟»
    for match in re.finditer(r"[0-9][0-9\s+\-*/%^().]{1,120}", t):
        expr = match.group(0).strip().rstrip(".")
        if not re.search(r"\d\s*[+\-*/^%]\s*\d", expr):
            continue
        out = calc_tool({"expression": expr})
        if out.get("ok"):
            out["tool"] = "calc"
            return out
    asks_time = re.search(r"(ساعت چند|تاریخ امروز|چه روزی|امروز چندم|امروز چندمه)", raw)
    unrelated = re.search(r"کیلومتر|متر|تومان|درصد|٪|مسافت|سرعت|ضرب|تقسیم", raw)
    if asks_time and not unrelated:
        out = now_tool()
        if out.get("ok"):
            out["tool"] = "now"
            return out
    conv = re.search(r"(تبدیل|چند\s*(کیلومتر|متر|مایل|گرم|کیلوگرم|پوند|ساعت|دقیقه))", raw)
    if conv:
        return None
    return None
