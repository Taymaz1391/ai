"""آزمون‌های نگهبان برای باگ‌های رابط که یک‌بار برگشته‌اند.

هر مورد اینجا از یک ایراد واقعی می‌آید و مانع برگشتنش می‌شود:

* دکمهٔ همبرگری صفحهٔ گفتگو: قاعدهٔ دیرترِ ``.sidebar-open { display: none }``
  دکمه را برای همیشه پنهان می‌کرد.
* لوگوتایپ: نسبت تصویر در نشانه‌گذاری باید با نسبت واقعی فایل بخواند،
  وگرنه حروف کشیده می‌شوند.
* ویدیو: هر سه نسبت تصویر باید فایل واقعی داشته باشند و ویدیوی پس از
  ثبت‌نام تمام‌صفحه پخش شود.
* زبان: سایت تک‌زبانه است؛ هیچ صفحهٔ انگلیسی یا کلید زبان نمی‌ماند.
"""
from __future__ import annotations

import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"
VIDEO = STATIC / "assets" / "video"
BRAND = STATIC / "assets" / "brand"

FA = re.compile(r"[\u0600-\u06FF]")


def png_size(path: Path) -> tuple[int, int]:
    """عرض و ارتفاع را از سرصفحهٔ IHDR می‌خواند.

    Pillow در نیازمندی‌های اجرا نیست و CI نباید برای یک آزمون تصویر نصبش کند؛
    سرصفحهٔ PNG استاندارد است و همین دو عدد کافی‌اند.
    """
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"not a png: {path}")
    return struct.unpack(">II", head[16:24])


def css_rules(path: Path) -> list[tuple[str, str]]:
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    text = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", text, flags=re.S)
    return [(m.group(1).strip(), m.group(2).strip()) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text)]


class SidebarTest(unittest.TestCase):
    """نوار گفتگوها باید باز شود، کامل ناپدید شود و با همان دکمه برگردد."""

    def setUp(self):
        self.rules = css_rules(STATIC / "chat.css")

    def test_toggle_never_hidden(self):
        for selector, body in self.rules:
            if selector.split(",")[0].strip() == ".sidebar-open":
                self.assertNotIn("display: none", body.replace("\n", " "),
                                 "دکمهٔ همبرگری دوباره پنهان شده است")

    def test_single_source_of_truth(self):
        """فقط یک قاعده دربارهٔ دیده‌شدن نوار تصمیم می‌گیرد."""
        open_rules = [b for s, b in self.rules if s.split(",")[0].strip() in (".sidebar.is-open", ".sidebar")]
        joined = " ".join(open_rules)
        self.assertIn("visibility: hidden", joined, "حالت بسته باید نامرئی باشد")
        self.assertIn("visibility: visible", joined, "حالت باز باید دیده شود")

    def test_close_button_visible(self):
        bodies = [b for s, b in self.rules if s.split(",")[0].strip() == ".sidebar-close"]
        self.assertTrue(bodies, "قاعدهٔ دکمهٔ بستن پیدا نشد")
        self.assertFalse(any("display: none" in b for b in bodies), "دکمهٔ بستن پنهان شده است")

    def test_js_toggles_state_and_inert(self):
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('classList.toggle("is-open"', js)
        self.assertIn('toggleAttribute("inert"', js)
        self.assertIn('sidebarToggle.addEventListener("click"', js)


class BrandTest(unittest.TestCase):
    def test_mark_ratio_matches_markup(self):
        """نسبت لوگوتایپ در نشانه‌گذاری باید با فایل رسمی بخواند، وگرنه کشیده می‌شود."""
        for name in ("mark-ink.png", "mark-white.png"):
            w, h = png_size(BRAND / name)
            self.assertAlmostEqual(w / h, 1026 / 520, places=2, msg=name)
        for page in STATIC.glob("*.html"):
            html = page.read_text(encoding="utf-8")
            for w, h in re.findall(r'mark-(?:ink|white)\.png"[^>]*width="(\d+)" height="(\d+)"', html):
                self.assertAlmostEqual(int(w) / int(h), 1026 / 520, delta=0.08,
                                       msg=f"{page.name}: {w}×{h}")

    def test_css_reserves_intrinsic_ratio(self):
        css = (STATIC / "styles.css").read_text(encoding="utf-8")
        self.assertIn("aspect-ratio: 1026 / 520", css)

    def test_brand_name_is_a_logotype_not_text(self):
        """هیچ صفحه‌ای نام برند را به‌تنهایی به‌صورت متن نمی‌نویسد."""
        offenders = []
        for page in STATIC.glob("*.html"):
            html = page.read_text(encoding="utf-8")
            for match in re.finditer(r">\s*(رایان|Rayan)\s*<", html):
                offenders.append(f"{page.name}: {match.group(0)!r}")
        self.assertEqual(offenders, [], "نام برند باید تصویر لوگو باشد")


class LanguageTest(unittest.TestCase):
    """سایت تک‌زبانه است: همهٔ صفحه‌ها فارسی و راست‌چین، بدون نسخهٔ انگلیسی."""

    FA_PAGES = ("index.html", "app.html", "auth.html", "about.html", "course.html", "docs.html",
                "download.html", "models.html", "offline.html", "pricing.html", "share.html",
                "summary.html", "admin.html")

    def test_persian_is_default(self):
        for name in self.FA_PAGES:
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn('lang="fa"', html, name)
            self.assertIn('dir="rtl"', html, name)

    def test_no_english_pages_left(self):
        for name in ("en.html", "en-docs.html", "en-course.html", "en.css"):
            self.assertFalse((STATIC / name).exists(), name)
        for page in STATIC.glob("*.html"):
            html = page.read_text(encoding="utf-8")
            self.assertNotIn('href="/en"', html, page.name)
            self.assertNotIn('hreflang="en"', html, page.name)


