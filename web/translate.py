"""ترجمهٔ فارسی ↔ انگلیسی با واژه‌نامهٔ قطعی، الگوی جمله و صداقت در ناشناخته‌ها.

این ماژول ادعای مترجمِ عمومی ندارد؛ کاری می‌کند که واقعاً از دستش برمی‌آید:

* جمله‌های کوتاهِ روزمره را با **الگوی ساختاری** ترجمه می‌کند
  («کتاب روی میز است» → «The book is on the table.»)
* واژه‌های پرکاربرد را از واژه‌نامه پیدا می‌کند (با نقش دستوری و مثال)
* اگر بخشی از جمله را نشناسد، همان را صریح علامت می‌زند؛ ترجمهٔ ساختگی نمی‌سازد

نقطهٔ ورود::

    from web import translate
    out = translate.answer("«کتاب روی میز است» را به انگلیسی ترجمه کن")
"""
from __future__ import annotations

import re

__all__ = ["answer", "direction", "translate", "gloss", "lookup"]

_KNOWN = "?"
_MARKS = re.compile("[\u064b-\u065f\u0670\u06d6-\u06ed]")   # اعراب و همزه‌های ترکیبی
_FA_CHARS = re.compile(r"[\u0600-\u06FF]")


# ═══════════════════════════════════════════════════════ ۱) واژه‌نامه
# ساختار: فارسی → (انگلیسی، نقش واژه)
_FA_EN: dict[str, tuple[str, str]] = {
    # نام‌ها
    "کتاب": ("book", "noun"), "کتاب‌ها": ("books", "noun"), "میز": ("table", "noun"),
    "خانه": ("house", "noun"), "اتاق": ("room", "noun"), "در": ("door", "noun"),
    "پنجره": ("window", "noun"), "ماشین": ("car", "noun"), "دوچرخه": ("bicycle", "noun"),
    "شهر": ("city", "noun"), "روستا": ("village", "noun"), "کشور": ("country", "noun"),
    "مدرسه": ("school", "noun"), "دانشگاه": ("university", "noun"),
    "دانشجو": ("student", "noun"), "معلم": ("teacher", "noun"), "دوست": ("friend", "noun"),
    "خانواده": ("family", "noun"), "مادر": ("mother", "noun"), "پدر": ("father", "noun"),
    "برادر": ("brother", "noun"), "خواهر": ("sister", "noun"), "فرزند": ("child", "noun"),
    "کودک": ("child", "noun"), "آب": ("water", "noun"), "نان": ("bread", "noun"),
    "چای": ("tea", "noun"), "قهوه": ("coffee", "noun"), "شیر": ("milk", "noun"),
    "سیب": ("apple", "noun"), "غذا": ("food", "noun"), "هوا": ("weather", "noun"),
    "باران": ("rain", "noun"), "برف": ("snow", "noun"), "خورشید": ("sun", "noun"),
    "ماه": ("moon", "noun"), "ستاره": ("star", "noun"), "آسمان": ("sky", "noun"),
    "زمین": ("earth", "noun"), "دریا": ("sea", "noun"), "کوه": ("mountain", "noun"),
    "درخت": ("tree", "noun"), "گل": ("flower", "noun"), "پرنده": ("bird", "noun"),
    "سگ": ("dog", "noun"), "گربه": ("cat", "noun"), "اسب": ("horse", "noun"),
    "کار": ("work", "noun"), "زمان": ("time", "noun"), "روز": ("day", "noun"),
    "شب": ("night", "noun"), "صبح": ("morning", "noun"), "هفته": ("week", "noun"),
    "سال": ("year", "noun"), "دلار": ("dollar", "noun"), "پول": ("money", "noun"),
    "کامپیوتر": ("computer", "noun"), "گوشی": ("phone", "noun"),
    "برنامه": ("program", "noun"), "زبان": ("language", "noun"), "درس": ("lesson", "noun"),
    "سؤال": ("question", "noun"), "پاسخ": ("answer", "noun"), "کلمه": ("word", "noun"),
    "جمله": ("sentence", "noun"), "متن": ("text", "noun"), "داستان": ("story", "noun"),
    "شعر": ("poem", "noun"), "آهنگ": ("song", "noun"), "فیلم": ("film", "noun"),
    "کفش": ("shoes", "noun"), "لباس": ("clothes", "noun"), "صندلی": ("chair", "noun"),
    "تخت": ("bed", "noun"), "قلم": ("pen", "noun"), "دفتر": ("notebook", "noun"),
    "کاغذ": ("paper", "noun"), "دست": ("hand", "noun"), "سر": ("head", "noun"),
    "چشم": ("eye", "noun"), "قلب": ("heart", "noun"), "دل": ("heart", "noun"),
    "ذهن": ("mind", "noun"), "فکر": ("thought", "noun"), "دوستان": ("friends", "noun"),
    # صفت‌های پرکاربرد
    "warm": ("گرم", "adj"), "hot": ("داغ", "adj"), "cold": ("سرد", "adj"),
    "fast": ("سریع", "adj"), "slow": ("کند", "adj"), "strong": ("قوی", "adj"),
    "weak": ("ضعیف", "adj"), "happy": ("خوشحال", "adj"), "sad": ("غمگین", "adj"),
    "big": ("بزرگ", "adj"), "small": ("کوچک", "adj"), "new": ("نو", "adj"),
    "old": ("کهنه", "adj"), "good": ("خوب", "adj"), "bad": ("بد", "adj"),
    "easy": ("آسان", "adj"), "hard": ("سخت", "adj"), "clean": ("تمیز", "adj"),
    "long": ("دراز", "adj"), "short": ("کوتاه", "adj"), "beautiful": ("زیبا", "adj"),
    # مفاهیم (پرسش‌های «معنی … چیست»)
    "امید": ("hope", "noun"), "عشق": ("love", "noun"), "دوستی": ("friendship", "noun"),
    "آزادی": ("freedom", "noun"), "صلح": ("peace", "noun"), "جنگ": ("war", "noun"),
    "زندگی": ("life", "noun"), "مرگ": ("death", "noun"), "شادی": ("joy", "noun"),
    "غم": ("sadness", "noun"), "ترس": ("fear", "noun"), "دانش": ("knowledge", "noun"),
    "علم": ("science", "noun"), "هنر": ("art", "noun"), "موسیقی": ("music", "noun"),
    "ورزش": ("sport", "noun"), "سلامتی": ("health", "noun"), "بیماری": ("disease", "noun"),
    "درد": ("pain", "noun"), "درمان": ("treatment", "noun"), "دولت": ("government", "noun"),
    "قانون": ("law", "noun"), "حق": ("right", "noun"), "وظیفه": ("duty", "noun"),
    "مسئولیت": ("responsibility", "noun"), "اعتماد": ("trust", "noun"),
    "احترام": ("respect", "noun"), "صبر": ("patience", "noun"), "حقیقت": ("truth", "noun"),
    "دروغ": ("lie", "noun"), "خطر": ("danger", "noun"), "امنیت": ("security", "noun"),
    "پیشرفت": ("progress", "noun"), "موفقیت": ("success", "noun"),
    "شکست": ("failure", "noun"), "تلاش": ("effort", "noun"), "هدف": ("goal", "noun"),
    "آینده": ("future", "noun"), "گذشته": ("past", "noun"), "حال": ("present", "noun"),
    "طبیعت": ("nature", "noun"), "محیط": ("environment", "noun"), "انرژی": ("energy", "noun"),
    "برق": ("electricity", "noun"), "آتش": ("fire", "noun"), "خاک": ("soil", "noun"),
    "سنگ": ("stone", "noun"), "فلز": ("metal", "noun"), "طلا": ("gold", "noun"),
    "نقره": ("silver", "noun"), "آهن": ("iron", "noun"), "چوب": ("wood", "noun"),
    "شیشه": ("glass", "noun"), "ساعت": ("clock", "noun"), "بازار": ("market", "noun"),
    "غذا‌خوری": ("restaurant", "noun"), "بیمارستان": ("hospital", "noun"),
    "کتابخانه": ("library", "noun"), "خیابان": ("street", "noun"), "پل": ("bridge", "noun"),
    "پارک": ("park", "noun"), "باغ": ("garden", "noun"), "ساحل": ("beach", "noun"),
    "فرودگاه": ("airport", "noun"), "قطار": ("train", "noun"), "هواپیما": ("plane", "noun"),
    "ورزشگاه": ("stadium", "noun"), "مسجد": ("mosque", "noun"), "دفتر": ("office", "noun"),
    # قید
    "امروز": ("today", "adv"), "دیروز": ("yesterday", "adv"), "فردا": ("tomorrow", "adv"),
    "الان": ("now", "adv"), "همیشه": ("always", "adv"), "هرگز": ("never", "adv"),
    "خیلی": ("very", "adv"), "کمی": ("a little", "adv"), "دوباره": ("again", "adv"),
    "اینجا": ("here", "adv"), "آنجا": ("there", "adv"), "زود": ("early", "adv"),
    "دیر": ("late", "adv"), "سریع": ("fast", "adv"), "آرام": ("slowly", "adv"),
    # صفت
    "خوب": ("good", "adj"), "بد": ("bad", "adj"), "بزرگ": ("big", "adj"),
    "کوچک": ("small", "adj"), "زیبا": ("beautiful", "adj"), "گرم": ("hot", "adj"),
    "سرد": ("cold", "adj"), "جدید": ("new", "adj"), "قدیمی": ("old", "adj"),
    "آهسته": ("slow", "adj"), "آسان": ("easy", "adj"), "سخت": ("hard", "adj"),
    "خوشحال": ("happy", "adj"), "خسته": ("tired", "adj"), "گرسنه": ("hungry", "adj"),
    "تشنه": ("thirsty", "adj"), "قرمز": ("red", "adj"), "آبی": ("blue", "adj"),
    "سبز": ("green", "adj"), "زرد": ("yellow", "adj"), "سیاه": ("black", "adj"),
    "سفید": ("white", "adj"), "شجاع": ("brave", "adj"), "دلیر": ("brave", "adj"),
    "مهربان": ("kind", "adj"), "قوی": ("strong", "adj"), "ضعیف": ("weak", "adj"),
    "ثروتمند": ("rich", "adj"), "فقیر": ("poor", "adj"), "جوان": ("young", "adj"),
    "پیر": ("old", "adj"), "بلند": ("tall", "adj"), "کوتاه": ("short", "adj"),
    "نزدیک": ("near", "adj"), "دور": ("far", "adj"), "تمیز": ("clean", "adj"),
    "کثیف": ("dirty", "adj"), "ساکت": ("quiet", "adj"), "شاد": ("happy", "adj"),
    "ناراحت": ("sad", "adj"), "مهم": ("important", "adj"),
    "خطرناک": ("dangerous", "adj"), "آزاد": ("free", "adj"), "مشغول": ("busy", "adj"),
    "پر": ("full", "adj"), "خالی": ("empty", "adj"), "باز": ("open", "adj"),
    "بسته": ("closed", "adj"), "شیرین": ("sweet", "adj"), "تلخ": ("bitter", "adj"),
    # شهرها و کشورها
    "تهران": ("Tehran", "noun"), "شیراز": ("Shiraz", "noun"), "اصفهان": ("Isfahan", "noun"),
    "مشهد": ("Mashhad", "noun"), "تبریز": ("Tabriz", "noun"), "یزد": ("Yazd", "noun"),
    "کرمان": ("Kerman", "noun"), "رشت": ("Rasht", "noun"), "اهواز": ("Ahvaz", "noun"),
    "قزوین": ("Qazvin", "noun"), "بوشهر": ("Bushehr", "noun"), "کرج": ("Karaj", "noun"),
    "لندن": ("London", "noun"), "پاریس": ("Paris", "noun"), "برلین": ("Berlin", "noun"),
    "رم": ("Rome", "noun"), "توکیو": ("Tokyo", "noun"), "مسکو": ("Moscow", "noun"),
    "استانبول": ("Istanbul", "noun"), "دوبی": ("Dubai", "noun"), "دبی": ("Dubai", "noun"),
    "ایران": ("Iran", "noun"), "فرانسه": ("France", "noun"), "آلمان": ("Germany", "noun"),
    "ژاپن": ("Japan", "noun"), "روسیه": ("Russia", "noun"), "ترکیه": ("Turkey", "noun"),
    "مدرسه": ("school", "noun"), "دانشگاه": ("university", "noun"), "بیمارستان": ("hospital", "noun"),
    "پزشک": ("doctor", "noun"), "دکتر": ("doctor", "noun"), "معلم": ("teacher", "noun"),
    "مهندس": ("engineer", "noun"), "دانشجو": ("student", "noun"), "نویسنده": ("writer", "noun"),
    "صادق": ("honest", "adj"), "راستگو": ("honest", "adj"), "درستکار": ("honest", "adj"),
    "صبور": ("patient", "adj"), "کنجکاو": ("curious", "adj"), "باهوش": ("smart", "adj"),
    "سخت‌کوش": ("hardworking", "adj"), "خوش‌بین": ("optimistic", "adj"),
    "منظم": ("organized", "adj"), "خلاق": ("creative", "adj"), "بخشنده": ("generous", "adj"),
    # عبارت‌ها
    "سلام": ("hello", "phrase"), "خداحافظ": ("goodbye", "phrase"),
    "ممنون": ("thank you", "phrase"), "مرسی": ("thanks", "phrase"),
    "بله": ("yes", "phrase"), "خیر": ("no", "phrase"), "نه": ("no", "phrase"),
    "لطفاً": ("please", "phrase"), "ببخشید": ("excuse me", "phrase"),
    "صبح بخیر": ("good morning", "phrase"), "شب بخیر": ("good night", "phrase"),
    "عصر بخیر": ("good afternoon", "phrase"), "خوش آمدید": ("welcome", "phrase"),
    "چطوری": ("how are you", "phrase"), "حال شما چطور است": ("how are you", "phrase"),
    "اسم من": ("my name is", "phrase"),
    # ضمیر
    "من": ("I", "pron"), "تو": ("you", "pron"), "شما": ("you", "pron"),
    "او": ("he/she", "pron"), "ما": ("we", "pron"), "آن‌ها": ("they", "pron"),
    "آنها": ("they", "pron"), "این": ("this", "pron"), "آن": ("that", "pron"),
    # حرف اضافه
    "روی": ("on", "prep"), "زیر": ("under", "prep"), "کنار": ("next to", "prep"),
    "با": ("with", "prep"), "برای": ("for", "prep"), "از": ("from", "prep"),
    "به": ("to", "prep"),
}

