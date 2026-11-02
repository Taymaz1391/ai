"""نقشهٔ اجرای مدل ۱ میلیارد پارامتری — همهٔ عددها محاسبه‌شده، هیچ عددی ادعاشده نیست.

اجرا::

    python scripts/plan_1b.py                 # خلاصهٔ انسانی
    python scripts/plan_1b.py --json          # گزارش ماشین‌خوان
    python scripts/plan_1b.py --write         # ذخیره در reports/upgrade-1b.json

خروجی شاملِ: تعداد پارامتر (از خودِ معماری)، حجمِ حافظهٔ آموزش و استنتاج، تعداد
توکن و نویسهٔ لازمِ داده، و ساعت/هزینهٔ آموزش در چند سناریوی سخت‌افزاری است.
"""

from __future__ import annotations

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "configs", "rayan-1b.json")
REPORT = os.path.join(ROOT, "reports", "upgrade-1b.json")


def count_params(cfg: dict) -> dict:
    """پارامترها را از معماری می‌شمارد؛ کوکیِ «۱ میلیارد» دستی نوشته نمی‌شود."""
    v = int(cfg["vocab_size"])
    d = int(cfg["n_embd"])
    layers = int(cfg["n_layer"])
    mult = int(cfg.get("ffn_mult", 4))

    emb = v * d                      # لایهٔ ورودی
    head = 0 if cfg.get("tie_embeddings") else v * d
    attn = 4 * d * d                 # q, k, v, o
    ffn = 2 * mult * d * d           # دو ماتریسِ FFN؛ SwiGLU گیت را جدا می‌شمارد
    norms = 2 * d                    # دو نرمال‌سازی برای هر لایه (تقریب)
    per_layer = attn + ffn + norms
    total = emb + head + layers * per_layer
    return {"embedding": emb, "head": head, "per_layer": per_layer,
            "layers": layers, "total": total}


def plan(cfg: dict) -> dict:
    model = cfg["model"]
    data = cfg["data"]
    p = count_params(model)
    params = p["total"]

    tokens = int(data.get("target_tokens") or round(params * float(data["tokens_per_param"])))
    chars = tokens * float(data["chars_per_token"])
    # متن فارسی UTF-8 حدوداً ۱٫۸ بایت بر نویسه
    corpus_gb = chars * 1.8 / 1e9

    # حافظهٔ آموزش: وزن‌ها + گرادیان + حالت‌های Adam (bf16 وزن، fp32 حالت‌ها)
    weights_gb = params * 2 / 1e9
    grads_gb = params * 2 / 1e9
    adam_gb = params * 8 / 1e9
    activations_gb = 8.0
    train_gb = weights_gb + grads_gb + adam_gb + activations_gb

    scenarios = []
    for s in cfg["hardware_scenarios"]:
        tps = float(s["tokens_per_second"])
        hours = tokens / tps / 3600
        cost = hours * float(s["hourly_usd"])
        scenarios.append({
            "hardware": s["name"], "tokens_per_second": tps,
            "hours": round(hours, 1), "days": round(hours / 24, 2),
            "cost_usd": round(cost),
            "docs_per_hour": round(tps * 3600 / 1000, 1),
        })

    return {
        "params_total": params,
        "params_billion": round(params / 1e9, 3),
        "breakdown": p,
        "architecture": model,
        "tokens_needed": tokens,
        "chars_needed": int(chars),
        "corpus_gb_estimate": round(corpus_gb, 1),
        "memory": {"weights_gb": round(weights_gb, 2), "grads_gb": round(grads_gb, 2),
                   "adam_gb": round(adam_gb, 2), "train_total_gb": round(train_gb, 1),
                   "inference_gb_bf16": round(weights_gb + 1.0, 2)},
        "scenarios": scenarios,
        "fits_on_cpu": False,
        "honest_note": ("آموزشِ این مدل روی CPUِ همین سرور ممکن نیست: هم توان محاسباتی و "
                        "هم حافظهٔ لازم چند مرتبه بیشتر از این ماشین است. اعدادِ ساعت و "
                        "هزینه تخمینِ خطی از توانِ اعلام‌شدهٔ هر سخت‌افزار است، نه اندازه‌گیری."),
    }


def render(report: dict) -> str:
    fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    lines = [
        "نقشهٔ مدل ۱ میلیارد پارامتری",
        f"پارامتر: {report['params_total']:,}".translate(fa),
        f"توکن لازم برای آموزش: {report['tokens_needed']:,}".translate(fa),
        f"دادهٔ لازم (تقریب): {report['corpus_gb_estimate']} گیگابایت".translate(fa),
        f"حافظهٔ آموزش: {report['memory']['train_total_gb']} گیگابایت".translate(fa),
        f"حافظهٔ استنتاج (bf16): {report['memory']['inference_gb_bf16']} گیگابایت".translate(fa),
        "",
        "زمان و هزینه در سناریوهای سخت‌افزاری:",
    ]
    for s in report["scenarios"]:
        lines.append(f"  • {s['hardware']}: {s['hours']} ساعت ({s['days']} روز)، "
                     f"حدود {s['cost_usd']} دلار".translate(fa))
    lines += ["", report["honest_note"]]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="نقشهٔ مدل ۱ میلیارد پارامتری")
    parser.add_argument("--json", action="store_true", help="خروجی JSON")
    parser.add_argument("--write", action="store_true", help="ذخیره در reports/upgrade-1b.json")
    args = parser.parse_args()

    with open(CONFIG, encoding="utf-8") as fh:
        cfg = json.load(fh)
    report = plan(cfg)
    if args.write:
        os.makedirs(os.path.dirname(REPORT), exist_ok=True)
        with open(REPORT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"نوشته شد: {os.path.relpath(REPORT, ROOT)}")
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
