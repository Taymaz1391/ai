#!/usr/bin/env python3
"""آموزش توکنایزر BPE روی پیکرهٔ بزرگ، به‌صورت جریانی.

    python scripts/train_tokenizer.py --corpus data/train.txt \
        --chars 100000000 --vocab 32000 --out tokenizer/rayan_bpe.json

برای پیکره‌ای که در حافظه جا نمی‌شود: فایل را تکه‌تکه می‌خوانیم و فقط شمارش
تکه‌ها را نگه می‌داریم. عدد ``--chars`` سقف نویسه‌ای است که واقعاً دیده
می‌شود؛ اگر پیکره کوچک‌تر باشد، همان‌قدر خوانده می‌شود و گزارش می‌دهد.

دربارهٔ «۱۰۰ میلیون»: واژگان ۱۰۰ میلیون توکنی عملاً ناممکن است — خودِ جدول
جاسازی برای مدل کوچک چند صد گیگابایت می‌شود و هیچ متنی آن را پر نمی‌کند.
آنچه معنا دارد این است: آموزش توکنایزر روی ۱۰۰ میلیون نویسهٔ متن، با واژگانی
که با اندازهٔ مدل می‌خواند (۱۰ تا ۳۲ هزار). همان کار را همین ابزار می‌کند.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rayan.tokenizer import BPETokenizer, pretokenize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="آموزش BPE جریانی")
    ap.add_argument("--corpus", default="data/train.txt")
    ap.add_argument("--chars", type=int, default=100_000_000)
    ap.add_argument("--vocab", type=int, default=32_000)
    ap.add_argument("--min-frequency", type=int, default=2)
    ap.add_argument("--out", default="tokenizer/rayan_bpe-32k.json")
    args = ap.parse_args()

    path = Path(args.corpus)
    if not path.exists():
        print(f"پیکره پیدا نشد: {path}", file=sys.stderr)
        return 1

    freq: Counter[str] = Counter()
    read = 0
    started = time.time()
    last = started
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            freq.update(pretokenize(line))
            read += len(line)
            now = time.time()
            if now - last > 10:
                last = now
                print(f"[tokenizer] {read:,} نویسه · {len(freq):,} تکهٔ یکتا", flush=True)
            if read >= args.chars:
                break

    # تکه‌های تک‌بارمصرف را دور می‌ریزیم؛ برای مرزهای واژه لازم نیستند و حافظه را
    # چند برابر می‌کنند. آستانه با اندازهٔ پیکره تنظیم می‌شود.
    cut = args.min_frequency if read > 20_000_000 else 1
    kept = Counter({k: v for k, v in freq.items() if v >= cut})
    print(f"[tokenizer] خوانده‌شده {read:,} نویسه · نگه‌داشته {len(kept):,} تکه", flush=True)

    tok = BPETokenizer.train_from_freq(kept, vocab_size=args.vocab, verbose=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tok.save(str(out))
    size = out.stat().st_size
    print(f"[tokenizer] {out} · واژگان {len(tok.vocab):,} · {size / 1024:.0f} کیلوبایت · "
          f"{time.time() - started:.0f} ثانیه")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