_EN_FA: dict[str, tuple[str, str]] = {}
for _fa, (_en, _kind) in _FA_EN.items():
    for _alt in _en.split("/"):
        _EN_FA.setdefault(_alt.strip().lower(), (_fa, _kind))

# عبارت‌های ثابتِ روزمره: واژه‌به‌واژه معنا را خراب می‌کند
_PHRASES: dict[str, str] = {
    "صبح بخیر": "good morning", "شب بخیر": "good night", "عصر بخیر": "good afternoon",
    "روز بخیر": "good day", "خسته نباشید": "well done", "خسته نباشی": "well done",
    "دستت درد نکنه": "thank you", "لطفاً": "please", "لطفا": "please",
    "ببخشید": "excuse me", "متأسفم": "I am sorry", "متاسفم": "I am sorry",
    "تولدت مبارک": "happy birthday", "سال نو مبارک": "happy new year",
    "good morning": "صبح بخیر", "good night": "شب بخیر", "good afternoon": "عصر بخیر",
    "happy birthday": "تولدت مبارک", "thank you": "ممنون", "please": "لطفاً",
}

_COMMON_EN_EXTRA = {
    "hello": "سلام", "hi": "سلام", "goodbye": "خداحافظ", "bye": "خداحافظ",
    "thanks": "ممنون", "thank you": "ممنون", "please": "لطفاً", "yes": "بله",
    "no": "نه", "good morning": "صبح بخیر", "good night": "شب بخیر", "ok": "باشه",
    "good afternoon": "عصر بخیر", "how are you": "حال شما چطور است",
    "water": "آب", "book": "کتاب", "table": "میز", "house": "خانه", "home": "خانه",
    "friend": "دوست", "love": "عشق", "peace": "صلح", "car": "ماشین", "city": "شهر",
    "school": "مدرسه", "teacher": "معلم", "student": "دانشجو", "tea": "چای",
    "bread": "نان", "milk": "شیر", "apple": "سیب", "food": "غذا", "sun": "خورشید",
    "moon": "ماه", "star": "ستاره", "sky": "آسمان", "tree": "درخت", "flower": "گل",
    "bird": "پرنده", "dog": "سگ", "cat": "گربه", "money": "پول", "time": "زمان",
    "day": "روز", "night": "شب", "morning": "صبح", "year": "سال", "work": "کار",
    "language": "زبان", "question": "سؤال", "answer": "پاسخ", "word": "کلمه",
    "story": "داستان", "friend ": "دوست",
}
_EN_FA.update({k: (v, "phrase") for k, v in _COMMON_EN_EXTRA.items() if k not in _EN_FA})


