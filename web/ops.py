"""اتاق فرمان: کانال دستور از پنل مالک به عاملِ سازنده — بدون بازکردن ترمینال.

مالک در سایت (تب «اتاق فرمان») پیام یا دستور می‌نویسد؛ این ماژول آن را در
``data/ops/orders.jsonl`` ثبت می‌کند. عامل (همان کسی که کد را می‌نویسد) در هر
نشست با ``scripts/ops_console.py`` همین پرونده را می‌خواند، کار را انجام می‌دهد
و پاسخ را با ``reply`` می‌نویسد. پرونده فقط-افزودنی است و هیچ دستوری خودکار
اجرا نمی‌شود؛ اجرا همیشه با بازبینی انسان/عامل است.

    from web import ops
    ops.add("رنگ دکمه‌ها را عوض کن", kind="order")
    for row in ops.listing(): print(row["id"], row["status"], row["text"])
"""
from __future__ import annotations

import json
import os
import secrets
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("RAYAN_OPS_DIR") or os.path.join(ROOT, "data", "ops")
QUEUE = os.path.join(DATA_DIR, "orders.jsonl")

KINDS = {"order", "note"}
STATUSES = {"pending", "working", "done", "skipped"}
MAX_TEXT = 2000
MAX_ROWS = 200


def _ensure() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _append(record: dict) -> None:
    _ensure()
    line = json.dumps(record, ensure_ascii=False)
    with open(QUEUE, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _records() -> list[dict]:
    if not os.path.exists(QUEUE):
        return []
    rows: list[dict] = []
    with open(QUEUE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _merge(records: list[dict]) -> list[dict]:
    """آخرین وضعیت هر شناسه برنده است؛ پرونده فقط-افزودنی می‌ماند."""
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for row in records:
        key = row.get("id")
        if not key:
            continue
        if key not in by_id:
            order.append(key)
            by_id[key] = {"id": key, "at": row.get("at", 0), "kind": "order",
                          "text": "", "status": "pending", "replies": []}
        item = by_id[key]
        if row.get("text") and not item["text"]:
            item["text"] = row["text"]
            item["at"] = row.get("at", item["at"])
            item["kind"] = row.get("kind", "order")
            item["author"] = row.get("author", "owner")
        if row.get("status"):
            item["status"] = row["status"]
        if row.get("reply"):
            item["replies"].append({"at": row.get("at", 0), "text": row["reply"],
                                    "by": row.get("by", "agent")})
        if row.get("page"):
            item["page"] = row["page"]
    return [by_id[key] for key in order]


def add(text: str, *, kind: str = "order", author: str = "owner", page: str = "") -> dict:
    body = (text or "").strip()[:MAX_TEXT]
    if not body:
        raise ValueError("متن خالی است")
    if kind not in KINDS:
        raise ValueError("نوع نامعتبر")
    record = {"id": "op_" + secrets.token_hex(6), "at": time.time(), "kind": kind,
              "text": body, "author": author[:60], "status": "pending",
              "page": (page or "")[:120]}
    _append(record)
    return record


def reply(order_id: str, text: str, *, status: str = "done", by: str = "agent") -> dict:
    if status not in STATUSES:
        raise ValueError("وضعیت نامعتبر")
    record = {"id": order_id, "at": time.time(), "status": status,
              "reply": (text or "").strip()[:MAX_TEXT], "by": by}
    _append(record)
    return record


def listing(limit: int = 40) -> list[dict]:
    rows = _merge(_records())
    rows.sort(key=lambda row: row["at"], reverse=True)
    return rows[:max(1, min(limit, MAX_ROWS))]


def pending() -> list[dict]:
    return [row for row in _merge(_records()) if row["status"] in ("pending", "working")]


def stats() -> dict:
    rows = _merge(_records())
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    last = max((row["at"] for row in rows), default=0)
    return {"total": len(rows), "pending": counts.get("pending", 0),
            "working": counts.get("working", 0), "done": counts.get("done", 0),
            "last_at": last, "queue": os.path.relpath(QUEUE, ROOT)}
