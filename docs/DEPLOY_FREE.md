# استقرار رایگان رایان

هدف: بالا آوردن همین سایت روی یک نشانی عمومی، بدون پرداخت پول و بدون سرویس هوش مصنوعی بیرونی. مدل ۲۴ مگابایتی است و در ۵۱۲ مگابایت رم هم اجرا می‌شود، بنابراین گزینه‌های رایگان زیادی وجود دارد.

> **صادق باشیم:** هیچ سرویسی نمی‌تواند برای شما دامنهٔ سطح‌اول رایگان و دائمی بدهد. آنچه رایگان است، **زیردامنه** است (مثل `rayan.onrender.com` یا `user-rayan.hf.space`). دامنهٔ اختصاصی فقط با خرید یا ثبت رایگان در برخی ثبت‌کننده‌ها (مثل `eu.org` با تأخیر طولانی) ممکن است.

---

## گزینهٔ ۰: GitHub Pages (فقط نسخهٔ استاتیک)

اگر می‌خواهید صفحهٔ اصلی، تعرفه، مدل‌ها، مستندات و درباره با دامنهٔ `github.io` بالا بیاید:

1. در GitHub → **Settings → Pages** → Source را روی **GitHub Actions** بگذارید.
2. workflowهای `pages.yml` (انتشار) و `tests.yml` (آزمون) از پیش در `.github/workflows/` هستند.
3. با هر push به `main`، اسکریپت `scripts/export_site.py` سایت را در `_site/` می‌سازد و منتشر می‌کند.
4. آدرس: `https://<username>.github.io/ai/`

**چه چیزی کار می‌کند:** همهٔ صفحه‌های اطلاعاتی، مانیفست PWA، آیکون‌ها و حرکت‌ها.
**چه چیزی کار نمی‌کند:** گفتگو، ورود و ذخیرهٔ گفتگو — چون GitHub Pages فقط فایل ایستا سرو می‌کند و پایتون اجرا نمی‌کند. صفحهٔ گفتگو در این نسخه یک نوار «نمایشی» نشان می‌دهد و فرم را غیرفعال می‌کند.

اگر بک‌اند را روی Render/HF بالا آوردید، در `web/static/config.js` مقدار `apiBase` را به آن آدرس بدهید و
دوباره export کنید؛ برای کوکی بین‌دامنه‌ای هم `SameSite=None; Secure` لازم است (فعلاً توصیه نمی‌شود و
ساده‌تر آن است که خود دامنهٔ Render را به کاربر بدهید).

---

## گزینهٔ ۱ (پیشنهادی): Hugging Face Spaces با Docker

**چرا:** ۲ هستهٔ CPU و ۱۶ گیگابایت رم رایگان، زیردامنهٔ `*.hf.space`، مناسب مدل‌های کوچک، بدون خواب اجباری سریع.