# ═══════════════════════════════════════════════════════ ۲) نرمال‌سازی
def _norm(text: str) -> str:
    """یکسان‌سازی نویسه‌ها: نیم‌فاصله، ی/ک عربی، اعراب و فاصله‌های تکراری."""
    text = (text or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    text = _MARKS.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" .!؟?،؛:")


def _dictionary() -> dict[str, str]:
    table: dict[str, str] = {}
    for fa, (en, _kind) in _FA_EN.items():
        first = en.split("/")[0].strip()
        if first and first != _KNOWN:
            table[_norm(fa)] = first
    return table


def _en_of(word: str, table: dict[str, str]) -> str:
    """معادل انگلیسیِ یک واژه یا عبارتِ چندواژه‌ای."""
    key = _norm(word)
    if not key:
        return _KNOWN
    if key in table:
        return table[key]
    # کسرهٔ اضافه چسبیده به واژه: «هوای» → «هوا»
    if len(key) > 2 and key.endswith("ی") and key[:-1] in table:
        return table[key[:-1]]
    # چندواژه‌ای: اگر همهٔ جزءها شناخته باشند
    parts = [part for part in key.split(" ") if part]
    if len(parts) > 1:
        rendered = []
        for part in parts:
            if part in table:
                rendered.append(table[part])
            elif len(part) > 2 and part.endswith("ی") and part[:-1] in table:
                rendered.append(table[part[:-1]])
            else:
                rendered = []
                break
        if rendered:
            return " ".join(rendered)
    return _KNOWN


