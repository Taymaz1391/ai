"""دستیار موضوعی رایان — دستور زبان، کد و دانش پایه.

این لایه برای سه دستهٔ پرسش ساخته شده که مدل کوچک از پسشان برنمی‌آید و
جوابِ سرهم‌بندی‌شده هم به کار کاربر نمی‌آید:

* **دستور زبان**: جملهٔ فارسی تجزیه می‌شود (فعل، نهاد، مفعول، مسند، قید، زمان)
  و پاسخ از خودِ جمله بیرون می‌آید، نه از یک مقالهٔ عمومی.
* **کد**: برای درخواست‌های پرتکرار، کدِ واقعیِ پایتون نوشته می‌شود که اجرا هم
  می‌شود؛ اگر درخواست در الگوها نباشد، صریح گفته می‌شود.
* **دانش پایه**: عددها و ثابت‌های علمی قطعی، با قید شرطشان (مثلاً دمای جوش آب
  در فشار یک اتمسفر).

هیچ‌کدام از این پاسخ‌ها تولید مدل نیست؛ همه قطعی‌اند، پس هم سریع‌اند و هم
قابل بازبینی.
"""
from __future__ import annotations

import re

# ══════════════════════════════════════════════════════════ ۱) دستور زبان

def _has(text: str, *words: str) -> bool:
    """آیا واژه (به‌صورت مستقل) در متن آمده است؟ «پیشنهادی» نباید «نهاد» شمرده شود."""
    for word in words:
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text):
            return True
    return False


_VERBS: set[str] = {
    # ماضی ساده
    "رفت", "آمد", "خورد", "گفت", "دید", "نوشت", "خواند", "شنید", "گرفت", "داد",
    "کرد", "شد", "بود", "بودند", "شدند", "کردند", "رفتند", "آمدند", "خوردند",
    "خرید", "فروخت", "ساخت", "بست", "شکست", "برد", "آورد", "ماند", "نشست",
    "خوابید", "بیدارشد", "افتاد", "پرید", "خندید", "گریه‌کرد", "دوید", "زد",
    "پرسید", "پاسخ‌داد", "داشت", "دوست‌داشت", "می‌خواست", "توانست", "دانست",
    "دیدم", "رفتم", "رفتی", "رفتیم", "رفتید", "خوردم", "گفتم", "گفتی", "گفتیم",
    # مضارع و فعل‌های پرکاربرد
    "است", "هست", "نیست", "می‌رود", "می‌آید", "می‌خورد", "می‌گوید", "می‌بیند",
    "می‌نویسد", "می‌کند", "می‌شود", "دارد", "دارند", "می‌دهد", "می‌گیرد",
    "می‌خواند", "می‌ماند", "می‌خواهد", "می‌تواند", "می‌داند", "باید", "نباید",
    "شود", "کن", "برو", "بیا", "بخوان", "بنویس", "بگیر", "بده",
    # ماضی نقلی/التزامی پرکاربرد
    "رفته‌است", "خورده‌است", "گفته‌است", "شده‌است", "کرده‌است", "بوده‌است",
}

_COPULAS = {"است", "هست", "نیست", "بود", "شد", "می‌شود", "شود", "باشد"}

_ADVERBS = {
    "دیروز", "امروز", "فردا", "پریشب", "فرداشب", "صبح", "ظهر", "عصر", "شب",
    "همیشه", "هرگز", "هرگز", "گاهی", "اغلب", "معمولاً", "حتماً", "قطعاً",
    "خیلی", "بسیار", "کمی", "اندکی", "سریع", "آرام", "دوباره", "دوباره",
    "اینجا", "آنجا", "همین‌جا", "خانه", "مدرسه", "بیرون", "داخل",
}

_STOP = set("،؛:!؟«»\"'().[]{}…")


def _clean(word: str) -> str:
    """نویسه‌های نگارشیِ چسبیده به واژه را می‌گیرد."""
    return word.strip("".join(_STOP) + " ")


def _tokens(sentence: str) -> list[str]:
    return [tok for tok in (_clean(part) for part in re.split(r"\s+", sentence or "")) if tok]


def _find_verb(tokens: list[str]) -> tuple[int, str] | None:
    """واژهٔ فعل را پیدا می‌کند؛ آخرین فعل جمله معیار است (فارسی SOV است)."""
    for index in range(len(tokens) - 1, -1, -1):
        word = tokens[index]
        if word in _VERBS:
            return index, word
        # پایان‌های فعلی: «می‌نویسد»، «نوشتند»، «خوردیم» …
        stem = word
        for suffix in ("ند", "یم", "ید", "ام", "ای", "د", "م", "ی"):
            if stem.endswith(suffix) and len(stem) - len(suffix) >= 2:
                base = stem[: -len(suffix)]
                if base in _VERBS or any(base.startswith(p) for p in ("می‌", "نمی‌")):
                    return index, word
                if any(v.startswith(base[: max(2, len(base) - 1)]) for v in _VERBS):
                    return index, word
    return None


def _subject(tokens: list[str], verb_index: int) -> str:
    """نهاد: واژه/گروهی که پیش از مفعول و فعل می‌آید."""
    head = tokens[:verb_index]
    if not head:
        return ""
    # اگر مفعول با «را» نشانه دارد، نهاد پیش از آن است
    for index, word in enumerate(head):
        if word.endswith("را") and len(word) > 2:
            return " ".join(head[:index]) or head[0]
        if word == "را" and index > 0:
            return " ".join(head[: index - 1]) or head[0]
    # جملهٔ اسمیه: «هوا سرد است» → نهاد نخستین واژه است
    return head[0]


def _object(tokens: list[str], verb_index: int) -> str:
    """مفعول: واژه یا گروهی که با «را» نشانه گرفته است."""
    head = tokens[:verb_index]
    for index, word in enumerate(head):
        if word == "را" and index > 0:
            return head[index - 1]
        if word.endswith("را") and len(word) > 2:
            return word[:-2]
    return ""


def _predicate(tokens: list[str], verb_index: int) -> str:
    """مسند: بین نهاد و فعلِ اسنادی («هوا سرد است» → سرد)."""
    head = tokens[:verb_index]
    return head[1] if len(head) > 1 else ""


def _quoted(text: str) -> str:
    """متنی که کاربر داخل گیومه یا «» گذاشته است."""
    for pattern in (r"«([^»]{1,120})»", r'“([^”]{1,120})”', r'"([^"]{1,120})"',
                    r"'([^']{1,120})'"):
        found = re.search(pattern, text or "")
        if found:
            return found.group(1).strip()
    return ""