1. در [huggingface.co](https://huggingface.co) حساب بسازید.
2. **New Space** → نام `rayan` → SDK را روی **Docker** بگذارید → Public → Create.
3. مخزن را push کنید (Space یک git repo است):

```bash
git remote add hf https://huggingface.co/spaces/<username>/rayan
git push hf arena/cb46300d-ai:main
```

اگر فایل ۲۴ مگابایتی checkpoint رد شد، Git LFS را فعال کنید:

```bash
git lfs install
git lfs track "checkpoints/*.npz"
git add .gitattributes
git commit -m "track checkpoints with LFS"
git push hf arena/cb46300d-ai:main
```

4. در تنظیمات Space، پورت برنامه `8000` است (در `Dockerfile` تنظیم شده). فضای Docker به‌طور پیش‌فرض پورت ۷۸۶۰ را انتظار دارد؛ اگر باز نشد، در فایل `README.md` مخزن Space این خط را اضافه کنید:

```yaml
---
title: Rayan
sdk: docker
app_port: 8000
---
```

5. آدرس نهایی: `https://<username>-rayan.hf.space`

نکته: Spaceهای رایگان پس از مدت بی‌استفادگی می‌خوابند و اولین بازدید چند ده ثانیه طول می‌کشد.

---

## گزینهٔ ۲: Render (Blueprint آماده)

فایل `render.yaml` در مخزن هست.

1. در [render.com](https://render.com) با GitHub وارد شوید.
2. **New → Blueprint** → مخزن را انتخاب کنید.
3. Render خودش سرویس رایگان می‌سازد:

```yaml
services:
  - type: web
    name: rayan
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python web/server.py --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
```

4. صبر کنید تا build تمام شود؛ آدرس `https://rayan-xxxx.onrender.com` آماده است.

محدودیت‌های نسخهٔ رایگان: ۵۱۲ مگابایت رم، خواب پس از بی‌کاری (cold start ~۳۰ ثانیه)، پهنای باند محدود.

---

## گزینهٔ ۳: پروکسی سریع برای دموی موقت

اگر فقط می‌خواهید چند دقیقه لینک عمومی داشته باشید:

```bash
# سرور را اجرا کنید
python web/server.py --host 0.0.0.0 --port 8000

# در ترمینال دیگر (نیازمند نصب cloudflared)
cloudflared tunnel --url http://localhost:8000
```

Cloudflare یک نشانی موقت `*.trycloudflare.com` می‌دهد. پایدار نیست و برای دموی کوتاه مناسب است. هیچ داده‌ای به سرویس هوش مصنوعی نمی‌رود؛ فقط ترافیک وب عبور می‌کند.

---

## دامنهٔ اختصاصی

اگر دامنه‌ای دارید (مثلاً `rayan.ir`):

- در Render: **Settings → Custom Domain** و یک `CNAME` به میزبان Render.
- در Hugging Face: قابلیت دامنهٔ سفارشی فقط برای Spaces پولی است؛ در نسخهٔ رایگان از زیردامنهٔ `hf.space` استفاده کنید.
- DNS رایگان: Cloudflare (ثبت دامنه هزینه دارد، DNS رایگان است). `eu.org` زیردامنهٔ رایگان می‌دهد اما صف تأیید طولانی دارد و برای دموی فوری مناسب نیست.

---

## متغیرهای محیطی

| متغیر | پیش‌فرض | کار |
|---|---|---|
| `RAYAN_DB` | `data/rayan.sqlite3` | مسیر پایگاه‌دادهٔ SQLite |
| `RAYAN_PROD` | خالی | با `1` کوکی‌ها `Secure` می‌شوند |
| `PORT` | `8000` | پورت شنود (Render آن را تعیین می‌کند) |
| `OPENBLAS_NUM_THREADS` | — | محدودکردن نخ‌های BLAS برای رم کمتر |

> در پلن رایگان یک نمونهٔ واحد اجرا می‌شود؛ مدل با یک قفل تک‌نخی پاسخ می‌دهد، پس هم‌زمانی بالا صف می‌شود.
> برای دمو کافی است. فایل SQLite را روی دیسک موقت می‌گذارید؛ با هر بازاستقرار پاک می‌شود.

---

## چک‌لیست پیش از انتشار عمومی

- [ ] `python scripts/evaluate.py` را اجرا و نتایج را در `docs/MODEL_CARD.md` به‌روز کنید.
- [ ] `python -m unittest discover -s tests` و `python tests/gradcheck.py` را سبز نگه دارید.
- [ ] متن حریم خصوصی/شرایط را با سیاست واقعی خود هم‌راست کنید (اکنون در `/about` آمده است).
- [ ] اگر سایت عمومی است، ارسال ایمیل بازیابی گذرواژه و تأیید ایمیل را در نظر بگیرید (اکنون وجود ندارد).
- [ ] هدر `Content-Security-Policy` را در صورت افزودن اسکریپت بیرونی بازبینی کنید.
- [ ] اندازهٔ RAM را بررسی کنید: مدل بارگذاری‌شده حدود ۲۵ مگابایت، فرایند Python با NumPy حدود ۱۵۰–۲۵۰ مگابایت.
- [ ] بکاپ `checkpoints/rayan-1-small.npz` و `logs/metrics.jsonl` را نگه دارید.
- [ ] شرایط منابع داده (`NOTICE.md`) را در صفحهٔ عمومی ذکر کنید.

---

## هزینهٔ واقعی

| مورد | هزینه |
|---|---|
| آموزش روی CPU این سندباکس | ~۳٫۲ ساعت-core |
| میزبانی Hugging Face (پایه) | ۰ |
| میزبانی Render (پایه) | ۰ |
| دامنهٔ اختصاصی | معمولاً سالانه |