def _fa_of(word: str) -> str | None:
    """معادل فارسیِ یک واژهٔ انگلیسی (با تحمل s/es/ing)."""
    key = (word or "").strip().lower().strip(".,!?;:\"'")
    if not key:
        return None
    if key in _EN_FA:
        return _EN_FA[key][0]
    for suffix, cut in (("s", 1), ("es", 2), ("ies", 3), ("ed", 2), ("ing", 3)):
        if key.endswith(suffix) and len(key) > len(suffix) + 2:
            base = key[:-cut] + ("y" if suffix == "ies" else "")
            if base in _EN_FA:
                return _EN_FA[base][0]
    return None


# ═══════════════════════════════════════════════════════ ۳) الگوهای جمله
_TIME_ADV = {"امروز", "دیروز", "فردا", "الان", "همیشه", "هرگز"}
_SUBJ_EN = {"من": "I", "تو": "you", "شما": "you", "او": "he", "ما": "we",
            "آن": "it", "آن‌ها": "they", "آنها": "they"}
_POSS = {"من": "my", "تو": "your", "شما": "your", "او": "his", "ما": "our",
         "آن‌ها": "their", "آنها": "their", "آن": "its"}

_CAP = r"[\w\u200c ]+"


def _adj_sentence(match: re.Match, table: dict[str, str]) -> str:
    """«کتاب خیلی خوب است» → «The book is very good.» و
    «هوای امروز سرد است» → «The weather today is cold.» (جای قید درست)."""
    subject = _en_of(match["a"], table)
    parts = _norm(match["adj"]).split(" ")
    if parts and parts[0] in _TIME_ADV:
        subject = f"{subject} {_en_of(parts[0], table)}"
        parts = parts[1:]
    adjective = " ".join(_en_of(part, table) for part in parts)
    return f"The {subject} is {adjective}."


def _poss_sentence(match: re.Match, table: dict[str, str]) -> str:
    """«خانهٔ من بزرگ است» → «My house is big.»"""
    owner = _POSS.get(_norm(match["p"]), "")
    subject = _en_of(match["a"], table)
    adjective = " ".join(_en_of(part, table) for part in _norm(match["adj"]).split(" "))
    return f"{owner.capitalize()} {subject} is {adjective}."


_HAVE = {"دارم": "I", "داری": "you", "دارد": "he", "داریم": "we", "دارید": "you",
         "دارند": "they"}


def _have_sentence(match: re.Match, table: dict[str, str]) -> str:
    """«(من) کتاب دارم» → «I have book.»"""
    subject = _SUBJ_EN.get(_norm(match["p"]), "") if match["p"] else ""
    subject = subject or _HAVE.get(match["v"], "I")
    verb = "has" if subject in ("he", "she", "it") else "have"
    return f"{subject.capitalize()} {verb} {_en_of(match['a'], table)}."


def _like_sentence(match: re.Match, table: dict[str, str]) -> str:
    """«(من) چای را دوست دارم» → «I like tea.»"""
    subject = _SUBJ_EN.get(_norm(match["subj"]) if match["subj"] else "من", "I")
    verb = "likes" if subject in ("he", "it") else "like"
    return f"{subject.capitalize()} {verb} {_en_of(match['a'], table)}."