def grammar_answer(question: str) -> dict | None:
    """اگر پرسش، پرسشِ دستوری دربارهٔ یک جملهٔ مشخص باشد، پاسخ تحلیلی می‌دهد."""
    text = (question or "").strip()
    if not text:
        return None
    sentence = _quoted(text)
    number = _number_answer(text, sentence)
    if number:
        return number
    asks_verb = _has(text, "فعل", "مسند", "نهاد", "مفعول", "قید", "جمله", "دستور", "زمان")
    if not asks_verb:
        # پرسش مفهومی («تفاوت را و به») هم بدون کلیدواژهٔ تجزیه پاسخ دارد
        return _grammar_concept(text)
    if not sentence:
        return _grammar_concept(text)

    tokens = _tokens(sentence)
    if not tokens:
        return None
    found = _find_verb(tokens)
    if not found:
        return None
    verb_index, verb = found
    subject = _subject(tokens, verb_index)
    obj = _object(tokens, verb_index)
    pred = _predicate(tokens, verb_index)

    if "زمان" in text:
        if any(marker in verb for marker in ("می‌", "نمی‌", "می ")):
            tense, why = "حال (مضارع)", "پیشوند «می‌» نشانهٔ حال است"
        elif verb in ("خواهد", "خواهم", "خواهی", "خواهیم", "خواهید", "خواهند"):
            tense, why = "آینده", "فعل کمکی «خواه» آینده را می‌سازد"
        elif verb.endswith(("د", "ند", "یم", "ید", "م")) and verb not in _COPULAS:
            tense, why = "گذشته (ماضی)", "بن ماضی و شناسه، گذشته را نشان می‌دهد"
        elif verb in _COPULAS:
            tense, why = "حال (اسنادی)", "فعل اسنادی، زمان حال را می‌رساند"
        else:
            tense, why = "حال یا گذشتهٔ ساده بسته به بافت", "نشانهٔ صریح زمان در فعل نیست"
        return {"answer": f"فعل جملهٔ «{sentence}» — «{verb}» — در زمان {tense} است؛ {why}.",
                "source": "دستور زبان", "engine": "grammar"}

    if re.search(r"\bفعل|فعلِ|فعل جمله", text) or ("فعل" in text and "قید" not in text):
        extra = ""
        if verb in _COPULAS:
            extra = f"؛ «{verb}» فعل اسنادی است و جمله را به مسند («{pred}») وصل می‌کند."
        elif verb_index == len(tokens) - 1:
            extra = "؛ در فارسی فعل معمولاً آخر جمله می‌آید."
        return {"answer": f"در جملهٔ «{sentence}»، فعل «{verb}» است{extra}",
                "source": "دستور زبان", "engine": "grammar"}

    if "نهاد" in text:
        if subject:
            return {"answer": (f"در جملهٔ «{sentence}»، نهاد «{subject}» است. "
                               "نهاد همان کسی یا چیزی است که درباره‌اش خبر می‌دهیم و فعل با آن هم‌خوان می‌شود."),
                    "source": "دستور زبان", "engine": "grammar"}
        return {"answer": (f"در جملهٔ «{sentence}» نهاد جداگانه نیامده است؛ در فارسی نهاد را "
                           "می‌توان حذف کرد و از شناسهٔ فعل فهمید."),
                "source": "دستور زبان", "engine": "grammar"}

    if "مفعول" in text:
        if obj:
            return {"answer": (f"در جملهٔ «{sentence}»، مفعول «{obj}» است؛ نشانهٔ مفعول «را» ست. "
                               "مفعول چیزی است که فعل بر آن واقع می‌شود."),
                    "source": "دستور زبان", "engine": "grammar"}
        return {"answer": (f"در جملهٔ «{sentence}» مفعول صریحی با نشانهٔ «را» نیست؛ "
                           "فعل این جمله لازم است و مفعول نمی‌گیرد."),
                "source": "دستور زبان", "engine": "grammar"}

    if "مسند" in text:
        if pred:
            return {"answer": (f"در جملهٔ «{sentence}»، مسند «{pred}» است و فعل «{verb}» "
                               "فعل اسنادی است که نهاد را به مسند نسبت می‌دهد."),
                    "source": "دستور زبان", "engine": "grammar"}

    if "قید" in text:
        adverbs = [word for word in tokens if word in _ADVERBS]
        if adverbs:
            return {"answer": (f"در جملهٔ «{sentence}»، قید «{'، '.join(adverbs)}» است؛ "
                               "قید چگونگی، زمان یا مکان انجام کار را نشان می‌دهد."),
                    "source": "دستور زبان", "engine": "grammar"}
        return {"answer": (f"در جملهٔ «{sentence}» قید صریحی نیست؛ قیدهایی مثل «دیروز»، "
                           "«خیلی» یا «آرام» چگونگی و زمان فعل را روشن می‌کنند."),
                "source": "دستور زبان", "engine": "grammar"}

    return _grammar_concept(text)


def _number_answer(text: str, word: str) -> dict | None:
    """پرسش‌های جمع و مفرد: «کتاب‌ها» جمع چه واژه‌ای است؟"""
    if not word:
        return None
    if "جمع" in text and re.search(r"چه|کدام|چیست", text):
        base = word
        for suffix in ("های", "ها", "ان", "جات", "ات", "ون"):
            if base.endswith(suffix) and len(base) - len(suffix) >= 2:
                base = base[: -len(suffix)].rstrip("\u200c")
                return {"answer": (f"«{word}» جمع «{base}» است؛ پسوند «{suffix}» نشانهٔ جمع است "
                                   "و مفرد آن با حذف همین پسوند به دست می‌آید."),
                        "source": "دستور زبان", "engine": "grammar"}
        return {"answer": (f"«{word}» خودش مفرد است و نشانهٔ جمع ندارد؛ جمعش «{word}ها» می‌شود."),
                "source": "دستور زبان", "engine": "grammar"}
    if "مفرد" in text and re.search(r"چه|کدام|چیست", text):
        for suffix in ("های", "ها", "ان", "جات", "ات", "ون"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                base = word[: -len(suffix)].rstrip("\u200c")
                return {"answer": (f"مفرد «{word}» برابر «{base}» است؛ «{suffix}» پسوند جمع است."),
                        "source": "دستور زبان", "engine": "grammar"}
        return {"answer": (f"«{word}» نشانهٔ جمع ندارد و مفرد است؛ جمعش «{word}ها» می‌شود."),
                "source": "دستور زبان", "engine": "grammar"}
    return None


_GRAMMAR_CONCEPTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("تفاوت", "را", "به"), "«را» نشانهٔ مفعول است و چیزی را که فعل بر آن واقع می‌شود مشخص می‌کند: «کتاب را خواندم». "
                 "«به» حرف اضافه است و به مفعول غیرمستقیم یا مقصد و جهت معنا می‌دهد: «به مدرسه رفتم». "
                 "پس «را» نقش دستوری می‌سازد و «به» رابطهٔ معنایی؛ این دو جای هم نمی‌نشینند."),
    (("جمع", "مفرد"), "جمع فارسی با «ها» و «ان» ساخته می‌شود: «کتاب←کتاب‌ها»، «مرد←مردان». "
                       "پسوند «ها» برخلاف «ان» همیشه و برای همهٔ واژه‌ها به کار می‌رود و شمارش‌پذیر است."),
    (("نهاد",), "نهاد کسی یا چیزی است که جمله دربارهٔ آن خبر می‌دهد و فعل با شناسهٔ آن هم‌خوان است: "
                "«هوا سرد است» ← نهاد «هوا». نهاد می‌تواند حذف شود و از فعل فهمیده گردد."),
    (("فعل",), "فعل واژه‌ای است که کار یا حالت را نشان می‌دهد و در فارسی معمولاً آخر جمله می‌آید: "
               "«رفتم»، «می‌نویسد»، «است». فعل شناسه (شخص و شمار) می‌گیرد و زمان دارد."),
    (("مفعول",), "مفعول چیزی است که فعل بر آن واقع می‌شود و نشانهٔ آن «را» ست: "
                 "«نامه را نوشتم» ← مفعول «نامه». هر فعلی مفعول نمی‌گیرد؛ فعل لازم مفعول ندارد."),
    (("قید",), "قید چگونگی، زمان یا مکان انجام کار را نشان می‌دهد و لازم نیست جمله را کامل کند: "
               "«دیروز آرام آمد» ← «دیروز» قید زمان و «آرام» قید حالت."),
)


def _grammar_concept(text: str) -> dict | None:
    """پرسش مفهومیِ دستور زبان، بدون نمونهٔ جمله."""
    if not _has(text, "دستور", "زبان", "گرامر", "جمله", "نقش", "تعریف", "یعنی", "چیست",
                "تفاوت", "فرق"):
        return None
    for words, answer in _GRAMMAR_CONCEPTS:
        if all(_has(text, word) for word in words):
            return {"answer": answer, "source": "دستور زبان", "engine": "grammar"}
    return None


# ══════════════════════════════════════════════════════════ ۲) کد

_OP_NAMES = {
    "جمع": ("add", "جمع", "+", "جمع دو عدد"),
    "تفریق": ("subtract", "تفریق", "-", "تفریق دو عدد"),
    "ضرب": ("multiply", "ضرب", "*", "ضرب دو عدد"),
    "تقسیم": ("divide", "تقسیم", "/", "تقسیم دو عدد"),
    "باقیمانده": ("remainder", "باقیمانده", "%", "باقیماندهٔ تقسیم"),
}


def _function_code(name: str, title: str, params: str, body: str, call: str) -> str:
    return (f"def {name}({params}):\n"
            f'    """{title}"""\n'
            f"{body}\n\n\n"
            f"{call}")


