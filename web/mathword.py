"""مسائل کلامیِ رایج: پول، اعدادِ متوالی، تقسیمِ مساوی، کسر، عددِ اول، سن.

هر پاسخ با **گام‌های عددی** و بازبینی همراه است؛ هیچ عددی از پیش نوشته نشده و
همه‌چیز از خودِ متنِ پرسش و با ارقامِ فارسی محاسبه می‌شود.

نقطهٔ ورود::

    from web import mathword
    out = mathword.answer("۳ کتاب ۴۵ هزار تومانی خریدم و ۲۰۰ هزار تومان داشتم؛ چقدر می‌ماند؟")
"""
from __future__ import annotations

import re

__all__ = ["answer", "parse_amount"]

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"
_DIGITS = str.maketrans(_FA_DIGITS + "٠١٢٣٤٥٦٧٨٩٫", _EN_DIGITS + _EN_DIGITS + ".")
_THOUSANDS = re.compile(r"(?<=\d)[,\u066c\u060c ](?=\d{3}(?!\d))")


def _plain(text: str) -> str:
    """ارقامِ لاتین و بدونِ جداکنندهٔ هزارگان: «۴۵,۰۰۰» → «45000»."""
    return _THOUSANDS.sub("", (text or "").translate(_DIGITS))

_SCALE = {"هزار": 1_000, "میلیون": 1_000_000, "میلیارد": 1_000_000_000}

_WORD_NUMBERS = {
    "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7, "هشت": 8,
    "نه": 9, "ده": 10, "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14,
    "پانزده": 15, "شانزده": 16, "هفده": 17, "هجده": 18, "نوزده": 19, "بیست": 20,
    "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70, "هشتاد": 80, "نود": 90,
}


_TENS = {"بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70,
         "هشتاد": 80, "نود": 90}
