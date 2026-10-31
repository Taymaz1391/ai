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
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER,
    user_id     INTEGER,
    value       INTEGER NOT NULL,
    comment     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
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
                "INSERT INTO users(email, name, pw_hash, pw_salt, plan, created_at, last_seen)"
                " VALUES(?,?,?,?, 'free', ?, ?)",
                (email, name.strip()[:60], pw_hash, salt, now, now),
            )
        except sqlite3.IntegrityError:
            return None
        return self.get_user(int(cur.lastrowid))

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
        row = self._one("SELECT id,email,name,plan,created_at,last_seen FROM users WHERE id=?", (user_id,))
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
