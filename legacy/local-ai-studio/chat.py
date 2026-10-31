import argparse
import torch
from model import ByteTokenizer, load_checkpoint


def generate_reply(model, prompt, max_new_tokens=180, temperature=0.75, top_k=40, top_p=0.92, device="cpu"):
    tokenizer = ByteTokenizer()
    ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long, device=device)
    result = model.generate(ids, max_new_tokens=max_new_tokens, temperature=temperature, top_k=top_k, top_p=top_p)
    return tokenizer.decode(result[0, ids.shape[1]:].tolist()).strip()


def main():
    parser = argparse.ArgumentParser(description="Chat with a local checkpoint")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--prompt")
    parser.add_argument("--max-new-tokens", type=int, default=180)
    parser.add_argument("--temperature", type=float, default=.75)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--top-p", type=float, default=.92)
    args = parser.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_checkpoint(args.checkpoint, device)
    if args.prompt:
        print(generate_reply(model, args.prompt, args.max_new_tokens, args.temperature, args.top_k, args.top_p, device))
        return
    print("Local AI آماده است؛ برای خروج exit بنویسید.")
    while True:
        prompt = input("شما: ").strip()
        if prompt.lower() in {"exit", "quit", "خروج"}: break
        if prompt:
            print("مدل:", generate_reply(model, prompt, args.max_new_tokens, args.temperature, args.top_k, args.top_p, device))

if __name__ == "__main__": main()
