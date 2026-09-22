import argparse, math, os, time
import torch
from model import ByteTokenizer, GPTConfig, LocalGPT


def get_batch(data, batch_size, block_size, device):
    starts = torch.randint(0, len(data) - block_size - 1, (batch_size,))
    x = torch.stack([data[i:i + block_size] for i in starts]).to(device)
    y = torch.stack([data[i + 1:i + block_size + 1] for i in starts]).to(device)
    return x, y


def main():
    p = argparse.ArgumentParser(description="Train LocalGPT from a local UTF-8 text file")
    p.add_argument("--input", required=True); p.add_argument("--out", default="checkpoints/localgpt.pt")
    p.add_argument("--steps", type=int, default=3000); p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--block-size", type=int, default=256); p.add_argument("--layers", type=int, default=6)
    p.add_argument("--heads", type=int, default=6); p.add_argument("--embed", type=int, default=384)
    p.add_argument("--lr", type=float, default=3e-4); p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(); torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    text = open(args.input, "r", encoding="utf-8").read()
    ids = torch.tensor(ByteTokenizer().encode(text), dtype=torch.long)
    if len(ids) <= args.block_size + 1: raise ValueError("input file must contain more than block_size bytes")
    cfg = GPTConfig(block_size=args.block_size, n_layer=args.layers, n_head=args.heads, n_embd=args.embed)
    model = LocalGPT(cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.95), weight_decay=0.1)
    model.train(); start = time.time()
    for step in range(args.steps):
        progress = step / max(1, args.steps - 1)
        lr = args.lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress)))
        for group in optimizer.param_groups: group["lr"] = lr
        x, y = get_batch(ids, args.batch_size, args.block_size, device)
        _, loss = model(x, y); optimizer.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
        if step % 50 == 0 or step == args.steps - 1:
            print(f"step={step:5d}/{args.steps} loss={loss.item():.4f} lr={lr:.2e} device={device}")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    torch.save({"config": model.config_dict(), "model": model.state_dict(), "step": args.steps}, args.out)
    print(f"saved {args.out} ({time.time() - start:.1f}s)")

if __name__ == "__main__": main()