_HUNDREDS = {"صد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400, "پانصد": 500}
_UNITS = {key: value for key, value in _WORD_NUMBERS.items() if value < 20}


def _number_words(text: str) -> str:
    """عددهای نوشتاریِ فارسی (با «و» یا نیم‌فاصله) را به رقم تبدیل می‌کند."""
    # «سی و پنج» / «سی‌وپنج» / «بیست ویک»
    compound = re.compile(
        rf"(?<![\w\u200c])((?:{'|'.join(_HUNDREDS)})?\s*(?:{'|'.join(_TENS)})"
        rf"(?:[\u200c\s]*و?[\u200c\s]*(?:{'|'.join(_UNITS)}))?)(?![\w\u200c])")

    def swap(match: re.Match) -> str:
        piece = match.group(0)
        total = 0
        for word in re.split(r"[\u200c\s]+|و", piece):
            word = word.strip()
            if not word:
                continue
            total += _HUNDREDS.get(word, _TENS.get(word, _UNITS.get(word, 0)))
        return str(total) if total else piece

    text = compound.sub(swap, text)
    # عددهای تک‌واژه‌ایِ باقی‌مانده
    keys = "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True))
    return re.sub(rf"(?<![\w\u200c])({keys})(?![\w\u200c])",
                  lambda match: str(_WORD_NUMBERS[match.group(0)]), text)


def _numbers(text: str) -> str:
    """عددهای نوشتاری را به رقم تبدیل می‌کند («سی‌وپنج» → «35»)."""
    return _number_words(_plain(text))


def _fa(number: float) -> str:
    """عدد را با جداکنندهٔ هزارگان و ارقام فارسی برمی‌گرداند."""
    if abs(number - round(number)) < 1e-9:
        text = f"{int(round(number)):,}"
    else:
        text = f"{number:,.2f}".rstrip("0").rstrip(".")
    return text.translate(str.maketrans(_EN_DIGITS, _FA_DIGITS))


def parse_amount(text: str) -> tuple[float, str] | None:
    """«۴۵ هزار تومان» → (45000, 'تومان')؛ «۱٫۵ میلیون» → (1500000, '')."""
    norm = _plain(text)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(هزار|میلیون|میلیارد)?\s*(تومان|ریال|دلار|یورو)?", norm)
    if not match:
        return None
    value = float(match.group(1))
    scale = match.group(2) or ""
    unit = match.group(3) or ""
    if scale:
        value *= _SCALE.get(scale, 1)
    return value, unit


_SHAPES = {
    "مربع": lambda a, b: (4 * a, a * a, "محیط", "مساحت"),
    "مستطیل": lambda a, b: (2 * (a + b), a * b, "محیط", "مساحت"),
    "دایره": lambda a, b: (2 * 3.14159 * a, 3.14159 * a * a, "محیط", "مساحت"),
}


def _shape(text: str) -> dict | None:
    """محیط و مساحتِ مربع/مستطیل با ابعادِ داده‌شده."""
    norm = _plain(text)
    want_area = bool(re.search(r"مساحت|سطح", norm))
    want_around = bool(re.search(r"محیط|پیرامون", norm))
    if not (want_area or want_around):
        return None
    for name, rule in _SHAPES.items():
        if name not in norm:
            continue
        numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", norm)]
        if not numbers:
            return None
        a = numbers[0]
        b = numbers[1] if len(numbers) > 1 else a
        around, area, around_name, area_name = rule(a, b)
        if want_area and not want_around:
            if name == "مربع":
                return _shape_answer(f"مربع با ضلع {_fa(a)}", area_name,
                                     f"{_fa(a)} × {_fa(a)}", area)
            if name == "مستطیل":
                return _shape_answer(f"مستطیل با ابعاد {_fa(a)} و {_fa(b)}", area_name,
                                     f"{_fa(a)} × {_fa(b)}", area)
            return _shape_answer(f"دایره با شعاع {_fa(a)}", area_name,
                                 f"π × {_fa(a)}²", area)
        if name == "مربع":
            return _shape_answer(f"مربع با ضلع {_fa(a)}", around_name, f"۴ × {_fa(a)}", around)
        if name == "مستطیل":
            return _shape_answer(f"مستطیل با ابعاد {_fa(a)} و {_fa(b)}", around_name,
                                 f"۲ × ({_fa(a)} + {_fa(b)})", around)
        return _shape_answer(f"دایره با شعاع {_fa(a)}", around_name,
                                 f"۲ × π × {_fa(a)}", around)
    return None


def _shape_answer(dims: str, what: str, formula: str, value: float) -> dict:
    return {"answer": f"{what}ِ {dims} = {formula} = **{_fa(round(value, 2))}**",
            "engine": "mathword", "source": "هندسه"}


def _triangle(text: str) -> dict | None:
    """مساحتِ مثلث با قاعده و ارتفاع."""
    norm = _plain(text)
    if "مثلث" not in norm or not re.search(r"مساحت|سطح", norm):
        return None
    base = re.search(r"(?:قاعدهٔ?|قاعده)\s*[:=]?\s*(\d+(?:\.\d+)?)", norm)
    height = re.search(r"(?:ارتفاع)\s*[:=]?\s*(\d+(?:\.\d+)?)", norm)
    if not base or not height:
        return None
    b, h = float(base.group(1)), float(height.group(1))
    return {"answer": (f"مساحتِ مثلث = قاعده × ارتفاع ÷ ۲ = {_fa(b)} × {_fa(h)} ÷ ۲ = "
                       f"**{_fa(round(b * h / 2, 2))}**"),
            "engine": "mathword", "source": "هندسه"}


def _discount(text: str) -> dict | None:
    """«کتاب ۱۲۰ هزار تومانی ۲۵ درصد تخفیف» → قیمتِ نهایی."""
    norm = _numbers(text)
    if not re.search(r"تخفیف|حراج|تخفیف‌خورده", norm):
        return None
    # مبلغ را از عددی برمی‌داریم که کنارش واحدِ پول یا مقیاس آمده؛ «۲۵ درصد» مبلغ نیست
    found = re.search(r"(\d+(?:[.,]\d+)?)\s*(هزار|میلیون|میلیارد)?\s*"
                      r"(?:تومان|ریال|دلار|یورو)", norm)
    if not found:
        found = re.search(r"(\d+(?:[.,]\d+)?)\s*(هزار|میلیون|میلیارد)(?![\d\s]*درصد)", norm)
    price = parse_amount(" ".join(g for g in found.groups() if g)) if found else None
    rate = re.search(r"(\d+(?:\.\d+)?)\s*(?:درصد|٪|%)", norm)
    if not price or not rate:
        return None
    amount, currency = price
    pct = float(rate.group(1))
    final = amount * (100 - pct) / 100
    suffix = f" {currency}" if currency else ""
    return {"answer": (f"قیمتِ اصلی {_fa(amount)}{suffix} است و {_fa(pct)}٪ تخفیف یعنی "
                       f"{_fa(amount)} × {_fa(pct)} ÷ ۱۰۰ = {_fa(amount * pct / 100)}{suffix} "
                       f"کم می‌شود؛ پس قیمتِ نهایی **{_fa(final)}{suffix}** است."),
            "engine": "mathword", "source": "مسئلهٔ کلامی"}


def _work_days(text: str) -> dict | None:
    """«۵ کارگر، ۵ روز» → نفر-روز."""
    norm = _numbers(text)
    if not re.search(r"کارگر|نفر|کارمند", norm):
        return None
    if not re.search(r"نفر[- ]?روز|نفر روز|چند .*روز کار|مجموع", norm):
        return None
    match = re.search(r"(\d+)\s*(?:کارگر|نفر|کارمند)[^\d]{0,12}?(\d+)\s*(?:روز|ساعت)", norm)
    if not match:
        return None
    people, days = float(match.group(1)), float(match.group(2))
    return {"answer": (f"هر کارگر {_fa(days)} روز کار کرده و {_fa(people)} کارگر داریم؛ "
                       f"{_fa(people)} × {_fa(days)} = **{_fa(people * days)}** نفر-روز."),
            "engine": "mathword", "source": "مسئلهٔ کلامی"}


def _money_problem(text: str) -> dict | None:
    """خرید چند قلم و باقی‌ماندهٔ پول."""
    norm = _plain(text)
    if not re.search(r"(بخرم|خریدم|بخرد|خرید|هزینه|قیمت)", norm):
        return None
    # تعداد × قیمتِ واحد
    pair = re.search(r"(\d+)\s*(?:عدد|تا|جلد|کتاب|دفتر|کیلو|قرص|بسته|نفر|بلیط|بلیت)?"
                     r"[^\d]{0,12}?(\d+(?:\.\d+)?\s*(?:هزار|میلیون|میلیارد)?)\s*"
                     r"(?:تومان|ریال|دلار|یورو)?\s*(?:ای|ی|ه؟)", norm)
    if not pair:
        pair = re.search(r"(\d+)\s*[^\d]{0,10}?(\d+(?:\.\d+)?)\s*(هزار|میلیون|میلیارد)", norm)
    if not pair:
        return None
    count = float(pair.group(1))
    unit = parse_amount(" ".join(g for g in pair.groups()[1:] if g))
    if not unit or count <= 0:
        return None
    unit_price, currency = unit
    total = count * unit_price
    suffix = f" {currency}" if currency else ""

    budget = None
    change_word = False
    paid = re.search(r"(برمی‌گردد|برگردد|برگشتی|بقیه|باقی‌مانده|پس\s*می‌دهد|چقدر\s*می‌ماند)",
                     norm)
    if paid:
        change_word = True
    for probe in re.finditer(r"(\d+(?:\.\d+)?)\s*(هزار|میلیون|میلیارد)?\s*(تومان|ریال|دلار|یورو)?"
                             r"\s*(?:دارم|داشته\s*باشم|داشتم|دادم|پرداخت\s*کردم|داده‌ام|هست|"
                             r"پول|کاغذ)", norm):
        parsed = parse_amount(probe.group(0))
        if parsed and parsed[0] > total:
            budget = parsed[0]
            break
    if budget is None:
        return {"answer": (f"{_fa(count)} × {_fa(unit_price)} = **{_fa(total)}**{suffix}"),
                "engine": "mathword", "source": "مسئلهٔ کلامی"}

    left = budget - total
    paid_label = "پولِ پرداختی" if change_word else "پولِ همراه"
    left_label = "پولِ برگشتی" if change_word else "باقی‌مانده"
    steps = [
        f"خرجِ خرید: {_fa(count)} × {_fa(unit_price)} = {_fa(total)}{suffix}",
        f"{paid_label}: {_fa(budget)}{suffix}",
        f"{left_label}: {_fa(budget)} − {_fa(total)} = **{_fa(left)}**{suffix}",
    ]
    return {"answer": "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)),
            "engine": "mathword", "source": "مسئلهٔ کلامی"}


def _consecutive(text: str) -> dict | None:
    """اعدادِ متوالی با جمعِ معلوم."""
    norm = _plain(text)
    match = re.search(r"(\d+)\s*عدد\s*(زوج|فرد)?\s*متوالی.{0,30}?(?:جمعشان|جمعش|مجموعشان|مجموع)"
                      r"\s*(\d+)", norm)
    if match:
        count, kind, total = int(match.group(1)), match.group(2) or "", float(match.group(3))
    else:
        alt = re.search(r"(?:جمع|مجموع)\s*(\d+).{0,20}?(\d+)\s*عدد\s*(زوج|فرد)?\s*متوالی", norm)
        if not alt:
            return None
        total, count, kind = float(alt.group(1)), int(alt.group(2)), alt.group(3) or ""
    if count < 2 or count > 10:
        return None
    step = 2 if kind in ("زوج", "فرد") else 1
    first = (total - step * count * (count - 1) / 2) / count
    if kind == "زوج":
        first = round(first / 2) * 2
    elif kind == "فرد":
        first = round((first - 1) / 2) * 2 + 1
    else:
        first = round(first)
    numbers = [first + step * i for i in range(count)]
    check = sum(numbers)
    lines = [f"اعداد: {'، '.join(_fa(n) for n in numbers)}",
             f"بررسی: {' + '.join(_fa(n) for n in numbers)} = {_fa(check)}"]
    if check != total:
        lines[0] = (f"با {_fa(count)} عددِ متوالی، جمعِ {_fa(total)} به‌دست نمی‌آید؛ "
                    f"نزدیک‌ترین حالت {_fa(check)} است.")
    return {"answer": "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1)),
            "engine": "mathword", "source": "مسئلهٔ کلامی"}


def _share(text: str) -> dict | None:
    """تقسیمِ مساوی بین چند نفر."""
    norm = _plain(text)
    match = re.search(r"(\d+)\s*(?:نفر|نفرند|شریک)\D{0,25}?"
                      r"(\d+(?:\.\d+)?\s*(?:هزار|میلیون|میلیارد)?)\s*(?:تومان|ریال|دلار)?"
                      r"\D{0,20}?(?:تقسیم|پخش|قسمت|سهم)", norm)
    if match:
        count = float(match.group(1))
        amount = parse_amount(match.group(2))
    else:
        alt = re.search(r"(\d+(?:\.\d+)?\s*(?:هزار|میلیون|میلیارد)?)\s*(?:تومان|ریال)?"
                        r"\D{0,20}?بین\s*(\d+)\s*نفر", norm)
        if not alt:
            return None
        amount = parse_amount(alt.group(1))
        count = float(alt.group(2))
    if not amount or count <= 0:
        return None
    total, currency = amount
    share = total / count
    suffix = f" {currency}" if currency else ""
    return {"answer": (f"سهم هر نفر: {_fa(total)}{suffix} ÷ {_fa(count)} = "
                       f"**{_fa(share)}**{suffix}"),
            "engine": "mathword", "source": "مسئلهٔ کلامی"}


_FRACTIONS = {"نصف": (1, 2), "یک‌دوم": (1, 2), "نیم": (1, 2), "یک‌سوم": (1, 3),
              "دوسوم": (2, 3), "دو‌سوم": (2, 3), "یک‌چهارم": (1, 4), "ربع": (1, 4),
              "سه‌چهارم": (3, 4), "یک‌پنجم": (1, 5), "یک‌دهم": (1, 10)}


_COUNT_FA = {"یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7,
             "هشت": 8, "نه": 9, "ده": 10}
_ORDINAL_FA = {"سوم": 3, "چهارم": 4, "پنجم": 5, "ششم": 6, "هفتم": 7, "هشتم": 8,
               "نهم": 9, "دهم": 10}


def _ratio(text: str) -> dict | None:
    """«پدر ۴۰ و پسر ۱۰؛ پدر چند برابر پسر است؟»"""
    if not re.search(r"چند\s*(?:برابر|بار)|(?:برابر|بار)\s*(?:بزرگ|بیشتر)", text):
        return None
    if re.search(r"درصد|٪|%", text):
        return None
    nums = [int(n) for n in re.findall(r"\d+", text)][:2]
    if len(nums) < 2 or not nums[0] or not nums[1]:
        return None
    small, big = sorted(nums)
    ratio = round(big / small, 2)
    return {"tool": "mathword", "engine": "mathword",
            "answer": (f"{_fa(big)} ÷ {_fa(small)} = **{_fa(ratio)}**؛ "
                       f"یعنی {_fa(big)} نزدیک به {_fa(ratio)} برابر {_fa(small)} است."),
            "expression": f"{big}/{small}", "value": ratio}


def _rate(text: str) -> dict | None:
    """مسافت = سرعت × زمان، و دو حالتِ وارونه‌اش."""
    if "کیلومتر" not in text:
        return None
    speed = re.search(r"(\d+(?:\.\d+)?)\s*(?:کیلومتر|کیلو\s*متر)\s*(?:بر|در)\s*ساعت", text)
    hours = re.search(r"(\d+(?:\.\d+)?)\s*ساعت", text)
    distance = re.search(r"(\d+(?:\.\d+)?)\s*(?:کیلومتر|کیلو\s*متر)", text)
    if speed and hours and "چند کیلومتر" in text:
        v, h = float(speed.group(1)), float(hours.group(1))
        out = v * h
        return {"tool": "mathword", "engine": "mathword",
                "answer": f"{_fa(v)} × {_fa(h)} = **{_fa(out)} کیلومتر**.\nمسافت = سرعت × زمان.",
                "value": out}
    asks_speed = re.search(r"چند کیلومتر بر ساعت|سرعت", text)
    if distance and hours and asks_speed and not re.search(r"بر\s*ساعت\s*در", text):
        d, h = float(distance.group(1)), float(hours.group(1))
        if h and d != h:
            out = d / h
            return {"tool": "mathword", "engine": "mathword",
                    "answer": (f"{_fa(d)} ÷ {_fa(h)} = **{_fa(out)} کیلومتر بر ساعت**.\n"
                               "سرعت = مسافت ÷ زمان."),
                    "value": out}
    if distance and speed and "چند ساعت" in text:
        d, v = float(distance.group(1)), float(speed.group(1))
        if v and d != v:
            out = d / v
            return {"tool": "mathword", "engine": "mathword",
                    "answer": f"{_fa(d)} ÷ {_fa(v)} = **{_fa(out)} ساعت**.\nزمان = مسافت ÷ سرعت.",
                    "value": out}
    return None


def _workers_inverse(text: str) -> dict | None:
    """«۴ نفر در ۳ روز؛ ۶ نفر در چند روز؟» → نسبتِ وارونه."""
    if not re.search(r"نفر|کارگر|کارمند", text) or "چند روز" not in text:
        return None
    pairs = re.findall(r"(\d+)\s*(?:نفر|کارگر|کارمند)\D{0,12}?(\d+)\s*روز", text)
    if not pairs:
        return None
    p1, d1 = int(pairs[0][0]), int(pairs[0][1])
    rest = re.search(r"(\d+)\s*(?:نفر|کارگر|کارمند)(?!\D{0,12}?\d+\s*روز)", text)
    if not rest or not p1 or not d1:
        return None
    p2 = int(rest.group(1))
    if not p2 or p2 == p1:
        return None
    total = p1 * d1
    days = total / p2
    return {"engine": "mathword", "tool": "mathword",
            "answer": (f"کار برابر {_fa(total)} نفر-روز است؛ با {_fa(p2)} نفر: "
                       f"{_fa(total)} ÷ {_fa(p2)} = **{_fa(days)} روز**.\n"
                       "نفر بیشتر، روز کمتر — نسبت وارونه."),
            "value": days}


_SHAPES_WORD = {"مربع": "مربع", "مستطیل": "مستطیل", "مثلث": "مثلث",
                "دایره": "دایره", "دائره": "دایره"}


def _triangle_perimeter(text: str) -> dict | None:
    """محیطِ مثلث با سه ضلع؛ فرمولش جمعِ ساده است."""
    if "مثلث" not in text or not re.search(r"محیط", text):
        return None
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(nums) < 3:
        return None
    a, b, c = nums[:3]
    if a + b <= c or a + c <= b or b + c <= a:
        return None                      # این سه ضلع مثلث نمی‌سازند
    total = a + b + c
    return {"engine": "mathword", "tool": "mathword",
            "answer": (f"محیطِ مثلث = {_fa(a)} + {_fa(b)} + {_fa(c)} = **{_fa(total)}**.\n"
                       "محیط یعنی جمعِ سه ضلع."),
            "value": total}


def _geometry(text: str) -> dict | None:
    """محیط و مساحتِ شکل‌های ساده، با فرمول و واحد."""
    shape = next((v for k, v in _SHAPES_WORD.items() if k in text), "")
    if not shape:
        return None
    want_area = bool(re.search(r"مساحت", text))
    want_perimeter = bool(re.search(r"محیط|پیرامون", text))
    if not (want_area or want_perimeter):
        return None
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not nums:
        return None
    if shape == "مربع":
        side = nums[0]
        if want_area:
            value, formula, unit = side * side, f"{_fa(side)} × {_fa(side)}", "سانتی‌متر مربع"
        else:
            value, formula, unit = 4 * side, f"۴ × {_fa(side)}", "سانتی‌متر"
    elif shape == "مستطیل":
        if len(nums) < 2:
            return None
        a, b = nums[0], nums[1]
        if want_area:
            value, formula, unit = a * b, f"{_fa(a)} × {_fa(b)}", "سانتی‌متر مربع"
        else:
            value, formula, unit = 2 * (a + b), f"۲ × ({_fa(a)} + {_fa(b)})", "سانتی‌متر"
    elif shape == "مثلث":
        if len(nums) < 2 or not want_area:
            return None
        base, height = nums[0], nums[1]
        value, formula, unit = base * height / 2, f"{_fa(base)} × {_fa(height)} ÷ ۲", "سانتی‌متر مربع"
    else:
        radius = nums[0]
        pi = 3.141592653589793
        if want_area:
            value, formula, unit = pi * radius * radius, f"π × {_fa(radius)}²", "سانتی‌متر مربع"
        else:
            value, formula, unit = 2 * pi * radius, f"۲π × {_fa(radius)}", "سانتی‌متر"
    nice = round(value, 2)
    what = "مساحت" if want_area else "محیط"
    return {"engine": "mathword", "tool": "mathword",
            "answer": f"{what}ِ **{shape}**: {formula} = **{_fa(nice)} {unit}**.",
            "value": nice}


def _fraction(text: str) -> dict | None:
    """«یک‌سومِ ۹۰ چند است؟» و «۳/۴ از ۲۰۰»."""
    norm = _plain(text)
    worded = re.search(r"(?<![\w\u200c])(\d+|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده)\s+"
                       r"(سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم)(?![\w\u200c])", norm)
    if worded:
        first = worded.group(1)
        num = int(first) if first.isdigit() else _COUNT_FA.get(first, 1)
        den = _ORDINAL_FA.get(worded.group(2), 3)
        amount = re.search(r"(\d+(?:\.\d+)?)", norm.replace(worded.group(0), " ", 1))
        if amount and den:
            total = float(amount.group(1))
            value = total * num / den
            return {"answer": (f"{_fa(num)}/{_fa(den)} از {_fa(total)} = "
                               f"{_fa(total)} × {_fa(num)} ÷ {_fa(den)} = **{_fa(value)}**"),
                    "engine": "mathword", "source": "مسئلهٔ کلامی"}
    for word, (num, den) in _FRACTIONS.items():
        if re.search(rf"(?<![\w\u200c]){re.escape(word)}(?![\w\u200c])", norm):
            amount = re.search(r"(\d+(?:\.\d+)?)", norm)
            if not amount:
                return None
            total = float(amount.group(1))
            value = total * num / den
            return {"answer": (f"{_fa(num)}/{_fa(den)} از {_fa(total)} = "
                               f"{_fa(total)} × {_fa(num)} ÷ {_fa(den)} = **{_fa(value)}**"),
                    "engine": "mathword", "source": "مسئلهٔ کلامی"}
    pair = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:از|ِ)?\s*(\d+(?:\.\d+)?)", norm)
    if pair:
        num, den, total = float(pair.group(1)), float(pair.group(2)), float(pair.group(3))
        if den:
            value = total * num / den
            return {"answer": f"**{_fa(value)}**  ({_fa(num)}/{_fa(den)} از {_fa(total)})",
                    "engine": "mathword", "source": "مسئلهٔ کلامی"}
    return None


