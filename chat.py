import argparse
import math
import os
import time

import torch

from model import ByteTokenizer, GPTConfig, LocalGPT, save_checkpoint


def chunked_train_data(text: str, block_size: int):
    tokenizer = ByteTokenizer()
    tokens = torch.tensor(tokenizer.encode(text), dtype=torch.long)
    if len(tokens) <= block_size:
        raise ValueError("The text is too short for the configured block size.")
    return tokens


def get_batch(data: torch.Tensor, batch_size: int, block_size: int, device: str):
    starts = torch.randint(0, len(data) - block_size, (batch_size,))
    x = torch.stack([data[s:s + block_size] for s in starts]).to(device)
    y = torch.stack([data[s + 1:s + block_size + 1] for s in starts]).to(device)
    return x, y


def main():
    parser = argparse.ArgumentParser(description="Train a local GPT from a UTF-8 text file.")
    parser.add_argument("--input", required=True, help="Path to a UTF-8 text corpus")
    parser.add_argument("--output", default="checkpoints/local_model.pt", help="Where to save the checkpoint")
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--layers", type=int, default=8)
    parser.add_argument("--heads", type=int, default=8)
    parser.add_argument("--embed", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    tokens = chunked_train_data(text, args.block_size)
    cfg = GPTConfig(
        vocab_size=256,
        block_size=args.block_size,
        n_layer=args.layers,
        n_head=args.heads,
        n_embd=args.embed,
        dropout=0.1,
    )
    model = LocalGPT(cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.95), weight_decay=0.1)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.steps)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    start_time = time.time()

    model.train()
    for step in range(1, args.steps + 1):
        x, y = get_batch(tokens, args.batch_size, args.block_size, device)
        _, loss = model(x, y)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        if step % 50 == 0 or step == args.steps:
            print(f"step={step:05d}/{args.steps} loss={loss.item():.4f} lr={optimizer.param_groups[0]['lr']:.3e}")

    save_checkpoint(model, args.output)
    elapsed = time.time() - start_time
    print(f"Training complete in {elapsed:.1f}s. Model saved to {args.output}")


if __name__ == "__main__":
    main()
