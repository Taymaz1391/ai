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

# نمونهٔ میراث اختیاری است: اگر این میزبان در دسترس نباشد (فیلتر شبکه یا خطای SSL)
# بقیهٔ منابع باید همچنان کامل شوند، وگرنه پیکره ناقص می‌ماند.
if [ ! -f miras-sample.txt ]; then
  printf '[+] MirasText sample\n'
  if ! curl -L --fail --retry 2 --retry-delay 2 \
      "https://raw.githubusercontent.com/miras-tech/MirasText/master/MirasText/MirasText_sample.txt" \
      -o miras-sample.txt; then
    printf '[!] MirasText در دسترس نیست؛ بدون این منبع ادامه می‌دهیم.\n'
    rm -f miras-sample.txt
  fi
fi

# میزان در یک فایل zip می‌آید؛ اگر از قبل باز نشده، بازش کن.
# تاربال، zip را یک پوشه پایین‌تر می‌گذارد (Mizan-master/)، پس با find پیدایش می‌کنیم.
if [ ! -s omidkashefi_Mizan/ext/mizan/mizan_fa.txt ]; then
  MIZAN_ZIP="$(find omidkashefi_Mizan -maxdepth 3 -name 'mizan.zip' -print -quit 2>/dev/null || true)"
  if [ -n "${MIZAN_ZIP}" ]; then
    mkdir -p omidkashefi_Mizan/ext
    unzip -q -o "${MIZAN_ZIP}" -d omidkashefi_Mizan/ext
  fi
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
