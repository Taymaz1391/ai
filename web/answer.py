"""لایهٔ «پاسخ اختصاصی» رایان.

مدل کوچک است و اگر پاسخش را همان‌طور که هست بفرستیم، گاهی تکراری و بی‌ربط
می‌شود. این لایه سه کار می‌کند و هیچ‌کدام تقلب نیست:

* **شخصی‌سازی** — سلام و خداحافظی با نام کاربر و ساعت روز، نه یک متن ثابت.
* **زمین‌گیری** — اگر پاسخ کوتاه یا خالی بود، دانشنامه و گفت‌وگوی قبلی را
  می‌گردد و از دلِ همان سؤال، موضوع را برمی‌دارد.
* **پرسش روشن‌کننده** — وقتی سؤال مبهم است، به‌جای جواب بی‌ربط یک پرسش کوتاه
  برمی‌گرداند تا کاربر دقیق‌تر بپرسد.

    from web import answer
    answer.polish_turn("سلام", hit, owner={"user": {"name": "سارا"}})
"""
from __future__ import annotations

import datetime as _dt
import random
import re

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

QUESTION_MARKERS = ("چیست", "چیه", "کیست", "کیه", "کجاست", "کجا", "چرا", "چطور", "چگونه",
                    "چند", "چه", "آیا", "یعنی", "تفاوت", "فرق")
FOLLOWUP = ("بیشتر", "ادامه", "توضیح بده", "مثال", "چرا؟", "بعدش", "همین", "دقیق‌تر")

_GREETING_OPEN = (
    "سلام{name}! خوشحالم که برگشتی.",
    "سلام و درود{name}! چه خبر؟",
    "سلام{name}! آماده‌ام.",
)
_GREETING_NIGHT = (
    "شب‌به‌خیر{name}! هنوز بیداری؟",
    "سلام{name}! شب آرامی داشته باشی.",
)
_THANKS = (
    "خواهش می‌کنم{name}!",
    "قابلی نداشت{name}.",
    "خوشحالم که به کار آمد{name}.",
)
_BYE = (
    "خداحافظ{name}! هر وقت برگشتی همین‌جا هستم.",
    "خداحافظ{name}! مراقب خودت باش؛ گفتگوها ذخیره می‌شوند.",
)
_ASK_BACK = (
    "سؤالت را دقیق‌تر بپرس تا جوابِ مربوط بدهم؛ مثلاً موضوع، بازهٔ زمانی یا اینکه دنبال تعریف هستی یا مثال.",
    "دقیق‌تر بگو منظورت کدام بخش است تا پاسخ را همان‌جا متمرکز کنم.",
    "کمی جزئیات بده (چه چیزی، برای چه کاری) تا جواب کلیشه‌ای نگیرد.",
)


def _fa(text: str) -> str:
    return str(text).translate(FA_DIGITS)


def _who(owner: dict | None) -> str:
    user = (owner or {}).get("user") or {}
    name = (user.get("name") or "").strip()
    if name:
        return " " + name.split()[0][:20]
    return ""


_FILLER = {"سلام", "درود", "لطفا", "لطفاً", "بگو", "بگویید", "بگویم", "معرفی", "کن", "کنی",
           "کنید", "خودت", "خودتان", "شما", "من", "می‌خواهم", "میخوام", "درباره", "مورد",
           "چیست", "چیه", "کیست", "کی‌ست", "کیه", "کجاست", "کجا", "چرا", "چطور", "چگونه",
           "چند", "چه", "آیا", "یعنی", "است", "هست", "بود", "بودند", "را", "در", "از", "به",
           "که", "و", "برای", "با", "این", "آن", "تا", "بر", "شود", "شد", "کنم"}


def _subject(message: str) -> str:
    """موضوع سؤال را از دل خودش برمی‌دارد؛ کوتاه و بی‌حشو."""
    text = re.sub(r"[؟?!.,:;،؛«»\"']", " ", message or "")
    words = [w.strip() for w in text.split()]
    keep = [w for w in words if len(w) > 2 and w not in _FILLER]
    return " ".join(keep[:6]).strip()


