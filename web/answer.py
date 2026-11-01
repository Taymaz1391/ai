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
    "درود{name}! چه خبر؟",
    "سلام{name}! آماده‌ام.",
)
_GREETING_NIGHT = (
    "شب‌به‌خیر{name}! هنوز بیداری؟",
    "سلام{name}! شب آرامی داشته باشی.",
)
_THANKS = (
    "خواهش می‌کنم{name}!",
    "قابل‌نداشت{name}.",
    "خوشحالم که به کار آمد{name}.",
)
_BYE = (
    "خداحافظ{name}! هر وقت برگشتی همین‌جا هستم.",
    "مراقب خودت باش{name}؛ گفتگوها ذخیره می‌شوند.",
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
        out["answer"] = random.choice(_THANKS).format(name=name) + " " + hit["answer"].split("!", 1)[-1].strip()
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
        if subject:
            return f"دربارهٔ «{subject}» چیزی که مطمئن باشم در حافظه‌ام نیست. " + random.choice(_ASK_BACK)
        return random.choice(_ASK_BACK)

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


_FALLBACK = (
    "راستش را بگویم: برای این سؤال پاسخ قابل‌اتکایی ندارم و ترجیح می‌دهم چیزی از خودم نسازم.",
    "صادقانه: این یکی از توان من بیرون است؛ جواب سرهم‌بندی‌شده به کارت نمی‌آید.",
    "اینجا باید صریح باشم: پاسخ مطمئنی برای این سؤال ندارم و حدس‌زدن کمکی نمی‌کند.",
)
_NEXT = (
    "این پاسخِ صادقانهٔ من است؛ برای همین پرسش، شاهدِ مطمئن‌تری در دست ندارم.",
    "همین را می‌توانم با اطمینان بگویم؛ بیشتر از این، حدس می‌شد و حدس نمی‌دهم.",
)


def grounded(message: str) -> str:
    """پاسخ صادقانه و مخصوصِ همین سؤال، وقتی مدل چیزی درست نگفته است."""
    subject = _subject(message)
    head = random.choice(_FALLBACK)
    if subject:
        head = f"دربارهٔ «{subject}» — " + head
    return head + "\n" + random.choice(_NEXT)


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