def _is_prime(number: int) -> bool:
    if number < 2:
        return False
    if number % 2 == 0:
        return number == 2
    factor = 3
    while factor * factor <= number:
        if number % factor == 0:
            return False
        factor += 2
    return True


def _even_prime(text: str) -> dict | None:
    """«یک عدد که هم زوج باشد هم اول» → تنها پاسخ ۲ است."""
    norm = _plain(text)
    if not (re.search(r"زوج", norm) and re.search(r"اول", norm)):
        return None
    if not re.search(r"(عدد|کدام|چه)", norm):
        return None
    return {"answer": ("تنها عددی که هم زوج است و هم اول، **۲** است: تنها عددِ زوجی است که "
                       "فقط بر ۱ و خودش بخش‌پذیر است؛ هر زوجِ بزرگ‌تر از ۲ بر ۲ هم بخش می‌شود."),
            "engine": "mathword", "source": "ریاضی"}


def _primes(text: str) -> dict | None:
    """«چند عددِ اول بین ۱ و ۲۰ هست؟» و «اعدادِ اولِ کمتر از ۳۰»."""
    norm = _plain(text)
    if "اول" not in norm or "عدد" not in norm:
        return None
    if not re.search(r"(بین|تا|کمتر\s*از|زیرِ?|کوچک‌تر\s*از)", norm):
        return None
    numbers = [int(float(m)) for m in re.findall(r"\d+", norm)]
    if len(numbers) >= 2:
        low, high = sorted(numbers[:2])
        span = True
    elif numbers:
        low, high = 2, numbers[0]
        span = False
    else:
        return None
    if high > 10_000 or high < low:
        return None
    found = [n for n in range(max(2, low), high + 1) if _is_prime(n)]
    head = (f"بین {_fa(low)} و {_fa(high)}، **{_fa(len(found))} عددِ اول** هست:"
            if span else f"کمتر از {_fa(high)}، **{_fa(len(found))} عددِ اول** هست:")
    return {"answer": f"{head} {'، '.join(_fa(n) for n in found)}.", "engine": "mathword",
            "source": "مسئلهٔ کلامی"}


