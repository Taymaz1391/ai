#!/usr/bin/env bash
# خصوصی‌کردن مخزن گیت‌هاب
#
# چرا این فایل وجود دارد؟ توکن اتصالِ GitHub در محیط اجرا، یک توکن «اپ» است و
# اجازهٔ تغییر تنظیمات مخزن (administration) ندارد؛ برای همین تغییر دسترسی با خطای
# 403 «Resource not accessible by integration» رد می‌شود. با یک توکن شخصی (PAT) که
# محدودهٔ «repo» دارد، همین فرمان مخزن را خصوصی می‌کند.
#
#   ساخت توکن: https://github.com/settings/tokens  (Scope: repo)
#   اجرا:      GH_TOKEN=ghp_xxx bash scripts/make_private.sh
#
# راه ساده‌تر و بی‌نیاز از توکن:
#   https://github.com/Taymaz1391/ai/settings  →  پایین صفحه، Danger Zone
#   → Change repository visibility → Make private
set -euo pipefail

OWNER="${RAYAN_REPO_OWNER:-Taymaz1391}"
NAME="${RAYAN_REPO_NAME:-ai}"

if [ -z "${GH_TOKEN:-}" ]; then
  echo "GH_TOKEN تنظیم نشده است." >&2
  echo "یک توکن شخصی با محدودهٔ repo بساز و همین‌طور اجرا کن:" >&2
  echo "  GH_TOKEN=ghp_xxx bash scripts/make_private.sh" >&2
  exit 2
fi

echo "→ بررسی وضعیت فعلی…"
curl -s -H "Authorization: token ${GH_TOKEN}" \
  "https://api.github.com/repos/${OWNER}/${NAME}" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("   visibility:", d.get("visibility") or ("private" if d.get("private") else "public"))'

echo "→ خصوصی‌کردن ${OWNER}/${NAME}…"
CODE=$(curl -s -o /tmp/make_private.out -w "%{http_code}" -X PATCH \
  -H "Authorization: token ${GH_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${OWNER}/${NAME}" \
  -d '{"private": true}')

if [ "${CODE}" = "200" ]; then
  python3 -c 'import json; d=json.load(open("/tmp/make_private.out")); print("✓ حالا خصوصی است:", d.get("private"), d.get("visibility"))'
else
  echo "✗ تغییر انجام نشد (HTTP ${CODE})" >&2
  cat /tmp/make_private.out >&2
  echo >&2
  echo "اگر ۴۰۳ گرفتی، توکن محدودهٔ «repo» ندارد یا اپ نصب‌شده اجازهٔ administration ندارد." >&2
  exit 1
fi
