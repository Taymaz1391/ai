"""آزمون پایگاه‌دادهٔ رایان (کاربر، نشست، گفتگو، اشتراک، سهمیه)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web.store import Store  # noqa: E402


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.store = Store(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_user_lifecycle(self):
        user = self.store.create_user("A@Example.com", "secret-pass", "آزمون")
        self.assertIsNotNone(user)
        self.assertEqual(user["email"], "a@example.com")
        self.assertIsNone(self.store.create_user("a@example.com", "other"))

        self.assertIsNone(self.store.verify_user("a@example.com", "wrong"))
        self.assertEqual(self.store.verify_user("a@example.com", "secret-pass")["id"], user["id"])

    def test_password_hashing_is_salted(self):
        u1 = self.store.create_user("x@a.com", "samepassword")
        u2 = self.store.create_user("y@a.com", "samepassword")
        rows = self.store._all("SELECT pw_hash, pw_salt FROM users")
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["pw_hash"], rows[1]["pw_hash"])
        dumped = "".join(str(dict(r)) for r in rows)
        self.assertNotIn("samepassword", dumped)
        self.assertNotEqual(u1["id"], u2["id"])

    def test_sessions(self):
        user = self.store.create_user("s@a.com", "password-123")
        token = self.store.create_session(user_id=user["id"], ip="1.2.3.4")
        self.assertEqual(self.store.session_user(token)["id"], user["id"])
        self.store.delete_session(token)
        self.assertIsNone(self.store.session_user(token))
        self.assertIsNone(self.store.session_user("bogus-token"))

    def test_conversations_and_ownership(self):
        user = self.store.create_user("c@a.com", "password-123")
        owner = {"user_id": user["id"], "guest_id": None}
        conv = self.store.create_conversation(owner, "عنوان آزمایشی")
        self.assertTrue(self.store.owns(owner, conv["id"]))
        self.assertFalse(self.store.owns({"user_id": None, "guest_id": "guest-1"}, conv["id"]))

        self.store.add_message(conv["id"], "user", "سلام")
        self.store.add_message(conv["id"], "assistant", "درود", {"deep": False})
        messages = self.store.get_messages(conv["id"])
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[1]["meta"], {"deep": False})

        self.assertEqual(len(self.store.list_conversations(owner)), 1)
        self.store.rename_conversation(conv["id"], "نام تازه")
        self.assertEqual(self.store.get_conversation_meta(conv["id"])["title"], "نام تازه")
        self.store.delete_conversation(conv["id"])
        self.assertEqual(self.store.list_conversations(owner), [])

    def test_guest_isolation(self):
        a = {"user_id": None, "guest_id": "guest-a"}
        b = {"user_id": None, "guest_id": "guest-b"}
        conv = self.store.create_conversation(a, "مهمان الف")
        self.assertTrue(self.store.owns(a, conv["id"]))
        self.assertFalse(self.store.owns(b, conv["id"]))
        self.assertEqual(len(self.store.list_conversations(b)), 0)

    def test_share_roundtrip(self):
        owner = {"user_id": None, "guest_id": "guest-s"}
        conv = self.store.create_conversation(owner, "قابل اشتراک")
        self.store.add_message(conv["id"], "user", "پرسش")
        token = self.store.share(conv["id"])
        self.assertEqual(token, self.store.share(conv["id"]))  # idempotent
        shared = self.store.shared_conversation(token)
        self.assertEqual(shared["title"], "قابل اشتراک")
        self.assertEqual(shared["views"], 1)
        self.store.unshare(conv["id"])
        self.assertIsNone(self.store.shared_conversation(token))

    def test_usage_counters(self):
        user = {"user_id": 7, "guest_id": None}
        for _ in range(3):
            self.store.record_event("chat", user_id=7, ip="9.9.9.9")
        self.assertEqual(self.store.usage_today("chat", user_id=7, ip="9.9.9.9"), 3)
        self.assertEqual(self.store.usage_today("deep", user_id=7, ip="9.9.9.9"), 0)
        self.store.record_event("chat", guest_id="g1", ip="5.5.5.5")
        self.assertEqual(self.store.usage_today("chat", guest_id="g1", ip="5.5.5.5"), 1)

    def test_public_stats(self):
        self.store.create_user("stats@a.com", "password-123")
        owner = {"user_id": 1, "guest_id": None}
        conv = self.store.create_conversation(owner)
        self.store.add_message(conv["id"], "assistant", "پاسخ")
        stats = self.store.public_stats()
        self.assertEqual(stats["users"], 1)
        self.assertEqual(stats["conversations"], 1)
        self.assertEqual(stats["answers"], 1)


if __name__ == "__main__":
    unittest.main()
