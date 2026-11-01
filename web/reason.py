"""استدلال ترکیبی رایان — «فکر کردن» با شاهد، دستور و محاسبه.

سه لایه دارد و هر لایه فقط وقتی وارد می‌شود که لایهٔ قبلی پاسخ مطمئن نداده باشد:

۱. **شاهد** (``retrieval.think``) — پاسخ از پیکرهٔ فارسی با ارجاع.
۲. **دستور/محاسبه** — اگر سؤال عددی یا دستوری است، ابزار دقیق جواب می‌دهد.
۳. **مدل** — تولید چندمسیره با امتیازدهی واقعی؛ اگر هنوز پاسخ به سؤال نمی‌خورد،
   صادقانه گفته می‌شود و موضوع‌های نزدیک پیشنهاد می‌شوند.

هیچ متنی از پیش نوشته نشده: پاسخ یا از شاهد ساخته می‌شود، یا از خروجی مدل، یا
صریحاً «نمی‌دانم» است. ردپای هر مرحله برای نمایش در رابط کاربری برگردانده می‌شود.
"""
from __future__ import annotations

import re
import time

from web import retrieval
from web import tools as tools_module

_MATH = re.compile(r"^[\d\s()+\-*/×÷^.%]+$")
_CONVERT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(کیلومتر|متر|سانتی‌متر|میلی‌متر|کیلوگرم|گرم|"
                      r"مایل|فوت|اینچ|هکتار|متر مربع)\s*(?:به|در)\s*(کیلومتر|متر|سانتی‌متر|"
                      r"میلی‌متر|کیلوگرم|گرم|مایل|فوت|اینچ|هکتار|متر مربع)")


def _step(trace: list[dict], name: str, detail: str, started: float) -> None:
    trace.append({"step": name, "detail": detail, "seconds": round(time.time() - started, 3)})


def compute(message: str) -> dict | None:
    """محاسبهٔ دقیق یا تبدیل یکا، اگر سؤال از این جنس باشد."""
    text = (message or "").strip()
    detected = tools_module.detect(text)
    if detected and detected.get("tool") == "calc":
        value = detected.get("value")
        expr = str(detected.get("expression") or "").replace("*", "×").replace("/", "÷")
        expr = expr.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        value = str(value).translate(str.maketrans("0123456789.-", "۰۱۲۳۴۵۶۷۸۹٫−"))
        return {"answer": f"{expr} = {value}", "engine": "calc"}
    match = _CONVERT.search(text)
    if match:
        value, src, dst = match.groups()
        aliases = {"کیلومتر": "km", "متر": "m", "سانتی‌متر": "cm", "میلی‌متر": "mm",
                   "کیلوگرم": "kg", "گرم": "g", "مایل": "mile", "فوت": "ft", "اینچ": "inch"}
        out = tools_module.convert_tool({"value": float(value.replace(",", ".")),
                                         "from": aliases.get(src, src),
                                         "to": aliases.get(dst, dst)})
        if out.get("ok"):
            number = f"{out['value']:,.4f}".rstrip("0").rstrip(".").replace(",", "٬")
            number = number.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")).replace(".", "٫")
            return {"answer": f"{value} {src} برابر است با {number} {dst}", "engine": "convert"}
    return None


def _near_subjects(question: str, limit: int = 3) -> list[str]:
    """موضوع‌های نزدیک از ایندکس، برای وقتی که شاهدی برای خودِ سؤال نیست."""
    try:
        hits = retrieval.search(question, limit=limit * 3, path=None)
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for hit in hits:
        title = (hit.title or "").strip()
        if title and title not in out and len(out) < limit:
            out.append(title[:70])
    return out


def answer(message: str, engine=None, history=None, mode: str = "chat",
           want_deep: bool = False) -> dict:
    """مسیر کامل پاسخ: شاهد → ابزار → مدل → صداقت. همیشه با ردپا."""
    started = time.time()
    trace: list[dict] = []
    message = (message or "").strip()

    # ۱) شاهد از پیکره
    if mode == "chat" and retrieval.looks_factual(message) and retrieval.index_exists():
        evidence = retrieval.think(message)
        trace.extend(evidence.get("trace") or [])
        if evidence.get("answer"):
            return {"answer": evidence["answer"], "sources": evidence.get("sources") or [],
                    "engine": "think", "trace": trace,
                    "confidence": evidence.get("confidence", 0.0),
                    "thought": {"steps": trace, "confidence": evidence.get("confidence")}}
        _step(trace, "شاهد", "شاهد کافی پیدا نشد", started)

    # ۲) ابزار دقیق
    computed = compute(message)
    if computed:
        _step(trace, "محاسبه", "با ابزار دقیق", started)
        return {"answer": computed["answer"], "sources": [], "engine": computed["engine"],
                "trace": trace, "confidence": 0.99,
                "thought": {"steps": trace, "confidence": 0.99}}

    # ۳) مدل
    if engine is None:
        return {"answer": None, "sources": [], "engine": "none", "trace": trace,
                "confidence": 0.0, "thought": None}

    if want_deep:
        from rayan.thinking import deep_reply
        text, generation, deep_trace = deep_reply(engine, message, mode=mode, history=history)
        candidates = (deep_trace or {}).get("candidates") or []
        _step(trace, "مدل", f"{len(candidates)} مسیر موازی · امتیازدهی", started)
        thought = {"steps": trace, "candidates": candidates,
                   "confidence": (candidates[deep_trace["chosen"] - 1]["confidence"]
                                  if candidates and deep_trace else None)}
        return {"answer": text, "sources": [], "engine": "deep", "trace": trace,
                "confidence": (thought["confidence"] or 0.0), "thought": thought}

    text, generation, prompt = engine.reply(message, mode=mode, history=history)
    _step(trace, "مدل", f"{len(generation.tokens)} توکن تولید شد", started)
    return {"answer": text, "sources": [], "engine": "chat", "trace": trace,
            "confidence": generation.confidence,
            "thought": {"steps": trace, "confidence": generation.confidence},
            "generation": generation, "prompt": prompt}


def honest(message: str, near: list[str] | None = None) -> str:
    """وقتی شاهدی نیست و مدل هم پاسخ مربوطی نساخت: صریح، اما بی‌دست‌خالی.

    چیزی ساخته نمی‌شود؛ فقط جمله‌های واقعیِ نزدیک از پیکره نقل می‌شوند تا کاربر
    ببیند چه چیزی در دسترس است.
    """
    subject = " ".join(retrieval.subject_phrase(message)) or "این سؤال"
    head = ("برای «" + subject + "» شاهد مطمئنی در پیکرهٔ فارسی‌ام پیدا نکردم و "
            "ترجیح می‌دهم چیزی از خودم نسازم.")
    try:
        found = retrieval.evidence(message, limit=3)
    except Exception:  # noqa: BLE001 - نقل شاهد نباید پاسخ را بشکند
        found = []
    if found:
        lines = [f"• «{item['text'].strip()}» — {item['title']}" for item in found]
        head += "\n\nاما این جمله‌ها در پیکره به آن اشاره دارند:\n" + "\n".join(lines)
    if near:
        items = "، ".join(f"«{item}»" for item in near[:3])
        head += ("\n\nنزدیک‌ترین موضوع‌هایی که در پیکره دارم: " + items +
                 ". اگر یکی از آن‌ها را می‌خواهی، همان را بپرس.")
    head += ("\n\nمی‌توانی دکمهٔ «وب» را روشن کنی تا از منابع زنده با لینک جواب بدهم، "
             "یا سؤال را جزئی‌تر بپرسی.")
    return head
