#!/usr/bin/env bash
# انتشار ایندکس‌ها به‌عنوان داراییِ یک انتشار گیت‌هاب (به‌جای گذاشتن ۸۶۵ مگابایت در مخزن)
#
#   bash scripts/publish_index.sh v1-index
#
# بعد از انتشار، این دو متغیر را روی سرور تنظیم کن:
#   RAYAN_INDEX_URL=https://github.com/<owner>/<repo>/releases/download/v1-index/index.sqlite3
#   RAYAN_WIKI_URL=https://github.com/<owner>/<repo>/releases/download/v1-index/wiki.sqlite3
# و در شروع اجرا:  python scripts/fetch_index.py
set -euo pipefail

TAG="${1:-v1-index}"
REPO="${RAYAN_REPO:-Taymaz1391/ai}"

for file in data/index.sqlite3 data/wiki.sqlite3; do
  if [ ! -f "$file" ]; then
    echo "فایل $file نیست؛ اول scripts/build_index.py و scripts/build_wiki.py را اجرا کن." >&2
    exit 2
  fi
done

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "→ انتشار $TAG از قبل هست؛ فایل‌ها جایگزین می‌شوند (--clobber)"
else
  echo "→ ساخت انتشار $TAG"
  gh release create "$TAG" --repo "$REPO" \
    --title "ایندکس دانش رایان $TAG" \
    --notes "ایندکس پیکرهٔ فارسی و دانشنامهٔ ویکی‌پدیای فارسی (بازسازی با scripts/build_index.py و scripts/build_wiki.py)"
fi

echo "→ بارگذاری (ممکن است چند دقیقه طول بکشد)…"
gh release upload "$TAG" data/index.sqlite3 data/wiki.sqlite3 --repo "$REPO" --clobber

echo "✓ آماده. نشانی‌ها:"
gh release view "$TAG" --repo "$REPO" --json assets \
  --jq '.assets[] | "  \(.name)  \(.size) bytes\n  \(.url)"'
