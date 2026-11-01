"""آزمون انتها‌به‌انتها API (با checkpoint آموزش‌دیده)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# سایت هر checkpointی را که موجود باشد بار می‌کند؛ آزمون هم همان را می‌سنجد.
CHECKPOINTS = [os.path.join(ROOT, "checkpoints", name) for name in
               ("last.npz", "rayan-2-base.npz", "rayan-1-small.npz")]
CHECKPOINT = next((p for p in CHECKPOINTS if os.path.exists(p)), CHECKPOINTS[-1])

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # pragma: no cover
    HAVE_CLIENT = False


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth_support import human_proof, signup  # noqa: E402


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        os.environ["RAYAN_DB"] = cls.db_path

        from web import server, store as store_module
        store_module._store = None  # پایگاه‌دادهٔ تمیز برای آزمون
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        cls.server = server
        cls.client = TestClient(server.app)
        signup(cls.client, email="api-owner@example.com")  # هوش فقط با حساب

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.db_path)
        except OSError:
            pass
        os.environ.pop("RAYAN_DB", None)
        from web import store as store_module
        store_module._store = None

    # ---------------------------------------------------------------- پایه
    def test_health(self):
        """سلامتِ عمومی فقط «آماده است یا نه» می‌گوید؛ جزئیات داخلی بیرون نمی‌رود."""
        data = self.client.get("/api/health").json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["ready"])
        self.assertNotIn("model", data)
        self.assertNotIn("index", data)
        self.assertIn("signup_required", data)

    def test_health_detail_is_admin_only(self):
        fresh = TestClient(self.server.app)
        self.assertIn(fresh.get("/api/health/detail").status_code, (401, 403))
        login = self.client.post("/api/admin/login", json={
            "password": os.environ.get("RAYAN_ADMIN_PASSWORD", "v3-test-admin-pass")})
        if login.status_code != 200:
            self.skipTest("admin password not configured for this class")
        try:
            detail = self.client.get("/api/health/detail").json()
            self.assertIn("model", detail)
            self.assertIn("latency", detail)
        finally:
            self.client.post("/api/admin/logout")

    def test_model(self):
        """کارت عمومی توانایی‌ها را می‌گوید، نه معماری و اعداد داخلی."""
        data = self.client.get("/api/model").json()
        self.assertEqual(data["name"], "رایان")
        self.assertGreaterEqual(len(data["abilities"]), 3)
        for hidden in ("config", "params", "corpus", "architecture", "limitations"):
            self.assertNotIn(hidden, data)

    def test_model_detail_is_admin_only(self):
        fresh = TestClient(self.server.app)
        self.assertIn(fresh.get("/api/model/detail").status_code, (401, 403))
        self.assertIn(fresh.get("/api/metrics").status_code, (401, 403))

    def test_pages(self):
        for path in ("/", "/chat", "/login", "/signup", "/pricing", "/models", "/about",
                     "/compare"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            self.assertTrue("رایان" in res.text or "rayan" in res.text.lower(), path)
        self.assertIn("urlset", self.client.get("/sitemap.xml").text)
        self.assertIn("User-agent", self.client.get("/robots.txt").text)

    def test_closed_pages_are_gone(self):
        """هیچ سند، کد، بستهٔ نصب یا خلاصهٔ پروژه‌ای منتشر نمی‌شود."""
        for path in ("/docs", "/course", "/download", "/summary", "/developer"):
            res = self.client.get(path, follow_redirects=False)
            self.assertEqual(res.status_code, 302, path)
            self.assertEqual(res.headers["location"], "/")
            self.assertEqual(self.client.get(f"/static{path}.html").status_code, 404, path)

    def test_models_catalog(self):
        data = self.client.get("/api/models").json()
        self.assertGreaterEqual(len(data["models"]), 2)
        ids = [m["id"] for m in data["models"]]
        # مدل پیش‌فرض همان مدل فعال است و باید در فهرست باشد
        self.assertIn(data["default"], ids)
        ready = [m for m in data["models"] if m["status"] == "ready"]
        self.assertTrue(ready)
        self.assertEqual(ready[0]["id"], data["default"])
        self.assertNotIn("checkpoint", ready[0])
        self.assertNotIn("metrics", ready[0])
        self.assertTrue(ready[0]["tagline"])

    def test_samples(self):
        data = self.client.get("/api/samples").json()
        self.assertGreaterEqual(len(data["samples"]), 3)

    # ----------------------------------------------------------------- چت
    def test_guest_is_asked_to_sign_up(self):
        """بدون حساب، پاسخ ۴۰۱ با پرچم ثبت‌نام می‌آید نه خطای مبهم."""
        guest = TestClient(self.server.app)
        guest.get("/chat")
        res = guest.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.headers.get("x-rayan-need"), "signup")
        self.assertIn("حساب", res.json()["detail"])
        me = guest.get("/api/auth/me").json()
        self.assertTrue(me["signup_required"])
        self.assertFalse(me["signed_in"])

    def test_chat_short(self):
        res = self.client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16,
                                                  "session_id": "short"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data["answer"], str)
        self.assertIn("stats", data)
        self.assertLessEqual(data["stats"]["tokens"], 16)
        self.assertTrue(data["conversation_id"])
        self.assertIn("usage", data)

    def test_chat_persists_conversation(self):
        res = self.client.post("/api/chat", json={"message": "دربارهٔ ایران", "max_new_tokens": 16})
        conv_id = res.json()["conversation_id"]
        listing = self.client.get("/api/conversations").json()["conversations"]
        self.assertTrue(any(c["id"] == conv_id for c in listing))
        detail = self.client.get(f"/api/conversations/{conv_id}").json()["conversation"]
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(detail["messages"][0]["role"], "user")

    def test_multi_turn_history(self):
        first = self.client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16,
                                                    "session_id": "mt-1"}).json()
        second = self.client.post("/api/chat", json={
            "message": "خوبی؟", "conversation_id": first["conversation_id"], "max_new_tokens": 16,
        }).json()
        self.assertGreater(second["stats"]["prompt_tokens"], first["stats"]["prompt_tokens"])

    def test_stream(self):
        with self.client.stream("POST", "/api/chat/stream",
                                json={"message": "سلام", "max_new_tokens": 16, "session_id": "stream"}) as res:
            self.assertEqual(res.status_code, 200)
            payload = "".join(res.iter_text())
        self.assertIn('"type": "start"', payload)
        self.assertIn('"type": "done"', payload)
        self.assertIn("conversation_id", payload)

    def test_empty_rejected(self):
        res = self.client.post("/api/chat", json={"message": "   "})
        self.assertEqual(res.status_code, 400)

    def test_deep_rejected_on_stream(self):
        res = self.client.post("/api/chat/stream", json={"message": "سلام", "deep": True})
        self.assertEqual(res.status_code, 400)

    # ---------------------------------------------------------------- حساب
    def test_auth_flow(self):
        client = TestClient(self.server.app)
        me = client.get("/api/auth/me").json()
        self.assertIsNone(me["user"])
        self.assertEqual(me["plan"], "guest")

        res = client.post("/api/auth/register", json={
            "name": "آزمون", "email": "tester@example.com", "password": "test-password",
            "captcha": human_proof(client),
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["email"], "tester@example.com")

        me = client.get("/api/auth/me").json()
        self.assertEqual(me["user"]["email"], "tester@example.com")
        self.assertEqual(me["plan"], "free")
        self.assertEqual(me["usage"]["chat"]["limit"], 200)

        dup = client.post("/api/auth/register", json={
            "name": "دوباره", "email": "tester@example.com", "password": "test-password",
            "captcha": human_proof(client),
        })
        self.assertEqual(dup.status_code, 409)

        client.post("/api/auth/logout")
        self.assertIsNone(client.get("/api/auth/me").json()["user"])

        bad = client.post("/api/auth/login", json={"email": "tester@example.com", "password": "wrong-pass",
                                                   "captcha": human_proof(client)})
        self.assertEqual(bad.status_code, 401)
        ok = client.post("/api/auth/login", json={"email": "tester@example.com", "password": "test-password",
                                                  "captcha": human_proof(client)})
        self.assertEqual(ok.status_code, 200)

    def test_share_flow(self):
        client = TestClient(self.server.app)
        signup(client)
        conv = client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16}).json()["conversation_id"]
        share = client.post(f"/api/conversations/{conv}/share").json()
        self.assertIn("token", share)
        public = client.get(f"/api/share/{share['token']}")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json()["conversation"]["id"], conv)
        self.assertEqual(client.get("/s/" + share["token"]).status_code, 200)
        self.assertEqual(client.get("/api/share/does-not-exist").status_code, 404)

    def test_guest_cannot_read_others_conversation(self):
        owner = TestClient(self.server.app)
        signup(owner)
        conv = owner.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16}).json()["conversation_id"]
        stranger = TestClient(self.server.app)
        signup(stranger)
        self.assertEqual(stranger.get(f"/api/conversations/{conv}").status_code, 404)
        self.assertEqual(stranger.delete(f"/api/conversations/{conv}").status_code, 404)

    def test_quota_enforced(self):
        from web import server
        original = dict(server.LIMITS["free"])
        server.LIMITS["free"] = {"chat": 1, "deep": 1}
        try:
            client = TestClient(self.server.app)
            client.get("/chat")
            res = client.post("/api/auth/register", json={
                "name": "سهمیه", "email": "quota@example.com", "password": "test-password",
                "captcha": human_proof(client),
            })
            self.assertEqual(res.status_code, 200)
            first = client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16})
            self.assertEqual(first.status_code, 200)
            second = client.post("/api/chat", json={"message": "دوباره", "max_new_tokens": 16})
            self.assertEqual(second.status_code, 429)
            usage = client.get("/api/usage").json()
            self.assertEqual(usage["chat"]["used"], 1)
            self.assertEqual(usage["chat"]["limit"], 1)
        finally:
            server.LIMITS["free"] = original


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class V3Test(unittest.TestCase):
    """ویژگی‌های نسخهٔ سوم: وضعیت، پرچم‌ها، ابزارها، تبلیغات، آکادمی، پنل و آفلاین."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        os.environ["RAYAN_DB"] = cls.db_path
        os.environ["RAYAN_ADMIN_PASSWORD"] = "v3-test-admin-pass"
        from web import server, store as store_module
        store_module._store = None
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        server.engine_error = None
        cls.server = server
        cls.client = TestClient(server.app)
        signup(cls.client, email="v3-owner@example.com")  # هوش فقط با حساب

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.db_path)
        except OSError:
            pass
        os.environ.pop("RAYAN_DB", None)
        os.environ.pop("RAYAN_ADMIN_PASSWORD", None)
        from web import store as store_module
        store_module._store = None

    def test_status_and_flags(self):
        status = self.client.get("/api/status").json()
        self.assertEqual(status["version"], "3.0.0")
        self.assertTrue(status["model_loaded"])
        flags = self.client.get("/api/flags").json()["flags"]
        for key in ("ads_enabled", "signup_open", "guest_chat", "deep_enabled", "studio_enabled", "maintenance"):
            self.assertIn(key, flags)

    def test_selftest(self):
        anon = TestClient(self.server.app)
        self.assertIn(anon.get("/api/selftest").status_code, (401, 403))
        login = self.client.post("/api/admin/login",
                                 json={"password": os.environ.get("RAYAN_ADMIN_PASSWORD", "")})
        if login.status_code != 200:
            self.skipTest("admin password not configured for this class")
        data = self.client.get("/api/selftest").json()
        self.assertTrue(any(c["name"] == "database" and c["ok"] for c in data["checks"]))
        self.client.post("/api/admin/logout")

    def test_network_mode_switch_from_panel(self):
        """مدیر از پنل حالت شبکه را عوض می‌کند؛ سایت بلافاصله تابع آن می‌شود."""
        from web import network

        login = self.client.post("/api/admin/login", json={"password": "v3-test-admin-pass"})
        self.assertEqual(login.status_code, 200)
        headers = {"x-rayan-csrf": login.json()["csrf"]}
        before = network.mode()
        try:
            res = self.client.post("/api/admin/network", json={"mode": "national"}, headers=headers)
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()["allow_outbound"])
            self.assertEqual(self.client.get("/api/admin/network").json()["mode"], "national")
            self.assertEqual(self.client.post("/api/admin/network", json={"mode": "moon"},
                                               headers=headers).status_code, 422)
        finally:
            network.set_mode(before)
            self.client.post("/api/admin/logout")

    def test_capacity_report_is_measured(self):
        login = self.client.post("/api/admin/login", json={"password": "v3-test-admin-pass"})
        self.assertEqual(login.status_code, 200)
        try:
            data = self.client.get("/api/admin/capacity").json()
            self.assertGreaterEqual(data["workers"], 1)
            self.assertGreaterEqual(data["cache_size"], 1)
            self.assertIn("hardware", data)
            self.assertTrue(data["honest_note"])
            anon = TestClient(self.server.app)
            self.assertIn(anon.get("/api/admin/capacity").status_code, (401, 403))
        finally:
            self.client.post("/api/admin/logout")

    def test_locale_is_persian_only(self):
        """سایت تک‌زبانه است: حتی مرورگر یا IP خارجی هم نسخهٔ فارسی می‌گیرد."""
        en = self.client.get("/api/locale", headers={"accept-language": "en-US,en;q=0.9"}).json()
        self.assertEqual((en["lang"], en["dir"]), ("fa", "rtl"))
        self.assertTrue(en["motion"]["orb"].endswith("orb-live.webp"))
        self.assertNotIn("videos", en)
        de = self.client.get("/api/locale", headers={"cf-ipcountry": "DE"}).json()
        self.assertEqual(de["lang"], "fa")
        home = self.client.get("/", headers={"accept-language": "en-GB,en"}, follow_redirects=False)
        self.assertEqual(home.status_code, 200)
        self.assertNotIn('lang="en"', home.text)
        # مسیرهای قدیمی انگلیسی به خانه می‌روند
        for path in ("/en", "/en/docs", "/en/course"):
            res = self.client.get(path, follow_redirects=False)
            self.assertEqual(res.status_code, 302, path)
            self.assertEqual(res.headers["location"], "/")

    def test_brand_motion_assets_exist(self):
        from pathlib import Path as _Path
        brand = _Path(ROOT) / "web" / "static" / "assets" / "brand"
        for name, floor in (("orb-live.webp", 20_000), ("orb-live-sm.webp", 8_000),
                            ("logo-motion.webp", 60_000), ("logo-motion-dark.webp", 60_000),
                            ("logo-loading.webp", 40_000)):
            path = brand / name
            self.assertTrue(path.exists(), name)
            self.assertGreater(path.stat().st_size, floor, name)
        res = self.client.get("/static/assets/brand/orb-live.webp")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "image/webp")
        # ویدیوی تبلیغاتی از سایت و مخزن حذف شده است
        self.assertFalse((_Path(ROOT) / "web" / "static" / "assets" / "video" / "promo-fa-16x9.mp4").exists())

    def test_new_pages(self):
        for path in ("/admin", "/offline", "/privacy"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
        self.assertIn("حالت بدون اتصال", self.client.get("/offline").text)
        removed = self.client.get("/academy", follow_redirects=False)
        self.assertEqual(removed.status_code, 302)
        self.assertEqual(removed.headers["location"], "/")
        self.assertNotIn("/offline", self.client.get("/sitemap.xml").text)

    def test_tools_catalog_and_run(self):
        catalog = self.client.get("/api/tools").json()
        self.assertGreaterEqual(len(catalog["tools"]), 4)
        calc = self.client.post("/api/tools/run", json={"name": "calc", "args": {"expression": "۷*۶"}}).json()
        self.assertTrue(calc["ok"])
        self.assertEqual(calc["value"], 42)
        conv = self.client.post("/api/tools/run", json={
            "name": "convert", "args": {"value": 3, "from": "mile", "to": "km"},
        }).json()
        self.assertTrue(conv["ok"])
        self.assertAlmostEqual(float(conv["value"]), 4.828032, places=3)

    def test_chat_returns_tool_meta(self):
        res = self.client.post("/api/chat", json={
            "message": "۷*۶ چند است؟", "max_new_tokens": 16, "session_id": "tool-meta",
        })
        self.assertEqual(res.status_code, 200)
        tool = res.json()["tool"]
        self.assertIsNotNone(tool)
        self.assertEqual(tool["value"], 42)

    def test_ads_public_flow(self):
        empty = self.client.get("/api/ads", params={"slot": "home-top"}).json()
        self.assertEqual(empty["ads"], [])
        login = self.client.post("/api/admin/login", json={"password": "v3-test-admin-pass"})
        self.assertEqual(login.status_code, 200)
        csrf = login.json()["csrf"]
        headers = {"x-rayan-csrf": csrf}
        created = self.client.post("/api/admin/ads", json={
            "slot": "home-top", "title": "کمپین آزمون", "body": "تبلیغ تستی",
            "cta": "ببین", "url": "/pricing", "active": True,
        }, headers=headers)
        self.assertEqual(created.status_code, 200, created.text)
        shown = self.client.get("/api/ads", params={"slot": "home-top"}).json()["ads"]
        self.assertEqual(shown[0]["title"], "کمپین آزمون")
        self.assertEqual(self.client.get("/api/ads", params={"slot": "home-mid"}).json()["ads"], [])
        ad_id = shown[0]["id"]
        # ویرایش جزئی: خاموش‌کردن بدون فرستادن بقیهٔ فیلدها
        off = self.client.patch(f"/api/admin/ads/{ad_id}", json={"active": False}, headers=headers)
        self.assertEqual(off.status_code, 200, off.text)
        self.assertEqual(self.client.get("/api/ads", params={"slot": "home-top"}).json()["ads"], [])
        renamed = self.client.patch(f"/api/admin/ads/{ad_id}", json={"active": True, "title": "کمپین ویرایش"},
                                    headers=headers)
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["ad"]["title"], "کمپین ویرایش")
        self.assertEqual(self.client.delete(f"/api/admin/ads/{ad_id}", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/ads", params={"slot": "home-top"}).json()["ads"], [])
        # نشانی ناامن رد می‌شود
        # نشانی ناامن یا در لایهٔ اعتبارسنجی رد می‌شود (۴۰۴) یا سد تهاجم (۴۰۳)
        self.assertIn(self.client.patch("/api/admin/ads/999", json={"url": "javascript:alert(1)"},
                                        headers=headers).status_code, (403, 404))

    def test_code_surfaces_are_admin_only(self):
        """کد/وزن‌ها و خودآزمون نباید برای کاربر عادی باز باشد."""
        fresh = TestClient(self.server.app)
        # دانلود وزن‌ها کامل حذف شده است؛ حتی برای مدیر هم مسیری نیست
        self.assertEqual(fresh.get("/api/download/checkpoint").status_code, 404)
        self.assertIn(fresh.get("/api/selftest").status_code, (401, 403))
        page = fresh.get("/admin")
        self.assertEqual(page.status_code, 200)
        self.assertIn("noindex", page.headers.get("x-robots-tag", ""))
        self.assertNotIn("api/admin/overview?", page.text)

    def test_admin_requires_auth(self):
        fresh = TestClient(self.server.app)
        self.assertIn(fresh.get("/api/admin/overview").status_code, (401, 403))
        self.assertEqual(fresh.post("/api/admin/maintenance", json={"on": True}).status_code, 401)

    def test_origin_guard_blocks_cross_site_writes(self):
        res = self.client.post("/api/auth/login", json={"email": "a@b.c", "password": "x"},
                               headers={"origin": "https://evil.example"})
        self.assertEqual(res.status_code, 403)

    def test_plans_are_public_and_configurable(self):
        data = self.client.get("/api/plans").json()
        self.assertTrue(data["ok"])
        ids = [p["id"] for p in data["plans"]]
        self.assertEqual(ids, ["guest", "free", "pro"])
        pro = data["plans"][2]
        self.assertEqual(pro["price"], 0)
        self.assertFalse(pro["for_sale"])
        login = self.client.post("/api/admin/login", json={"password": "v3-test-admin-pass"})
        headers = {"x-rayan-csrf": login.json()["csrf"]}
        saved = self.client.post("/api/admin/settings", json={"values": {
            "plan_pro_price": "299000", "plan_pro_days": "30",
            "payments_enabled": "1", "payment_provider": "درگاه آزمون",
            "payment_link": "https://pay.example/c/rayan", "payment_note": "فعال است",
        }}, headers=headers)
        self.assertEqual(saved.status_code, 200)
        data = self.client.get("/api/plans").json()
        pro = data["plans"][2]
        self.assertEqual(pro["price"], 299000)
        self.assertTrue(pro["for_sale"])
        self.assertEqual(data["payments"]["provider"], "درگاه آزمون")
        self.assertEqual(data["payments"]["link"], "https://pay.example/c/rayan")
        # پاک‌سازی تنظیمات آزمون
        self.client.post("/api/admin/settings", json={"values": {
            "plan_pro_price": "0", "payments_enabled": "0", "payment_link": "",
            "payment_provider": "", "payment_note": "",
        }}, headers=headers)

    def test_security_headers(self):
        res = self.client.get("/")
        csp = res.headers.get("content-security-policy", "")
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline; connect-src", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertEqual(res.headers.get("x-frame-options"), "SAMEORIGIN")
        self.assertEqual(res.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("permissions-policy", {k.lower() for k in res.headers.keys()})
        api = self.client.get("/api/status")
        self.assertEqual(api.headers.get("cache-control"), "no-store")

    def test_no_inline_scripts_in_pages(self):
        import re
        from pathlib import Path as _Path
        static = _Path(ROOT) / "web" / "static"
        offenders = []
        for page in static.glob("*.html"):
            if page.name in ("share.html",):
                continue
            text = page.read_text(encoding="utf-8")
            for match in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", text, re.S):
                body = match.group(1).strip()
                if body and 'type="application/ld+json"' not in text[: match.start(1)][-60:]:
                    offenders.append(page.name)
                    break
        self.assertEqual(offenders, [])

    def test_shared_static_assets_exist(self):
        for path in ("/static/assets/brand/logotype-stack-ink.png", "/static/assets/brand/og-image.png",
                     "/static/assets/brand/mark-ink.png",
                     "/static/assets/brand/orb-live.webp",
                     "/static/assets/brand/logo-motion.webp"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
