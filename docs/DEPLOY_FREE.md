# استقرار رایگان پارسیا

هدف: بالا آوردن همین سایت روی یک نشانی عمومی، بدون پرداخت پول و بدون سرویس هوش مصنوعی بیرونی. مدل ۲۴ مگابایتی است و در ۵۱۲ مگابایت رم هم اجرا می‌شود، بنابراین گزینه‌های رایگان زیادی وجود دارد.

> **صادق باشیم:** هیچ سرویسی نمی‌تواند برای شما دامنهٔ سطح‌اول رایگان و دائمی بدهد. آنچه رایگان است، **زیردامنه** است (مثل `parsia.onrender.com` یا `user-parsia.hf.space`). دامنهٔ اختصاصی فقط با خرید یا ثبت رایگان در برخی ثبت‌کننده‌ها (مثل `eu.org` با تأخیر طولانی) ممکن است.

---

## گزینهٔ ۱ (پیشنهادی): Hugging Face Spaces با Docker

**چرا:** ۲ هستهٔ CPU و ۱۶ گیگابایت رم رایگان، زیردامنهٔ `*.hf.space`، مناسب مدل‌های کوچک، بدون خواب اجباری سریع.

1. در [huggingface.co](https://huggingface.co) حساب بسازید.
2. **New Space** → نام `parsia` → SDK را روی **Docker** بگذارید → Public → Create.
3. مخزن را push کنید (Space یک git repo است):

```bash
git remote add hf https://huggingface.co/spaces/<username>/parsia
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
title: Parsia
sdk: docker
app_port: 8000
---
```

5. آدرس نهایی: `https://<username>-parsia.hf.space`

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
    name: parsia
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python web/server.py --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
```

4. صبر کنید تا build تمام شود؛ آدرس `https://parsia-xxxx.onrender.com` آماده است.

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

اگر دامنه‌ای دارید (مثلاً `parsia.ir`):

- در Render: **Settings → Custom Domain** و یک `CNAME` به میزبان Render.
- در Hugging Face: قابلیت دامنهٔ سفارشی فقط برای Spaces پولی است؛ در نسخهٔ رایگان از زیردامنهٔ `hf.space` استفاده کنید.
- DNS رایگان: Cloudflare (ثبت دامنه هزینه دارد، DNS رایگان است). `eu.org` زیردامنهٔ رایگان می‌دهد اما صف تأیید طولانی دارد و برای دموی فوری مناسب نیست.

---

## چک‌لیست پیش از انتشار عمومی

- [ ] `python scripts/evaluate.py` را اجرا و نتایج را در `docs/MODEL_CARD.md` به‌روز کنید.
- [ ] فیلتر محتوا و محدودیت نرخ اضافه کنید (سرویس فعلی بدون احراز هویت است).
- [ ] هدر `Content-Security-Policy` را در صورت افزودن اسکریپت بیرونی بازبینی کنید.
- [ ] اندازهٔ RAM را بررسی کنید: مدل بارگذاری‌شده حدود ۲۵ مگابایت، فرایند Python با NumPy حدود ۱۵۰–۲۵۰ مگابایت.
- [ ] بکاپ `checkpoints/parsia-1-small.npz` و `logs/metrics.jsonl` را نگه دارید.
- [ ] شرایط منابع داده (`NOTICE.md`) را در صفحهٔ عمومی ذکر کنید.

---

## هزینهٔ واقعی

| مورد | هزینه |
|---|---|
| آموزش روی CPU این سندباکس | ~۳٫۲ ساعت-core |
| میزبانی Hugging Face (پایه) | ۰ |
| میزبانی Render (پایه) | ۰ |
| دامنهٔ اختصاصی | معمولاً سالانه |
