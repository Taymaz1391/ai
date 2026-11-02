"""آزمون‌های میزبانی روی هاست: پوشهٔ نوشتنی، زیرشاخه، پلِ WSGI و بستهٔ آپلود."""
from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web import hosting  # noqa: E402


# ─────────────────────────────────────────────── ۱) بازنویسیِ نشانی‌ها
def test_absolute_urls_are_prefixed():
    html = '<link href="/static/a.css"><a href="/about">x</a><b style="background:url(/x.png)">'
    out = hosting.absolute_urls(html, "/rayan")
    assert 'href="/rayan/static/a.css"' in out
    assert 'href="/rayan/about"' in out
    assert "url(/rayan/x.png)" in out
    assert hosting.absolute_urls(html, "") == html


# ─────────────────────────────────────────────── ۲) میان‌افزارِ زیرشاخه
def _run(app, scope):
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    return messages


def _scope(path: str) -> dict:
    return {"type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
            "query_string": b"", "headers": [], "scheme": "http", "root_path": ""}


def test_base_path_strips_prefix_and_rewrites_html():
    seen: dict = {}

    async def app(scope, receive, send):
        seen["path"] = scope["path"]
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/html; charset=utf-8")]})
        await send({"type": "http.response.body",
                    "body": b'<html><head><link href="/static/x.css"></head></html>'})

    messages = _run(hosting.BasePathMiddleware(app, "/rayan"), _scope("/rayan/app"))
    assert seen["path"] == "/app"
    body = b"".join(m.get("body") or b"" for m in messages if m["type"] == "http.response.body")
    text = body.decode()
    assert 'href="/rayan/static/x.css"' in text
    assert "__RAYAN_BASE__" in text                     # اسکریپتِ هم‌مسیرکردن تزریق شد
    headers = dict(messages[0]["headers"])
    assert int(headers[b"content-length"]) == len(body)


def test_base_path_leaves_binary_untouched():
    payload = b"\x89PNG\r\n\x1a\n" + bytes(range(32))

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"image/png")]})
        await send({"type": "http.response.body", "body": payload})

    messages = _run(hosting.BasePathMiddleware(app, "/rayan"), _scope("/rayan/static/a.png"))
    body = b"".join(m.get("body") or b"" for m in messages if m["type"] == "http.response.body")
    assert body == payload


# ─────────────────────────────────────────────── ۳) پلِ ASGI → WSGI
def _wsgi_call(wsgi, path: str, method: str = "GET", body: bytes = b"",
               content_type: str = "") -> tuple[str, dict, bytes]:
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "",
        "SERVER_NAME": "localhost", "SERVER_PORT": "8000",
        "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body), "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type, "REMOTE_ADDR": "127.0.0.1",
    }
    payload = b"".join(wsgi(environ, start_response))
    return captured.get("status", ""), captured.get("headers", {}), payload


def test_wsgi_bridge_serves_health():
    from web import server

    wsgi = hosting.to_wsgi(server.app)
    status, headers, payload = _wsgi_call(wsgi, "/api/health")
    assert status.startswith("200"), status
    assert headers.get("content-type", "").startswith("application/json")
    data = json.loads(payload)
    assert "ok" in data and "ready" in data


def test_wsgi_bridge_repeats_without_loop_error():
    from web import server

    wsgi = hosting.to_wsgi(server.app)
    for _ in range(3):
        status, _, payload = _wsgi_call(wsgi, "/api/health")
        assert status.startswith("200") and b"ok" in payload


# ─────────────────────────────────────────────── ۴) پوشهٔ نوشتنی
def test_prepare_host_env_sets_writable_paths(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("RAYAN_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RAYAN_DATA_DIR", str(tmp_path / "var"))
    data_dir = hosting.prepare_host_env(str(tmp_path))
    assert Path(data_dir) == tmp_path / "var"
    db = os.environ["RAYAN_DB"]
    assert db.startswith(data_dir)
    assert os.environ["RAYAN_HOST"] == "1"
    assert os.environ["RAYAN_WATCH"] == "0"
    Path(db).write_bytes(b"probe")                      # پوشه واقعاً نوشتنی است
    assert os.environ["RAYAN_OWNER_FILE"].startswith(data_dir)
    assert os.environ["RAYAN_SECRET_FILE"].startswith(data_dir)


def test_prepare_host_env_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("RAYAN_DATA_DIR", str(tmp_path / "v"))
    first = hosting.prepare_host_env(str(tmp_path))
    monkeypatch.setenv("RAYAN_DB", "/custom/db.sqlite3")
    hosting.prepare_host_env(str(tmp_path))
    assert os.environ["RAYAN_DB"] == "/custom/db.sqlite3"    # مقدارِ کاربر دست‌نخورده
    assert first == os.environ["RAYAN_DATA_DIR"]


# ─────────────────────────────────────────────── ۵) بستهٔ آپلود
def test_host_package_contains_runtime_files(tmp_path):
    out = tmp_path / "pkg"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_host_package.py"), "--out", str(out)],
        capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    assert result.returncode == 0, result.stderr[-800:]
    package = out / "rayan-host.zip"
    assert package.exists() and package.stat().st_size > 10_000_000
    with zipfile.ZipFile(package) as zf:
        names = set(zf.namelist())
        for required in ("passenger_wsgi.py", "README-HOST.md", "requirements.txt",
                         "htaccess.sample", "MANIFEST.txt", "web/server.py",
                         "web/hosting.py", "deploy/host_check.py",
                         "checkpoints/rayan-1-small.npz", "data/knowledge.jsonl"):
            assert required in names, required
        assert not [name for name in names if "__pycache__" in name or name.startswith(".git/")]
        manifest = zf.read("MANIFEST.txt").decode()
        assert "README-HOST.md" in manifest