# کلیدها بدونِ نیم‌فاصله‌اند تا با متنِ نرمال‌شده هم‌خوان باشند
_GO_VERBS = {"رفتم": ("I", "went"), "رفتی": ("you", "went"), "رفت": ("he", "went"),
             "رفتیم": ("we", "went"), "رفتید": ("you", "went"), "رفتند": ("they", "went"),
             "میروم": ("I", "go"), "میروی": ("you", "go"), "میرود": ("he", "goes"),
             "میرویم": ("we", "go"), "میروید": ("you", "go"), "میروند": ("they", "go")}
_TIME_EN = {"فردا": "tomorrow", "امروز": "today", "دیروز": "yesterday", "امشب": "tonight",
            "هفتهٔ بعد": "next week", "این هفته": "this week"}
_GO_TAIL = {"فردا": "will go", "دیروز": "went", "هفتهٔ بعد": "will go"}
_FREQ_EN = {"هر روز": "every day", "هر هفته": "every week", "هر ماه": "every month",
            "همیشه": "always"}


def _go_sentence(match: re.Match, table: dict[str, str]) -> str:
    """«من فردا به تهران می‌روم» → «I will go to Tehran tomorrow.»"""
    key = "".join(_norm(match["v"]).split())
    subj, verb = _GO_VERBS.get(key, ("I", "go"))
    if match["s"]:
        subj = _SUBJ_EN.get(_norm(match["s"]), subj)
    time = _norm(match["t"]).replace(" ", "\u200c") if match["t"] else ""
    freq = " ".join(_norm(match["f"]).split()) if match["f"] else ""
    verb = _GO_TAIL.get(time, verb)
    place = _en_of(match["place"], table)
    sentence = f"{subj} {verb} to {place}"
    if time:
        sentence += f" {_TIME_EN.get(time, '')}".rstrip()
    if freq:
        sentence += f" {_FREQ_EN.get(freq, 'every day')}"
    return (sentence[:1].upper() + sentence[1:]).replace("i ", "I ") + "."


_PREPS_FA = {"روی": "on", "زیر": "under", "در": "in", "کنار": "next to"}

_FA_PATTERNS = [
    # من [فردا] به X می‌روم  →  I will go to X tomorrow
    (re.compile(rf"^(?:(?P<s>من|تو|او|ما|شما|آن‌ها|آنها)\s+)?"
                r"(?:(?P<t>فردا|امروز|دیروز|امشب|هفتهٔ بعد|این هفته)\s+)?"
                r"(?:(?P<f>هر\s*روز|هر\s*هفته|هر\s*ماه|همیشه)\s+)?"
                rf"به\s+(?P<place>{_CAP}?)\s+"
                r"(?P<v>می\s*روم|می\s*روی|می\s*رود|می\s*رویم|می\s*روید|می\s*روند|"
                r"رفتم|رفتی|رفت|رفتیم|رفتید|رفتند)\.?$"),
     lambda m, t: _go_sentence(m, t)),
    # X [حرف اضافه] Y است  →  The X is on the Y
    (re.compile(rf"^(?P<a>{_CAP}?)\s+(?P<prep>روی|زیر|در|کنار)\s+(?P<b>{_CAP}?)\s+"
                r"(?:است|هست)\.?$"),
     lambda m, t: f"The {_en_of(m['a'], t)} is {_PREPS_FA[m['prep']]} the {_en_of(m['b'], t)}."),
    # من X هستم  →  I am X
    (re.compile(rf"^من\s+(?P<a>{_CAP}?)\s+(?:هستم|ام)\.?$"),
     lambda m, t: f"I am {_en_of(m['a'], t)}."),
    # این (یک) X است  →  This is a X
    (re.compile(rf"^این\s+(?:یک\s+)?(?P<a>{_CAP}?)\s+(?:است|هست)\.?$"),
     lambda m, t: f"This is a {_en_of(m['a'], t)}."),
    # X من صفت است  →  My X is adjective
    (re.compile(rf"^(?P<a>{_CAP}?)\s+(?P<p>من|تو|شما|او|ما|آن‌ها|آنها)\s+"
                rf"(?P<adj>{_CAP}?)\s+(?:است|هست)\.?$"),
     lambda m, t: _poss_sentence(m, t)),
    # (من) X را دوست دارم  →  I like X
    (re.compile(rf"^(?:(?P<subj>من|تو|او|ما|شما|آن‌ها|آنها)\s+)?(?P<a>{_CAP}?)\s+را\s+"
                r"دوست\s+(?:دارم|داری|دارد|داریم|دارید|دارند)\.?$"),
     lambda m, t: _like_sentence(m, t)),
    # (من) X دارم  →  I have X
    (re.compile(rf"^(?:(?P<p>من|تو|او|ما|شما|آن‌ها|آنها)\s+)?(?P<a>{_CAP}?)\s+"
                r"(?P<v>دارم|داری|دارد|داریم|دارید|دارند)\.?$"),
     lambda m, t: _have_sentence(m, t)),
    # X [قید] صفت است  →  The X is [adverb] adjective
    (re.compile(rf"^(?P<a>{_CAP}?)\s+(?P<adj>{_CAP}?)\s+(?:است|هست)\.?$"),
     lambda m, t: _adj_sentence(m, t)),
]