def _code_answer_python(text: str) -> str | None:
    low = text
    programming = re.search(r"پایتون|python|(?<![\w\u200c])کد(?![\w\u200c])|برنامه|"
                            r"جاوااسکریپت|javascript|حلقه|\bsql\b|select\s|insert\s|جدول",
                            text, re.I)
    # توان
    if re.search(r"توان|به قوه|power", low):
        return ("توان در پایتون:\n\n"
                "```python\nprint(2 ** 10)      # 1024\n"
                "print(pow(2, 10))   # 1024\n"
                "print(pow(2, 10, 7))  # 2  (باقیماندهٔ تقسیم بر ۷)\n"
                "import math\nprint(math.sqrt(16))  # جذر: 4.0\n```")

    # بزرگ/کوچک‌کردنِ حروف
    if re.search(r"upper|lower|بزرگ|کوچک|حروف", low) and re.search(r"رشته|متن|حرف|string", low):
        return ("بزرگ و کوچک‌کردنِ حروفِ رشته:\n\n"
                "```python\ntext = \"salam donya\"\n"
                "print(text.upper())      # SALAM DONYA\n"
                "print(text.lower())      # salam donya\n"
                "print(text.title())      # Salam Donya\n"
                "print(text.capitalize())  # Salam donya\n```")

    # حذف از دیکشنری
    if re.search(r"دیکشنری|dict", low) and re.search(r"حذف|پاک|بردار", low):
        return ("حذفِ کلید از دیکشنری:\n\n"
                "```python\nuser = {\"name\": \"سارا\", \"age\": 30}\n"
                "del user[\"age\"]        # حذفِ مستقیم؛ اگر کلید نباشد KeyError\n"
                "value = user.pop(\"name\", None)  # حذف + گرفتنِ مقدار، امن\n"
                "print(user)            # {}\n```\n\n"
                "`pop` امن‌تر است؛ `del` سرعتِ بیشتری دارد.")

    # بازهٔ اعداد
    if re.search(r"\brange\b|بازه|محدوده", low) and re.search(r"عدد|اعداد|شمار", low):
        return ("ساختِ بازهٔ اعداد با `range()`:\n\n"
                "```python\nprint(list(range(5)))        # [0, 1, 2, 3, 4]\n"
                "print(list(range(1, 6)))     # [1, 2, 3, 4, 5]\n"
                "print(list(range(0, 20, 5)))  # [0, 5, 10, 15]  گامِ ۵\n"
                "for i in range(3):\n    print(i)\n```\n\n"
                "`range` خودش فهرست نیست؛ برای دیدنش `list()` لازم است.")

    # نزدیک‌کردنِ عدد
    if re.search(r"گرد|round", low):
        return ("گردکردنِ عدد در پایتون:\n\n"
                "```python\nprint(round(3.7))       # 4\n"
                "print(round(3.14159, 2))  # 3.14\n"
                "print(round(2.5))         # 2  (گردِ بانکی: زوج نزدیک‌تر)\n```\n\n"
                "برای همیشه دو رقم اعشار در نمایش: `f\"{x:.2f}\"`.")

    # رشته → فهرست واژه‌ها
    if re.search(r"split|فهرست|لیست", low) and re.search(r"واژه|کلمه|رشته|متن|جمله", low):
        return ("بریدنِ رشته به فهرستِ واژه‌ها با `split()`:\n\n"
                "```python\ntext = \"سلام دنیا\"\n"
                "words = text.split()        # ['سلام', 'دنیا']\n"
                "print(len(words))           # 2\n"
                "print(\" \".join(words))      # سلام دنیا\n```\n\n"
                "`split(\",\")` بر اساسِ نویسهٔ دلخواه می‌برد؛ `split()` با فاصله و خط تازه.")

    # نوشتنِ فایل متنی
    if "فایل" in low and re.search(r"بنویسم|نوشتن|write|ذخیره|بسازم", low):
        return ("نوشتنِ فایل متنی با `with` و حالت `w`:\n\n"
                "```python\nwith open(\"out.txt\", \"w\", encoding=\"utf-8\") as handle:\n"
                "    handle.write(\"سلام\\n\")\n\n"
                "with open(\"out.txt\", \"a\", encoding=\"utf-8\") as handle:\n"
                "    handle.write(\"خطِ دوم\\n\")   # a = افزودن به انتهای فایل\n```\n\n"
                "`w` فایل را از نو می‌نویسد، `a` به انتهایش اضافه می‌کند؛ همیشه "
                "`encoding=\"utf-8\"` بگذار تا فارسی سالم بماند.")

    # خواندنِ سطر‌به‌سطر
    if re.search(r"سطر|خط‌به‌خط|خط به خط|line", low) and re.search(r"فایل|بخوان", low):
        return ("خواندنِ فایل سطر‌به‌سطر:\n\n"
                "```python\nwith open(\"data.txt\", encoding=\"utf-8\") as handle:\n"
                "    for line in handle:\n"
                "        print(line.strip())     # strip خطِ تازه را برمی‌دارد\n```\n\n"
                "این روش حافظه را کم مصرف می‌کند؛ برای فایلِ بزرگ هم امن است.")

    # نوشتنِ فایل (زودتر از خواندن، تا «بنویسم» گم نشود)
    # JSON
    if re.search(r"json", low, re.I):
        return ("خواندن و نوشتنِ JSON:\n\n"
                "```python\nimport json\n\n"
                "with open(\"data.json\", encoding=\"utf-8\") as handle:\n"
                "    data = json.load(handle)          # دیکشنری/فهرست پایتونی\n\n"
                "with open(\"out.json\", \"w\", encoding=\"utf-8\") as handle:\n"
                "    json.dump(data, handle, ensure_ascii=False, indent=2)\n```\n\n"
                "اگر متن داری نه فایل: `json.loads(text)` و `json.dumps(obj)`.")

    # لیست → دیکشنری
    if re.search(r"دیکشنری|dict", low) and re.search(r"لیست|فهرست|list", low):
        return ("ساختِ دیکشنری از فهرست، با `dict()` و `zip()`:\n\n"
                "```python\nkeys = [\"name\", \"age\"]\nvalues = [\"سارا\", 30]\n"
                "person = dict(zip(keys, values))\n"
                "print(person)   # {'name': 'سارا', 'age': 30}\n\n"
                "# یا با درکِ دیکشنری از جفت‌ها\n"
                "pairs = [(\"a\", 1), (\"b\", 2)]\n"
                "print({k: v for k, v in pairs})\n```")

    # تاریخ و زمان
    if re.search(r"تاریخ|زمان|ساعت|datetime", low) and re.search(
            r"امروز|الان|اکنون|تاریخ|زمان|date|time", low):
        return ("تاریخ و زمان با ماژول `datetime`:\n\n"
                "```python\nfrom datetime import datetime, date\n\n"
                "now = datetime.now()\n"
                "print(now.strftime(\"%Y-%m-%d %H:%M\"))   # 2026-11-01 20:30\n"
                "print(date.today())                     # 2026-11-01\n```\n\n"
                "برای تاریخِ شمسی، تبدیل را خودت انجام بده یا از بستهٔ `jdatetime` استفاده کن.")

    # تبدیل نوع: رشته ↔ عدد
    if re.search(r"(رشته|متن|string)", low) and re.search(r"(عدد|int|float)", low):
        return ("تبدیل با `int()` و `float()` و بازگشت با `str()`:\n\n"
                "```python\ntext = \"۴۲\"\n"
                "number = int(text)        # 42\n"
                "decimal = float(\"3.5\")   # 3.5\n"
                "print(str(number))        # \"42\"\n```\n\n"
                "اگر ورودیِ کاربر آزاد است، تبدیل را در `try` بگذار:\n\n"
                "```python\ntry:\n    number = int(text)\n"
                "except ValueError:\n    number = 0\n```")

    # تقسیم رشته
    if re.search(r"split|تقسیم|جدا کردن|بریدن", low) and re.search(r"رشته|متن|string|جمله", low):
        return ("بریدنِ رشته با `split()` و چسباندن با `join()`:\n\n"
                "```python\ntext = \"سلام دنیا\"\n"
                "print(text.split())          # ['سلام', 'دنیا']\n"
                "print(text.split(\"ا\"))      # بر اساسِ نویسهٔ دلخواه\n"
                "print(\"-\".join([\"الف\", \"ب\"]))  # الف-ب\n```")

    # چاپ اعداد در بازه: «اعداد ۱ تا ۱۰»
    span = re.search(r"(?:اعداد|عددهای|عددها|از)\s*(\d+)\s*(?:تا|-|الی)\s*(\d+)", low)
    if span and re.search(r"(چاپ|بنویس|نمایش|حلقه|کد|for|پایتون)", low, re.I):
        start, end = int(span.group(1)), int(span.group(2))
        return (f"حلقه‌ای که اعداد {start} تا {end} را چاپ می‌کند:\n\n"
                "```python\n"
                f"for number in range({start}, {end} + 1):\n"
                "    print(number)\n"
                "```\n\n"
                "`range(a, b)` از a شروع می‌شود و به b **نمی‌رسد**؛ به همین دلیل "
                "`+ 1` گذاشته شده تا خودِ b هم چاپ شود. برای گامِ دو، "
                "`range(a, b + 1, 2)` بنویس.")

    # زوج/فرد به‌صورت تابع
    if (re.search(r"(زوج|فرد)", low)
            and re.search(r"(?<![\w\u200c])(تابع|کد|برنامه|def|پایتون)(?![\w\u200c])", low)):
        code = ("def is_even(number: int) -> bool:\n"
                '    """اگر عدد زوج باشد True برمی‌گرداند."""\n'
                "    return number % 2 == 0\n\n\n"
                "print(is_even(4))   # True\nprint(is_even(7))   # False")
        return ("زوج یا فرد بودن را با باقی‌ماندهٔ تقسیم بر ۲ می‌سنجیم:\n\n"
                f"```python\n{code}\n```\n\n"
                "`number % 2 == 0` یعنی باقی‌ماندهٔ تقسیم بر ۲ صفر است ← زوج.")

    if "فاکتوریل" in low:
        code = ("def factorial(n: int) -> int:\n"
                '    """n! را به روش تکرارشونده حساب می‌کند."""\n'
                "    result = 1\n"
                "    for number in range(2, n + 1):\n"
                "        result *= number\n"
                "    return result\n\n\n"
                "print(factorial(5))  # 120")
        return ("فاکتوریل یعنی حاصل‌ضرب همهٔ عددهای ۱ تا n. این نسخه تکرارشونده است و "
                "برای n منفی خطا نمی‌دهد (حاصل ۱ می‌شود)، پس اگر اعتبارسنجی لازم است "
                "شرط `if n < 0: raise ValueError` را اضافه کن:\n\n"
                f"```python\n{code}\n```")

    if "فیبوناچی" in low:
        code = ("def fibonacci(n: int) -> list[int]:\n"
                '    """n جملهٔ نخست دنبالهٔ فیبوناچی."""\n'
                "    series = []\n"
                "    a, b = 0, 1\n"
                "    for _ in range(n):\n"
                "        series.append(a)\n"
                "        a, b = b, a + b\n"
                "    return series\n\n\n"
                "print(fibonacci(8))  # [0, 1, 1, 2, 3, 5, 8, 13]")
        return ("هر جملهٔ دنباله جمع دو جملهٔ پیشین است؛ این نسخه خطی و سریع است:\n\n"
                f"```python\n{code}\n```")

    if "عدد اول" in low and re.search(r"تابع|بنویس|تشخیص|بررسی", low):
        code = ("def is_prime(n: int) -> bool:\n"
                '    """آیا n عدد اول است؟"""\n'
                "    if n < 2:\n"
                "        return False\n"
                "    i = 2\n"
                "    while i * i <= n:\n"
                "        if n % i == 0:\n"
                "            return False\n"
                "        i += 1\n"
                "    return True\n\n\n"
                "print(is_prime(97))  # True")
        return ("برای تشخیص عدد اول، فقط تا ریشهٔ دوم عدد بررسی می‌کنیم؛ همین کار را سریع می‌کند:\n\n"
                f"```python\n{code}\n```")

    if programming and ("فهرست" in low or "لیست" in low) and re.search(r"چطور|چه|ساخت|می‌ساز", low):
        code = ("numbers = [1, 2, 3]            # فهرست ساده\n"
                "empty = []                     # فهرست خالی\n"
                "numbers.append(4)              # افزودن به پایان\n"
                "numbers.insert(0, 0)           # افزودن در ابتدا\n"
                "print(numbers[1])              # دسترسی با اندیس\n"
                "print(numbers[-1])             # آخرین عضو\n"
                "print(len(numbers))            # تعداد عضوها\n"
                "squares = [n * n for n in numbers]  # فهرست‌سازی")
        return ("فهرست (list) در پایتون با کروشه ساخته می‌شود، ترتیب دارد و قابل تغییر است. "
                "مهم‌ترین کارها:\n\n"
                f"```python\n{code}\n```\n\n"
                "اگر فهرست ثابت می‌خواهی، تاپل با پرانتز: `point = (3, 5)`.")

    if ("مجموع" in low or "جمع اعداد" in low) and re.search(r"حلقه|for|while|یک تا|۱ تا", low):
        code = ("total = 0\n"
                "for number in range(1, 11):   # ۱ تا ۱۰\n"
                "    total += number\n"
                "print(total)                  # 55\n\n"
                "# اگر بازه را از کاربر می‌گیری:\n"
                "def sum_to(n: int) -> int:\n"
                "    total = 0\n"
                "    for number in range(1, n + 1):\n"
                "        total += number\n"
                "    return total\n\n\n"
                "print(sum_to(10))  # 55")
        return ("مجموع اعداد ۱ تا ۱۰ با یک حلقهٔ ساده حساب می‌شود؛ متغیری برای جمع نگه می‌داریم و "
                "در هر دور عدد را به آن اضافه می‌کنیم:\n\n"
                f"```python\n{code}\n```")

    if programming and ("حلقه" in low or "تکرار" in low) and re.search(r"چه|چطور|چگونه|دستور|بنویس", low):
        code = ("for i in range(5):        # ۰ تا ۴\n"
                "    print(i)\n\n"
                "count = 0\n"
                "while count < 5:          # تا وقتی شرط برقرار است\n"
                "    print(count)\n"
                "    count += 1\n\n"
                "for name in [\"سارا\", \"علی\"]:   # روی اعضای فهرست\n"
                "    print(name)")
        return ("در پایتون دو دستور تکرار داریم: «for» برای گردش روی یک مجموعه یا بازهٔ معلوم، "
                "و «while» برای تکرار تا وقتی شرطی برقرار است:\n\n"
                f"```python\n{code}\n```\n\n"
                "نکته: در «while» یادت نرود شرط را تغییر بدهی، وگرنه حلقه بی‌پایان می‌شود.")

    if programming and ("دیکشنری" in low or "dict" in low):
        code = ("person = {\"name\": \"سارا\", \"age\": 30}\n"
                "print(person[\"name\"])        # مقدار با کلید\n"
                "person[\"city\"] = \"تهران\"     # افزودن کلید تازه\n"
                "for key, value in person.items():\n"
                "    print(key, value)")
        return ("دیکشنری، جفت کلید و مقدار است و با آکولاد ساخته می‌شود:\n\n"
                f"```python\n{code}\n```")

    if programming and "مرتب" in low and re.search(r"فهرست|لیست", low):
        code = ("numbers = [5, 2, 8]\n"
                "numbers.sort()                 # مرتب‌سازی درجا، صعودی\n"
                "print(numbers)                 # [2, 5, 8]\n"
                "print(sorted(numbers, reverse=True))  # نسخهٔ نزولی")
        return ("برای مرتب‌سازی فهرست دو راه هست؛ `sort` خودِ فهرست را عوض می‌کند و "
                "`sorted` نسخهٔ تازه می‌دهد:\n\n"
                f"```python\n{code}\n```")

    if programming and "معکوس" in low and re.search(r"رشته|متن", low):
        code = ("text = \"سلام\"\n"
                "print(text[::-1])            # مالم\n"
                "print(\"\".join(reversed(text)))  # همان نتیجه")
        return ("ساده‌ترین راه معکوس‌کردن رشته، برش با گام منفی است:\n\n"
                f"```python\n{code}\n```")

    if ("تابع" in low and re.search(r"بنویس|بده|تعریف", low)
            and not re.search(r"جمع|تفریق|ضرب|تقسیم|باقیمانده|فاکتوریل|اول|زوج|فرد|"
                              r"مرتب|جستجو|جست‌وجو|بازگشتی|حساب", low)):
        code = ("def greet(name: str) -> str:\n"
                '    """سلامی شخصی می‌سازد."""\n'
                "    return f\"سلام {name}!\"\n\n\n"
                "print(greet(\"سارا\"))  # سلام سارا!")
        return ("ساختار یک تابع در پایتون این است: `def` + نام + پرانتز پارامترها + دو نقطه، "
                "و بدنه با تورفتگی. `return` خروجی را برمی‌گرداند:\n\n"
                f"```python\n{code}\n```")
    programming = re.search(r"پایتون|python|(?<![\w\u200c])کد(?![\w\u200c])|برنامه|"
                            r"جاوااسکریپت|javascript|حلقه|\bsql\b|select\s|insert\s|جدول",
                            text, re.I)
    # طول رشته/فهرست
    if re.search(r"طول|len\b", low) and re.search(r"رشته|فهرست|لیست|متن|string", low):
        code = ("text = \"سلام دنیا\"\n"
                "print(len(text))            # ۹ — شمارشِ نویسه‌ها\n"
                "words = text.split()\n"
                "print(len(words))           # ۲ — شمارشِ واژه‌ها\n"
                "print(len(\"👩\"))            # ۱ — نویسهٔ مرکب هم یک نویسه است")
        return ("`len()` طولِ رشته (تعدادِ نویسه) یا فهرست (تعدادِ عضو) را می‌دهد:\n\n"
                f"```python\n{code}\n```")

    # ورودی از کاربر
    if re.search(r"از کاربر|ورودی|input", low) and re.search(r"بگیر|خواندن|بخواه", low):
        code = ("name = input(\"نامت را بنویس: \")          # همیشه رشته است\n"
                "age = int(input(\"سنت را بنویس: \"))        # عددِ صحیح\n"
                "score = float(input(\"نمره‌ات را بنویس: \"))  # عددِ اعشاری\n"
                "print(f\"{name}، {age} ساله با نمرهٔ {score}\")")
        return ("`input()` هر ورودی را **رشته** برمی‌گرداند؛ برای عدد باید با `int()` یا "
                "`float()` تبدیلش کنی:\n\n"
                f"```python\n{code}\n```")

    # مرتب‌سازی فهرست
    if re.search(r"مرتب|sort", low) and re.search(r"فهرست|لیست|list", low):
        code = ("numbers = [5, 2, 8]\n"
                "numbers.sort()                        # درجا، صعودی\n"
                "print(numbers)                        # [2, 5, 8]\n"
                "print(sorted(numbers, reverse=True))  # نسخهٔ تازه، نزولی\n"
                "words = [\"کیوی\", \"انار\", \"سیب\"]\n"
                "print(sorted(words, key=len))         # با معیارِ دلخواه")
        return ("`sort()` خودِ فهرست را عوض می‌کند و `sorted()` نسخهٔ تازه می‌دهد؛ "
                "با `reverse=True` نزولی و با `key=` معیارِ دلخواه:\n\n"
                f"```python\n{code}\n```")

    # تابع سادهٔ حساب
    for word, (name, title, op, label) in _OP_NAMES.items():
        if word in low and re.search(r"تابع|def|بنویس|بده", low):
            guard = ""
            if op == "/":
                guard = ("    if b == 0:\n"
                         "        raise ValueError(\"تقسیم بر صفر مجاز نیست\")\n")
            body = f"{guard}    return a {op} b"
            code = _function_code(name, label, "a, b", body,
                                  f"print({name}(10, 2))  # {_eval_hint(op)}")
            return (f"این تابع دو عدد می‌گیرد و {title} را برمی‌گرداند:\n\n"
                    f"```python\n{code}\n```\n\n"
                    "برای تست، دو عدد را جای ۱۰ و ۲ بگذار.")

    # چاپ
    if re.search(r"چاپ|print", low) and re.search(r"چند خط|داخل متن|محل|خط تازه|newline|با هم", low):
        return ("چاپ با `print()` و چند خط در یک فراخوانی:\n\n"
                "```python\nprint(\"خط اول\", \"خط دوم\", sep=\"\\n\")   # هر کدام در خط تازه\n"
                "print(\"پایان\")                              # به‌طور پیش‌فرض با خط تازه تمام می‌شود\n"
                "print(\"بدون خط تازه\", end=\"\")              # end تعیین می‌کند بعدش چه بیاید\n```\n\n"
                "`sep` بین مقادیر و `end` بعد از آخرین مقدار گذاشته می‌شود.")

    # ساخت تابع
    if (re.search(r"تابع|function", low)
            and re.search(r"بساز|تعریف|بنویس|بده|چطور|چگونه", low)
            and not re.search(r"جمع|تفریق|ضرب|تقسیم|باقیمانده|فاکتوریل|اول|زوج|فرد|"
                              r"مرتب|جستجو|جست‌وجو|بازگشتی", low)):
        return ("ساخت تابع در پایتون با `def`:\n\n"
                "```python\ndef greet(name: str) -> str:\n"
                "    \"\"\"سلامِ کوتاه می‌سازد.\"\"\"\n"
                "    return f\"سلام {name}!\"\n\n"
                "print(greet(\"سارا\"))   # سلام سارا!\n```\n\n"
                "سه قاعده: نامِ روشن، پارامترهای صریح با نوعِ اختیاری، و `return` به‌جای `print` "
                "داخل تابع تا نتیجه قابلِ آزمون باشد.")

    # عدد تصادفی
    if re.search(r"تصادفی|random", low):
        return ("عدد تصادفی با ماژول `random`:\n\n"
                "```python\nimport random\n\n"
                "print(random.randint(1, 6))        # عدد صحیح بین ۱ و ۶\n"
                "print(random.choice([\"سنگ\", \"کاغذ\", \"قیچی\"]))\n"
                "random.shuffle([1, 2, 3])          # جابه‌جایی درجا\n```\n\n"
                "برای تکرارپذیری در آزمون: `random.seed(42)`.")

    return None


