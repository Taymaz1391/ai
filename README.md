# LocalGPT

یک مدل زبانی **کاملاً محلی و بدون اتصال به API**، از صفر با PyTorch. این پروژه یک پیاده‌سازی آموزشی اما قابل آموزش از معماری GPT است: توکن‌سازی بایتی، embedding، attention علّی، MLP، residual connection و sampling.

> نکتهٔ واقع‌بینانه: هیچ پروژهٔ کوچکی را نمی‌توان صادقانه «قوی‌تر از ChatGPT» نامید. قدرت مدل‌های بزرگ حاصل میلیاردها پارامتر، دادهٔ عظیم، GPUهای فراوان و ارزیابی/تنظیم گسترده است. این مخزن پایه‌ای قابل توسعه برای ساخت و آموزش مدل شخصی شماست و برای اجرای آن API خارجی لازم نیست.

## اجرا

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt

# یک متن آموزشی UTF-8 بسازید؛ هرچه بزرگ‌تر و باکیفیت‌تر بهتر
python train.py --input data.txt --out checkpoints/localgpt.pt --steps 3000
python chat.py --checkpoint checkpoints/localgpt.pt
```

برای تست سریع:

```bash
python train.py --input data.txt --out checkpoints/test.pt --steps 100 --batch-size 8
```

## معماری

- توکن‌ساز byte-level با واژگان ۲۵۶تایی؛ بنابراین فارسی و هر زبان UTF-8 بدون فایل vocabulary خارجی پشتیبانی می‌شود.
- Transformer decoder-only با masked self-attention.
- gradient clipping، AdamW، warmup و cosine decay.
- ذخیرهٔ checkpoint شامل وزن‌ها و تنظیمات مدل.
- تولید متن با temperature، top-k و top-p.

## مسیر ارتقا

برای مدل قدرتمندتر، دادهٔ پاک و دارای مجوز، tokenizer زیرکلمه‌ای، مجموعه‌دادهٔ instruction، ترجیح انسانی، ارزیابی مستقل، چند GPU و در ادامه distributed training اضافه کنید. مدل فعلی عمداً کوچک و شفاف است تا بتوان آن را روی یک GPU معمولی آموزش داد.

## مجوز

MIT