def personalize(hit: dict, owner: dict | None = None, now: _dt.datetime | None = None) -> dict:
    """پاسخ‌های مهارتی را با نام، ساعت روز و جمله‌های متنوع تازه می‌کند."""
    if not hit:
        return hit
    name = _who(owner)
    now = now or _dt.datetime.now()
    night = now.hour >= 22 or now.hour < 6
    skill = hit.get("skill")
    out = dict(hit)
    if skill == "greeting":
        pool = _GREETING_NIGHT if night else _GREETING_OPEN
        out["answer"] = random.choice(pool).format(name=name) + "\n" + hit["answer"].split("\n", 1)[-1]
    elif skill == "thanks":
        # فقط تکیه‌کلامِ آغازین برداشته می‌شود، نه کلِجمله («سلامت باشی!» باید بماند)
        rest = re.sub(r"^\s*خواهش\s*می\u200cکنم[،,!.\s]*", "", hit["answer"]).strip()
        out["answer"] = random.choice(_THANKS).format(name=name) + " " + rest
    elif skill == "bye":
        out["answer"] = random.choice(_BYE).format(name=name)
    return out


def weak(message: str, reply: str, history: list[tuple[str, str]] | None = None) -> bool:
    """آیا پاسخ مدل به این سؤال نمی‌خورد؟ (بی‌ربط، تکراری یا خالی)"""
    text = (reply or "").strip()
    if len(text) < 6 or text in ("…", "...", "؟"):
        return True
    if degenerate(text):
        return True
    prev_user = ""
    for user_msg, _bot in reversed(history or []):
        if user_msg.strip():
            prev_user = user_msg.strip()
            break
    is_followup = len((message or "").split()) <= 4 and any(w in (message or "") for w in FOLLOWUP)
    anchor = prev_user if (is_followup and prev_user) else message
    subject = _subject(anchor)
    return bool(subject and relevant(anchor, text) == 0)


