# Rayan — scaling, capacity & honest limits

This document answers the questions that come up whenever someone asks a
self-hosted model to behave like a hyperscaler:

> “Can it handle 1 billion concurrent users?”
> “Make the transformer a trillion parameters.”
> “Train it on all of Google.”

Short answer: **not on this machine, and not by editing this repository.** The
sections below separate what is implemented today from what a real deployment
would require, with numbers instead of adjectives.

---

## 1. What runs today

| Item | Value |
| --- | --- |
| Model | decoder-only transformer, **6,574,848** parameters, NumPy inference |
| Tokenizer | byte-level BPE, **10,000** tokens, Persian corpora only |
| Training | 2,400 steps · 14.7M tokens · val_loss 5.30 · ppl 201 |
| Throughput | ~80 tokens/second per CPU process (sandbox: 2 vCPU, 3.8 GiB) |
| Server | FastAPI + SQLite (`web/server.py`) |
| Concurrency guard | `RAYAN_MAX_CONCURRENCY` (default 4) generation slots; overflow gets `503` |
| Static delivery | gzip, immutable cache for `/static/assets/`, service worker |
| External services | **none** — fonts, icons, video, images are all local |

A single request that asks for 200 tokens therefore takes roughly 2.5 seconds
of pure compute. One process can finish on the order of **0.3–0.4 requests per
second** for that shape. That is the entire capacity of the sandbox.

### Why “1 billion concurrent users” is not a code change

1 billion concurrent means roughly 1e9 open connections and, at even 0.1
request/second each, **1e8 requests/second**. To put that in perspective:
Cloudflare peaks in the tens of millions of requests per second across the
whole internet. You would need:

- tens of thousands of GPU replicas (each serving hundreds of requests/s),
- a multi-region load balancer and edge cache,
- sharded databases with petabytes of state,
- an operations team and an energy budget measured in gigawatts.

No single Python file, however well written, makes that happen. What this
repository *does* provide is the correct **shape**: a stateless web tier, a
bounded generation queue, per-IP and per-account quotas, cacheable static
assets, and a health endpoint for autoscaling.

---

## 2. Scaling ladder (what to do, in order)

### Step 1 — Split state from compute (days)
- Move `data/rayan.sqlite3` to Postgres.
- Sessions become rows or signed cookies; the web process becomes stateless.
- Put N replicas behind a load balancer. Each replica already boots the model
  in a background thread (`boot()`), so rolling restarts are safe.

### Step 2 — Price the queue (days)
- Keep `RAYAN_MAX_CONCURRENCY` small per replica (1–2 × vCPU).
- The guard returns `503` with a Persian message instead of letting latency
  explode; a reverse proxy can add `Retry-After`.
- Add a Redis-backed queue when the request rate exceeds replica capacity, and
  serve short answers from a response cache keyed by normalised prompt.

### Step 3 — Replace the runtime (weeks)
NumPy is excellent for teaching and reproducibility, not for throughput.

| Runtime | Expected gain | Notes |
| --- | --- | --- |
| NumPy (today) | 1× | pure Python loops around BLAS |
| PyTorch + int8 | 10–40× | keep the same weights |
| llama.cpp / GGUF | 20–60× | ideal for CPU boxes |
| GPU + batched serving | 100–1,000× | vLLM/TensorRT-LLM, continuous batching |

The checkpoint format is plain `.npz`, so exporting the weights is mechanical.

### Step 4 — Edge (days)
- Static files already carry `Cache-Control: immutable`; put them on a CDN.
- The intro video (671 KB mp4 / 1.4 MB webm) is the heaviest asset; keep it
  behind a CDN and never inline it.
- The service worker caches the shell, so repeat visits cost almost nothing.

### Step 5 — Observability (days)
- `/api/status` exposes `requests`, `queue`, `max_concurrency`, `uptime_s`.
- `/api/selftest` checks database, model, checkpoint, tokenizer, static dir,
  admin credentials and disk space.
- Scrape both endpoints; alert on queue depth and 503 rate.

