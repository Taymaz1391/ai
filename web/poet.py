"""بیت‌سازِ رایان — شعرِ تازه از واژه‌های فارسی، بدون نقلِ بیتِ شاعران.

چرا این ماژول؟ مدلِ کوچکِ ما در تولیدِ شعر به هم می‌ریزد و پاسخِ بی‌معنی می‌دهد؛
در عوض می‌توان با قاعده‌های روشنِ فارسی شعر ساخت: هر مصراع از دو نیم‌مصراعِ
هم‌هجا ساخته می‌شود، مصراع‌ها هم‌قافیه‌اند و وزنِ هجایی ثابت است. نتیجه «شعرِ
رایان» است، نه شعری از حافظ یا فردوسی؛ همین را هم صریح می‌نویسیم.

    from web import poet
    poet.compose("دریا")     # {'title': ..., 'verses': [...], 'note': ...}
"""
from __future__ import annotations

import hashlib
import re

__all__ = ["compose", "wants_poem"]

# ─────────────────────────────────────────── واژه‌های هم‌قافیه (آخرِ مصراع)
# هر گروه: واژه‌هایی که با یک آوای پایانی تمام می‌شوند و می‌توانند قافیه بسازند.
# ───────────────────────────────────── تصویرهای هم‌خوان با هر موضوع
# قافیه از میانِ همین تصویرها انتخاب می‌شود تا بیت بی‌ربط نشود.
_IMAGES: dict[str, tuple[str, ...]] = {
    "دریا": ("دریا", "موج", "ساحل", "کف", "ماه", "ستاره", "باد", "آواز"),
    "شب": ("شب", "ماه", "ستاره", "سکوت", "خواب", "سپیده", "آواز"),
    "بهار": ("بهار", "شکوفه", "نسیم", "باران", "باغ", "آواز", "سبزه"),
    "پاییز": ("پاییز", "برگ", "باد", "باران", "کوچه", "خاطره"),
    "زمستان": ("برف", "سرما", "سکوت", "شب", "آتش", "خاطره"),
    "عشق": ("دل", "جان", "لبخند", "آرزو", "شور", "آواز", "نگاه"),
    "دوستی": ("دل", "مهر", "آغوش", "لبخند", "خاطره", "آواز"),
    "مادر": ("مادر", "مهر", "آغوش", "دل", "خاطره", "لبخند"),
    "وطن": ("وطن", "خاک", "دل", "خاطره", "آواز"),
    "تنهایی": ("تنهایی", "سکوت", "شب", "خاطره", "دل"),
    "امید": ("امید", "فردا", "سپیده", "روشنی", "آرزو", "دل"),
    "زندگی": ("زندگی", "راه", "دل", "آرزو", "خاطره", "آواز"),
}
_GENERIC_IMAGES = ("شب", "ماه", "ستاره", "باد", "باران", "نور", "آواز", "راز",
                   "خاطره", "دل", "جان", "لبخند", "آرزو", "سکوت", "سپیده",
                   "نسیم", "باغ", "چراغ", "نگاه", "ترانه")

# ─────────────────────────────────────── نیم‌مصراع‌ها؛ {q} جای قافیه است
# هر قالب یک نیم‌مصراعِ کامل است؛ با کنارِ هم گذاشتنِ دو قالبِ سازگار، بیت ساخته
# می‌شود. شمارِ هجاها نزدیک نگه داشته شده تا وزنِ هجایی نلنگد.
_OPENERS: tuple[str, ...] = (
    "در {topic} ای دوست، چه بسیار",
    "امشب که {topic} در دلِ من",
    "با {topic} سخن گفتم به آواز",
    "از {topic} پرسیدم این راز",
    "در سایهٔ {topic} نشستم",
    "چون {topic} گذشت از کنارم",
    "به یادِ {topic} می‌خوانم",
    "اگر {topic} مرا خواند",
    "میانِ {topic} و دل",
    "ز {topic} مانده در جانم",
    "دلم با {topic} می‌گوید",
    "سحرگاهان که {topic} بیدار",
    "تو را در {topic} می‌بینم",
    "در آغوشِ {topic} آرام",
    "حدیثِ {topic} می‌گویم",
    "چو {topic} بگذرد از من",
)

