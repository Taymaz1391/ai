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
fetch_repo "amnghd/Persian_poems_corpus" "master"
fetch_repo "omidkashefi/Mizan" "master"

# دامپ ویکی‌پدیای فارسی (پنج فایل زیپ JSONL) و نمونهٔ میراث
printf '[+] Persian-Wikipedia-Corpus\n'
curl -L --fail --retry 3 --retry-delay 2 \
  "https://codeload.github.com/Text-Mining/Persian-Wikipedia-Corpus/tar.gz/refs/heads/master" \
  -o wiki.tar.gz
mkdir -p _wiki && tar xzf wiki.tar.gz -C _wiki && rm wiki.tar.gz
# تاربال یک پوشه می‌سازد؛ اسکریپت استخراج، پوشهٔ حاوی zipها را می‌خواهد
if [ -d "_wiki/Persian-Wikipedia-Corpus-master" ] && [ ! -d "_wiki/repo" ]; then
  mv "_wiki/Persian-Wikipedia-Corpus-master" "_wiki/repo"
fi

if [ ! -f miras-sample.txt ]; then
  printf '[+] MirasText sample\n'
  curl -L --fail --retry 3 \
    "https://raw.githubusercontent.com/miras-tech/MirasText/master/MirasText/MirasText_sample.txt" \
    -o miras-sample.txt
fi

# میزان در یک فایل zip می‌آید؛ اگر از قبل باز نشده، بازش کن
if [ -f "omidkashefi_Mizan/mizan.zip" ] && [ ! -f "omidkashefi_Mizan/ext/mizan/mizan_fa.txt" ]; then
  ( cd omidkashefi_Mizan && unzip -q mizan.zip -d ext )
fi

echo
echo "منابع در $DEST آماده شد."
echo "قدم بعدی:"
echo "  python scripts/import_wikipedia.py --source $DEST/_wiki --max-chars 150000000"
echo "  python scripts/merge_corpus.py --out-dir data \\"
echo "      $DEST/milad-4274_persian_news:18000000 $DEST/wiki.txt:26000000 \\"
echo "      $DEST/omidkashefi_Mizan/ext/mizan/mizan_fa.txt:40000000 \\"
echo "      $DEST/amnghd_Persian_poems_corpus/normalized:25000000 \\"
echo "      $DEST/miras-sample.txt:6600000"
echo "  python data/train_tokenizer.py --vocab-size 16000 --sample-chars 24000000"
echo "  python scripts/tokenize_corpus.py --tokenizer tokenizer/rayan_bpe_16k.json \\"
echo "      --input data/train.txt --out data/train.u16 --val data/val.txt --val-out data/val.u16"
echo
echo "توجه: این داده‌ها متعلق به منابع اصلی هستند؛ شرایط آن‌ها را در NOTICE.md ببینید."