# فعل‌های پرکاربرد انگلیسی: شش صیغهٔ فارسی برای ترتیبِ درستِ جمله
_EN_VERBS: dict[str, tuple[str, ...]] = {
    "like": ("دوست دارم", "دوست داری", "دوست دارد", "دوست داریم", "دوست دارید", "دوست دارند"),
    "love": ("دوست دارم", "دوست داری", "دوست دارد", "دوست داریم", "دوست دارید", "دوست دارند"),
    "want": ("می‌خواهم", "می‌خواهی", "می‌خواهد", "می‌خواهیم", "می‌خواهید", "می‌خواهند"),
    "need": ("لازم دارم", "لازم داری", "لازم دارد", "لازم داریم", "لازم دارید", "لازم دارند"),
    "eat": ("می‌خورم", "می‌خوری", "می‌خورد", "می‌خوریم", "می‌خورید", "می‌خورند"),
    "drink": ("می‌نوشم", "می‌نوشی", "می‌نوشد", "می‌نوشیم", "می‌نوشید", "می‌نوشند"),
    "see": ("می‌بینم", "می‌بینی", "می‌بیند", "می‌بینیم", "می‌بینید", "می‌بینند"),
    "know": ("می‌دانم", "می‌دانی", "می‌داند", "می‌دانیم", "می‌دانید", "می‌دانند"),
    "read": ("می‌خوانم", "می‌خوانی", "می‌خواند", "می‌خوانیم", "می‌خوانید", "می‌خوانند"),
    "write": ("می‌نویسم", "می‌نویسی", "می‌نویسد", "می‌نویسیم", "می‌نویسید", "می‌نویسند"),
    "speak": ("حرف می‌زنم", "حرف می‌زنی", "حرف می‌زند", "حرف می‌زنیم", "حرف می‌زنید",
              "حرف می‌زنند"),
    "have": ("دارم", "داری", "دارد", "داریم", "دارید", "دارند"),
    "play": ("بازی می‌کنم", "بازی می‌کنی", "بازی می‌کند", "بازی می‌کنیم", "بازی می‌کنید",
             "بازی می‌کنند"),
}
_EN_SUBJ = {"i": 0, "you": 1, "he": 2, "she": 2, "it": 2, "we": 3, "they": 5}

_EN_PREPS_FA = {"on": "روی", "in": "در", "under": "زیر", "next to": "کنار"}


def _en_pattern(source: str) -> dict | None:
    """جمله‌های سادهٔ انگلیسی را با ترتیبِ درستِ فارسی می‌نویسد."""
    low = source.strip()
    match = re.match(r"^the\s+(?P<a>[\w ]+?)\s+is\s+(?P<prep>on|in|under|next to)\s+"
                     r"the\s+(?P<b>[\w ]+?)[.!]?$", low, re.I)
    if match:
        first = _fa_of(match["a"])
        second = _fa_of(match["b"])
        if first and second:
            return {"text": f"{first} {_EN_PREPS_FA[match['prep'].lower()]} {second} است",
                    "unknown": [], "complete": True}
    match = re.match(r"^this\s+is\s+a\s+(?P<a>[\w ]+?)[.!]?$", low, re.I)
    if match:
        word = _fa_of(match["a"])
        if word:
            return {"text": f"این {word} است", "unknown": [], "complete": True}
    match = re.match(r"^i\s+am\s+(?P<a>[\w ]+?)[.!]?$", low, re.I)
    if match:
        word = _fa_of(match["a"])
        if word:
            return {"text": f"من {word} هستم", "unknown": [], "complete": True}
    # She is a doctor  →  او یک پزشک است
    match = re.match(r"^(?P<s>i|you|he|she|it|we|they)\s+(?:am|is|are)\s+"
                     r"(?:a|an|the)?\s*(?P<n>[\w ]+?)[.!]?$", low, re.I)
    if match:
        noun = _fa_of(match["n"])
        plural = bool(match["n"].lower().endswith("s")) and not match["n"].lower().endswith("ss")
        if noun:
            subject = {"i": "من", "you": "تو", "he": "او", "she": "او", "it": "آن",
                       "we": "ما", "they": "آن‌ها"}[match["s"].strip().lower()]
            if plural:
                verb = {"من": "هستم", "تو": "هستی", "شما": "هستید", "او": "هستند",
                        "ما": "هستیم", "آن": "هستند"}.get(subject, "هستند")
                return {"text": f"{subject} {noun}ها {verb}", "unknown": [], "complete": True}
            copula = {"من": "هستم", "تو": "هستی", "شما": "هستید", "ما": "هستیم"}.get(subject, "است")
            return {"text": f"{subject} یک {noun} {copula}", "unknown": [], "complete": True}

    # I have a book  →  من یک کتاب دارم
    match = re.match(r"^(?P<s>i|you|he|she|we|they)\s+(?:have|has)\s+"
                     r"(?:a|an|the)?\s*(?P<o>[\w ]+?)[.!]?$", low, re.I)
    if match:
        subject = {"i": "من", "you": "تو", "he": "او", "she": "او", "we": "ما",
                   "they": "آن‌ها"}[match["s"].strip().lower()]
        verb = {"من": "دارم", "تو": "داری", "او": "دارد", "ما": "داریم", "آن‌ها": "دارند"}[subject]
        obj = _fa_of(match["o"])
        if obj:
            return {"text": f"{subject} یک {obj} {verb}", "unknown": [], "complete": True}

    # We go to school  →  ما به مدرسه می‌رویم
    match = re.match(r"^(?P<s>i|you|he|she|we|they)\s+go(?:es)?\s+to\s+"
                     r"(?P<p>[\w ]+?)[.!]?$", low, re.I)
    if match:
        subject = {"i": "من", "you": "تو", "he": "او", "she": "او", "we": "ما",
                   "they": "آن‌ها"}[match["s"].strip().lower()]
        verb = {"من": "می‌روم", "تو": "می‌روی", "او": "می‌رود", "ما": "می‌رویم",
                "آن‌ها": "می‌روند"}[subject]
        place = _fa_of(match["p"])
        if place:
            return {"text": f"{subject} به {place} {verb}", "unknown": [], "complete": True}

    match = re.match(r"^(?P<s>i|you|he|she|it|we|they)\s+(?P<v>[\w]+)\s+"
                     r"(?P<o>[\w ]+?)[.!]?$", low, re.I)
    if match:
        verb = match["v"].strip().lower()
        if verb not in _EN_VERBS:
            for suffix, cut in (("es", 2), ("s", 1)):
                if verb.endswith(suffix) and verb[:-cut] in _EN_VERBS:
                    verb = verb[:-cut]
                    break
        forms = _EN_VERBS.get(verb)
        obj = _fa_of(match["o"])
        if forms and obj:
            person = _EN_SUBJ.get(match["s"].strip().lower(), 0)
            prefix = "من " if person == 0 else ""
            return {"text": f"{prefix}{obj} را {forms[person]}", "unknown": [],
                    "complete": True}
    return None