def _eval_hint(op: str) -> str:
    return {"+": "12", "-": "8", "*": "20", "/": "5.0", "%": "0"}.get(op, "")


    # خواندنِ فایل متنی
    if "فایل" in low and re.search(r"(بخوانم|خواندن|read|باز کنم|بازکردن)", low):
        return ("خواندنِ فایل در پایتون با `with` انجام می‌شود تا فایل حتی وقتی خطا "
                "رخ داد بسته شود:\n\n"
                "```python\n"
                "with open(\"data.txt\", encoding=\"utf-8\") as handle:\n"
                "    text = handle.read()\n\n"
                "print(text[:200])\n"
                "```\n\n"
                "برای خواندنِ خط‌به‌خط از `for line in handle:` استفاده کن، و برای فایل‌های "
                "بزرگ همین روش مصرفِ حافظه را کم نگه می‌دارد.")
    # نوشتنِ فایل متنی
    if "فایل" in low and re.search(r"(بنویسم|نوشتن|write|ذخیره)", low):
        return ("نوشتنِ فایل هم با `with` و حالت `w`:\n\n"
                "```python\n"
                "with open(\"out.txt\", \"w\", encoding=\"utf-8\") as handle:\n"
                "    handle.write(\"سلام\\n\")\n"
                "```\n\n"
                "حالت `w` فایل را از نو می‌نویسد؛ برای افزودن به انتهای فایل از `a` استفاده کن.")



