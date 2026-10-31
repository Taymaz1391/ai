# انتشار عمومی رایان — دو دقیقه تا یک لینک واقعی

این مخزن طوری چیده شده که با یک کلیک روی سرویس‌های رایگان بالا بیاید. هیچ سرویس
هوش مصنوعی بیرونی لازم نیست؛ خودِ مدل (۲۴ مگابایت) داخل مخزن است.

## ۱) Render — سریع‌ترین راه (رایگان)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Taymaz1391/ai)

۱. روی دکمه بزن و با حساب GitHub وارد شو.
۲. Render فایل `render.yaml` را می‌خواند و سرویس را می‌سازد.
۳. هنگام ساخت، دو متغیر از تو می‌پرسد:

   | متغیر | مقدار |
   |---|---|
   | `RAYAN_OWNER_PASSWORD` | یک گذرواژهٔ قوی برای پنل مدیریت (`/admin`) |
   | `RAYAN_PUBLIC_URL` | آدرس نهایی سرویس، مثل `https://rayan.onrender.com` |

۴. بعد از چند دقیقه، آدرس `https://<name>.onrender.com` لینک عمومی توست.

> پلن رایگان Render بعد از ۱۵ دقیقه بی‌کاری می‌خوابد و اولین درخواست بعدی چند
> ثانیه طول می‌کشد. برای همیشه‌بیدار، پلن استارتر یا یک VPS کوچک کافی است.

## ۲) Hugging Face Spaces (Docker)

```bash
# یک Space از نوع Docker بساز و این مخزن را وصل کن
sdk: docker
app_port: 8000
```

`Dockerfile` مخزن همین حالا آماده است و مدل و دادهٔ دانشنامه را داخل تصویر می‌برد.

## ۳) سرور خودت

```bash
git clone https://github.com/Taymaz1391/ai && cd ai
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
RAYAN_ENV=production RAYAN_OWNER_PASSWORD='یک-گذرواژهٔ-قوی' \
RAYAN_PUBLIC_URL='https://example.com' \
python web/server.py --host 0.0.0.0 --port 8000
```

پشت Nginx/Caddy بگذار و TLS را روشن کن. کوکی‌ها در `production` خودکار `Secure`
می‌شوند و مبدأهای ناشناس رد می‌شوند.

## ۴) انتشار فقط صفحه‌های ایستا (بدون مدل)

اگر فقط معرفی و مستندات لازم است:

```bash
python scripts/export_site.py     # خروجی در _site/
```

سپس `_site/` را روی GitHub Pages، Netlify یا Cloudflare Pages بگذار. گفتگو در این
حالت کار نمی‌کند چون به سرور مدل نیاز دارد.

## چک‌لیست پیش از انتشار

- [ ] `RAYAN_OWNER_PASSWORD` را در محیط تعریف کن (هیچ‌وقت در Git نگذار).
- [ ] `RAYAN_PUBLIC_URL` را با دامنهٔ واقعی پر کن تا کوکی مهمان و مبدأها درست باشند.
- [ ] پورت سرویس برابر `$PORT` باشد (Render آن را خودش می‌دهد).
- [ ] `curl -i https://<domain>/api/health` باید `200` و `"ok": true` بدهد.
