"""گفتگوی ترمینالی با رایان.

    python scripts/chat_cli.py --checkpoint checkpoints/rayan-1-small.npz
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.generate import Engine  # noqa: E402
from rayan.thinking import deep_reply  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="checkpoints/rayan-1-small.npz")
    parser.add_argument("--tokenizer", default="tokenizer/rayan_bpe.json")
    parser.add_argument("--mode", default="chat", choices=["chat", "continue", "poetry"])
    parser.add_argument("--deep", action="store_true")
    args = parser.parse_args()

    engine = Engine(args.checkpoint, args.tokenizer)
    history: list[tuple[str, str]] = []
    print(f"رایان آماده است (step={engine.meta.get('step')}). برای خروج «exit» بنویسید.")
    while True:
        try:
            message = input("\nشما: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in {"exit", "quit", "خروج"}:
            break
        if not message:
            continue
        if args.deep:
            answer, generation, trace = deep_reply(engine, message, mode=args.mode, history=history)
            print(f"\nرایان ({generation.tokens_per_second:.0f} tok/s): {answer}")
            print(f"  {trace['rationale']}")
        else:
            answer, generation, _ = engine.reply(message, mode=args.mode, history=history)
            print(f"\nرایان ({generation.tokens_per_second:.0f} tok/s): {answer}")
        if args.mode == "chat":
            history.append((message, answer))
            del history[:-2]


if __name__ == "__main__":
    main()
