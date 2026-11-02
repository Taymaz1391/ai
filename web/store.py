"""ذخیره‌سازی رایان — SQLite استاندارد پایتون، بدون وابستگی بیرونی.

جداول: کاربران، نشست‌ها، گفتگوها، پیام‌ها، سهام عمومی، رویدادهای مصرف و بازخورد.
همهٔ زمان‌ها Unix epoch (ثانیه) و همهٔ متن‌ها UTF-8 هستند.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from typing import Any, Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "rayan.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL DEFAULT '',
    pw_hash     TEXT NOT NULL,
    pw_salt     TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'free',
    role        TEXT NOT NULL DEFAULT 'user',
    verified    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    last_seen   REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER,
    guest_id    TEXT,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    user_agent  TEXT NOT NULL DEFAULT '',
    ip          TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER,
    guest_id    TEXT,
    title       TEXT NOT NULL DEFAULT 'گفتگوی تازه',
    model       TEXT NOT NULL DEFAULT 'rayan-1-small',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    pinned      INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    share_token TEXT
);
CREATE INDEX IF NOT EXISTS idx_conv_owner ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_guest ON conversations(guest_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id     TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id, id);
CREATE TABLE IF NOT EXISTS shares (
    token       TEXT PRIMARY KEY,
    conv_id     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    views       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    guest_id    TEXT,
    ip          TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at);
CREATE TABLE IF NOT EXISTS ads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slot        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    cta         TEXT NOT NULL DEFAULT 'بیشتر بدانید',
    url         TEXT NOT NULL,
    weight      INTEGER NOT NULL DEFAULT 1,
    active      INTEGER NOT NULL DEFAULT 1,
    views       INTEGER NOT NULL DEFAULT 0,
    clicks      INTEGER NOT NULL DEFAULT 0,
    starts_at   REAL NOT NULL DEFAULT 0,
    ends_at     REAL NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ads_slot ON ads(slot, active);
CREATE TABLE IF NOT EXISTS audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    actor       TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL,
    target      TEXT NOT NULL DEFAULT '',
    detail      TEXT NOT NULL DEFAULT '',
    ip          TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit(created_at DESC);
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    csrf        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    ip          TEXT NOT NULL DEFAULT '',
    user_agent  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_key ON login_attempts(key, created_at);
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER,
    user_id     INTEGER,
    value       INTEGER NOT NULL,
    comment     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    prefix      TEXT NOT NULL,
    key_hash    TEXT NOT NULL UNIQUE,
    scopes      TEXT NOT NULL DEFAULT 'chat',
    created_at  REAL NOT NULL,
    last_used   REAL NOT NULL DEFAULT 0,
    revoked_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_keys_user ON api_keys(user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS support_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    plan        TEXT NOT NULL DEFAULT 'pro',
    topic       TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL DEFAULT '',
    user_id     INTEGER,
    ip          TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new'
);
"""


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class Store:
    """دسترسی هم‌روند‌امن به پایگاه‌داده."""

    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self._conn = _connect(path)
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """ستون‌هایی که در نسخه‌های پیشین نبودند، بی‌آنکه داده‌ای از دست برود."""
        have = {row["name"] for row in self._conn.execute("PRAGMA table_info(users)")}
        for name, ddl in (("role", "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"),
                          ("verified", "ALTER TABLE users ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")):
            if name not in have:
                self._conn.execute(ddl)
        self._conn.execute("CREATE TABLE IF NOT EXISTS email_codes ("
                           "email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, salt TEXT NOT NULL,"
                           " expires_at REAL NOT NULL, sent_at REAL NOT NULL, tries INTEGER NOT NULL DEFAULT 0)")
        self._conn.commit()

    # ---------------------------------------------------------------- ابزار
    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def _one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def _all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    # -------------------------------------------------------------- کاربران
    @staticmethod
    def _hash(password: str, salt: str) -> str:
        return hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                              n=2 ** 14, r=8, p=1, dklen=32).hex()

    def create_user(self, email: str, password: str, name: str = "") -> dict | None:
        email = email.strip().lower()
        salt = secrets.token_hex(16)
        pw_hash = self._hash(password, salt)
        now = time.time()
        try:
            cur = self._exec(
                "INSERT INTO users(email, name, pw_hash, pw_salt, plan, role, created_at, last_seen)"
                " VALUES(?,?,?,?, 'free', 'user', ?, ?)",
                (email, name.strip()[:60], pw_hash, salt, now, now),
            )
        except sqlite3.IntegrityError:
            return None
        return self.get_user(int(cur.lastrowid))

    def set_owner(self, user_id: int) -> None:
        """یک کاربر را مالک می‌کند (فقط یکی در کل سامانه)."""
        self._exec("UPDATE users SET role='user' WHERE role='owner' AND id<>?", (user_id,))
        self._exec("UPDATE users SET role='owner' WHERE id=?", (user_id,))

    def user_by_email(self, email: str) -> dict | None:
        row = self._one("SELECT id,email,name,plan,role,verified,created_at FROM users "
                        "WHERE email=?", ((email or "").strip().lower(),))
        return dict(row) if row else None

    # ------------------------------------------------------- کد تأیید ایمیل
    def save_code(self, email: str, code_hash: str, salt: str, expires_at: float) -> None:
        self._exec(
            "INSERT INTO email_codes(email, code_hash, salt, expires_at, sent_at, tries)"
            " VALUES(?,?,?,?,?,0)"
            " ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash, salt=excluded.salt,"
            " expires_at=excluded.expires_at, sent_at=excluded.sent_at, tries=0",
            ((email or "").strip().lower(), code_hash, salt, expires_at, time.time()))

    def get_code(self, email: str) -> dict | None:
        row = self._one("SELECT * FROM email_codes WHERE email=?", ((email or "").strip().lower(),))
        return dict(row) if row else None

    def bump_code_tries(self, email: str) -> int:
        self._exec("UPDATE email_codes SET tries=tries+1 WHERE email=?",
                   ((email or "").strip().lower(),))
        row = self.get_code(email)
        return int(row["tries"]) if row else 0

    def clear_code(self, email: str) -> None:
        self._exec("DELETE FROM email_codes WHERE email=?", ((email or "").strip().lower(),))

    def mark_verified(self, email: str) -> None:
        self._exec("UPDATE users SET verified=1 WHERE email=?", ((email or "").strip().lower(),))

    def email_exists(self, email: str) -> bool:
        """آیا با این ایمیل حسابی ساخته شده است؟ (برای هدایت به ثبت‌نام)"""
        row = self._one("SELECT 1 FROM users WHERE email=?", ((email or "").strip().lower(),))
        return row is not None

    def verify_user(self, email: str, password: str) -> dict | None:
        row = self._one("SELECT * FROM users WHERE email=?", (email.strip().lower(),))
        if row is None:
            # زمان ثابت برای جلوگیری از افشای وجود حساب
            self._hash(password, "00" * 16)
            return None
        if not hmac.compare_digest(self._hash(password, row["pw_salt"]), row["pw_hash"]):
            return None
        self._exec("UPDATE users SET last_seen=? WHERE id=?", (time.time(), row["id"]))
        return self.get_user(int(row["id"]))

    def get_user(self, user_id: int) -> dict | None:
        row = self._one("SELECT id,email,name,plan,role,verified,created_at,last_seen "
                        "FROM users WHERE id=?", (user_id,))
        return dict(row) if row else None

    def update_user(self, user_id: int, name: str | None = None, plan: str | None = None) -> None:
        if name is not None:
            self._exec("UPDATE users SET name=? WHERE id=?", (name.strip()[:60], user_id))
        if plan is not None:
            self._exec("UPDATE users SET plan=? WHERE id=?", (plan, user_id))

    def change_password(self, user_id: int, new_password: str) -> None:
        salt = secrets.token_hex(16)
        self._exec("UPDATE users SET pw_hash=?, pw_salt=? WHERE id=?",
                   (self._hash(new_password, salt), salt, user_id))

    # --------------------------------------------------------------- کلید API
    @staticmethod
    def _key_hash(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def create_api_key(self, user_id: int, name: str = "", scopes: str = "chat") -> tuple[dict, str]:
        """کلید تازه می‌سازد و متن کامل را **یک‌بار** برمی‌گرداند."""
        raw = "rk_" + secrets.token_urlsafe(30)
        prefix = raw[:11]
        now = time.time()
        cur = self._exec(
            "INSERT INTO api_keys(user_id, name, prefix, key_hash, scopes, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (user_id, (name or "کلید پیش‌فرض").strip()[:60], prefix,
             self._key_hash(raw), scopes, now),
        )
        row = self._one("SELECT id,name,prefix,scopes,created_at,last_used,revoked_at"
                        " FROM api_keys WHERE id=?", (cur.lastrowid,))
        return dict(row), raw

    def list_api_keys(self, user_id: int) -> list[dict]:
        rows = self._all(
            "SELECT id,name,prefix,scopes,created_at,last_used,revoked_at FROM api_keys"
            " WHERE user_id=? ORDER BY created_at DESC", (user_id,))
        return [dict(r) for r in rows]

    def revoke_api_key(self, user_id: int, key_id: int) -> bool:
        cur = self._exec("UPDATE api_keys SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
                         (time.time(), key_id, user_id))
        return cur.rowcount > 0

    def api_key_owner(self, raw: str) -> dict | None:
        """کلید را به کاربر برمی‌گرداند و زمان آخرین استفاده را به‌روز می‌کند."""
        if not raw or not raw.startswith("rk_") or len(raw) > 80:
            return None
        row = self._one("SELECT k.*, u.plan AS plan, u.email AS email, u.name AS uname"
                        " FROM api_keys k JOIN users u ON u.id = k.user_id WHERE k.key_hash=?",
                        (self._key_hash(raw),))
        if row is None or row["revoked_at"]:
            return None
        now = time.time()
        self._exec("UPDATE api_keys SET last_used=? WHERE id=?", (now, row["id"]))
        return {
            "user_id": row["user_id"],
            "guest_id": None,
            "plan": row["plan"] or "free",
            "api_key_id": row["id"],
            "scopes": row["scopes"],
            "user": {"id": row["user_id"], "email": row["email"], "name": row["uname"], "plan": row["plan"]},
        }

    # ------------------------------------------------------------- پشتیبانی
    def add_support_request(self, name: str, email: str, plan: str, topic: str,
                            message: str, user_id: int | None, ip: str) -> int:
        cur = self._exec(
            "INSERT INTO support_requests(name,email,plan,topic,message,user_id,ip,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (name.strip()[:80], email.strip().lower()[:160], plan[:20], topic.strip()[:80],
             message.strip()[:2000], user_id, ip, time.time()),
        )
        return int(cur.lastrowid)

    def list_support_requests(self, limit: int = 100) -> list[dict]:
        rows = self._all("SELECT * FROM support_requests ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def count_users(self) -> int:
        row = self._one("SELECT COUNT(*) AS n FROM users")
        return int(row["n"]) if row else 0

    # --------------------------------------------------------------- نشست‌ها
    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(self, user_id: int | None = None, guest_id: str | None = None,
                       user_agent: str = "", ip: str = "", days: int = 30) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        self._exec(
            "INSERT INTO sessions(token_hash, user_id, guest_id, created_at, expires_at, user_agent, ip)"
            " VALUES(?,?,?,?,?,?,?)",
            (self._token_hash(token), user_id, guest_id, now, now + days * 86400, user_agent[:255], ip[:64]),
        )
        return token

    def session_user(self, token: str) -> dict | None:
        if not token:
            return None
        row = self._one(
            "SELECT s.user_id, s.expires_at FROM sessions s WHERE s.token_hash=?",
            (self._token_hash(token),),
        )
        if row is None or row["expires_at"] < time.time() or row["user_id"] is None:
            return None
        return self.get_user(int(row["user_id"]))

    def delete_session(self, token: str) -> None:
        if token:
            self._exec("DELETE FROM sessions WHERE token_hash=?", (self._token_hash(token),))

    def purge_expired(self) -> None:
        self._exec("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))

    # ------------------------------------------------------------- گفتگوها
    @staticmethod
    def new_conversation_id() -> str:
        return "c_" + secrets.token_hex(8)

    def create_conversation(self, owner: dict, title: str = "گفتگوی تازه",
                            model: str = "rayan-1-small") -> dict:
        cid = self.new_conversation_id()
        now = time.time()
        self._exec(
            "INSERT INTO conversations(id,user_id,guest_id,title,model,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (cid, owner.get("user_id"), owner.get("guest_id"), title[:120], model, now, now),
        )
        return self.get_conversation_meta(cid) or {}

    def _owner_clause(self, owner: dict) -> tuple[str, tuple]:
        if owner.get("user_id"):
            return "user_id=?", (owner["user_id"],)
        return "(guest_id=? AND user_id IS NULL)", (owner.get("guest_id") or "",)

    def list_conversations(self, owner: dict, limit: int = 100) -> list[dict]:
        clause, params = self._owner_clause(owner)
        rows = self._all(
            f"SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conv_id=c.id) AS msg_count"
            f" FROM conversations c WHERE {clause} AND archived=0"
            f" ORDER BY pinned DESC, updated_at DESC LIMIT ?",
            (*params, limit),
        )
        return [dict(r) for r in rows]

    def get_conversation_meta(self, conv_id: str) -> dict | None:
        row = self._one(
            "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conv_id=c.id) AS msg_count"
            " FROM conversations c WHERE c.id=?", (conv_id,))
        return dict(row) if row else None

    def owns(self, owner: dict, conv_id: str) -> bool:
        conv = self.get_conversation_meta(conv_id)
        if not conv:
            return False
        if owner.get("user_id"):
            return conv["user_id"] == owner["user_id"]
        return conv["user_id"] is None and conv["guest_id"] == owner.get("guest_id")

    def get_messages(self, conv_id: str, limit: int = 200) -> list[dict]:
        rows = self._all(
            "SELECT id, role, content, meta, created_at FROM messages WHERE conv_id=?"
            " ORDER BY id ASC LIMIT ?", (conv_id, limit))
        out = []
        for r in rows:
            item = dict(r)
            try:
                import json
                item["meta"] = json.loads(item["meta"] or "{}")
            except Exception:
                item["meta"] = {}
            out.append(item)
        return out

    def add_message(self, conv_id: str, role: str, content: str, meta: dict | None = None) -> int:
        import json
        now = time.time()
        cur = self._exec(
            "INSERT INTO messages(conv_id, role, content, meta, created_at) VALUES(?,?,?,?,?)",
            (conv_id, role, content, json.dumps(meta or {}, ensure_ascii=False), now),
        )
        self._exec("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
        return int(cur.lastrowid)

    def rename_conversation(self, conv_id: str, title: str) -> None:
        self._exec("UPDATE conversations SET title=?, updated_at=? WHERE id=?",
                   (title.strip()[:120] or "گفتگوی تازه", time.time(), conv_id))

    def set_pinned(self, conv_id: str, pinned: bool) -> None:
        self._exec("UPDATE conversations SET pinned=? WHERE id=?", (1 if pinned else 0, conv_id))

    def delete_conversation(self, conv_id: str) -> None:
        self._exec("DELETE FROM messages WHERE conv_id=?", (conv_id,))
        self._exec("DELETE FROM shares WHERE conv_id=?", (conv_id,))
        self._exec("DELETE FROM conversations WHERE id=?", (conv_id,))

    def clear_conversations(self, owner: dict) -> int:
        clause, params = self._owner_clause(owner)
        rows = self._all(f"SELECT id FROM conversations WHERE {clause}", params)
        for row in rows:
            self.delete_conversation(row["id"])
        return len(rows)

    # ---------------------------------------------------------------- سهام
    def share(self, conv_id: str) -> str:
        existing = self._one("SELECT token FROM shares WHERE conv_id=?", (conv_id,))
        if existing:
            return existing["token"]
        token = secrets.token_urlsafe(9).replace("-", "").replace("_", "")
        self._exec("INSERT INTO shares(token, conv_id, created_at) VALUES(?,?,?)",
                   (token, conv_id, time.time()))
        self._exec("UPDATE conversations SET share_token=? WHERE id=?", (token, conv_id))
        return token

    def unshare(self, conv_id: str) -> None:
        self._exec("DELETE FROM shares WHERE conv_id=?", (conv_id,))
        self._exec("UPDATE conversations SET share_token=NULL WHERE id=?", (conv_id,))

    def shared_conversation(self, token: str) -> dict | None:
        row = self._one("SELECT * FROM shares WHERE token=?", (token,))
        if row is None:
            return None
        self._exec("UPDATE shares SET views=views+1 WHERE token=?", (token,))
        conv = self.get_conversation_meta(row["conv_id"])
        if conv is None:
            return None
        conv["messages"] = self.get_messages(row["conv_id"])
        conv["views"] = row["views"] + 1
        return conv

    # --------------------------------------------------------------- مصرف
    def record_event(self, kind: str, user_id: int | None = None, guest_id: str | None = None,
                     ip: str = "") -> None:
        self._exec("INSERT INTO events(user_id, guest_id, ip, kind, created_at) VALUES(?,?,?,?,?)",
                   (user_id, guest_id, ip[:64], kind, time.time()))

    def usage_today(self, kind: str, user_id: int | None = None, guest_id: str | None = None,
                    ip: str = "") -> int:
        since = time.time() - 86400
        if user_id:
            row = self._one("SELECT COUNT(*) AS n FROM events WHERE kind=? AND user_id=? AND created_at>?",
                            (kind, user_id, since))
        else:
            row = self._one(
                "SELECT COUNT(*) AS n FROM events WHERE kind=? AND user_id IS NULL AND"
                " (guest_id=? OR ip=?) AND created_at>?",
                (kind, guest_id or "", ip, since))
        return int(row["n"]) if row else 0

    def add_feedback(self, message_id: int | None, value: int, user_id: int | None,
                     comment: str = "") -> None:
        self._exec(
            "INSERT INTO feedback(message_id, user_id, value, comment, created_at) VALUES(?,?,?,?,?)",
            (message_id, user_id, value, comment[:500], time.time()),
        )


    # ------------------------------------------------------------- مدیریت
    def setting(self, key: str, default: str = "") -> str:
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._exec(
            "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, time.time()),
        )

    def all_settings(self) -> dict:
        return {row["key"]: row["value"] for row in self._all("SELECT key, value FROM settings")}

    def audit(self, action: str, actor: str = "", target: str = "", detail: str = "", ip: str = "") -> None:
        self._exec(
            "INSERT INTO audit(actor, action, target, detail, ip, created_at) VALUES(?,?,?,?,?,?)",
            (actor[:120], action[:60], target[:120], detail[:400], ip[:64], time.time()),
        )

    def audit_log(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self._all("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    # -------------------------------------------------------------- تبلیغ
    def list_ads(self, slot: str | None = None, only_active: bool = False) -> list[dict]:
        now = time.time()
        sql = "SELECT * FROM ads"
        clauses: list[str] = []
        params: list[Any] = []
        if slot:
            clauses.append("slot=?")
            params.append(slot)
        if only_active:
            clauses.append("active=1")
            clauses.append("(starts_at=0 OR starts_at<=?)")
            clauses.append("(ends_at=0 OR ends_at>=?)")
            params.extend([now, now])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY weight DESC, id DESC"
        return [dict(r) for r in self._all(sql, params)]

    def create_ad(self, slot: str, title: str, body: str, url: str, cta: str = "بیشتر بدانید",
                  weight: int = 1, starts_at: float = 0, ends_at: float = 0) -> dict:
        cur = self._exec(
            "INSERT INTO ads(slot, title, body, cta, url, weight, active, starts_at, ends_at, created_at)"
            " VALUES(?,?,?,?,?,?,1,?,?,?)",
            (slot, title, body, cta, url, max(1, min(int(weight), 100)), starts_at, ends_at, time.time()),
        )
        row = self._one("SELECT * FROM ads WHERE id=?", (cur.lastrowid,))
        return dict(row) if row else {}

    def update_ad(self, ad_id: int, **fields: Any) -> None:
        allowed = {"slot", "title", "body", "cta", "url", "weight", "active", "starts_at", "ends_at"}
        pairs = [(k, v) for k, v in fields.items() if k in allowed]
        if not pairs:
            return
        sql = "UPDATE ads SET " + ", ".join(f"{k}=?" for k, _ in pairs) + " WHERE id=?"
        self._exec(sql, tuple(v for _, v in pairs) + (ad_id,))

    def delete_ad(self, ad_id: int) -> None:
        self._exec("DELETE FROM ads WHERE id=?", (ad_id,))

    def pick_ad(self, slot: str) -> dict | None:
        ads = self.list_ads(slot, only_active=True)
        if not ads:
            return None
        total = sum(max(1, int(a["weight"])) for a in ads)
        roll = secrets.randbelow(max(total, 1))
        acc = 0
        chosen = ads[0]
        for ad in ads:
            acc += max(1, int(ad["weight"]))
            if roll < acc:
                chosen = ad
                break
        self._exec("UPDATE ads SET views=views+1 WHERE id=?", (chosen["id"],))
        chosen["views"] = int(chosen["views"]) + 1
        return chosen

    def click_ad(self, ad_id: int) -> str | None:
        row = self._one("SELECT id, url, active FROM ads WHERE id=?", (ad_id,))
        if not row or not row["active"]:
            return None
        self._exec("UPDATE ads SET clicks=clicks+1 WHERE id=?", (ad_id,))
        return row["url"]

    # ------------------------------------------------------- نشست مدیریت
    def create_admin_session(self, user_id: int, csrf: str, ip: str = "", user_agent: str = "",
                             minutes: int = 120) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        self._exec(
            "INSERT INTO admin_sessions(token_hash, user_id, csrf, created_at, expires_at, ip, user_agent)"
            " VALUES(?,?,?,?,?,?,?)",
            (self._token_hash(token), user_id, csrf, now, now + minutes * 60, ip[:64], user_agent[:255]),
        )
        self._exec("DELETE FROM admin_sessions WHERE expires_at < ?", (now,))
        return token

    def admin_session(self, token: str) -> dict | None:
        if not token:
            return None
        row = self._one("SELECT * FROM admin_sessions WHERE token_hash=?", (self._token_hash(token),))
        if row is None or row["expires_at"] < time.time():
            return None
        user = self.get_user(int(row["user_id"]))
        if not user:
            return None
        return {"user": user, "csrf": row["csrf"], "expires_at": row["expires_at"]}

    def delete_admin_session(self, token: str) -> None:
        if token:
            self._exec("DELETE FROM admin_sessions WHERE token_hash=?", (self._token_hash(token),))

    def delete_admin_sessions_for(self, user_id: int) -> None:
        self._exec("DELETE FROM admin_sessions WHERE user_id=?", (user_id,))

    # ----------------------------------------------------- محدودیت ورود
    def note_attempt(self, key: str) -> int:
        self._exec("INSERT INTO login_attempts(key, created_at) VALUES(?,?)", (key[:120], time.time()))
        row = self._one(
            "SELECT COUNT(*) AS n FROM login_attempts WHERE key=? AND created_at>?",
            (key[:120], time.time() - 900),
        )
        return int(row["n"]) if row else 0

    def clear_attempts(self, key: str) -> None:
        self._exec("DELETE FROM login_attempts WHERE key=?", (key[:120],))

    # --------------------------------------------------------- آمار مدیریت
    def admin_stats(self, days: int = 14) -> dict:
        now = time.time()
        since_day = now - 86400
        since_week = now - 7 * 86400

        def count(sql: str, params: Iterable[Any] = ()) -> int:
            row = self._one(sql, params)
            return int(row["n"]) if row and row["n"] is not None else 0

        daily = []
        for i in range(days - 1, -1, -1):
            start = now - (i + 1) * 86400
            end = now - i * 86400
            daily.append({
                "day": round(end),
                "chats": count("SELECT COUNT(*) AS n FROM events WHERE kind IN ('chat','deep')"
                               " AND created_at>? AND created_at<=?", (start, end)),
                "signups": count("SELECT COUNT(*) AS n FROM users WHERE created_at>? AND created_at<=?",
                                 (start, end)),
                "messages": count("SELECT COUNT(*) AS n FROM messages WHERE created_at>? AND created_at<=?",
                                  (start, end)),
            })
        return {
            "users": count("SELECT COUNT(*) AS n FROM users"),
            "users_today": count("SELECT COUNT(*) AS n FROM users WHERE created_at>?", (since_day,)),
            "users_week": count("SELECT COUNT(*) AS n FROM users WHERE created_at>?", (since_week,)),
            "conversations": count("SELECT COUNT(*) AS n FROM conversations"),
            "messages": count("SELECT COUNT(*) AS n FROM messages"),
            "answers": count("SELECT COUNT(*) AS n FROM messages WHERE role='assistant'"),
            "chats_today": count("SELECT COUNT(*) AS n FROM events WHERE kind IN ('chat','deep')"
                                 " AND created_at>?", (since_day,)),
            "guest_chats": count("SELECT COUNT(*) AS n FROM events WHERE kind='chat' AND user_id IS NULL"),
            "feedback_up": count("SELECT COUNT(*) AS n FROM feedback WHERE value>0"),
            "feedback_down": count("SELECT COUNT(*) AS n FROM feedback WHERE value<0"),
            "share_views": count("SELECT COALESCE(SUM(views),0) AS n FROM shares"),
            "db_bytes": os.path.getsize(self.path) if os.path.exists(self.path) else 0,
            "daily": daily,
        }

    def conversation_counts(self) -> dict:
        rows = self._all(
            "SELECT user_id, COUNT(*) AS n FROM conversations WHERE user_id IS NOT NULL GROUP BY user_id")
        return {int(r["user_id"]): int(r["n"]) for r in rows}

    def list_users(self, limit: int = 200, query: str = "") -> list[dict]:
        if query:
            rows = self._all(
                "SELECT id,email,name,plan,created_at,last_seen FROM users"
                " WHERE email LIKE ? OR name LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit))
        else:
            rows = self._all(
                "SELECT id,email,name,plan,created_at,last_seen FROM users ORDER BY id DESC LIMIT ?", (limit,))
        counts = self.conversation_counts()
        out = []
        for row in rows:
            item = dict(row)
            item["conversations"] = counts.get(int(row["id"]), 0)
            out.append(item)
        return out

    def ban_user(self, user_id: int) -> None:
        self._exec("UPDATE users SET plan='banned' WHERE id=?", (user_id,))
        self._exec("DELETE FROM sessions WHERE user_id=?", (user_id,))
        self._exec("DELETE FROM admin_sessions WHERE user_id=?", (user_id,))

    def set_plan(self, user_id: int, plan: str) -> None:
        self.update_user(user_id, plan=plan)

    def vacuum(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.execute("VACUUM")

    def backup_to(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with self._lock:
            dest = sqlite3.connect(path)
            try:
                self._conn.backup(dest)
            finally:
                dest.close()
        return path

    def purge(self, days: int = 30) -> dict:
        cutoff = time.time() - days * 86400
        removed_events = self._exec("DELETE FROM events WHERE created_at<?", (cutoff,)).rowcount
        removed_sessions = self._exec("DELETE FROM sessions WHERE expires_at<?", (time.time(),)).rowcount
        removed_audit = self._exec("DELETE FROM audit WHERE created_at<?", (cutoff,)).rowcount
        return {"events": removed_events, "sessions": removed_sessions, "audit": removed_audit}

    # --------------------------------------------------------------- آمار
    def public_stats(self) -> dict:
        users = self._one("SELECT COUNT(*) AS n FROM users")
        convs = self._one("SELECT COUNT(*) AS n FROM conversations")
        msgs = self._one("SELECT COUNT(*) AS n FROM messages WHERE role='assistant'")
        ev = self._one("SELECT COUNT(*) AS n FROM events WHERE kind='chat'")
        return {
            "users": int(users["n"]) if users else 0,
            "conversations": int(convs["n"]) if convs else 0,
            "answers": int(msgs["n"]) if msgs else 0,
            "messages": int(ev["n"]) if ev else 0,
        }


_store: Store | None = None
_store_lock = threading.Lock()


def store() -> Store:
    global _store
    with _store_lock:
        if _store is None:
            path = os.environ.get("RAYAN_DB", DEFAULT_DB)
            _store = Store(path)
        return _store
