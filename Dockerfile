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
COPY data/corpus_stats.json ./data/corpus_stats.json
COPY configs ./configs
COPY logs ./logs
COPY checkpoints/rayan-1-small.npz ./checkpoints/rayan-1-small.npz

RUN useradd -m -u 1000 rayan && chown -R rayan:rayan /app
USER rayan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["sh", "-c", "python web/server.py --host 0.0.0.0 --port ${PORT:-8000}"]
