# رایان — تصویر سبک برای میزبانی رایگان
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENBLAS_NUM_THREADS=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rayan ./rayan
COPY web ./web
COPY tokenizer ./tokenizer
# دانشنامه بخشی از برنامه است؛ بدون این دو فایل، پاسخ‌ها بی‌پشتوانه می‌شوند.
COPY data/knowledge.jsonl data/knowledge-pack.jsonl data/corpus_stats.json ./data/
COPY configs ./configs
COPY logs ./logs
COPY checkpoints/rayan-1-small.npz ./checkpoints/rayan-1-small.npz
COPY deploy ./deploy
COPY README-HOST.md ./

# داده‌های نوشتنی جدا از کد می‌مانند تا با volume پایدار شوند.
ENV RAYAN_DATA_DIR=/app/var \
    RAYAN_ENV=production
RUN mkdir -p /app/var && useradd -m -u 1000 rayan && chown -R rayan:rayan /app
USER rayan
VOLUME ["/app/var"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["sh", "-c", "python web/server.py --host 0.0.0.0 --port ${PORT:-8000}"]
