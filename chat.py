import argparse, sys, torch
from model import ByteTokenizer, GPTConfig, LocalGPT


def main():
    p = argparse.ArgumentParser(description="Chat with a local checkpoint; no API or internet is used")
    p.add_argument("--checkpoint", required=True); p.add_argument("--tokens", type=int, default=200)
    p.add_argument("--temperature", type=float, default=0.8); p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--top-p", type=float, default=0.95); args = p.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    saved = torch.load(args.checkpoint, map_location=device)
    model = LocalGPT(GPTConfig(**saved["config"])).to(device); model.load_state_dict(saved["model"]); model.eval()
    tok = ByteTokenizer(); print("LocalGPT آماده است. برای خروج exit یا quit بنویسید.")
    while True:
        try: prompt = input("شما: ")
        except (EOFError, KeyboardInterrupt): print(); break
        if prompt.strip().lower() in {"exit", "quit", "خروج"}: break
        if not prompt.strip(): continue
        ids = torch.tensor([tok.encode(prompt)], dtype=torch.long, device=device)
        out = model.generate(ids, args.tokens, args.temperature, args.top_k, args.top_p)[0].tolist()
        answer = tok.decode(out[len(ids[0]):])
        print("مدل:", answer)

if __name__ == "__main__": main()
