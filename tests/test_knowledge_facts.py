"""آزمون بستهٔ دانشِ ساختاریافته و پاسخ‌های صادقانه.

این آزمون‌ها سه چیز را قفل می‌کنند:

۱. فایلِ `data/knowledge-facts.jsonl` سالم و از جدول ساخته شده باشد.
۲. پرسش‌های رایج (پایتخت، قله، مرجعِ سلامت) به پاسخِ *همان موضوع* برسند و
   هم‌معنی‌ها («کوه»/«قله») پاسخ را از دست ندهند.
۳. وقتی دانشی نداریم، پاسخ بن‌بست نباشد و دانشِ بی‌ربط هم تحویل داده نشود.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _facts():
    path = os.path.join(ROOT, "data", "knowledge-facts.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_facts_file_is_structured_and_unique():
    rows = _facts()
    assert len(rows) >= 80, "بستهٔ ساختاریافته نباید کوچک شود"
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    for row in rows:
        assert row["q"] and row["a"] and row["keys"], row
        assert row["source"].startswith("structured-facts")


def test_capitals_and_multi_capital():
    from web import knowledge

    for question, want in (("پایتخت ژاپن کجاست؟", "توکیو"),
                           ("پایتخت کانادا کجاست؟", "اتاوا"),
                           ("پایتخت استرالیا کجاست؟", "کانبرا")):
        hit = knowledge.lookup(question)
        assert hit, question
        assert want in hit["entry"]["a"], (question, hit["entry"]["a"])

    # آفریقای جنوبی سه پایتخت دارد؛ پاسخ باید هر سه را بگوید نه فقط یکی
    hit = knowledge.lookup("پایتخت آفریقای جنوبی کجاست؟")
    assert hit
    answer = hit["entry"]["a"]
    for city in ("پرتوریا", "کیپ‌تاون", "بلومفونتین"):
        assert city in answer


def test_synonym_bridge_peak_and_mountain():
    from web import knowledge

    # مدخل با «قله» نوشته شده، کاربر «کوه» می‌پرسد
    hit = knowledge.lookup("بلندترین کوه آفریقا کدام است؟")
    assert hit and "کیلینجارو" in hit["entry"]["a"]


def test_health_reference_ranges():
    from web import knowledge

    sugar = knowledge.lookup("قند خون نرمال چقدر است؟")
    assert sugar and "۷۰" in sugar["entry"]["a"] and "۱۰۰" in sugar["entry"]["a"]
    pressure = knowledge.lookup("فشار خون طبیعی چقدر است؟")
    assert pressure and "۱۲۰" in pressure["entry"]["a"] and "۸۰" in pressure["entry"]["a"]


def test_related_never_returns_another_topic():
    from web import knowledge

    # «پایتخت آفریقای جنوبی» نباید به «پایتخت کرهٔ جنوبی» بچسبد
    found = knowledge.related("پایتخت آفریقای جنوبی کجاست؟")
    assert all("کره" not in row["q"] for row in found)
    assert knowledge.related("بلندترین کوه جهان کدام است؟") == [] or all(
        "ایران" not in row["q"] for row in knowledge.related("بلندترین کوه جهان کدام است؟"))


def test_unknown_question_has_no_dead_end_phrasing():
    from web import answer

    text = answer.grounded("پایتخت آنتیگوآ و باربودا کجاست؟")
    assert "نزدیک‌ترین دانسته‌های بررسی‌شده" not in text
    assert "نمی‌دانم" in text or "اطمینان" in text
    assert len(text) > 40


def test_factual_question_gets_no_lifestyle_advice():
    from web import guide

    assert guide.answer("فشار خون طبیعی چقدر است؟") is None
    assert guide.answer("معاهدهٔ ترکمانچای بین ایران و کدام کشور بود؟") is None
    # درخواستِ واقعیِ راهنمایی باید همچنان جواب بگیرد
    assert guide.answer("چطور فشار خون را پایین بیاورم؟")


def test_code_answers_match_intent():
    from web import tutor

    sql = tutor.code_answer("در SQL چطور تعداد رکوردها را بشمارم؟")
    assert sql and "COUNT(" in sql["answer"]
    js = tutor.code_answer("در جاوااسکریپت چطور یک متن را در صفحه بنویسم؟")
    assert js and "textContent" in js["answer"]
    py = tutor.code_answer("در پایتون چطور یک رشته را بزرگ بنویسم؟")
    assert py and ".upper()" in py["answer"]


def test_word_lookup_phrasings():
    """«کلمهٔ کتاب به انگلیسی چیست» و «صبح بخیر به انگلیسی چی می‌شه» هر دو واژه‌نامه‌ای‌اند."""
    from web import translate

    for question, want in (("کلمهٔ کتاب به انگلیسی چیست؟", "book"),
                           ("واژهٔ صبح به انگلیسی چه می‌شود؟", "morning"),
                           ("صبح بخیر به انگلیسی چی می‌شه؟", "good morning"),
                           ("کتاب به انگلیسی چیست؟", "book")):
        out = translate.answer(question)
        assert out, question
        assert want in out["answer"], (question, out["answer"])


def test_rule_of_three_with_units():
    """«اگر ۳ کیلو ۱۸۰ هزار تومان است، ۵ کیلو چند؟» با قاعدهٔ سه‌تایی حل شود."""
    from web import mathword

    out = mathword.answer("اگر ۳ کیلو برنج ۱۸۰ هزار تومان باشد، ۵ کیلو چند تومان است؟")
    assert out and "۳۰۰" in out["answer"]
    assert "کیلو" in out["answer"]
    # درصدها هم دست‌نخورده بمانند
    percent = mathword.answer("۱۵ درصد از ۲۰۰ چند است؟")
    assert percent and "۳۰" in percent["answer"]


def test_frequent_words_do_not_hide_answers():
    """با بزرگ‌شدنِ دانشنامه، واژه‌های پرتکرار («پایتخت»، «ایران») نباید پاسخ را بپوشانند."""
    from web import knowledge

    for question, want in (("پایتخت ایران کجاست؟", "تهران"),
                           ("پایتخت فرانسه کجاست؟", "پاریس"),
                           ("ایران چند استان دارد؟", "۳۱")):
        hit = knowledge.lookup(question)
        assert hit, question
        assert want in hit["entry"]["a"], (question, hit["entry"]["a"])


def _pack_rows():
    path = os.path.join(ROOT, "data", "knowledge-pack.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_pack_ids_are_unique():
    """شناسهٔ تکراری، ردیف‌های تازه را در load() بی‌صدا حذف می‌کند."""
    for rows in (_facts(), _pack_rows()):
        ids = [row["id"] for row in rows]
        assert len(ids) == len(set(ids))


def test_built_pack_merges_without_losing_rows():
    """اسکریپتِ ساخت نباید ردیف‌های دستی را پاک کند."""
    import subprocess

    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "pack.jsonl")
        shutil.copy(os.path.join(ROOT, "data", "knowledge-pack.jsonl"), target)
        with open(target, encoding="utf-8") as fh:
            before = [json.loads(line) for line in fh if line.strip()]
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_knowledge_pack.py"),
                        "--out", target], check=True, capture_output=True, cwd=ROOT)
        with open(target, encoding="utf-8") as fh:
            after = [json.loads(line) for line in fh if line.strip()]
    assert len(after) >= len(before)
    # هیچ پرسشی نباید در ادغام گم شود و شناسه‌ها باید یکتا بمانند
    assert {row["q"] for row in before} <= {row["q"] for row in after}
    assert len({row["id"] for row in after}) == len(after)