def _sql_answer(text: str) -> str:
    """پاسخِ SQL بر اساسِ نیتِ پرسش، با دستورِ کامل و قابل اجرا."""
    low = text.lower()
    if re.search(r"insert|اضافه|افزودن|درج|رکورد تازه|ثبت", low):
        return ("افزودنِ رکورد با `INSERT INTO`:\n\n"
                "```sql\n"
                "INSERT INTO users (name, email) VALUES ('سارا', 'sara@example.com');\n"
                "```\n\n"
                "ستون‌ها را در پرانتزِ اول و مقدارها را به همان ترتیب در `VALUES` بنویس؛ "
                "مقدارِ متنی را در تک‌کوتیشن بگذار. برای چند رکورد، گروه‌های مقدار را با کاما ادامه بده.")
    if re.search(r"update|ویرایش|به‌روز", low):
        return ("به‌روزرسانی با `UPDATE` — بدونِ `WHERE` همهٔ ردیف‌ها تغییر می‌کنند:\n\n"
                "```sql\nUPDATE users SET email = 'new@example.com' WHERE id = 7;\n```")
    if re.search(r"delete|حذف", low):
        return ("حذف با `DELETE` — همیشه `WHERE` بگذار:\n\n"
                "```sql\nDELETE FROM users WHERE id = 7;\n```")
    if re.search(r"جدول|table|ساخت|بساز", low):
        return ("ساختِ جدول با `CREATE TABLE`:\n\n"
                "```sql\nCREATE TABLE users (\n"
                "    id      INTEGER PRIMARY KEY,\n"
                "    name    TEXT NOT NULL,\n"
                "    email   TEXT UNIQUE NOT NULL,\n"
                "    created TEXT DEFAULT CURRENT_TIMESTAMP\n"
                ");\n```")
    return ("خواندنِ داده با `SELECT`:\n\n"
            "```sql\nSELECT name, email FROM users WHERE created > '2026-01-01' "
            "ORDER BY name LIMIT 20;\n```\n\n"
            "ستون‌های موردنیاز را صریح بنویس، شرط را در `WHERE` بگذار و برای صفحه‌بندی "
            "`LIMIT` و `OFFSET` را اضافه کن.")