def _age(text: str) -> dict | None:
    """«علی ۳ سال از مریم بزرگ‌تر است و جمع سنشان ۲۵ است؛ علی چند ساله است؟»"""
    norm = _plain(text)
    gap = re.search(r"(\S+)\s+(\d+)\s*سال\s*(?:از\s*\S+\s*)?(بزرگ‌تر|کوچک‌تر|بزرگتر|کوچکتر)",
                    norm)
    total_match = re.search(r"(?:جمع|مجموع|روی\s*هم)\D{0,14}?(\d+)", norm)
    if not (gap and total_match):
        return None
    difference = float(gap.group(2))
    total = float(total_match.group(1))
    older = (total + difference) / 2
    younger = (total - difference) / 2
    if younger < 0:
        return None
    first = gap.group(1)
    if gap.group(3).startswith("بزرگ"):
        lead = f"**{first}** {_fa(older)} ساله است و دیگری {_fa(younger)} ساله"
    else:
        lead = f"**{first}** {_fa(younger)} ساله است و دیگری {_fa(older)} ساله"
    return {"answer": (f"{lead} (اختلاف {_fa(difference)} سال، جمع {_fa(total)}).\n"
                       f"• اختلاف: {_fa(total)} − {_fa(difference)} = {_fa(total - difference)} "
                       f"← نصفش {_fa(younger)}\n"
                       f"• بازبینی: {_fa(younger)} + {_fa(older)} = {_fa(total)}"),
            "engine": "mathword", "source": "مسئلهٔ کلامی"}


