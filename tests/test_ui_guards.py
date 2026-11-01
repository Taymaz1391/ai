"""آزمون‌های نگهبان برای باگ‌های رابط که یک‌بار برگشته‌اند.

هر مورد اینجا از یک ایراد واقعی می‌آید و مانع برگشتنش می‌شود:

* دکمهٔ همبرگری صفحهٔ گفتگو: قاعدهٔ دیرترِ ``.sidebar-open { display: none }``
  دکمه را برای همیشه پنهان می‌کرد.
* لوگوتایپ: نسبت تصویر در نشانه‌گذاری باید با نسبت واقعی فایل بخواند،
  وگرنه حروف کشیده می‌شوند.
* حرکت برند: کره و نشان باید فایل متحرک واقعی داشته باشند و نمایشِ پس از
  ثبت‌نام تمام‌صفحه پخش شود؛ ویدیوی تبلیغاتی حذف شده است.
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

    FA_PAGES = ("index.html", "app.html", "auth.html", "about.html", "compare.html",
                "models.html", "offline.html", "pricing.html", "share.html", "admin.html")

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


class BrandMotionTest(unittest.TestCase):
    """نشان و کرهٔ متحرک جای ویدیوی تبلیغاتی را گرفته‌اند: سبک، شفاف، بی‌ویدیو."""

    def test_motion_assets_are_animated_webp(self):
        for name in ("orb-live.webp", "orb-live-sm.webp", "logo-motion.webp",
                     "logo-motion-dark.webp", "logo-loading.webp"):
            path = BRAND / name
            self.assertTrue(path.exists(), name)
            head = path.read_bytes()[:16]
            self.assertEqual(head[:4], b"RIFF", name)
            self.assertEqual(head[8:12], b"WEBP", name)
            self.assertEqual(head[12:16], b"VP8X", name)
            self.assertGreater(path.stat().st_size, 8_000, name)
        # ویدیوی تبلیغاتی کامل از مخزن حذف شده است
        self.assertFalse((VIDEO / "promo-fa-16x9.mp4").exists())
        self.assertFalse((STATIC / "promo.js").exists())

    def test_home_uses_motion_not_video(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<video", html)
        self.assertIn('id="motion"', html)
        self.assertIn("logo-motion.webp", html)
        self.assertIn("orb-live.webp", html)
        self.assertIn("logo-motion-dark.webp", html)

    def test_chat_uses_motion_orb(self):
        html = (STATIC / "app.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("promo-modal", html)
        self.assertIn("orb-live.webp", html)
        self.assertIn("orb-live-sm.webp", js)

    def test_static_orb_has_alpha_and_square_ratio(self):
        for name in ("orb-128.png", "orb-256.png", "orb-512.png"):
            w, h = png_size(BRAND / name)
            self.assertEqual(w, h, name)


class WelcomeReelTest(unittest.TestCase):
    """بعد از ساخت حساب، آموزش با گوینده تمام‌صفحه پخش می‌شود."""

    def setUp(self):
        self.html = (STATIC / "auth.html").read_text(encoding="utf-8")
        self.js = (STATIC / "auth.js").read_text(encoding="utf-8")
        self.css = (STATIC / "pages.css").read_text(encoding="utf-8")

    def test_markup_has_fullscreen_reel(self):
        self.assertIn('id="welcome-reel"', self.html)
        self.assertIn('id="welcome-skip"', self.html)
        # پخش‌کنندهٔ واقعی آموزش با گوینده (به‌جای نماد متحرک بی‌صدا)
        self.assertIn('id="welcome-video"', self.html)
        self.assertIn("/static/assets/video/intro.mp4", self.html)

    def test_signup_triggers_reel(self):
        self.assertIn("function playWelcomeReel", self.js)
        self.assertIn('playWelcomeReel("/chat")', self.js)
        self.assertIn("video.play()", self.js)
        self.assertIn("ended", self.js)

    def test_reel_covers_viewport(self):
        block = re.search(r"\.welcome-reel\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(block)
        self.assertIn("position: fixed", block.group(1))
        self.assertIn("inset: 0", block.group(1))

    def test_no_api_keys_anywhere(self):
        """کلید API کاملاً حذف شده است؛ دسترسی فقط از خود سایت."""
        self.assertNotIn('id="key-form"', self.html)
        self.assertNotIn("api-key", self.html)
        self.assertNotIn("x-api-key", (STATIC / "ui.js").read_text(encoding="utf-8"))
        self.assertNotIn("x-api-key", (STATIC / "app.js").read_text(encoding="utf-8"))
        self.assertIn("/api/auth/me", self.js)
        # صفحه‌های «پشت صحنه» منتشر نمی‌شوند
        for name in ("developer.html", "docs.html", "course.html", "download.html", "summary.html"):
            self.assertFalse((STATIC / name).exists(), name)


class HumanShieldTest(unittest.TestCase):
    """«من ربات نیستم» امضاشده، یک‌بارمصرف و همراه شواهد رفتاری است."""

    def setUp(self):
        self.human = (STATIC / "human.js").read_text(encoding="utf-8")
        self.css = (STATIC / "pages.css").read_text(encoding="utf-8")
        self.auth = (STATIC / "auth.js").read_text(encoding="utf-8")

    def test_widget_sends_evidence(self):
        for needle in ("evidence:", "elapsed_ms", "honeypot", "moves", "keys"):
            self.assertIn(needle, self.human)

    def test_honeypot_field_is_hidden_from_people(self):
        self.assertIn("human-trap", self.human)
        self.assertIn("tabIndex = -1", self.human)
        self.assertIn(".human-trap", self.css)

    def test_verification_is_bound_and_single_use_server_side(self):
        security = (ROOT / "web" / "security.py").read_text(encoding="utf-8")
        self.assertIn("bound_fp", security)
        self.assertIn("MIN_FILL_TIME", security)
        self.assertIn("honeypot", security)
        self.assertIn("_used", security)

    def test_auth_page_has_no_key_panel(self):
        self.assertNotIn("api-key", self.auth)
        self.assertNotIn("x-api-key", self.auth)


class MotionShowcaseTest(unittest.TestCase):
    """بخش حرکت برند فقط خودِ نشان است؛ زیرش نوشته‌ای نیست."""

    def setUp(self):
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.css = (STATIC / "styles.css").read_text(encoding="utf-8")

    def test_no_copy_under_motion(self):
        start = self.html.index('id="motion"')
        end = self.html.index("<!-- ========================================================= تعرفه -->")
        block = self.html[start:end]
        self.assertNotIn("motion-copy", block)
        self.assertNotIn("motion-points", block)
        self.assertNotIn("<p", block)
        self.assertIn("logo-motion.webp", block)
        self.assertIn("orb-live.webp", block)

    def test_stage_is_wide_and_animated(self):
        self.assertIn(".motion-halo", self.css)
        self.assertIn("haloSpin", self.css)
        self.assertIn("prefers-reduced-motion", self.css)


class ChatComposerTest(unittest.TestCase):
    """نوار نوشتن به سبک دستیارهای بزرگ: یک کادر، ابزارها زیر دکمهٔ +."""

    def setUp(self):
        self.html = (STATIC / "app.html").read_text(encoding="utf-8")
        self.css = (STATIC / "chat.css").read_text(encoding="utf-8")
        self.js = (STATIC / "app.js").read_text(encoding="utf-8")

    def test_tools_live_behind_plus(self):
        self.assertIn('id="tools-btn"', self.html)
        self.assertIn('id="composer-tools"', self.html)
        self.assertIn("function setTools", self.js)

    def test_composer_is_one_rounded_box(self):
        self.assertIn(".composer-tools", self.css)
        self.assertIn("border-radius: 26px", self.css)

    def test_orb_is_animated_in_chat(self):
        self.assertIn("orb-live.webp", self.html)
        self.assertIn("orb-live-sm.webp", self.js)
        self.assertNotIn("orb-128.png", self.html)


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


class IntroVideoTest(unittest.TestCase):
    """آموزش استفاده باید ویدیوی واقعی با گوینده باشد و بعد از ثبت‌نام پخش شود."""

    VIDEO = STATIC / "assets" / "video" / "intro.mp4"
    POSTER = STATIC / "assets" / "video" / "intro-poster.jpg"

    def test_video_file_exists_and_is_mp4(self):
        self.assertTrue(self.VIDEO.exists(), "ویدیوی آموزش ساخته نشده؛ scripts/make_intro_video.py")
        with open(self.VIDEO, "rb") as fh:
            head = fh.read(12)
        self.assertEqual(head[4:8], b"ftyp", "فایل MP4 معتبر نیست")
        self.assertGreater(self.VIDEO.stat().st_size, 200_000)
        self.assertTrue(self.POSTER.exists())

    def test_video_has_audio_and_video_streams(self):
        """بدون باند صوتی، «گوینده» ادعای توخالی است."""
        import subprocess
        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        out = subprocess.run([ff, "-hide_banner", "-i", str(self.VIDEO)], capture_output=True,
                             text=True).stderr
        self.assertIn("Audio:", out)
        self.assertIn("Video:", out)
        self.assertIn("1280x720", out)

    def test_post_signup_plays_video_not_logo_reel(self):
        html = (STATIC / "auth.html").read_text(encoding="utf-8")
        self.assertIn('id="welcome-video"', html)
        self.assertIn("/static/assets/video/intro.mp4", html)
        js = (STATIC / "auth.js").read_text(encoding="utf-8")
        self.assertIn("playWelcomeReel", js)
        self.assertIn("video.play()", js)

    def test_rewatch_entry_exists_in_chat(self):
        html = (STATIC / "app.html").read_text(encoding="utf-8")
        self.assertIn('id="rewatch-intro"', html)
        self.assertIn('id="intro-video"', html)

    def test_script_and_narration_are_persian(self):
        import json

        script = ROOT / "data" / "intro" / "script.json"
        self.assertTrue(script.exists())
        scenes = json.loads(script.read_text(encoding="utf-8"))["scenes"]
        self.assertGreaterEqual(len(scenes), 4)
        for scene in scenes:
            self.assertTrue(FA.search(scene["narration"]), scene["id"])
            self.assertTrue(FA.search(scene["caption"]), scene["id"])


class IntroVideoTest(unittest.TestCase):
    """آموزش استفاده باید ویدیوی واقعی با گوینده باشد و بعد از ثبت‌نام پخش شود."""

    VIDEO = STATIC / "assets" / "video" / "intro.mp4"
    POSTER = STATIC / "assets" / "video" / "intro-poster.jpg"

    def test_video_file_exists_and_is_mp4(self):
        self.assertTrue(self.VIDEO.exists(), "ویدیوی آموزش ساخته نشده؛ scripts/make_intro_video.py")
        with open(self.VIDEO, "rb") as fh:
            head = fh.read(12)
        self.assertEqual(head[4:8], b"ftyp", "فایل MP4 معتبر نیست")
        self.assertGreater(self.VIDEO.stat().st_size, 200_000)
        self.assertTrue(self.POSTER.exists())

    def test_video_has_audio_and_video_streams(self):
        """بدون باند صوتی، «گوینده» ادعای توخالی است."""
        import subprocess
        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        out = subprocess.run([ff, "-hide_banner", "-i", str(self.VIDEO)], capture_output=True,
                             text=True).stderr
        self.assertIn("Audio:", out)
        self.assertIn("Video:", out)
        self.assertIn("1280x720", out)

    def test_post_signup_plays_video_not_logo_reel(self):
        html = (STATIC / "auth.html").read_text(encoding="utf-8")
        self.assertIn('id="welcome-video"', html)
        self.assertIn("/static/assets/video/intro.mp4", html)
        js = (STATIC / "auth.js").read_text(encoding="utf-8")
        self.assertIn("playWelcomeReel", js)
        self.assertIn("video.play()", js)

    def test_rewatch_entry_exists_in_chat(self):
        html = (STATIC / "app.html").read_text(encoding="utf-8")
        self.assertIn('id="rewatch-intro"', html)
        self.assertIn('id="intro-video"', html)

    def test_script_and_narration_are_persian(self):
        import json

        script = ROOT / "data" / "intro" / "script.json"
        self.assertTrue(script.exists())
        scenes = json.loads(script.read_text(encoding="utf-8"))["scenes"]
        self.assertGreaterEqual(len(scenes), 4)
        for scene in scenes:
            self.assertTrue(FA.search(scene["narration"]), scene["id"])
            self.assertTrue(FA.search(scene["caption"]), scene["id"])


if __name__ == "__main__":
    unittest.main()


class SecrecyTest(unittest.TestCase):
    """هیچ صفحهٔ عمومی نباید فایل، مخزن، پیکره یا عدد داخلی را لو بدهد."""

    BANNED = ("github", "gitlab", "checkpoint", ".npz", "wiki.sqlite3", "index.sqlite3",
              "merged.txt", "پارامتر", "میلیون پارامتری", "پیکره", "دیتاست", "dataset",
              "MIT License", "مجوز MIT", "/docs", "/developer", "/download")

    def test_public_pages_leak_nothing(self):
        static = ROOT / "web" / "static"
        for path in sorted(static.glob("*.html")):
            text = path.read_text(encoding="utf-8").lower()
            for word in self.BANNED:
                self.assertNotIn(word.lower(), text, f"{path.name} → {word}")

    def test_public_js_leak_nothing(self):
        static = ROOT / "web" / "static"
        for path in sorted(static.glob("*.js")):
            text = path.read_text(encoding="utf-8").lower()
            for word in ("github.com", "gitlab", "checkpoint", ".npz", "wiki.sqlite3"):
                self.assertNotIn(word, text, f"{path.name} → {word}")