_CLOSERS: tuple[str, ...] = (
    "همیشه در دلم {q}",
    "شبی روشن چو {q}",
    "بمان در خاطرِ من {q}",
    "نشانم داد راهِ {q}",
    "سخن گفتم ز {q}",
    "چه شیرین است {q}",
    "دلم در بندِ {q}",
    "فراموشم نشد {q}",
    "دلم را برد {q}",
    "حکایت شد ز {q}",
    "در این وادیِ {q}",
    "مرا مهمانِ {q}",
    "بمان ای خوبِ {q}",
    "شدم همراهِ {q}",
    "نوشتم نامِ {q}",
    "به یادِ {q}",
)

_KINDS = {
    "عشق": ("عاشقانه", ("دل", "عشق", "آرزو", "لبخند", "شور")),
    "دوستی": ("دوستانه", ("دل", "دوستی", "مهر", "آغوش")),
    "دریا": ("دریایی", ("دریا", "موج", "ساحل", "کف")),
    "شب": ("شبانه", ("شب", "ماه", "ستاره", "سکوت")),
    "بهار": ("بهاری", ("بهار", "شکوفه", "نسیم", "سبزه")),
    "پاییز": ("پاییزی", ("پاییز", "برگ", "باد", "کوچه")),
    "زمستان": ("زمستانی", ("برف", "سردی", "سکوت", "شب")),
    "دوست": ("دوستانه", ("دل", "دوستی", "مهر")),
    "مادر": ("مادرانه", ("مادر", "آغوش", "مهر")),
    "وطن": ("وطنانه", ("وطن", "خاک", "نامه")),
    "تنهایی": ("تنهاانه", ("تنهایی", "خاک", "شب")),
    "امید": ("امیدوارانه", ("امید", "فردا", "روشنی")),
    "زندگی": ("از زندگی", ("زندگی", "راه", "دل")),
}

_TOPIC_RE = re.compile(
    r"(?:دربارهٔ?|درباره|از|برای|در بارهٔ?|راجع به)\s+(?P<t>[^،.!؟?]{2,30})")
_ASK_RE = re.compile(
    r"(?:شعر|بیت|غزل|دوبیتی|رباعی|چهارپاره|سرود)\S*|"
    r"(?:شعر|بیت|غزل|دوبیتی|رباعی)\s+\S+")


def wants_poem(text: str) -> bool:
    """آیا کاربر شعر می‌خواهد؟ (نه اینکه دربارهٔ شعر بپرسد)"""
    raw = (text or "").strip()
    if not raw or len(raw) > 200:
        return False
    if re.search(r"شعر\s*(چیست|چیه|چی بود)|تاریخچهٔ شعر|وزنِ شعر|شاعر\s+کیست", raw):
        return False
    asks = re.search(r"(?:یک|یه|چند|دو|سه|چهار)?\s*(?:شعر|بیت|غزل|دوبیتی|رباعی|سرود)\S*\s*"
                     r"(?:بگو|بسرا|بخوان|بنویس|بساز|دربارهٔ?|از|برای|در بارهٔ?|برام|برایم)?", raw)
    if not asks:
        return False
    return bool(re.search(r"بگو|بسرا|بخوان|بنویس|بساز|دربارهٔ?|برام|برایم|^شعر|^بیت", raw))


_REQUEST = re.compile(
    r"(?:یک|یه|دو|سه|چند)?\s*(?:شعر|بیت|غزل|دوبیتی|رباعی|چهارپاره|ترانه|سرود)\S*")
_VERB = re.compile(r"\b(?:بگو|بگویم|بسرا|بسرای|بخوان|بنویس|بساز|بفرست|برام|برایم|"
                   r"لطفاً|لطفا|کوتاه|زیبا|قشنگ|تازه|خوب)\b")
_STOP_TOPIC = {"درباره", "دربارهٔ", "بارهٔ", "راجع", "به", "از", "برای", "در", "و",
               "را", "که", "می", "یک", "یه", "شعر", "بیت", "غزل", "دوبیتی", "رباعی"}


def _clean_topic(raw: str) -> str:
    text = re.sub(r"[\u200c]", " ", raw or "")
    text = text.replace("ي", "ی").replace("ک", "ک")
    text = _REQUEST.sub(" ", text)
    text = _VERB.sub(" ", text)
    # «مادرم»، «دلم»، «شهرم» → بی‌پسوندِ مالکیت
    words = []
    for token in re.split(r"[\s،,.!؟?:؛]+", text):
        token = token.strip("«»\"'()")
        if not token or token in _STOP_TOPIC:
            continue
        token = re.sub(r"(?:ام|ات|اش|مان|تان|شان|م|ت|ش)$", "", token) if len(token) > 3 else token
        if token and token not in _STOP_TOPIC:
            words.append(token)
    return " ".join(words[:2]).strip()


