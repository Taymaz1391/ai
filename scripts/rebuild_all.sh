#!/usr/bin/env bash
# بازسازی کامل پیکره و آموزش رایان ۲ از صفر — بدون دخالت دستی.
#
#   bash scripts/rebuild_all.sh [steps]
#
# مراحل: دانلود منابع → ساخت پیکرهٔ پایه → ادغام و حذف تکرار → توکن‌کردن →
# آموزش پایه → تنظیم گفتگو. هر مرحله لاگ خودش را در logs/ می‌نویسد و اگر فایل
# خروجی از قبل موجود باشد، از آن رد می‌شود (قابل ادامه بعد از قطع).
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CORPUS="${RAYAN_CORPUS:-/home/user/corpora}"
STEPS="${1:-2400}"
CHAT_STEPS="${2:-500}"
mkdir -p logs data checkpoints "$CORPUS"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a logs/rebuild.log; }

# ۱) منابع
if [ ! -d "$CORPUS/amnghd_Persian_poems_corpus" ]; then
  log "دانلود منابع فارسی"
  bash scripts/fetch_corpora.sh "$CORPUS" >> logs/fetch.log 2>&1 || log "هشدار: برخی منابع دانلود نشدند"
else
  log "منابع از قبل موجودند"
fi

# ۲) ویکی‌پدیا (اگر متن تمیزش نبود)
if [ ! -s "$CORPUS/wiki.txt" ]; then
  log "استخراج ویکی‌پدیای فارسی"
  .venv/bin/python scripts/import_wikipedia.py --src "$CORPUS/_wiki/repo" \
      --out "$CORPUS/wiki.txt" --max-chars 150000000 >> logs/wiki.log 2>&1 || log "هشدار: ویکی‌پدیا ساخته نشد"
fi

# ۳) پیکرهٔ پایه (خبر + شعر + گفتگو)
if [ ! -s "$CORPUS/base/train.txt" ]; then
  log "ساخت پیکرهٔ پایه (خبر، همشهری، شعر، گفتگو)"
  .venv/bin/python data/build_corpus.py --sources "$CORPUS" --out "$CORPUS/base" \
      >> logs/base-corpus.log 2>&1 || log "هشدار: پیکرهٔ پایه ناقص است"
fi

# ۴) ادغام منابع
INPUTS=()
[ -s "$CORPUS/base/train.txt" ] && INPUTS+=("$CORPUS/base/train.txt:18000000")
[ -s "$CORPUS/wiki.txt" ] && INPUTS+=("$CORPUS/wiki.txt:26000000")
[ -s "$CORPUS/omidkashefi_Mizan/ext/mizan/mizan_fa.txt" ] && INPUTS+=("$CORPUS/omidkashefi_Mizan/ext/mizan/mizan_fa.txt:40000000")
[ -d "$CORPUS/amnghd_Persian_poems_corpus/Persian_poems_corpus-master/normalized" ] && INPUTS+=("$CORPUS/amnghd_Persian_poems_corpus/Persian_poems_corpus-master/normalized:25000000")
[ -s "$CORPUS/miras-sample.txt" ] && INPUTS+=("$CORPUS/miras-sample.txt:6600000")