def _js_answer(text: str) -> str:
    """پاسخِ جاوااسکریپت بر اساسِ نیتِ پرسش."""
    low = text.lower()
    if re.search(r"دکمه|کلیک|رویداد|event|onclick|addEventListener", low):
        return ("وصل‌کردنِ رویداد به دکمه در جاوااسکریپت:\n\n"
                "```html\n<button id=\"save\">ذخیره</button>\n```\n\n"
                "```javascript\nconst button = document.querySelector('#save');\n"
                "button.addEventListener('click', () => {\n"
                "  console.log('کلیک شد');\n"
                "});\n```\n\n"
                "`addEventListener` بهتر از `onclick` است: چند شنونده را هم‌زمان می‌پذیرد.")
    if re.search(r"جمع|تابع|function|بنویس", low):
        return ("تابع در جاوااسکریپت:\n\n"
                "```javascript\nfunction add(a, b) {\n  return a + b;\n}\n\n"
                "// یا کوتاه‌تر:\nconst add = (a, b) => a + b;\n\n"
                "console.log(add(2, 3)); // 5\n```")
    if re.search(r"فهرست|آرایه|array", low):
        return ("آرایه در جاوااسکریپت:\n\n"
                "```javascript\nconst items = [3, 1, 2];\nitems.push(4);              // افزودن\n"
                "items.sort((a, b) => a - b); // مرتب‌سازی عددی\n"
                "console.log(items);         // [1, 2, 3, 4]\n```")
    return ("نمونهٔ پایهٔ جاوااسکریپت:\n\n"
            "```javascript\nconst name = 'سارا';\nconsole.log(`سلام ${name}`);\n```\n\n"
            "بگو ورودی و خروجی چه باشد تا همان را کامل بنویسم.")


def code_answer(question: str) -> dict | None:
    """برای درخواست کد، کدِ واقعی می‌نویسد یا صریح نمی‌تواند."""
    text = (question or "").strip()
    if not text:
        return None
    if not re.search(r"(?<![\w\u200c])کد(?![\w\u200c])|برنامه|تابع|پایتون|python|"
                     r"جاوااسکریپت|javascript|حلقه|دیکشنری|فهرست|لیست|"
                     r"\bsql\b|select\s|insert\s|جدول|پایگاه‌?داده", text, re.I):
        return None
    # ریاضی و ادبیات، کد نمی‌خواهند
    if re.search(r"ریاضی|ریاضیات|تابع خطی|تابع سهمی|مثلثاتی|صرف|نحو|شعر", text):
        return None
    # بدون بافت برنامه‌نویسی، فقط «تابع … بنویس» درخواست کد است
    programming = re.search(r"پایتون|python|(?<![\w\u200c])کد(?![\w\u200c])|برنامه|"
                            r"جاوااسکریپت|javascript|حلقه|\bsql\b|select\s|insert\s|جدول",
                            text, re.I)
    if not programming and not re.search(r"تابع.*(بنویس|بده)", text):
        return None
    if re.search(r"حلقه", text) and not re.search(
            r"بنویس|بده|چطور|چگونه|چه دستور|دستور|مجموع|چاپ|نمایش|اعداد|بساز", text):
        return None
    if re.search(r"\bsql\b|select\s|insert\s|پایگاه‌?داده", text, re.I):
        return {"answer": _sql_answer(text), "source": "کد", "engine": "code"}
    if re.search(r"جاوااسکریپت|javascript|\bjs\b", text, re.I):
        if re.search(r"تصادفی|random", text):
            return {"answer": ("عدد تصادفی در جاوااسکریپت:\n\n"
                               "```javascript\n// عدد صحیح بین ۱ و ۶\n"
                               "const dice = Math.floor(Math.random() * 6) + 1;\n\n"
                               "// عدد اعشاری بین ۰ و ۱\nconsole.log(Math.random());\n```"),
                    "source": "کد", "engine": "code"}
        return {"answer": _js_answer(text), "source": "کد", "engine": "code"}
    code = _code_answer_python(text)
    if code:
        return {"answer": code, "source": "کد", "engine": "code"}
    return None


_PROVINCE_CENTERS = {
    "تهران": "تهران", "البرز": "کرج", "اصفهان": "اصفهان", "فارس": "شیراز",
    "خراسان رضوی": "مشهد", "خراسان شمالی": "بجنورد", "خراسان جنوبی": "بیرجند",
    "آذربایجان شرقی": "تبریز", "آذربایجان غربی": "ارومیه", "اردبیل": "اردبیل",
    "زنجان": "زنجان", "گیلان": "رشت", "مازندران": "ساری", "گلستان": "گرگان",
    "سمنان": "سمنان", "قم": "قم", "مرکزی": "اراک", "همدان": "همدان",
    "کردستان": "سنندج", "کرمانشاه": "کرمانشاه", "لرستان": "خرم‌آباد",
    "ایلام": "ایلام", "چهارمحال و بختیاری": "شهرکرد", "کهگیلویه و بویراحمد": "یاسوج",
    "خوزستان": "اهواز", "بوشهر": "بوشهر", "هرمزگان": "بندرعباس", "کرمان": "کرمان",
    "یزد": "یزد", "سیستان و بلوچستان": "زاهدان", "قزوین": "قزوین",
}

_BOOK_AUTHORS = {
    "شاهنامه": "فردوسی", "گلستان": "سعدی", "بوستان": "سعدی", "مثنوی معنوی": "مولانا",
    "مثنوی": "مولانا", "دیوان حافظ": "حافظ", "رباعیات": "خیام",
    "مخزن‌الاسرار": "نظامی", "خمسه": "نظامی", "لیلی و مجنون": "نظامی",
    "ویس و رامین": "فخرالدین اسعد گرگانی", "تاریخ بیهقی": "ابوالفضل بیهقی",
    "کلیله و دمنه": "نصرالله منشی", "تذکرةالاولیا": "عطار", "منطق‌الطیر": "عطار",
    "حدیقه الحدیقه": "سنایی", "بوف کور": "صادق هدایت", "سووشون": "سیمین دانشور",
    "چشمهایش": "بزرگ علوی",
}


def _relation_table(text: str) -> dict | None:
    """مرکز استان، نویسندهٔ کتاب و شمار استان‌ها: از جدول قطعی، نه از حدس."""
    center = re.search(r"مرکز\s+استان\s+«?([^»؟?،]+)»?", text)
    if center:
        name = center.group(1).strip()
        for province, capital in _PROVINCE_CENTERS.items():
            if name == province or name.startswith(province):
                return {"answer": f"مرکز استان {province} شهر {capital} است.",
                        "source": "دانش پایه", "engine": "fact"}
    if re.search(r"نویسنده|مولف|مؤلف|سراینده", text):
        for book, author in _BOOK_AUTHORS.items():
            if book in text:
                return {"answer": f"نویسندهٔ «{book}» {author} است.",
                        "source": "دانش پایه", "engine": "fact"}
    if re.search(r"چند استان", text) and "ایران" in text:
        return {"answer": ("ایران ۳۱ استان دارد؛ آخرین آن استان البرز است که در سال ۱۳۸۹ "
                           "از استان تهران جدا شد."),
                "source": "دانش پایه", "engine": "fact"}
    return None


# ═══════════════════════════════════════════════════ ۳) دانش پایه

