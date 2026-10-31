#!/usr/bin/env bash
# دانلود منابع خام فارسی برای بازسازی پیکرهٔ رایان.
# داده‌ها بیرون از مخزن ذخیره می‌شوند (پیش‌فرض: ../corpora).
set -euo pipefail

DEST="${1:-../corpora}"
mkdir -p "$DEST"
cd "$DEST"

fetch_repo() {
  local repo="$1" branch="$2" name
  name="$(echo "$repo" | tr '/' '_')"
  if [ -d "$name" ]; then
    echo "[=] $repo از قبل هست"
    return
  fi
  echo "[+] $repo ($branch)"
  curl -L --fail --retry 3 --retry-delay 2 \
    "https://codeload.github.com/$repo/tar.gz/refs/heads/$branch" -o "$name.tar.gz"
  mkdir -p "$name"
  tar xzf "$name.tar.gz" -C "$name"
  rm "$name.tar.gz"
}

fetch_repo "milad-4274/persian_news" "master"
fetch_repo "danialfarsi/hamshahri_corpus" "main"
fetch_repo "namnamir/JSON_of_Classic_Persian_Poems" "master"

echo
echo "منابع در $DEST آماده شد."
echo "قدم بعدی:"
echo "  python data/build_corpus.py --sources $DEST --out data"
echo "  python data/train_tokenizer.py --vocab-size 10000"
echo "  python -m rayan.train --steps 1800 --batch-size 24 --block-size 256 --layers 5 --heads 4 --embed 256"
echo
echo "توجه: این داده‌ها متعلق به منابع اصلی هستند؛ شرایط آن‌ها را در NOTICE.md ببینید."
