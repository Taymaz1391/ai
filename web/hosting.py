"""میزبانی روی هاست اشتراکی — آماده‌سازی مسیرها، مسیرِ زیرشاخه و پلِ ASGI→WSGI.

این ماژول سه کار می‌کند و هیچ بستهٔ تازه‌ای لازم ندارد:

۱. **مسیرهای نوشتنی** (``prepare_host_env``): روی هاست اشتراکی، پوشهٔ برنامه معمولاً
   خواندنی است. پایگاه‌داده، کلیدِ امنیتی، پروندهٔ مالک و لاگ‌ها به پوشه‌ای می‌روند که
   واقعاً قابلِ نوشتن باشد؛ اگر ``<root>/var`` قابلِ نوشتن نبود، ``~/.rayan/var``.

۲. **زیرشاخه** (``BasePathMiddleware``): اگر برنامه روی ``https://example.com/rayan``
   بالا بیاید، مسیرِ ورودی از پیشوند پاک می‌شود و نشانی‌های مطلقِ HTML/CSS با همان
   پیشوند بازنویسی می‌شوند؛ یک اسکریپتِ کوچک هم ``fetch``/``XHR``/``EventSource`` را
   برای درخواست‌های ``/api/...`` هم‌مسیر می‌کند.

۳. **پلِ WSGI** (``to_wsgi``): cPanel، Plesk و DirectAdmin برنامه را با Passenger یا
   mod_wsgi (WSGI) اجرا می‌کنند؛ این پل هر درخواست را به ASGI می‌دهد و پاسخ را
   (چون Passenger بدنه را بافر می‌کند) یک‌جا برمی‌گرداند.

هیچ‌کدام از این‌ها رفتارِ سرورِ معمولی (uvicorn) را تغییر نمی‌دهد؛ همه فقط با
``RAYAN_HOST``/``RAYAN_BASE_PATH`` فعال می‌شوند.
"""
from __future__ import annotations

import asyncio
import http
import json
import os
import sys
import traceback

__all__ = ["prepare_host_env", "BasePathMiddleware", "to_wsgi", "ROOT"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════ ۱) پوشهٔ نوشتنی
def _writable(path: str) -> bool:
    """آیا می‌شود در این پوشه نوشت؟ (پوشه ساخته می‌شود اگر نباشد.)"""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def prepare_host_env(root: str | None = None) -> dict:
    """مسیرهای نوشتنی و پیش‌فرض‌های هاست را در محیط می‌گذارد؛ مسیرِ داده را برمی‌گرداند."""
    root = root or ROOT
    data_dir = (os.environ.get("RAYAN_DATA_DIR") or "").strip()
    if not data_dir:
        local = os.path.join(root, "var")
        data_dir = local if _writable(local) else os.path.join(
            os.path.expanduser("~"), ".rayan", "var")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        data_dir = os.path.join(os.path.expanduser("~"), ".rayan", "var")
        os.makedirs(data_dir, exist_ok=True)
    os.environ["RAYAN_DATA_DIR"] = data_dir

    defaults = {
        "RAYAN_DB": os.path.join(data_dir, "rayan.sqlite3"),
        "RAYAN_OWNER_FILE": os.path.join(data_dir, "owner.json"),
        "RAYAN_ADMIN_FILE": os.path.join(data_dir, "admin.json"),
        "RAYAN_SECRET_FILE": os.path.join(data_dir, "secret.key"),
        "RAYAN_LEARNED": os.path.join(data_dir, "learned.sqlite3"),
        "RAYAN_SECURITY_LOG": os.path.join(data_dir, "security_events.jsonl"),
        "RAYAN_OPS_DIR": os.path.join(data_dir, "ops"),
        "RAYAN_NETWORK_STATE": os.path.join(data_dir, "network.json"),
        "RAYAN_BACKUP_DIR": os.path.join(data_dir, "backups"),
    }
    for key, value in defaults.items():
        if not (os.environ.get(key) or "").strip():
            os.environ[key] = value
        parent = value if key.endswith("DIR") else os.path.dirname(value)
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            pass

    os.environ.setdefault("RAYAN_HOST", "1")
    # Passenger/mod_wsgi فرایندِ کوتاه‌عمر دارد؛ نخ‌های پس‌زمینه در آن‌ها عمر نمی‌کنند.
    os.environ.setdefault("RAYAN_WATCH", "0")
    os.environ.setdefault("RAYAN_AUTO_GROW", "0")
    if not (os.environ.get("RAYAN_ENV") or "").strip():
        os.environ["RAYAN_ENV"] = "production"
    return data_dir