def _percent(text: str) -> dict | None:
    """«۳۰ درصد از ۵۰ چند است؟» و «۳۵٪ از ۸۰»."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:درصد|٪|%)\s*(?:از|ِ)?\s*(\d+(?:\.\d+)?)",
                      text)
    if not match:
        return None
    rate, total = float(match.group(1)), float(match.group(2))
    value = total * rate / 100
    return {"answer": (f"{_fa(rate)}٪ از {_fa(total)} = {_fa(total)} × {_fa(rate)} ÷ ۱۰۰ "
                       f"= **{_fa(value)}**"),
            "engine": "mathword", "source": "ریاضی"}


def _root(text: str) -> dict | None:
    """«جذر ۱۴۴ چند است؟» و «ریشهٔ سوم ۲۷»."""
    norm = _plain(text)
    match = re.search(r"(?:جذر|ریشه(?:ٔ|\s)?(سوم|چهارم)?)\s*(?:عدد\s*)?(\d+(?:\.\d+)?)", norm)
    if not match:
        return None
    degree = {"سوم": 3, "چهارم": 4}.get(match.group(1) or "", 2)
    value = float(match.group(2))
    root = value ** (1 / degree)
    rounded = round(root)
    exact = abs(root - rounded) < 1e-9
    shown = _fa(rounded) if exact else _fa(round(root, 3))
    label = "جذر" if degree == 2 else f"ریشهٔ {match.group(1)}"
    body = f"{label}ِ {_fa(value)} = **{shown}**"
    if exact:
        body += f"\n• بازبینی: {_fa(rounded)} × {_fa(rounded)} = {_fa(value)}" \
            if degree == 2 else f"\n• بازبینی: {_fa(rounded)} به توانِ {_fa(degree)} = {_fa(value)}"
    return {"answer": body, "engine": "mathword", "source": "ریاضی"}


def _average(text: str) -> dict | None:
    """«متوسط ۱۰، ۲۰ و ۳۰ چند است؟»"""
    norm = _plain(text)
    if not re.search(r"(متوسط|میانگین)", norm):
        return None
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", norm)]
    numbers = [n for n in numbers if n != 0][:6] if numbers else []
    if len(numbers) < 2:
        return None
    total = sum(numbers)
    mean = total / len(numbers)
    return {"answer": (f"میانگین: ({' + '.join(_fa(n) for n in numbers)}) ÷ {_fa(len(numbers))} "
                       f"= {_fa(total)} ÷ {_fa(len(numbers))} = **{_fa(mean)}**"),
            "engine": "mathword", "source": "ریاضی"}


def answer(question: str) -> dict | None:
    """اگر پرسش یک مسئلهٔ کلامیِ پشتیبانی‌شده بود، حلش می‌کند."""
    text = _numbers((question or "").strip())
    if not text or len(text) > 500:
        return None
    if not re.search(r"\d", text):
        return None
    for handler in (_triangle, _triangle_perimeter, _shape, _geometry, _discount, _workers_inverse,
                    _rate, _work_days, _even_prime, _percent, _root,
                    _average, _fraction, _ratio,
                    _money_problem, _consecutive, _share, _primes, _age):
        try:
            found = handler(text)
        except Exception:  # noqa: BLE001 - یک لایه نباید پاسخ را بشکند
            found = None
        if found:
            return found
    return None