_FACTS: tuple[tuple[str, str], ...] = (
    (r"تفاوت هوش مصنوعی و یادگیری ماشین|هوش مصنوعی با یادگیری ماشین",
     "هوش مصنوعی چتر گسترده‌تری است: هر سامانه‌ای که کاری شبیه فهم یا تصمیم انسانی انجام دهد. "
     "یادگیری ماشین زیرمجموعهٔ آن است و به روش‌هایی می‌گوید که الگو را از داده یاد می‌گیرند، "
     "نه اینکه قاعده‌ها دستی نوشته شوند. یادگیری عمیق هم زیرمجموعهٔ یادگیری ماشین است و با "
     "شبکه‌های عصبی چندلایه کار می‌کند. پس هر یادگیری ماشین، هوش مصنوعی است؛ اما هر هوش "
     "مصنوعی، یادگیری ماشین نیست."),
    (r"هوش مصنوعی چیست|یادگیری ماشین چیست",
     "هوش مصنوعی شاخه‌ای از علوم رایانه است که سامانه‌هایی می‌سازد تا کاری شبیه فهم، استدلال "
     "یا تصمیم انسانی انجام دهند. یادگیری ماشین روشی در همین شاخه است که در آن سامانه از "
     "داده الگو می‌آموزد."),
    (r"تفاوت (اینترنت|وب) و|وب چیست",
     "اینترنت شبکهٔ زیرساختی است که رایانه‌ها را به هم وصل می‌کند؛ وب یکی از سرویس‌های روی "
     "همین شبکه است: صفحه‌هایی که با نشانی باز می‌شوند. پس وب بدون اینترنت کار نمی‌کند، "
     "اما اینترنت چیزهای دیگری هم دارد؛ مثل ایمیل و انتقال فایل."),
    (r"واحد اندازه‌گیری نیرو|یکای نیرو",
     "یکای نیرو در دستگاه بین‌المللی یکاها نیوتون است؛ نماد آن N. یک نیوتون نیرویی است که "
     "به جرم یک کیلوگرم شتاب یک متر بر مربع ثانیه می‌دهد."),
    (r"واحد اندازه‌گیری انرژی|یکای انرژی",
     "یکای انرژی ژول است؛ نماد J. یک ژول کار نیروی یک نیوتون در مسیر یک متر است."),
    (r"واحد اندازه‌گیری فشار|یکای فشار",
     "یکای فشار پاسکال است؛ نماد Pa. یک پاسکال برابر یک نیوتون بر متر مربع است."),
    (r"واحد اندازه‌گیری توان|یکای توان",
     "یکای توان وات است؛ نماد W. یک وات یعنی یک ژول انرژی در هر ثانیه."),
    (r"واحد اندازه‌گیری (شدت )?جریان",
     "یکای جریان الکتریکی آمپر است؛ نماد A."),
    (r"آب از چه عنصر|آب از چه چیزی ساخته|آب از چه ساخته",
     "آب از دو عنصر ساخته شده است: هیدروژن و اکسیژن، با نسبت دو اتم هیدروژن به یک اتم اکسیژن (H₂O)."),
    (r"دمای? جوش(یدن)? آب|آب در چه دمایی می‌جوشد|آب چند درجه می‌جوشد",
     "آب در فشار یک اتمسفر (سطح دریا) در ۱۰۰ درجهٔ سلسیوس می‌جوشد. "
     "در ارتفاع بالاتر فشار کمتر است و آب زودتر می‌جوشد؛ مثلاً در تهران حدود ۹۵ درجه."),
    (r"دمای? انجماد آب|آب در چه دمایی یخ می‌زند|آب چند درجه یخ",
     "آب در فشار یک اتمسفر در ۰ درجهٔ سلسیوس یخ می‌زند و در همان دما ذوب می‌شود."),
    (r"سرعت\s*نور|نور\s*چقدر\s*سریع|نور.{0,20}(سرعت|تندی).{0,20}(حرکت|سفر|برود)|"
     r"(سرعت|تندی)\s*نور|سریع‌ترین\s*نور",
     "سرعت نور در خلأ ۲۹۹٬۷۹۲٬۴۵۸ متر بر ثانیه است؛ نزدیک به ۳۰۰ هزار کیلومتر بر ثانیه."),
    (r"چند سیاره|تعداد سیارات|سیارات منظومه",
     "منظومهٔ شمسی هشت سیاره دارد: عطارد، زهره، زمین، مریخ، مشتری، زحل، اورانوس و نپتون. "
     "پلوتو از سال ۲۰۰۶ در ردهٔ سیارهٔ کوتوله قرار گرفت."),
    (r"(?:سیاره|کره).{0,45}خورشید|خورشید.{0,45}(?:سیاره|کره)|"
     r"(?:نزدیک‌ترین|اولین)\s*سیاره",
     "نزدیک‌ترین سیاره به خورشید عطارد است؛ یک سال آن فقط ۸۸ روز زمینی طول می‌کشد."),
    (r"بزرگ‌ترین سیاره|بزرگترین سیاره",
     "بزرگ‌ترین سیارهٔ منظومهٔ شمسی مشتری است؛ جرمش بیش از دو برابر مجموع بقیهٔ سیاره‌هاست."),
    (r"بلندترین قلهٔ? جهان|بلندترین کوه جهان",
     "بلندترین قلهٔ جهان اورست است با ارتفاع ۸٬۸۴۹ متر از سطح دریا."),
    (r"بلندترین قلهٔ? ایران|بلندترین کوه ایران",
     "بلندترین قلهٔ ایران دماوند است؛ ارتفاعش حدود ۵٬۶۱۰ متر و یک آتشفشان نیمه‌فعال است."),
    (r"طولانی‌ترین رود|بلندترین رود",
     "بلندترین رود جهان نیل است (حدود ۶٬۶۵۰ کیلومتر) و پس از آن آمازون قرار دارد؛ "
     "اندازه‌گیری دقیق این دو نزدیک است و در منابع اختلاف وجود دارد."),
    (r"عمیق‌ترین اقیانوس|عمیق‌ترین نقطهٔ? زمین|درازگودال",
     "عمیق‌ترین نقطهٔ زمین در اقیانوس آرام است: درازگودال ماریانا با ژرفای حدود ۱۱٬۰۰۰ متر."),
    (r"چند استخوان|تعداد استخوان",
     "بدن انسان بالغ ۲۰۶ استخوان دارد. نوزاد با حدود ۳۰۰ استخوان متولد می‌شود و برخی در رشد به هم می‌پیوندند."),
    (r"نماد شیمیایی طلا|نشانهٔ? شیمیایی طلا",
     "نماد شیمیایی طلا Au است؛ از واژهٔ لاتین aurum گرفته شده."),
    (r"نماد شیمیایی (آهن|نشانهٔ? شیمیایی آهن)",
     "نماد شیمیایی آهن Fe است؛ از واژهٔ لاتین ferrum."),
    (r"فرمول (شیمیایی )?آب",
     "فرمول شیمیایی آب H₂O است: دو اتم هیدروژن و یک اتم اکسیژن."),
    (r"چند قاره|تعداد قاره",
     "زمین هفت قاره دارد: آسیا، آفریقا، آمریکای شمالی، آمریکای جنوبی، جنوبگان، اروپا و اقیانوسیه."),
    (r"بزرگ‌ترین قاره",
     "بزرگ‌ترین قارهٔ زمین آسیاست؛ هم پهناورترین است و هم پرجمعیت‌ترین."),
    (r"چند رنگ|رنگ‌های رنگین‌کمان",
     "رنگین‌کمان هفت رنگ اصلی دارد: سرخ، نارنجی، زرد، سبز، آبی، نیلی و بنفش."),
    (r"سال چند روز|چند روز است سال",
     "سال خورشیدی حدود ۳۶۵ روز و ۶ ساعت است؛ همین کسر، هر چهار سال یک روز کبیسه می‌سازد."),
    (r"پرجمعیت‌ترین کشور",
     "پرجمعیت‌ترین کشور جهان هند است و پس از آن چین قرار دارد."),
    (r"بزرگ‌ترین اقیانوس",
     "بزرگ‌ترین اقیانوس زمین، اقیانوس آرام است؛ حدود یک‌سوم سطح کرهٔ زمین را می‌پوشاند."),
    (r"بزرگ‌ترین کشور",
     "بزرگ‌ترین کشور جهان از نظر پهناوری روسیه است و پس از آن کانادا."),
    (r"(نقطهٔ )?جوش(یدن)? (الکل|اتانول)",
     "اتانول در فشار یک اتمسفر حدود ۷۸ درجهٔ سلسیوس می‌جوشد؛ به همین دلیل در دمای پایین‌تر از آب تبخیر می‌شود."),
    (r"چند ماه طول می‌کشد.*(زمین|خورشید)|زمین.*(دور خورشید|به دور خورشید)",
     "زمین یک دور کامل به دور خورشید را در حدود ۳۶۵٫۲۵ روز می‌زند؛ همین ۰٫۲۵ روز کبیسه را می‌سازد."),
    (r"چند ماه|ماه‌های سال شمسی",
     "سال شمسی دوازده ماه دارد: فروردین تا اسفند. شش ماه نخست ۳۱ روزه، شش ماه دوم ۳۰ روزه و اسفند ۲۹ روزه است (۳۰ روز در سال کبیسه)."),
    (r"(?:قوانین|قانون(?:‌|\s)?های?)\s*نیوتن|نیوتن\s*\d?\s*قانون|"
     r"نیوتن\s*چند\s*قانون",
     "نیوتن **سه قانون** حرکت دارد:\n"
     "۱. هر جسم بدون نیرو در حالت خود می‌ماند (لختی).\n"
     "۲. نیرو = جرم × شتاب (F = ma).\n"
     "۳. هر کنش، واکنشی برابر و مخالف دارد."),
    (r"(?:جاذبه|گرانش)[\u064b-\u065f]*\s*(?:ماه|کرهٔ?\s*ماه)|"
     r"(?:ماه|قمر).{0,18}(?:جاذبه|گرانش)",
     "گرانش سطح ماه حدود **یک‌ششم** گرانش زمین است (نزدیک ۱٫۶۲ متر بر مربع ثانیه در "
     "برابر ۹٫۸۱). برای همین فضانورد با همان نیرو می‌تواند چند برابر زمین بپرد."),
    (r"کوچک‌ترین\s*کشور|کوچکترین\s*کشور|[کچ]دام\s*کشور.{0,20}(کوچک|خرد)", 
     "کوچک‌ترین کشور جهان **واتیکان** است؛ کمتر از نیم کیلومتر مربع مساحت و حدود "
     "۸۰۰ نفر جمعیت دارد و در دلِ شهر رم جای گرفته است."),
    (r"آهن.{0,30}(ویژگی|خاصیت|پرکاربرد|چرا)|(?:ویژگی|خاصیت).{0,20}آهن",
     "آهن ارزان، فراوان و بسیار سخت است و در دمای بالا شکل می‌گیرد؛ همین سه ویژگی، "
     "آن را ستونِ سازه‌ها، ریل و ماشین کرده. نقطهٔ ذوبش ۱٬۵۳۸ درجهٔ سلسیوس است و "
     "با کربن، فولادِ محکم‌تر می‌سازد."),
    (r"(?:چرا|علت).{0,15}برگ.{0,25}سبز|سبزیِ?\s*برگ|برگ\s*گیاهان\s*سبز",
     "برگ‌ها سبزند چون **کلروفیل** (سبزینه) نورِ سرخ و آبی را می‌بلعد و نورِ سبز را "
     "بازمی‌تاباند؛ رنگِ سبزی که می‌بینیم همان نوری است که جذب نشده."),
    (r"کلیله\s*و\s*دمنه",
     "کلیله و دمنه کتابی از افسانه‌های حیوانات است که در اصل هندی (پنچه‌تنتره) بود، "
     "در دورهٔ ساسانی به پهلوی برگردانده شد و نصرالله منشی در سدهٔ ششم هجری از همان "
     "پهلوی به فارسی دری آورد."),
    (r"(?:دیوان|اشعار|غزل‌های)\s*حافظ.{0,25}(زبان|فارسی)|حافظ.{0,18}چه\s*زبانی",
     "حافظ غزل‌هایش را به **فارسی** سروده — فارسیِ شیرینِ سدهٔ هشتم، آمیخته به "
     "تلمیح‌های قرآنی و اصطلاح‌های روزگارِ خودش. تنها چند بیتِ انگشت‌شمار در دیوانش "
     "به عربی است."),
    (r"خون\s*(از\s*چه|چه\s*چیزی)|خون\s*چه\s*کاری",
     "خون از **پلاسما** (بیشتر آب، پروتئین و نمک) و سه دستهٔ سلول ساخته شده: "
     "گلبول‌های سرخ که اکسیژن را می‌برند، گلبول‌های سفید که از بدن دفاع می‌کنند و "
     "پلاکت‌ها که جلوی خون‌ریزی را می‌گیرند."),
    (r"نیروی گرانش|گرانش زمین|شتاب گرانش",
     "شتاب گرانش زمین نزدیک سطح آن حدود ۹٫۸ متر بر مربع ثانیه است؛ یعنی سرعت سقوط آزاد "
     "هر ثانیه حدود ۹٫۸ متر بر ثانیه بیشتر می‌شود (بدون در نظر گرفتن مقاومت هوا)."),
)