# ═══════════════════════════════════════════════════ ۲) زیرشاخه
_SHIM = """<script>window.__RAYAN_BASE__=%s;(function(b){if(!b)return;
function fix(u){return (typeof u==="string"&&u.charAt(0)==="/"&&u!==b&&
  !u.startsWith(b+"/"))?b+u:u;}
var f=window.fetch;if(f){window.fetch=function(i,o){try{
  if(typeof i==="string")i=fix(i);
  else if(i&&i.url){var u=fix(i.url);if(u!==i.url)i=new Request(u,i);}
}catch(e){}return f.call(this,i,o);};}
var op=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(m,u){try{u=fix(u);}catch(e){}return op.call(this,m,u);};
var R=window.Request;if(R&&R.prototype){var RW=function(u,o){return new R(fix(u),o);};
  RW.prototype=R.prototype;window.Request=RW;}
var E=window.EventSource;if(E&&E.prototype){var EW=function(u,c){return new E(fix(u),c);};
  EW.prototype=E.prototype;window.EventSource=EW;}
var sw=window.navigator&&window.navigator.serviceWorker;
if(sw&&sw.register){var reg=sw.register.bind(sw);
  try{sw.register=function(u,o){return reg(fix(u),o);};}catch(e){}}
})(window.__RAYAN_BASE__);</script>"""


def absolute_urls(text: str, base: str) -> str:
    """نشانی‌های مطلقِ ریشه‌دار را با پیشوندِ برنامه هم‌مسیر می‌کند."""
    if not base or not text:
        return text
    text = text.replace('="/', '="%s/' % base)
    text = text.replace("='/", "='%s/" % base)
    text = text.replace("url(/", "url(%s/" % base)
    text = text.replace("url('/", "url('%s/" % base)
    text = text.replace('url("/', 'url("%s/' % base)
    return text


class BasePathMiddleware:
    """برنامه را زیرِ ``/base`` هم کار می‌کند: پاک‌کردنِ پیشوند و بازنویسیِ HTML/CSS."""

    def __init__(self, app, base: str = ""):
        self.app = app
        base = (base or "").strip()
        self.base = "/" + base.strip("/") if base.strip("/") else ""

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not self.base:
            return await self.app(scope, receive, send)
        scope = dict(scope)
        path = scope.get("path") or "/"
        if path == self.base or path.startswith(self.base + "/"):
            path = path[len(self.base):] or "/"
            scope["path"] = path
            if "raw_path" in scope:
                scope["raw_path"] = path.encode("latin-1", "ignore")

        state: dict = {"rewrite": False, "html": False, "chunks": []}

        async def wrapped(message):
            kind = message.get("type")
            if kind == "http.response.start":
                headers = list(message.get("headers") or [])
                content_type = b""
                compressed = False
                for name, value in headers:
                    lowered = name.lower()
                    if lowered == b"content-type":
                        content_type = value.lower()
                    elif lowered == b"content-encoding":
                        compressed = True
                textual = b"text/html" in content_type or b"text/css" in content_type
                state["rewrite"] = textual and not compressed
                state["html"] = b"text/html" in content_type
                if state["rewrite"]:
                    # سرآیند را نگه می‌داریم تا پس از بازنویسیِ بدنه بفرستیم
                    state["start"] = dict(message)
                    state["headers"] = headers
                    return None
                return await send(message)

            if kind == "http.response.body" and state["rewrite"]:
                state["chunks"].append(message.get("body") or b"")
                if message.get("more_body"):
                    return None
                text = b"".join(state["chunks"]).decode("utf-8", "ignore")
                text = absolute_urls(text, self.base)
                if state["html"] and "<head>" in text:
                    text = text.replace("<head>",
                                        "<head>" + (_SHIM % json.dumps(self.base,
                                                                       ensure_ascii=False)), 1)
                payload = text.encode("utf-8")
                headers = [(name, value) for name, value in state["headers"]
                           if name.lower() != b"content-length"]
                headers.append((b"content-length", str(len(payload)).encode()))
                start = dict(state["start"])
                start["headers"] = headers
                await send(start)
                return await send({"type": "http.response.body", "body": payload,
                                   "more_body": False})

            return await send(message)

        return await self.app(scope, receive, wrapped)


