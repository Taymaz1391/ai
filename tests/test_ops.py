"""آزمون اتاق فرمان (کانال دستور مالک) و ورود یکپارچهٔ پنل مدیریت.

    python -m pytest tests/test_ops.py -q
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # pragma: no cover
    HAVE_CLIENT = False

CHECKPOINT = next((os.path.join(ROOT, "checkpoints", name) for name in
                   ("last.npz", "rayan-2-base.npz", "rayan-1-small.npz")
                   if os.path.exists(os.path.join(ROOT, "checkpoints", name))), "")


class OpsQueueTest(unittest.TestCase):
    """پروندهٔ فقط-افزودنی: دستور ثبت می‌شود، پاسخ اضافه می‌شود، وضعیت می‌رسد."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["RAYAN_OPS_DIR"] = self.tmp.name
        from web import ops
        self.ops = ops
        import importlib
        importlib.reload(ops)
        self.ops.DATA_DIR = self.tmp.name
        self.ops.QUEUE = os.path.join(self.tmp.name, "orders.jsonl")

    def tearDown(self):
        os.environ.pop("RAYAN_OPS_DIR", None)
        self.tmp.cleanup()

    def test_add_and_list(self):
        row = self.ops.add("رنگ دکمه‌ها را عوض کن", kind="order", author="مالک")
        self.assertTrue(row["id"].startswith("op_"))
        self.assertEqual(row["status"], "pending")
        rows = self.ops.listing()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "رنگ دکمه‌ها را عوض کن")
        self.assertEqual(rows[0]["replies"], [])

    def test_reply_updates_status_and_keeps_history(self):
        row = self.ops.add("صفحهٔ تعرفه را ساده کن")
        self.ops.reply(row["id"], "انجام شد؛ نسخهٔ تازه منتشر شد.", status="done")
        rows = self.ops.listing()
        self.assertEqual(rows[0]["status"], "done")
        self.assertEqual(rows[0]["replies"][0]["text"], "انجام شد؛ نسخهٔ تازه منتشر شد.")
        # پرونده فقط-افزودنی است: دو خط نوشته شده، یک دستور خوانده می‌شود
        with open(self.ops.QUEUE, encoding="utf-8") as fh:
            self.assertEqual(len([line for line in fh if line.strip()]), 2)

    def test_pending_only_counts_open_orders(self):
        first = self.ops.add("یک")
        self.ops.add("دو")
        self.ops.reply(first["id"], "شد", status="done")
        pending = self.ops.pending()
        self.assertEqual([row["text"] for row in pending], ["دو"])
        stats = self.ops.stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["done"], 1)
        self.assertEqual(stats["pending"], 1)

    def test_long_and_empty_text_handled(self):
        with self.assertRaises(ValueError):
            self.ops.add("   ")
        row = self.ops.add("ب" * 5000)
        self.assertLessEqual(len(row["text"]), 2000)

    def test_bad_kind_and_status_rejected(self):
        with self.assertRaises(ValueError):
            self.ops.add("متن", kind="shell")
        with self.assertRaises(ValueError):
            self.ops.reply("op_x", "پاسخ", status="exploded")

    def test_corrupt_line_is_skipped(self):
        os.makedirs(self.tmp.name, exist_ok=True)
        with open(self.ops.QUEUE, "w", encoding="utf-8") as fh:
            fh.write('{"id": "op_a", "at": 1, "text": "سالم", "status": "pending"}\n')
            fh.write("این خط خراب است\n")
            fh.write(json.dumps({"id": "op_b", "at": 2, "text": "دومی"}) + "\n")
        self.assertEqual(len(self.ops.listing()), 2)


@unittest.skipUnless(HAVE_CLIENT and CHECKPOINT, "TestClient یا checkpoint موجود نیست")
class AdminAccessTest(unittest.TestCase):
    """ورود پنل با گذرواژهٔ مالک؛ اتاق فرمان پشت همان نشست."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        os.environ["RAYAN_DB"] = os.path.join(cls.tmpdir.name, "test.sqlite3")
        os.environ["RAYAN_OPS_DIR"] = os.path.join(cls.tmpdir.name, "ops")
        os.environ.pop("RAYAN_ADMIN_PASSWORD", None)
        os.environ.pop("RAYAN_ADMIN_HASH", None)
        os.environ.pop("RAYAN_ADMIN_SALT", None)
        os.environ["RAYAN_OWNER_PASSWORD"] = "13911391"
        from web import admin as admin_module
        from web import ops as ops_module
        from web import owner as owner_module
        from web import server, store as store_module
        store_module._store = None
        owner_module.OWNER_FILE = os.path.join(cls.tmpdir.name, "owner.json")
        admin_module.ADMIN_FILE = os.path.join(cls.tmpdir.name, "admin.json")
        ops_module.DATA_DIR = os.path.join(cls.tmpdir.name, "ops")
        ops_module.QUEUE = os.path.join(ops_module.DATA_DIR, "orders.jsonl")
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        cls.server = server
        cls.client = TestClient(server.app)
        cls.client.get("/admin")
        cls.admin_module = admin_module

    @classmethod
    def tearDownClass(cls):
        for key in ("RAYAN_DB", "RAYAN_OPS_DIR", "RAYAN_OWNER_PASSWORD"):
            os.environ.pop(key, None)
        from web import store as store_module
        store_module._store = None
        cls.tmpdir.cleanup()

    def test_owner_password_opens_console(self):
        res = self.client.post("/api/admin/login", json={"password": "13911391"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json().get("csrf"))
        session = self.client.get("/api/admin/session").json()
        self.assertTrue(session["authenticated"])

    def test_wrong_password_refused(self):
        client = TestClient(self.server.app)
        client.get("/admin")
        res = client.post("/api/admin/login", json={"password": "not-the-password"})
        self.assertEqual(res.status_code, 401)

    def test_order_round_trip_through_api(self):
        login = self.client.post("/api/admin/login", json={"password": "13911391"}).json()
        csrf = login["csrf"]
        bad = self.client.post("/api/admin/ops", json={"text": "بدون توکن امنیتی"})
        self.assertEqual(bad.status_code, 403)

        ok = self.client.post("/api/admin/ops", json={"text": "فونت سایت را بزرگ‌تر کن"},
                              headers={"x-rayan-csrf": csrf})
        self.assertEqual(ok.status_code, 200, ok.text)
        order_id = ok.json()["order"]["id"]

        listed = self.client.get("/api/admin/ops").json()
        self.assertEqual(listed["orders"][0]["id"], order_id)
        self.assertEqual(listed["stats"]["pending"], 1)

        from web import ops as ops_module
        ops_module.reply(order_id, "انجام شد", status="done")
        again = self.client.get("/api/admin/ops").json()
        self.assertEqual(again["orders"][0]["status"], "done")
        self.assertEqual(again["stats"]["pending"], 0)

    def test_ops_requires_admin(self):
        anon = TestClient(self.server.app)
        self.assertEqual(anon.get("/api/admin/ops").status_code, 401)
        self.assertEqual(anon.post("/api/admin/ops", json={"text": "سلام"}).status_code, 401)

    def test_reload_endpoint_is_guarded(self):
        anon = TestClient(self.server.app)
        self.assertEqual(anon.post("/api/admin/reload").status_code, 401)


if __name__ == "__main__":
    unittest.main()
