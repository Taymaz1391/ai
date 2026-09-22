from dataclasses import asdict, dataclass
import math
from typing import Optional

import torch
from torch import nn
import torch.nn.functional as F


class ByteTokenizer:
    vocab_size = 256

    def encode(self, text: str) -> list[int]:
        return list(text.encode("utf-8"))

    def decode(self, ids: list[int]) -> str:
        payload = bytes(max(0, min(255, int(i))) for i in ids)
        return payload.decode("utf-8", errors="ignore")


@dataclass
class GPTConfig:
    vocab_size: int = 256
    block_size: int = 256
    n_layer: int = 8
    n_head: int = 8
    n_embd: int = 512
    dropout: float = 0.1


class CausalSelfAttention(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        assert cfg.n_embd % cfg.n_head == 0
        self.n_head = cfg.n_head
        self.head_dim = cfg.n_embd // cfg.n_head
        self.qkv = nn.Linear(cfg.n_embd, 3 * cfg.n_embd)
        self.proj = nn.Linear(cfg.n_embd, cfg.n_embd)
        self.attn_drop = nn.Dropout(cfg.dropout)
        self.resid_drop = nn.Dropout(cfg.dropout)
        self.register_buffer(
            "mask",
            torch.tril(torch.ones(cfg.block_size, cfg.block_size, dtype=torch.bool)).view(
                1, 1, cfg.block_size, cfg.block_size
            ),
        )

    def forward(self, x):
        b, t, c = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)

        q = q.view(b, t, self.n_head, self.head_dim).transpose(1, 2)
        k = k.view(b, t, self.n_head, self.head_dim).transpose(1, 2)
        v = v.view(b, t, self.n_head, self.head_dim).transpose(1, 2)

        scores = (q @ k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        scores = scores.masked_fill(self.mask[:, :, :t, :t] == 0, -torch.finfo(scores.dtype).max)
        weights = F.softmax(scores, dim=-1)
        weights = self.attn_drop(weights)

        y = (weights @ v).transpose(1, 2).contiguous().view(b, t, c)
        return self.resid_drop(self.proj(y))


class MLP(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(cfg.n_embd, 4 * cfg.n_embd),
            nn.GELU(),
            nn.Linear(4 * cfg.n_embd, cfg.n_embd),
            nn.Dropout(cfg.dropout),
        )

    def forward(self, x):
        return self.net(x)


class Block(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.ln1 = nn.LayerNorm(cfg.n_embd)
        self.attn = CausalSelfAttention(cfg)
        self.ln2 = nn.LayerNorm(cfg.n_embd)
        self.mlp = MLP(cfg)

    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.mlp(self.ln2(x))
        return x


class LocalGPT(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.cfg = cfg
        self.transformer = nn.ModuleDict(
            {
                "wte": nn.Embedding(cfg.vocab_size, cfg.n_embd),
                "wpe": nn.Embedding(cfg.block_size, cfg.n_embd),
                "drop": nn.Dropout(cfg.dropout),
                "h": nn.ModuleList([Block(cfg) for _ in range(cfg.n_layer)]),
                "ln_f": nn.LayerNorm(cfg.n_embd),
            }
        )
        self.lm_head = nn.Linear(cfg.n_embd, cfg.vocab_size, bias=False)
        self.transformer["wte"].weight = self.lm_head.weight
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(self, idx, targets=None):
        b, t = idx.shape
        if t > self.cfg.block_size:
            raise ValueError(f"sequence length {t} exceeds block_size {self.cfg.block_size}")

        pos = torch.arange(t, device=idx.device)
        pos_emb = self.transformer["wpe"](pos).unsqueeze(0).expand(b, -1, -1)
        tok_emb = self.transformer["wte"](idx)
        x = self.transformer["drop"](tok_emb + pos_emb)

        for block in self.transformer["h"]:
            x = block(x)

        x = self.transformer["ln_f"](x)
        logits = self.lm_head(x)

        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))

        return logits, loss

    @torch.no_grad()
    def generate(self, idx, max_new_tokens, temperature=0.8, top_k=50, top_p=0.95):
        self.eval()
        for _ in range(max_new_tokens):
            context = idx[:, -self.cfg.block_size:]
            logits, _ = self(context)
            logits = logits[:, -1, :] / max(temperature, 1e-5)

            if top_k is not None and top_k > 0:
                top_v, top_i = torch.topk(logits, min(top_k, logits.size(-1)))
                logits = torch.full_like(logits, float("-inf"))
                logits.scatter_(1, top_i, top_v)

            if top_p < 1.0:
                probs = torch.softmax(logits, dim=-1)
                sorted_probs, sorted_ids = torch.sort(probs, descending=True)
                cumulative = sorted_probs.cumsum(dim=-1)
                mask = cumulative > top_p
                if mask.any():
                    mask[..., 1:] = mask[..., :-1].clone()
                    mask[..., 0] = False
                    sorted_probs[mask] = 0.0
                    sorted_probs = sorted_probs / sorted_probs.sum(dim=-1, keepdim=True)
                    next_id = torch.multinomial(sorted_probs, 1)
                    next_id = sorted_ids.gather(1, next_id)
                    idx = torch.cat((idx, next_id), dim=1)
                    continue

            next_id = torch.multinomial(torch.softmax(logits, dim=-1), 1)
            idx = torch.cat((idx, next_id), dim=1)

        return idx

    def config_dict(self):
        return asdict(self.cfg)


def save_checkpoint(model: LocalGPT, path: str):
    payload = {
        "model_state": model.state_dict(),
        "config": model.config_dict(),
    }
    torch.save(payload, path)


def load_checkpoint(path: str, device: str = "cpu") -> LocalGPT:
    checkpoint = torch.load(path, map_location=device)
    cfg = GPTConfig(**checkpoint["config"])
    model = LocalGPT(cfg).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model