class VideoTest(unittest.TestCase):
    RATIOS = ("16x9", "9x16", "1x1")

    def test_all_versions_exist(self):
        for lang in ("fa",):
            self.assertTrue((VIDEO / f"promo-{lang}-poster.jpg").exists(), lang)
            for ratio in self.RATIOS:
                clip = VIDEO / f"promo-{lang}-{ratio}.mp4"
                self.assertTrue(clip.exists(), clip.name)
                self.assertGreater(clip.stat().st_size, 200_000, clip.name)
                self.assertTrue((VIDEO / f"promo-{lang}-{ratio}-poster.jpg").exists(), clip.name)

    def test_mp4_header_has_faststart(self):
        """moov باید پیش از mdat باشد تا پخش تدریجی سریع شروع شود."""
        for ratio in self.RATIOS:
            data = (VIDEO / f"promo-fa-{ratio}.mp4").read_bytes()[:400_000]
            self.assertLess(data.find(b"moov"), data.find(b"mdat"), ratio)

    def test_embedded_with_autoplay_and_poster(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        video = re.search(r"<video id=\"promo-video\".*?>", html, re.S)
        self.assertIsNotNone(video)
        tag = video.group(0)
        for attr in ("autoplay", "muted", "loop", "playsinline", "poster="):
            self.assertIn(attr, tag, attr)

    def test_chat_page_has_player(self):
        html = (STATIC / "app.html").read_text(encoding="utf-8")
        self.assertIn('id="promo-modal"', html)
        self.assertIn("promo-modal-video", html)
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("promo-${promoLang}-${ratio}.mp4", js)


class WelcomeReelTest(unittest.TestCase):
    """بعد از ساخت حساب، ویدیوی معرفی باید تمام‌صفحه پخش شود."""

    def setUp(self):
        self.html = (STATIC / "auth.html").read_text(encoding="utf-8")
        self.js = (STATIC / "auth.js").read_text(encoding="utf-8")
        self.css = (STATIC / "pages.css").read_text(encoding="utf-8")

    def test_markup_has_fullscreen_reel(self):
        self.assertIn('id="welcome-reel"', self.html)
        self.assertIn("promo-fa-16x9.mp4", self.html)
        self.assertIn("promo-fa.vtt", self.html)
        self.assertIn('id="welcome-skip"', self.html)

    def test_signup_triggers_reel(self):
        self.assertIn("function playWelcomeReel", self.js)
        self.assertIn('playWelcomeReel("/chat")', self.js)
        self.assertIn("ended", self.js)

    def test_reel_covers_viewport(self):
        block = re.search(r"\.welcome-reel\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(block)
        self.assertIn("position: fixed", block.group(1))
        self.assertIn("inset: 0", block.group(1))


class StingTest(unittest.TestCase):
    """ویدیوی کوتاه برند: فایل واقعی و آمادهٔ پخش در دسترس باشد."""

    def test_stings_exist(self):
        for lang in ("fa",):
            for ratio in ("16x9", "1x1"):
                clip = VIDEO / f"sting-{lang}-{ratio}.mp4"
                self.assertTrue(clip.exists(), clip.name)
                self.assertGreater(clip.stat().st_size, 120_000, clip.name)
                self.assertTrue((VIDEO / f"sting-{lang}-{ratio}-poster.jpg").exists(), clip.name)


class OrbMotionTest(unittest.TestCase):
    """حالت «در حال نوشتن» باید کره را چشمک‌زن و تاب‌خوران کند."""

    def setUp(self):
        self.css = (STATIC / "styles.css").read_text(encoding="utf-8")
        self.js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.ui = (STATIC / "ui.js").read_text(encoding="utf-8")

    def test_writing_state_has_motion(self):
        self.assertIn('data-state="writing"', self.css)
        self.assertIn("orbSway", self.css)
        self.assertIn("@keyframes orbWink", self.css)

    def test_app_sets_writing_while_streaming(self):
        self.assertIn('setOrbState("writing")', self.js)
        self.assertIn("streamOrb", self.js)

    def test_face_wrapper_is_built(self):
        self.assertIn('"face"', self.ui)
        self.assertIn('"face"', self.js)


class PaletteTest(unittest.TestCase):
    """هیچ‌جا خاکستری خنثی؛ خنثی‌ها همه آبی‌مایل‌اند."""

    def test_no_neutral_grey(self):
        offenders = []
        for path in list(STATIC.glob("*.css")) + list(STATIC.glob("*.html")):
            text = path.read_text(encoding="utf-8")
            for raw in re.findall(r"#([0-9a-fA-F]{6})\b", text):
                r, g, b = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
                if max(r, g, b) - min(r, g, b) <= 12 and (r, g, b) not in ((255, 255, 255), (0, 0, 0)):
                    offenders.append(f"{path.name}: #{raw}")
        self.assertEqual(offenders, [], "رنگ خاکستری خنثی پیدا شد")

    def test_no_grayscale_filter(self):
        for path in list(STATIC.glob("*.css")) + list(STATIC.glob("*.html")):
            self.assertNotIn("grayscale(", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