# ═══════════════════════════════════════════════════ ۳) پلِ ASGI → WSGI
def _scope_from_environ(environ: dict) -> dict:
    path = environ.get("PATH_INFO") or "/"
    if not path.startswith("/"):
        path = "/" + path
    headers: list[tuple[bytes, bytes]] = []
    for key, value in environ.items():
        if key.startswith("HTTP_") and value:
            headers.append((key[5:].replace("_", "-").lower().encode("latin-1"),
                            str(value).encode("latin-1", "replace")))
    if environ.get("CONTENT_TYPE"):
        headers.append((b"content-type", environ["CONTENT_TYPE"].encode("latin-1")))
    if environ.get("CONTENT_LENGTH"):
        headers.append((b"content-length", str(environ["CONTENT_LENGTH"]).encode()))
    if environ.get("HTTP_HOST"):
        headers.append((b"host", environ["HTTP_HOST"].encode("latin-1", "replace")))
    server = (environ.get("SERVER_NAME") or "localhost",
              int(environ.get("SERVER_PORT") or 80))
    client = (environ.get("REMOTE_ADDR") or "0.0.0.0", 0)
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": environ.get("SERVER_PROTOCOL", "HTTP/1.1").replace("HTTP/", ""),
        "method": (environ.get("REQUEST_METHOD") or "GET").upper(),
        "scheme": environ.get("wsgi.url_scheme") or "http",
        "path": path,
        "raw_path": path.encode("latin-1", "ignore"),
        "query_string": (environ.get("QUERY_STRING") or "").encode("latin-1", "replace"),
        "root_path": "",
        "headers": headers,
        "server": server,
        "client": client,
    }


def _read_body(environ: dict) -> bytes:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    stream = environ.get("wsgi.input")
    if length > 0 and stream is not None:
        return stream.read(length)
    return b""


def to_wsgi(app):
    """``app`` (ASGI) را به یک WSGI callable تبدیل می‌کند؛ برای Passenger/mod_wsgi."""

    def application(environ: dict, start_response):
        scope = _scope_from_environ(environ)
        body = _read_body(environ)
        state: dict = {"status": 500, "headers": [], "chunks": []}
        delivered = {"body": False}
        finished = asyncio.Event()

        async def receive():
            # بدنه یک بار تحویل می‌شود؛ بعد از آن تا پایانِ پاسخ منتظر می‌مانیم.
            # (Starlette برای هر درخواست «شنوندهٔ قطع اتصال» می‌سازد و انتظار
            #  دارد پیامِ تکراریِ http.request نگیرد.)
            if not delivered["body"]:
                delivered["body"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            await finished.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                state["status"] = message.get("status", 200)
                state["headers"] = [(name.decode("latin-1"), value.decode("latin-1"))
                                    for name, value in (message.get("headers") or [])]
            elif message["type"] == "http.response.body":
                chunk = message.get("body") or b""
                if chunk:
                    state["chunks"].append(chunk)
                if not message.get("more_body"):
                    finished.set()

        try:
            asyncio.run(app(scope, receive, send))
        except RuntimeError as exc:                      # حلقهٔ در حال اجرا
            if "asyncio.run()" not in str(exc):
                traceback.print_exc()
                return _fail(start_response)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(app(scope, receive, send))
            finally:
                loop.close()
        except Exception:  # noqa: BLE001 - یک درخواست نباید فرایند را بخواباند
            traceback.print_exc()
            return _fail(start_response)

        try:
            status_line = "%d %s" % (state["status"], http.HTTPStatus(state["status"]).phrase)
        except ValueError:
            status_line = "500 Internal Server Error"
        start_response(status_line, state["headers"])
        payload = b"".join(state["chunks"])
        if not payload:
            return [b""]
        return [payload]

    return application


def _fail(start_response):
    payload = json.dumps({"detail": "خطای داخلی سرور"}, ensure_ascii=False).encode()
    start_response("500 Internal Server Error",
                   [("content-type", "application/json; charset=utf-8"),
                    ("content-length", str(len(payload)))])
    return [payload]


if __name__ == "__main__":                              # اجرای سادهٔ WSGI برای آزمون
    print("این ماژول کتابخانه است؛ از passenger_wsgi.py استفاده کن.", file=sys.stderr)