def _topic(text: str) -> str:
    """موضوعِ شعر را از دلِ درخواست بیرون می‌کشد."""
    raw = (text or "").strip()
    for marker in ("دربارهٔ", "درباره", "در بارهٔ", "راجع به", "برای", "از"):
        if marker in raw:
            after = raw.split(marker, 1)[1]
            topic = _clean_topic(after)
            if topic:
                return topic
    topic = _clean_topic(_REQUEST.sub(" ", raw))
    if not topic or len(topic) > 24:
        return "دل"
    return topic


def _seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _syllables(text: str) -> int:
    """شمارشِ تقریبیِ هجا با شمارِ مصوت‌های فارسی."""
    vowels = "اآایئوءه‌َُِْ" + "ouei"
    return sum(1 for ch in text if ch in vowels)


def compose(text: str, verses: int = 2) -> dict | None:
    """بیتِ تازه می‌سازد: هم‌قافیه، هم‌وزن (تقریبی) و بی‌نقلِ قول از شاعری."""
    if not wants_poem(text):
        return None
    topic = _topic(text)
    if re.search(r"کوتاه|یک\s*بیت", text):
        verses = 1
    elif re.search(r"دو\s*بیت|سه\s*بیت", text):
        verses = 2
    seed = _seed(topic)
    tone, _hints = _KINDS.get(topic, ("", ()))
    pool = _IMAGES.get(topic, ()) + _GENERIC_IMAGES

    def rhyme_of(word: str) -> str:
        """آوای پایانی: دو حرفِ آخر پس از حذفِ «ها»/«ی»."""
        clean = re.sub(r"[\u200c\s]", " ", word).strip()
        for tail in ("ها", "ی", "ان", "ام"):
            if clean.endswith(tail) and len(clean) > len(tail) + 1:
                clean = clean[: -len(tail)]
                break
        return clean[-2:]

    groups: dict[str, list[str]] = {}
    for word in dict.fromkeys(pool):
        groups.setdefault(rhyme_of(word), []).append(word)
    pairs = [words for words in groups.values() if len(words) >= 2]
    pairs.sort(key=lambda words: (len(words) < 2, abs(len(words[0]) - 4)))
    if not pairs:
        pairs = [["دل", "گل"]]
    out: list[str] = []
    used: set[str] = set()
    for i in range(max(1, min(verses, 3))):
        opener = _OPENERS[(seed + i * 5) % len(_OPENERS)].format(topic=topic)
        group = pairs[(seed + i) % len(pairs)]
        q1 = group[(seed + i) % len(group)]
        q2 = group[(seed + i + 1) % len(group)]
        if q2 == q1:
            q2 = group[(seed + i + 2) % len(group)]
        if q2 in used:
            q2 = next((w for w in group if w not in used and w != q1), q2)
        used.update({q1, q2})
        closer1 = _CLOSERS[(seed + i * 7) % len(_CLOSERS)].format(q=q1)
        closer2 = _CLOSERS[(seed + i * 7 + 4) % len(_CLOSERS)].format(q=q2)
        # وزنِ ساده: مصراعِ اول از دو نیم‌مصراعِ کوتاه‌تر ساخته می‌شود
        out.append(f"{opener}،\n{closer1}.")
        out.append(f"{_OPENERS[(seed + i * 5 + 3) % len(_OPENERS)].format(topic=topic)}،\n{closer2}.")
    title = f"بیتی تازه دربارهٔ {topic}"
    if tone:
        title = f"بیتی {tone} دربارهٔ {topic}"
    return {
        "title": title,
        "topic": topic,
        "verses": out,
        "note": "این بیت را رایان با قاعده‌های قافیه و وزن ساخته است؛ نقلِ قول از "
                "شاعری نیست. برای بیتِ کلاسیکِ شاعران، نامِ شاعر و اثر را بپرس.",
    }


def render(result: dict) -> str:
    """متنِ آمادهٔ نمایش برای پاسخِ چت."""
    body = "\n\n".join(result["verses"])
    return f"**{result['title']}**\n\n{body}\n\n*{result['note']}*"