if [ ${#INPUTS[@]} -eq 0 ]; then
  log "هیچ منبعی آماده نیست؛ توقف"
  exit 1
fi

if [ ! -s data/train.txt ]; then
  log "ادغام ${#INPUTS[@]} منبع"
  .venv/bin/python scripts/merge_corpus.py --out data --inputs "${INPUTS[@]}" >> logs/merge.log 2>&1 || exit 1
fi

# ۵) توکن‌های uint16
if [ ! -s data/train.u16 ]; then
  log "توکن‌کردن پیکره با رایان‌بی‌پی‌ئی ۱۶هزارتایی"
  .venv/bin/python scripts/tokenize_corpus.py --tokenizer tokenizer/rayan_bpe_16k.json \
      --input data/train.txt --out data/train.u16 \
      --val data/val.txt --val-out data/val.u16 \
      >> logs/tokenize.log 2>&1 || exit 1
fi

# ۶) آموزش پایه از صفر
if [ ! -s checkpoints/rayan-2-base.npz ]; then
  log "آموزش پایه: ${STEPS} گام"
  .venv/bin/python -m rayan.train --tokenizer tokenizer/rayan_bpe_16k.json \
      --train-ids data/train.u16 --val-ids data/val.u16 \
      --out checkpoints/rayan-2-base.npz --latest checkpoints/rayan-2-last.npz \
      --metrics logs/metrics-v2.jsonl --steps "$STEPS" --batch-size 8 --block-size 256 \
      --layers 6 --heads 6 --embed 384 --lr 1e-3 --min-lr 1e-4 --warmup 150 \
      --eval-every 100 --eval-batches 4 --save-every 100 --log-every 25 \
      --name "رایان ۲" --corpus-note "خبر + ویکی‌پدیا + کتاب + شعر کلاسیک، ۹۹٫۱ میلیون نویسه" \
      >> logs/train-base.log 2>&1 || { log "آموزش پایه شکست خورد"; exit 1; }
fi

# ۷) تنظیم گفتگو: ۱۰٪ دادهٔ گفتگویی در جریان آموزش
if [ -s checkpoints/rayan-2-last.npz ] && ! grep -q '"stage": "chat"' logs/metrics-v2.jsonl 2>/dev/null; then
  log "ساخت ترکیب گفتگویی و تنظیم نهایی (${CHAT_STEPS} گام)"
  .venv/bin/python scripts/make_chat_mix.py --train-ids data/train.u16 --out data/mix.u16 \
      --seed-jsonl data/chat_seed.jsonl --tokenizer tokenizer/rayan_bpe_16k.json \
      --general-tokens 1290000 --chat-tokens 140000 >> logs/chat-mix.log 2>&1 || true
  if [ -s data/mix.u16 ]; then
    START=$(grep -o '"step": [0-9]*' logs/metrics-v2.jsonl | tail -1 | grep -o '[0-9]*')
    END=$(( ${START:-2400} + CHAT_STEPS ))
    .venv/bin/python -m rayan.train --tokenizer tokenizer/rayan_bpe_16k.json \
        --train-ids data/mix.u16 --val-ids data/val.u16 --resume checkpoints/rayan-2-last.npz \
        --out checkpoints/rayan-2-base.npz --latest checkpoints/rayan-2-last.npz \
        --metrics logs/metrics-v2.jsonl --steps "$END" --batch-size 8 --block-size 256 \
        --layers 6 --heads 6 --embed 384 --lr 3e-4 --min-lr 6e-5 --warmup 40 \
        --eval-every 100 --eval-batches 4 --save-every 100 --log-every 25 \
        --name "رایان ۲" --corpus-note "خبر + ویکی‌پدیا + کتاب + شعر کلاسیک + تنظیم گفتگو" \
        >> logs/train-chat.log 2>&1 || log "تنظیم گفتگو شکست خورد"
  fi
fi

# ۸) انتشار و کارت واقعی
if [ -s checkpoints/rayan-2-last.npz ]; then
  log "ارزیابی نهایی و انتشار checkpoint"
  .venv/bin/python scripts/finalize_run.py --checkpoint checkpoints/rayan-2-last.npz \
      --tokenizer tokenizer/rayan_bpe_16k.json --metrics logs/metrics-v2.jsonl \
      --name "رایان ۲" --batch-size 8 --lr 3e-4 --min-lr 6e-5 --warmup 40 \
      --corpus-note "خبر + ویکی‌پدیا + کتاب + شعر کلاسیک + تنظیم گفتگو" \
      >> logs/finalize.log 2>&1 || log "بستن اجرا شکست خورد"
fi

log "پایان بازسازی"