# ═══════════════════════════════════════════════════════ ۴) ترجمه
def _phrase(text: str, to: str) -> dict | None:
    """عبارتِ ثابتِ شناخته‌شده را کامل ترجمه می‌کند، نه واژه‌به‌واژه."""
    key = " ".join((text or "").strip().strip(".!؟?").split()).lower()
    target = _PHRASES.get(key)
    if target:
        return {"text": target, "unknown": [], "complete": True}
    return None


def translate(text: str, to: str = "en") -> dict:
    """ترجمهٔ متنی کوتاه؛ خروجی شامل متن، واژه‌های ناشناخته و کامل‌بودن است."""
    source = _norm(text)
    if not source:
        return {"text": "", "unknown": [], "complete": False}
    fixed = _phrase(source, to)
    if fixed:
        return fixed
    if to == "fa":
        patterned = _en_pattern(source)
        if patterned:
            return patterned
        low = source.lower().strip(" .!?")
        if low in _EN_FA:                       # عبارتِ کامل، نه واژه‌به‌واژه
            return {"text": _EN_FA[low][0], "unknown": [], "complete": True}
        words = source.split(" ")
        out: list[str] = []
        unknown: list[str] = []
        for word in words:
            key = word.lower().strip(".,!?;:")
            if not key:
                continue
            hit = _fa_of(key)
            if hit:
                out.append(hit)
            else:
                unknown.append(word)
                out.append("…")
        return {"text": " ".join(out).strip(), "unknown": unknown,
                "complete": not unknown}

    # فارسی → انگلیسی
    table = _dictionary()
    clean = source.strip(" «»\"'")
    for pattern, build in _FA_PATTERNS:
        match = pattern.match(clean)
        if match:
            rendered = build(match, table)
            if _KNOWN not in rendered:
                return {"text": rendered, "unknown": [], "complete": True}
    words = clean.split(" ")
    out = []
    unknown = []
    for word in words:
        piece = _en_of(word, table)
        if piece == _KNOWN:
            unknown.append(word)
            out.append("…")
        else:
            out.append(piece)
    return {"text": " ".join(out).strip(), "unknown": unknown, "complete": not unknown}


def _render(result: dict, to: str) -> str:
    """نمایشِ خوانای ترجمه: جملهٔ کامل پررنگ، و اعلام صریحِ ناشناخته‌ها."""
    body = result.get("text") or ""
    if to == "en":
        body = body[:1].upper() + body[1:] if body else body
        if result.get("complete"):
            body = body if body.endswith((".", "!", "?")) else body + "."
    if result.get("complete"):
        return f"**{body}**"
    unknown = "، ".join(result.get("unknown") or [])
    target = "انگلیسی" if to == "en" else "فارسی"
    return (f"ترجمهٔ بخشِ شناخته‌شده به {target}:\n**{body}**\n\n"
            f"واژه‌های «{unknown}» در واژه‌نامهٔ من نیست؛ برای ترجمهٔ دقیقِ این جمله، "
            "همان واژه‌ها را ساده‌تر بنویس یا جمله را کوتاه‌تر کن.")


# ═══════════════════════════════════════════════════════ ۵) تشخیص جهت و متن
def direction(text: str) -> str:
    """«fa2en»، «en2fa» یا «none»."""
    low = text or ""
    if re.search(r"به\s*انگلیسی|in english|to english|انگلیسی\s*کن", low, re.I):
        return "fa2en"
    if re.search(r"به\s*فارسی|in persian|to persian|فارسی\s*کن|فارسی\s*برگردان", low, re.I):
        return "en2fa"
    return "none"


def _extract(question: str) -> str:
    """متنِ مورد ترجمه را از دلِ پرسش بیرون می‌کشد."""
    text = (question or "").strip()
    # ۱) داخل گیومه
    quoted = re.search(r"[«\"'“](.+?)[»\"'”]", text)
    if quoted and len(quoted.group(1).strip()) > 1:
        return quoted.group(1).strip()
    # ۲) پس از دو نقطه: «ترجمه کن: Good morning»
    after = re.search(r"[:：]\s*(.+)$", text)
    if after and len(after.group(1).strip()) > 1:
        return after.group(1).strip()
    # ۳) پیش از «را به انگلیسی»
    before = re.split(r"\s+را\s+به\s+(?:انگلیسی|فارسی)", text)[0]
    if before and before != text:
        return before.strip(" .،")
    # ۴) حذفِ دستورهای ترجمه
    cleaned = re.sub(r"(لطفاً|لطفا)?\s*(این\s+(?:متن|جمله|عبارت)\s+را|این\s+را)?\s*"
                     r"(به|به‌)\s*(?:انگلیسی|فارسی)\s*"
                     r"(?:ترجمه\s*کن|ترجمه\s*کنید|برگردان|بنویس|چی\s*می‌شود|چی\s*میشه|"
                     r"چی\s*می‌گن|چی\s*می‌گویند)?", "", text)
    cleaned = re.sub(r"(ترجمه|translate)( کن| کنید)?", "", cleaned)
    return cleaned.strip(" .!؟?،؛:«»\"'")


