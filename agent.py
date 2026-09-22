import argparse

import torch

from model import ByteTokenizer, load_checkpoint


def generate_reply(model, prompt: str, max_new_tokens: int = 200, temperature: float = 0.8, top_k: int = 50, top_p: float = 0.95):
    tokenizer = ByteTokenizer()
    token_ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long)
    output = model.generate(
        token_ids,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_k=top_k,
        top_p=top_p,
    )
    generated = output[0].tolist()
    return tokenizer.decode(generated[len(token_ids[0]):])


def main():
    parser = argparse.ArgumentParser(description="Use a local GPT checkpoint.")
    parser.add_argument("--checkpoint", required=True, help="Path to .pt checkpoint")
    parser.add_argument("--prompt", default=None, help="Optional single prompt")
    parser.add_argument("--max-new-tokens", type=int, default=200)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--top-p", type=float, default=0.95)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_checkpoint(args.checkpoint, device=device)

    if args.prompt:
        print(generate_reply(model, args.prompt, args.max_new_tokens, args.temperature, args.top_k, args.top_p))
        return

    print("Local GPT ready. Type 'exit' or 'خروج' to quit.")
    while True:
        text = input("You: ")
        if text.strip().lower() in {"exit", "quit", "خروج"}:
            break
        if not text.strip():
            continue
        result = generate_reply(model, text, args.max_new_tokens, args.temperature, args.top_k, args.top_p)
        print(f"Model: {result}")


if __name__ == "__main__":
    main()
