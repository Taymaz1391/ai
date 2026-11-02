# میزبانی رایان — از بستهٔ zip تا سایتِ زنده

رایان یک برنامهٔ **FastAPI** است که مدلش را خودش اجرا می‌کند. بنابراین هر میزبانی که
پایتون ۳.۱۰+ اجرا کند کافی است؛ سرویس هوش مصنوعی بیرونی و پایگاه‌دادهٔ بیرونی لازم نیست.

## ۱) ساخت بسته

```bash
python scripts/build_host_package.py              # dist/rayan-host.zip  (~۲۵ مگابایت)
python scripts/build_host_package.py --with-index # همراه با ایندکسِ شاهد دانشنامه
```

داخل بسته:

| مسیر | کار |
|---|---|
| `passenger_wsgi.py` | نقطهٔ ورود برای cPanel/Plesk/DirectAdmin (WSGI) |
| `web/` | سرور، صفحه‌ها، دانشنامه، استاتیک |
| `rayan/` | مدل و توکن‌ساز (بدون وابستگی سنگین) |
| `checkpoints/rayan-1-small.npz` | وزن‌ها (۲۴ مگابایت) |
| `data/knowledge*.jsonl` | دانشنامهٔ بررسی‌شده |
| `deploy/host_check.py` | بررسی خودکار نصب با خروجی ✓/✗ |
| `deploy/apache.rules.conf` | قواعد امنیتی/کش آپاچی |
| `README-HOST.md` | راهنمای گام‌به‌گام فارسی |

بسته **بدون** تست‌ها، `.git`، `.venv`، پایگاه‌داده‌های محلی و لاگ‌ها ساخته می‌شود.

## ۲) چه چیزی در کد برای هاست اضافه شده است

| بخش | فایل | کار |
|---|---|---|
| مسیرهای نوشتنی | `web/hosting.py::prepare_host_env` | اگر `<root>/var` نوشتنی نبود، `~/.rayan/var`؛ تنظیمِ `RAYAN_DB`، `RAYAN_OWNER_FILE`، `RAYAN_SECRET_FILE`، `RAYAN_OPS_DIR`، `RAYAN_BACKUP_DIR` و… |
| زیرشاخه | `web/hosting.py::BasePathMiddleware` | پاک‌کردنِ پیشوند از مسیر و بازنویسیِ `/static/...` در HTML/CSS + هم‌مسیرکردنِ `fetch`/`XHR`/`EventSource` |
| پلِ WSGI | `web/hosting.py::to_wsgi` | اجرای ASGI زیر Passenger/mod_wsgi، بدون بستهٔ اضافه |
| کوکی | `web/server.py::COOKIE_SECURE` | `RAYAN_COOKIE_SECURE=0` برای هاستِ بدون HTTPS |
| پس‌زمینه | `web/server.py::boot` | در `RAYAN_HOST=1` نخ‌های واچر و یادگیری خودکار خاموش می‌شوند (در Passenger عمر نمی‌کنند) |
| مسیرها | `web/security.py`، `web/admin.py` | کلیدِ امنیتی و پوشهٔ پشتیبان از محیط خوانده می‌شوند |

## ۳) میزبان‌ها

| میزبان | نوع | وضعیت |
|---|---|---|
| cPanel با **Setup Python App** | Passenger/WSGI | ✅ بستهٔ zip + `passenger_wsgi.py` |
| Plesk / DirectAdmin با پشتیبانی Python | Passenger/WSGI | ✅ همان بسته |
| VPS (هر provider) | Docker | ✅ `docker compose up -d` |
| Render / Hugging Face (Docker) | کانتینر | ✅ `render.yaml` و `Dockerfile` |
| هاست فقط PHP | — | ❌ پایتون اجرا نمی‌شود؛ از VPS/کانتینر استفاده کن |
| GitHub Pages / Netlify | ایستا | ⚠️ فقط صفحه‌های معرفی؛ گفتگو نه |

## ۴) متغیرهای محیطی مهم

| متغیر | پیش‌فرض | کار |
|---|---|---|
| `RAYAN_OWNER_PASSWORD` | — | گذرواژهٔ پنل مدیریت (باید تعریف شود) |
| `RAYAN_PUBLIC_URL` | — | نشانی کامل برای کوکی و ارجاع‌ها |
| `RAYAN_ENV` | `production` در حالت هاست | کوکی امن، HSTS |
| `RAYAN_COOKIE_SECURE` | از `RAYAN_ENV` | `0` برای سایتِ HTTP |
| `RAYAN_BASE_PATH` | خالی | اگر برنامه زیر `/rayan` است |
| `RAYAN_DATA_DIR` | `<root>/var` | پایگاه‌داده و پرونده‌های نوشتنی |
| `RAYAN_HOST` | `1` در `passenger_wsgi.py` | خاموش‌کردنِ نخ‌های پس‌زمینه |
| `RAYAN_BACKUP_DIR` | `<data>/backups` | محلِ پشتیبان‌ها |

فهرست کامل در `README-HOST.md` و `docs/DEPLOY_FREE.md` آمده است.

## ۵) بررسیِ نصب

```bash
python deploy/host_check.py     # ✓/✗ برای پایتون، بسته‌ها، مدل، دانشنامه، پلِ WSGI
curl -s https://example.com/api/health
```

`host_check.py` واقعاً یک درخواستِ `/api/health` را از دلِ پلِ WSGI رد می‌کند؛
یعنی اگر آن ✓ شد، Passenger هم پاسخ می‌دهد.

## ۶) آنچه هنوز هاستِ اشتراکی ندارد

* **چند نمونهٔ هم‌زمان** — Passenger یک فرایند دارد؛ SQLite و مدل تک‌نمونه‌اند.
* **SSE واقعی** — Passenger بدنه را بافر می‌کند؛ پاسخ یک‌جا می‌رسد (متن کامل، بدون
  افکتِ تایپ). روی uvicorn/Gunicorn افکت هست.
* **اجرای طولانیِ پس‌زمینه** — یادگیریِ خودکار و واچر عمداً خاموش‌اند.

این‌ها محدودیتِ میزبان است، نه باگ؛ روی VPS/Docker هر سه کار می‌کنند.
