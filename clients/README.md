# کلاینت‌های رایان (APK و EXE)

این پوشه فقط «پوستهٔ نازک» است. هیچ تصمیم امنیتی، سهمیه یا نقش مدیری داخل
کلاینت گرفته نمی‌شود؛ هر دو برنامه صفحهٔ همان سرور رایان را نمایش می‌دهند و
نشست، مالکیت حساب و مصرف روزانه سمت سرور بررسی می‌شود. به همین دلیل کاربر
نمی‌تواند با دست‌کاری فایل برنامه، خودش را «آنلاین» یا «ویژه» جا بزند.

| فایل | توضیح |
| --- | --- |
| `android/` | پروژهٔ Gradle؛ WebView تمام‌صفحه، بدون نوار نشانی |
| `windows/` | پروژهٔ .NET 8 WinForms + WebView2؛ پنجرهٔ بومی |

## نشانی سرور

نشانی هنگام **ساخت** داخل برنامه قرار می‌گیرد:

* در CI از متغیر مخزن `RAYAN_SERVER_URL` خوانده می‌شود
  (Settings → Secrets and variables → Actions → Variables).
* به‌صورت دستی: `gradle :app:assembleRelease -PserverUrl=https://your-host`
  و برای ویندوز `RAYAN_SERVER_URL` را پیش از `dotnet publish` ست کن.
* در ویندوز، متغیر محیطی `RAYAN_SERVER_URL` هنگام اجرا هم نشانی را عوض می‌کند
  (برای آزمون محلی).

## امضا

APK با کلید `rayan-sideload.p12` امضا می‌شود. این کلید فقط برای نصب مستقیم
(sideload) است و برای انتشار در Google Play مناسب نیست؛ اگر کلید خصوصی
Play را داری، `signingConfigs.release` را به آن تغییر بده.

## ساخت خودکار

`.github/workflows/clients.yml` هر تغییری در این پوشه را می‌سازد و دو فایل را
به انتشار `clients` پیوست می‌کند:

* `https://github.com/Taymaz1391/ai/releases/latest/download/rayan-android.apk`
* `https://github.com/Taymaz1391/ai/releases/latest/download/rayan-windows.exe`
