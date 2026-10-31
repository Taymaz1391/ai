"""آزمون خروجی سایت استاتیک (GitHub Pages)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import export_site  # noqa: E402


class ExportSiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out = Path(cls.tmp) / "site"
        cls.info = export_site.build(cls.out)

    def test_pages_exist(self):
        for name in ("index.html", "chat.html", "login.html", "signup.html",
                     "pricing.html", "models.html", "about.html", "docs.html", "download.html",
                     "offline.html", "summary.html", "course.html", "404.html"):
            self.assertTrue((self.out / name).exists(), name)

    def test_download_page_links(self):
        html = (self.out / "download.html").read_text(encoding="utf-8")
        self.assertIn("releases/latest/download/rayan-android.apk", html)
        self.assertIn("releases/latest/download/rayan-windows.exe", html)
        self.assertIn("کلاینت نازک", html)

    def test_assets_copied(self):
        self.assertTrue((self.out / "static" / "styles.css").exists())
        self.assertTrue((self.out / "static" / "ui.js").exists())
        self.assertTrue((self.out / "static" / "assets" / "brand" / "orb-128.png").exists())
        self.assertTrue((self.out / "static" / "assets" / "fonts" / "Vazirmatn-Regular.woff2").exists())
        self.assertTrue((self.out / "static" / "config.js").exists())

    def test_no_absolute_internal_links(self):
        import re
        for page in self.out.glob("*.html"):
            refs = re.findall(r'(?:href|src)="(/[^"]*)"', page.read_text(encoding="utf-8"))
            internal = [r for r in refs if not r.startswith("/api/")]
            self.assertEqual(internal, [], page.name)

    def test_new_pages_wired(self):
        index = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("/academy", index)
        self.assertNotIn('src="/static/', index)
        self.assertFalse((self.out / "academy.html").exists())

    def test_static_config(self):
        config = (self.out / "static" / "config.js").read_text(encoding="utf-8")
        self.assertIn("static: true", config)
        self.assertIn('appUrl: "chat.html"', config)
        self.assertNotIn("apiBase: \"http", config)

    def test_auth_modes(self):
        self.assertIn('data-mode="login"', (self.out / "login.html").read_text(encoding="utf-8"))
        self.assertIn('data-mode="signup"', (self.out / "signup.html").read_text(encoding="utf-8"))

    def test_manifest_relative(self):
        import json
        manifest = json.loads((self.out / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["start_url"], "chat.html")
        for icon in manifest["icons"]:
            self.assertFalse(icon["src"].startswith("/"), icon["src"])

    def test_deterministic_counts(self):
        self.assertEqual(self.info["pages"], 12)
        self.assertGreater(self.info["files"], 30)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.chdir(ROOT)


if __name__ == "__main__":
    unittest.main()