---

## 3. Making the model bigger

### Parameter math (rough)

| Model | Params | Training tokens (Chinchilla-ish) | Compute (GPU-hours, A100) | Corpus size |
| --- | --- | --- | --- | --- |
| rayan-1-small (today) | 6.6M | 0.13B | < 1 | ~0.1 GB |
| Small (needed next) | 125M | 2.5B | ~600 | ~2 GB |
| Medium | 350M | 7B | ~3,000 | ~6 GB |
| Large | 1.3B | 26B | ~25,000 | ~25 GB |
| “Billion-scale” class | 7B | 140B | ~300,000 | ~300 GB |
| “Trillion” | 1T | 20T | > 10,000,000 | > 20 TB |

The sandbox has **no GPU** and 3.8 GiB of RAM. A 125M model alone needs
~500 MB of weights in fp16 and multi-GPU training to be practical. A trillion
parameters is a data-centre programme: thousands of accelerators, months of
wall-clock, and a corpus that must be legally cleared.

### What *can* be done here

- Keep training the 6.6M model on more curated Persian text (the loss curve is
  still improving).
- Add a 30–60M “rayan-1-medium” configuration to `configs/` and train it on a
  rented GPU for a weekend — the code path is identical.
- Distill a larger open model into the checkpoint *only if* the licence allows
  it and the weights are disclosed; otherwise it violates the “from scratch,
  no pretrained weights” rule of this project.

### Tokenizer scale

The tokenizer is already byte-level BPE: increasing the vocabulary from 10k to
32k/50k mostly improves compression, not capability. It must be retrained
together with the model (a new vocab invalidates the checkpoint), so ship it as
`rayan-2` rather than mutating `rayan-1`.

---

## 4. “Train on all of Google”

There are three blockers, in order of severity:

1. **Legal** — Google’s index is not a redistributable dataset. Training on
   crawled pages without licences creates liability that no amount of code
   fixes.
2. **Practical** — the index is measured in exabytes; even a filtered Persian
   slice would not fit in this sandbox (3.8 GiB) or its disk.
3. **Quality** — raw web text is mostly boilerplate; the current pipeline
   (`data/build_corpus.py`) already removes navigation, ads and duplicates.

What the project does instead: public Persian corpora with recorded provenance
(`data/corpus_stats.json`), deterministic cleaning, and a documented pipeline.
That is how a small model stays honest about what it learned.

---

## 5. Language scope

The product is Persian-only by design: every page is `lang="fa"` and `dir="rtl"`,
there is no English mirror, no language switch and no language auto-detection.
One language also means one set of promo assets, one sitemap and one copy deck,
which keeps the surface small and honest — the model answers in Persian because
it was trained on Persian only.

## 6. Security posture (summary)

- Strict CSP (`script-src 'self'`), no inline scripts anywhere.
- COOP/CORP, `X-Frame-Options`, `nosniff`, referrer and permissions policies.
- Admin: scrypt passwords, CSRF header, HttpOnly + SameSite=Strict cookie,
  5-attempt lockout, audit log.
- Origin checks on every mutating request; SQL is parameterised; ad URLs are
  validated and escaped on render.
- Per-IP sliding-window limits plus per-account daily quotas.

“Unhackable” is not a property software can have. These controls remove the
common failure classes and make abuse expensive; they do not make a promise
that no vulnerability will ever exist.

---

## 7. Deployment checklist

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export RAYAN_ENV=prod
export RAYAN_ADMIN_PASSWORD='a-long-unique-password'
export RAYAN_ORIGINS='https://your-domain.example'
export RAYAN_DB=/var/lib/rayan/rayan.sqlite3
python -m web.server --host 0.0.0.0 --port 8000
```

- Put a TLS-terminating proxy in front (Caddy/nginx); HSTS is emitted when
  `RAYAN_ENV=prod`.
- Mount `data/` on persistent storage; the scheduler writes daily backups.
- Keep `RAYAN_MAX_CONCURRENCY` at 1–2 × vCPU and scale out with replicas.