# پرسش «دربارهٔ زبان» فرمانِ ترجمه نیست
_ABOUT_LANGUAGE = re.compile(
    r"(از|به|در)\s*(چه|کدام)\s*زبان|چه\s*زبانی|کدام\s*زبان|چند\s*زبان|"
    r"برگردانده\s*شد|برگردانده\s*شده|ترجمه\s*شد|ترجمه\s*شده|ترجمه‌شده|"
    r"ترجمهٔ\s*(کتاب|این\s*کتاب)|به\s*فارسی\s*(نوشته|سروده|برگردانده)")


def gloss(word: str) -> dict | None:
    """معنیِ یک واژه در هر دو جهت."""
    key = _norm(word)
    if not key:
        return None
    if key in _FA_EN:
        en, kind = _FA_EN[key]
        return {"word": key, "meaning": en.split("/")[0], "kind": kind, "to": "en"}
    fa = _fa_of(key)
    if fa:
        kind = _EN_FA.get(key.lower(), ("", "phrase"))[1]
        return {"word": key, "meaning": fa, "kind": kind, "to": "fa"}
    return None


def lookup(word: str) -> dict | None:
    """واژه‌نامهٔ ساده: معنی، نقش و چند مترادف."""
    hit = gloss(word)
    if not hit:
        return None
    return {"query": word, "meaning": hit["meaning"], "kind": hit["kind"],
            "direction": hit["to"]}


_KIND_FA = {"noun": "اسم", "verb": "فعل", "adj": "صفت", "adv": "قید",
            "pron": "ضمیر", "prep": "حرف اضافه", "phrase": "عبارت"}


def answer(question: str) -> dict | None:
    """اگر پرسش درخواستِ ترجمه یا معنیِ واژه بود، پاسخ می‌دهد."""
    raw = (question or "").strip()
    if not raw or len(raw) > 300:
        return None
    if _ABOUT_LANGUAGE.search(raw):
        return None
    # نرمال‌سازی برای الگوها؛ متنِ اصلی برای بیرون‌کشیدنِ جمله نگه داشته می‌شود
    text = _norm(raw)

    # معنی واژه: «معنی کلمهٔ امید چیست؟» / «brave به فارسی چی می‌شه؟»
    meaning = re.search(r"(?:معنی|معنای|ترجمهٔ?)\s*(?:کلم(?:ه|هٔ|ه‌ی)?|واژ(?:ه|هٔ|ه‌ی)?)?\s*"
                        r"[«\"']?(?P<w>[\w\u200c]+)[»\"']?\s*"
                        r"(?:به\s*انگلیسی|به\s*فارسی)?\s*"
                        r"(?:چیست|چیه|چی\s*می‌شود|چی\s*میشه|یعنی\s*چه|چی\s*است)", text)
    if meaning:
        hit = gloss(meaning.group("w"))
        if hit:
            kind = _KIND_FA.get(hit["kind"], "")
            return {"answer": f"«{hit['word']}» یعنی **{hit['meaning']}**"
                              + (f" ({kind})" if kind else "") + ".",
                    "engine": "translate", "source": "واژه‌نامه"}
        return None

    # «امید به انگلیسی چی می‌شه؟»
    word_ask = re.search(r"^(?P<w>[\w\u200c]{2,30})\s+(?:را\s+)?به\s+(?:انگلیسی|فارسی)\s+"
                         r"(?:چی|چه)\s*(?:می‌شود|می‌شه|می‌گن|می‌گویند|است|هست)?", text)
    if word_ask:
        hit = gloss(word_ask.group("w"))
        if hit:
            kind = _KIND_FA.get(hit["kind"], "")
            target = "انگلیسی" if hit["to"] == "en" else "فارسی"
            return {"answer": f"«{hit['word']}» به {target} **{hit['meaning']}** است"
                              + (f" ({kind})" if kind else "") + ".",
                    "engine": "translate", "source": "واژه‌نامه"}

    direction_name = direction(raw)
    if direction_name == "none":
        # «ترجمه کن: …» بدون گفتنِ مقصد؛ زبانِ متن خودش مقصد را تعیین می‌کند
        if re.search(r"(ترجمه|translate|برگردان)", text, re.I):
            payload = _extract(raw)
            if payload and payload.strip() != text.strip():
                to = "fa" if not _FA_CHARS.search(payload) else "en"
                result = translate(payload, to=to)
                return {"answer": _render(result, to), "engine": "translate",
                        "source": "مترجم"}
        return None
    payload = _extract(raw)
    if not payload:
        return None
    to = "en" if direction_name == "fa2en" else "fa"
    # متنِ هم‌زبان با مقصد، ترجمه نمی‌خواهد
    if to == "en" and not _FA_CHARS.search(payload):
        return None
    if to == "fa" and _FA_CHARS.search(payload):
        return None
    result = translate(payload, to=to)
    return {"answer": _render(result, to), "engine": "translate", "source": "مترجم"}