_IDENTITY = re.compile(
    r"(?:اسم|نام)\s*(?:تو|شما|خودت|خودتان)\s*(?:چی|چیه|چیست|چی‌ست)|"
    r"(?:تو|شما)\s*(?:کی|چه\s*کسی)\s*(?:هستی|هستید|ای)|"
    r"خودت\s*را\s*(?:معرفی|وصف)|معرفی\s*کن(?:\s*خودت)?|دربارهٔ\s*(?:خودت|خودتان)")
_IDENTITY_ANSWER = (
    "نام من **رایان** است — دستیارِ فارسی‌زبانِ همین سایت. "
    "کارم پاسخ‌دادن به پرسش‌های دانشی، ترجمه، نوشتن، تحلیل و حلِ مسئله است؛ "
    "بدونِ هیچ سرویسِ بیرونی و با داده‌ای که روی همین سرور نگه‌داری می‌شود."
)


_MARKS = re.compile("[\u064b-\u065f\u0670\u06d6-\u06ed]")


def _tolerant(pattern: str) -> str:
    """نیم‌فاصله در الگو، هم نیم‌فاصله و هم فاصله را می‌پذیرد."""
    return pattern.replace("\u200c", "[\u200c ]")


_WHO = re.compile(r"(چه کسی|چه کسانی|کدام دانشمند|کدام مخترع|کی بود|کیست|چه دانشمندی|"
                  r"چه کسی بود|کدام شاعر|کدام نویسنده)")
_WHO_FACTS = [
    (r"(گرانش|جاذبه).*(کشف|فرمول|قانون)|(کشف|فرمول|قانون).*(گرانش|جاذبه)",
     "**آیزاک نیوتن** قانونِ گرانشِ همگانی را در ۱۶۸۷ صورت‌بندی کرد."),
    (r"نسبیت", "**آلبرت اینشتین** نظریهٔ نسبیت (خاص در ۱۹۰۵ و عام در ۱۹۱۵) را ارائه کرد."),
    (r"تلفن", "**الکساندر گراهام بل** نخستین اختراعِ ثبت‌شدهٔ تلفن را در ۱۸۷۶ به نام خود کرد."),
    (r"لامپ", "**توماس ادیسون** لامپِ رشته‌ایِ تجاری و پایدار را در ۱۸۷۹ ارائه کرد؛ پیش از او "
              "جوزف سوان هم نمونه‌هایی ساخته بود."),
    (r"پنی‌سیلین|آنتی‌بیوتیک", "**الکساندر فلمینگ** پنی‌سیلین را در ۱۹۲۸ کشف کرد."),
    (r"ماه.*(قدم|اولین)|اولین.*ماه",
     "**نیل آرمسترانگ** در ۲۰ ژوئیهٔ ۱۹۶۹ نخستین انسانی بود که روی ماه قدم گذاشت."),
    (r"الگوریتم", "**محمد بن موسی خوارزمی** ریاضی‌دانِ ایرانیِ قرنِ سوم است که نامش با الگوریتم "
                  "گره خورده است."),
    (r"رایانه|کامپیوتر", "**آلن تورینگ** بنیانِ نظریِ رایانهٔ امروزی را با ماشینِ تورینگ گذاشت؛ "
                         "نخستین رایانه‌های الکترونیکی در دههٔ ۱۹۴۰ ساخته شدند."),
    (r"شاهنامه|فردوسی", "**فردوسی** سرایندهٔ شاهنامه است."),
    (r"مثنوی|مولانا|مولوی", "**مولانا** سرایندهٔ مثنویِ معنوی است."),
    (r"حافظ|غزل", "**حافظ** غزل‌سرایِ شیراز است."),
    (r"سعدی|گلستان|بوستان", "**سعدی** نویسندهٔ «گلستان» و سرایندهٔ «بوستان» است."),
]


def fact_answer(question: str) -> dict | None:
    """پاسخ‌های دانش پایه با شرط و قید دقیق."""
    text = _MARKS.sub("", (question or "").strip())
    if not text:
        return None
    if _IDENTITY.search(text):
        return {"answer": _IDENTITY_ANSWER, "source": "دانش پایه", "engine": "fact"}
    # جدول‌های قطعی (مرکز استان، نویسندهٔ کتاب) پیش از هر چیز
    table = _relation_table(text)
    if table:
        return table
    # پرسشِ «چه کسی» با پاسخِ مقداری جواب داده نمی‌شود
    if _WHO.search(text):
        for pattern, answer in _WHO_FACTS:
            if re.search(_tolerant(pattern), text):
                return {"answer": answer, "source": "دانش پایه", "engine": "fact"}
        return None
    for pattern, answer in _FACTS:
        if re.search(_tolerant(pattern), text):
            return {"answer": answer, "source": "دانش پایه", "engine": "fact"}
    return None


# ═══════════════════════════════════════════════════ ۴) نقطهٔ ورود

def answer(question: str) -> dict | None:
    """ترتیب: کد → دستور زبان → دانش پایه. هر سه قطعی و کوتاه‌اند."""
    for handler in (code_answer, grammar_answer, fact_answer):
        try:
            found = handler(question)
        except Exception:  # noqa: BLE001 - یک لایه نباید کل پاسخ را بشکند
            found = None
        if found:
            return found
    return None
