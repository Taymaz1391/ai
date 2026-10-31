"""ساخت فایل نمایش نمونه‌ها برای صفحهٔ مدل از گزارش ارزیابی.

    python scripts/build_showcase.py --evaluation reports/evaluation.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

PREFERRED = [
    ("chat", "خودت را معرفی"),
    ("poetry", "شعر"),
    ("continue", "کویر"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", default="reports/evaluation.json")
    parser.add_argument("--out", default="reports/showcase.json")
    args = parser.parse_args()
    data = json.load(open(args.evaluation, encoding="utf-8"))
    samples = data.get("samples", [])
    chosen = []
    for mode, hint in PREFERRED:
        for sample in samples:
            if sample["mode"] == mode and (hint in sample.get("prompt", "") or mode == "poetry"):
                chosen.append(sample)
                break
    if len(chosen) < 3:
        for sample in samples:
            if sample not in chosen:
                chosen.append(sample)
            if len(chosen) >= 3:
                break
    examples = [
        {
            "mode": s["mode"],
            "prompt": s.get("prompt", ""),
            "text": s.get("text", ""),
            "tokens": s.get("tokens", 0),
            "tok_s": s.get("tok_s", 0),
            "confidence": s.get("confidence", 0),
        }
        for s in chosen[:3]
    ]
    payload = {
        "examples": examples,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "checkpoint_step": data.get("meta", {}).get("step"),
        "note": "نمونه‌های تصادفی بدون ویرایش دستی از همین مدل.",
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(payload, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"wrote {args.out} with {len(examples)} examples")


if __name__ == "__main__":
    main()