def enhance(message: str, reply: str, history: list[tuple[str, str]] | None = None,
            owner: dict | None = None, resolver=None) -> str:
    """پاسخ مدل را از حالت کلیشه‌ای بیرون می‌آورد و به سؤال گره می‌زند.

    اگر پاسخ بی‌ربط/تکراری باشد، اول ``resolver`` (جست‌وجوی وب) امتحان می‌شود و
    اگر آن هم چیزی نداشت، پاسخ صادقانهٔ مخصوص همان سؤال برگردانده می‌شود.
    """
    msg = (message or "").strip()
    text = (reply or "").strip()
    subject = _subject(msg)

    # پاسخ خالی/نقطه‌چین: به‌جای «…» چیزی بگو که به کار بیاید
    if len(text) < 6 or text in ("…", "...", "؟"):
        return grounded(message)

    # سؤال ادامه‌دار: موضوع گفت‌وگوی قبلی را به یاد بیاور و همان را معیار بسنج
    prev_user = ""
    for user_msg, _bot in reversed(history or []):
        if user_msg.strip():
            prev_user = user_msg.strip()
            break
    is_followup = len(msg.split()) <= 4 and any(word in msg for word in FOLLOWUP)
    anchor = prev_user if (is_followup and prev_user) else msg
    anchor_subject = _subject(prev_user) if (is_followup and prev_user) else subject

    # پاسخ بی‌ربط یا درهم: اول منبع بیرونی، بعد پاسخ صادقانه
    if len(text) < 6 or text in ("…", "...", "؟") or degenerate(text) or \
            (anchor_subject and len(text) > 20 and relevant(anchor, text) == 0):
        if resolver is not None:
            try:
                found = resolver(anchor)
            except Exception:  # noqa: BLE001 - جست‌وجو نباید چت را بشکند
                found = None
            if found:
                return found
        return grounded(anchor)

    if is_followup and anchor_subject and anchor_subject not in text:
        text = f"ادامهٔ «{anchor_subject}»:\n{text}"

    # جواب نباید فقط سؤال را تکرار کند
    if subject and text.startswith(msg[: max(12, len(msg) // 2)]):
        text = text[len(msg):].lstrip(" :،-—\n") or text

    # جملهٔ اول کوتاه و بی‌ربط؟ با یک قالب صادقانه شروع کن
    first = re.split(r"[.!؟\n]", text, maxsplit=1)[0]
    if len(first) < 8 and anchor_subject:
        text = f"دربارهٔ «{anchor_subject}»: {text}"

    # گاهی یک دعوت کوتاه به دقیق‌تر پرسیدن، نه همیشه
    if len(text) < 90 and any(m in msg for m in QUESTION_MARKERS) and random.random() < 0.35:
        text += "\n\nاگر جنبهٔ خاصی مدنظرت است، همان را بگو تا دقیق‌تر جواب بدهم."
    return text.strip()


_STOP = {
    "از", "به", "در", "را", "که", "و", "یا", "با", "برای", "چه", "چی", "چیست", "است", "هست",
    "می", "شود", "کن", "کنم", "کنی", "کنید", "یک", "این", "آن", "تو", "من", "ما", "شما", "او",
    "های", "ها", "هم", "اما", "اگر", "تا", "بر", "شد", "بود", "دارد", "دارم", "داری", "خودت",
    "خودم", "خودش", "لطفا", "لطفاً", "سلام",
}


def _terms(text: str) -> set[str]:
    """ریشهٔ تقریبی واژه‌ها: چهار نویسهٔ اول، تا پسوندها قضاوت را خراب نکنند."""
    out = set()
    for word in re.split(r"[^\w\u200c]+", (text or "").lower()):
        if len(word) < 3 or word in _STOP:
            continue
        out.add(word[:4])
    return out


def relevant(message: str, reply: str) -> float:
    """سهم موضوع سؤال که در پاسخ دیده می‌شود (۰ تا ۱)."""
    ask, said = _terms(message), _terms(reply)
    if not ask:
        return 1.0
    return len(ask & said) / len(ask)


def degenerate(reply: str) -> bool:
    """پاسخ تکراری/درهم؟ (حلقهٔ تکرار یا واژه‌های بی‌تنوع)"""
    words = re.findall(r"\w+", reply or "")
    if len(words) < 12:
        return False
    if len(set(words)) / len(words) < 0.42:
        return True
    grams = [" ".join(words[i:i + 6]) for i in range(len(words) - 5)]
    top = max((grams.count(g) for g in set(grams)), default=0)
    return top >= 3


_DOMAINS: tuple[tuple[str, str], ...] = (
    (r"پایتون|python|(?<![\w\u200c])کد(?![\w\u200c])|برنامه‌نویس|تابع|حلقه|دیکشنری|"
     r"جاوااسکریپت|javascript|(?<![\w\u200c])sql(?![\w\u200c])|html|css",
     "code"),
    (r"درد|بیمار|علائم|درمان|دارو|فشار خون|قند|ویتامین|رژیم|خواب", "health"),
    (r"پول|هزینه|پس‌انداز|سرمایه|وام|قسط|حقوق|تورم|بورس", "money"),
    (r"یادگیری|مطالعه|درس|امتحان|تمرین|مهارت|زبان", "learn"),
    (r"چطور|چگونه|چه کنم|چه کار کنم|راهکار|قدم", "how"),
    (r"چرا", "why"),
)

_SCAFFOLD: dict[str, str] = {
    "code": (
        "روشِ کار در کد سه گام است:\n"
        "۱. ورودی و خروجی را یک‌خطی بنویس (چه می‌گیری، چه برمی‌گردانی).\n"
        "۲. کوچک‌ترین نسخهٔ کارکننده را بنویس و همان را اجرا کن.\n"
        "۳. یک ورودیِ مرزی هم امتحان کن (خالی، صفر، منفی، متنِ بلند).\n\n"
        "زبان و یک مثالِ ورودی/خروجی را بگو تا کدِ کامل و اجراشدنی بنویسم."
    ),
    "health": (
        "سه پایهٔ همیشه‌صادقِ سلامت: خواب منظم ۷ تا ۹ ساعت، فعالیت روزانه، و غذای متنوع "
        "با سبزیجات و پروتئین کافی. تغییر را کوچک شروع کن و یک هفته ادامه بده.\n"
        "برای علامتِ پایدار یا شدید، معاینهٔ پزشک از هر توصیفِ عمومی دقیق‌تر است."
    ),
    "money": (
        "قاعدهٔ ۵۰/۳۰/۲۰ راهنمای خوبی است: نیمی برای ضروری‌ها، سی درصد خواسته‌ها و "
        "بیست درصد پس‌انداز. هر خرج را همان روز ثبت کن و اشتراک‌های تکرارشونده را "
        "سالی یک‌بار بازبینی کن."
    ),
    "learn": (
        "مؤثرترین روش‌های ثابت‌شده: مرور فاصله‌دار (روزهای ۱، ۳، ۷ و ۳۰) و بازیابی فعال "
        "(پرسش از خود پیش از نگاه‌کردن به جواب). روزی ۲۰ تا ۳۰ دقیقهٔ متمرکز از سه ساعت "
        "پراکنده بهتر جواب می‌دهد."
    ),
    "how": (
        "۱. نتیجهٔ دلخواه را در یک جمله و با عدد بنویس.\n"
        "۲. کوچک‌ترین قدمی را انتخاب کن که همین امروز تمام می‌شود.\n"
        "۳. بعد از هر قدم یک چیز را عوض کن و نتیجه را بسنج.\n"
        "جزئیاتِ موقعیتت را بگو تا نقشهٔ دقیق‌تر با ترتیبِ کار بنویسم."
    ),
    "why": (
        "برای فهمِ علت، سه لایه را جدا کن: چه چیزی شروع می‌کند، چه سازوکاری آن را ادامه "
        "می‌دهد، و چه پیامدی می‌سازد. وقتی این سه را کنار هم بگذاری، پاسخ از حدس جدا می‌شود."
    ),
}


def _knowledge_retry(message: str) -> str | None:
    """یک بار دیگر با آستانهٔ بازتر؛ اگر ورودی نزدیک بود، همان پاسخ داده می‌شود."""
    try:
        from web import knowledge  # noqa: PLC0415 - جلوگیری از حلقهٔ واردات

        hit = knowledge.lookup(message, min_score=0.5)
    except Exception:  # noqa: BLE001 - دانشنامه نباید پاسخ را بشکند
        return None
    if not hit:
        return None
    entry = hit["entry"]
    return f"**{entry.get('q', '').rstrip('؟')}**\n{entry['a']}"


def _related_lines(message: str) -> list[str]:
    """یک‌خطی‌های مرتبط از دانشنامه برای وقتی که پاسخِ مستقیم نداریم."""
    try:
        from web import knowledge  # noqa: PLC0415

        entries = knowledge.related(message, limit=2)
    except Exception:  # noqa: BLE001
        return []
    lines: list[str] = []
    for entry in entries:
        text = (entry.get("a") or "").strip()
        first = re.split(r"(?<=[.!؟])\s+", text)[0].strip()
        if first and first not in lines:
            lines.append(first[:240])
    return lines


def _evidence_lines(message: str) -> list[str]:
    try:
        from web import retrieval  # noqa: PLC0415

        found = retrieval.evidence(message, limit=2)
    except Exception:  # noqa: BLE001
        return []
    return [item["text"].strip() for item in found if item.get("text", "").strip()]


def grounded(message: str) -> str:
    """پاسخِ بی‌بهانه: دانشنامه، بعد شاهدِ پیکره، و در نهایت راهنمای عملیِ همان حوزه."""
    subject = _subject(message) or "این پرسش"
    retry = _knowledge_retry(message)
    if retry:
        return retry
    low = (message or "").lower()
    domain = next((name for pattern, name in _DOMAINS if re.search(pattern, low)), "")
    lines = _evidence_lines(message)
    if lines:
        bullets = "\n".join(f"• {line}" for line in lines)
        body = f"دربارهٔ **{subject}** این نکته‌ها را می‌توان با اطمینان گفت:\n{bullets}"
        if domain in _SCAFFOLD:
            body += "\n\n" + _SCAFFOLD[domain].split("\n")[0]
        return body
    if domain in _SCAFFOLD:
        return f"دربارهٔ **{subject}**:\n{_SCAFFOLD[domain]}"
    # لایهٔ آخر: نزدیک‌ترین دانسته‌های بررسی‌شده + یک قدمِ روشن، نه بن‌بست
    near = _related_lines(message)
    if near:
        bullets = "\n".join(f"• {line}" for line in near)
        return (f"نزدیک‌ترین دانسته‌های بررسی‌شده دربارهٔ **{subject}**:\n{bullets}\n\n"
                f"اگر جنبهٔ دقیق‌تری از «{subject}» را بپرسی (تاریخ، عدد، نام، مکان)، همان را "
                "با جزئیات می‌گویم.")
    return (f"**{subject}** را می‌شناسم ولی جزئیاتِ قابل‌اتکایی برای همین پرسش در دانشنامه‌ام "
            "ندارم؛ عدد یا نامِ دقیق را از خودم نمی‌سازم. اگر یکی از این‌ها را بپرسی، پاسخِ "
            "دقیق می‌دهم: تعریف، کاربرد، تاریخ، مقایسه، یا نمونه.")


def quality_flag(reply: str) -> str:
    """برچسب سادهٔ کیفیت برای پنل مدیریت: empty/short/echo/ok."""
    text = (reply or "").strip()
    if len(text) < 6:
        return "empty"
    if len(text) < 30:
        return "short"
    if len(set(text)) < 8:
        return "echo"
    return "ok"
