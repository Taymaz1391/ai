"""توکنایزر BPE سازگار با فارسی — بدون کتابخانهٔ بیرونی.

نکته‌های طراحی:
  * نیم‌فاصله (ZWNJ) جزئی از واژه است و شکسته نمی‌شود.
  * نشانه‌گذاری به واژهٔ پیش از خود می‌چسبد تا «سلام،» یک واحد باشد.
  * هر واژه با نشانگر پایان واژه (</w>) بسته می‌شود تا مرز واژه‌ها گم نشود.
  * توکن‌های ویژه (سند، بیت، کاربر، ربات، خط جدید) هرگز ادغام نمی‌شوند.
  * خط جدید یک توکن ویژهٔ تک‌شناسه‌ای است تا مدل بتواند پاراگراف بسازد.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

SPECIAL_TOKENS = ["<|doc|>", "<|verse|>", "<|user|>", "<|bot|>", "<|nl|>"]
EOW = "</w>"

# واژه + نشانه‌های چسبیده به آن، یا نشانهٔ مستقل.
_CHUNK_RE = re.compile(r"[\w\u200c]+[^\s\w]*|[^\s\w]+", re.UNICODE)
_SPECIAL_RE = re.compile("(" + "|".join(re.escape(t) for t in SPECIAL_TOKENS) + ")")

MAX_CHUNK = 40

# ارقام فارسی/عربی حتی اگر ورودی نرمال‌سازی نشده باشد به لاتین نگاشت می‌شوند.
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def pretokenize(text: str) -> list[str]:
    """متن را به تکه‌های کوچک (واژه‌مانند) می‌شکند."""
    chunks: list[str] = []
    for match in _CHUNK_RE.finditer(text):
        chunk = match.group(0)
        if len(chunk) <= MAX_CHUNK:
            chunks.append(chunk)
        else:
            for i in range(0, len(chunk), MAX_CHUNK):
                chunks.append(chunk[i:i + MAX_CHUNK])
    return chunks


def _split_special(text: str) -> list[tuple[bool, str]]:
    """متن را به قطعه‌های (آیا توکن ویژه است؟، متن) می‌شکند."""
    parts: list[tuple[bool, str]] = []
    for i, piece in enumerate(_SPECIAL_RE.split(text)):
        if not piece:
            continue
        parts.append((i % 2 == 1, piece))
    return parts


def _word_pieces(chunk: str) -> list[str]:
    return list(chunk) + [EOW]


def _pairs(symbols) -> Counter:
    return Counter(zip(symbols, symbols[1:]))


def _merge_pair(symbols: list[str], pair: tuple[str, str]) -> list[str]:
    merged = pair[0] + pair[1]
    out, i = [], 0
    while i < len(symbols):
        if i < len(symbols) - 1 and symbols[i] == pair[0] and symbols[i + 1] == pair[1]:
            out.append(merged)
            i += 2
        else:
            out.append(symbols[i])
            i += 1
    return out


class BPETokenizer:
    """توکنایزر BPE آموزش‌پذیر، سریال‌پذیر و دقیق."""

    def __init__(self, merges: list[tuple[str, str]] | None = None, vocab: list[str] | None = None):
        self.merges: list[tuple[str, str]] = list(merges or [])
        if vocab is None:
            merged = {pair[0] + pair[1] for pair in self.merges}
            base = sorted(merged | {EOW})
            vocab = list(SPECIAL_TOKENS) + [tok for tok in base if tok not in SPECIAL_TOKENS]
        self.vocab: list[str] = list(vocab)
        self.token_to_id: dict[str, int] = {tok: i for i, tok in enumerate(self.vocab)}
        # توکنایزرهای قدیمی‌تر ممکن است بعضی توکن‌های ویژهٔ تازه را نداشته باشند؛
        # فقط آن‌هایی که واقعاً در واژگان‌اند نگاشت می‌شوند تا بارگذاری نسخه‌های قبلی نشکند.
        self.special_ids: dict[str, int] = {t: self.token_to_id[t] for t in SPECIAL_TOKENS
                                            if t in self.token_to_id}
        self.reverse_special: dict[int, str] = {v: k for k, v in self.special_ids.items()}
        self._ranks: dict[tuple[str, str], int] = {pair: i for i, pair in enumerate(self.merges)}

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    # ---------------------------------------------------------------- آموزش
    @classmethod
    def train(
        cls,
        text: str,
        vocab_size: int = 10_000,
        min_frequency: int = 2,
        verbose: bool = True,
    ) -> "BPETokenizer":
        """BPE را روی یک رشتهٔ متن آموزش می‌دهد."""
        return cls.train_from_freq(Counter(pretokenize(text)), vocab_size=vocab_size,
                                   min_frequency=min_frequency, verbose=verbose)

    @classmethod
    def train_from_freq(
        cls,
        freq: Counter[str],
        vocab_size: int = 10_000,
        min_frequency: int = 2,
        verbose: bool = True,
    ) -> "BPETokenizer":
        """BPE از روی شمارش تکه‌ها؛ برای پیکره‌های بزرگ که در حافظه جا نمی‌شوند.

        ابتدا پیکره را جریانی می‌خوانیم و فقط شمارش تکه‌ها را نگه می‌داریم
        (چند صد مگابایت برای ۱۰۰ میلیون نویسه)، بعد همان الگوریتم ادغام اجرا می‌شود.
        """
        freq = Counter(freq)
        words: list[list[str]] = [_word_pieces(chunk) for chunk in freq]
        counts: list[int] = list(freq.values())

        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        pair_words: dict[tuple[str, str], set[int]] = defaultdict(set)
        for wi, symbols in enumerate(words):
            c = counts[wi]
            for pair, n in _pairs(symbols).items():
                pair_count[pair] += n * c
                pair_words[pair].add(wi)

        buckets: dict[int, set[tuple[str, str]]] = defaultdict(set)
        for pair, c in pair_count.items():
            if c > 0:
                buckets[c].add(pair)
        max_count = max(buckets) if buckets else 0

        def set_count(pair: tuple[str, str], new: int) -> None:
            nonlocal max_count
            old = pair_count.get(pair, 0)
            if new == old:
                return
            if old > 0:
                bucket = buckets.get(old)
                if bucket is not None:
                    bucket.discard(pair)
                    if not bucket:
                        buckets.pop(old, None)
            if new > 0:
                pair_count[pair] = new
                buckets[new].add(pair)
                if new > max_count:
                    max_count = new
            else:
                pair_count.pop(pair, None)

        base_chars = sorted({ch for symbols in words for ch in symbols if ch != EOW} | {EOW})
        target = max(0, vocab_size - len(SPECIAL_TOKENS) - len(base_chars))
        merges: list[tuple[str, str]] = []

        while len(merges) < target:
            while max_count > 0 and max_count not in buckets:
                max_count -= 1
            if max_count < min_frequency:
                break
            pair = buckets[max_count].pop()
            if not buckets[max_count]:
                del buckets[max_count]
            if pair_count.get(pair, 0) != max_count:
                # ورودی کهنه
                continue

            for wi in list(pair_words.get(pair, ())):
                symbols = words[wi]
                c = counts[wi]
                old = _pairs(symbols)
                new_symbols = _merge_pair(symbols, pair)
                if new_symbols == symbols:
                    continue
                new = _pairs(new_symbols)
                for p in set(old) | set(new):
                    delta = (new.get(p, 0) - old.get(p, 0)) * c
                    if delta:
                        set_count(p, pair_count.get(p, 0) + delta)
                for p in set(old):
                    pair_words[p].discard(wi)
                for p in new:
                    pair_words[p].add(wi)
                words[wi] = new_symbols

            set_count(pair, 0)
            pair_words.pop(pair, None)
            merges.append(pair)
            if verbose and len(merges) % 1000 == 0:
                print(f"  merge {len(merges)}/{target} | best pair count={max_count}", flush=True)

        merged_pieces: list[str] = []
        seen: set[str] = set()
        for a, b in merges:
            piece = a + b
            if piece not in seen:
                seen.add(piece)
                merged_pieces.append(piece)
        vocab: list[str] = []
        for token in list(SPECIAL_TOKENS) + base_chars + merged_pieces:
            if token not in vocab:
                vocab.append(token)
        return cls(merges=merges, vocab=vocab)

    # --------------------------------------------------------------- کدگذاری
    def _encode_chunk(self, chunk: str) -> list[int]:
        symbols = _word_pieces(chunk)
        while len(symbols) > 1:
            best_rank, best_idx = None, -1
            for i in range(len(symbols) - 1):
                rank = self._ranks.get((symbols[i], symbols[i + 1]))
                if rank is not None and (best_rank is None or rank < best_rank):
                    best_rank, best_idx = rank, i
            if best_idx < 0:
                break
            symbols[best_idx:best_idx + 2] = [symbols[best_idx] + symbols[best_idx + 1]]
        return [self.token_to_id[p] for p in symbols if p in self.token_to_id]

    def encode(self, text: str, *, allow_specials: bool = True) -> list[int]:
        text = text.translate(_DIGIT_MAP)
        # خط جدید به توکن ویژه تبدیل می‌شود؛ وگرنه در شکستن تکه‌ها گم می‌شد.
        if allow_specials and "<|nl|>" in self.special_ids:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = text.replace("\n", " <|nl|> ")
        ids: list[int] = []
        parts = _split_special(text) if allow_specials else [(False, text)]
        for is_special, piece in parts:
            if is_special:
                token_id = self.special_ids.get(piece)
                if token_id is not None:
                    ids.append(token_id)
                continue
            for chunk in pretokenize(piece):
                ids.extend(self._encode_chunk(chunk))
        return ids

    def decode(self, ids, *, skip_specials: bool = False) -> str:
        parts: list[str] = []
        special_text = {"<|doc|>": "\n\n", "<|verse|>": "\n", "<|user|>": "", "<|bot|>": "",
                        "<|nl|>": "\n"}
        for raw in ids:
            i = int(raw)
            special = self.reverse_special.get(i)
            if special is not None:
                if not skip_specials:
                    parts.append(special_text[special])
                continue
            if 0 <= i < len(self.vocab):
                parts.append(self.vocab[i])
        text = "".join(parts).replace(EOW, " ")
        text = re.sub(r"[ \t]+\n", "\n", text)
        return re.sub(r"[ \t]{2,}", " ", text).strip()

    # -------------------------------------------------------------- ذخیره‌سازی
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": 1,
                    "special_tokens": SPECIAL_TOKENS,
                    "vocab": self.vocab,
                    "merges": [list(p) for p in self.merges],
                },
                f,
                ensure_ascii=False,
            )

    @classmethod
    def load(cls, path: str) -> "BPETokenizer":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(merges=[tuple(p) for p in data["merges"]], vocab=data["vocab"])

    def stats(self) -> dict:
        return {
            "vocab_size": self.vocab_size,
            "merges": len(self.merges),
            "special_tokens": len(SPECIAL_TOKENS),
        }
