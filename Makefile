PY ?= .venv/bin/python

.PHONY: install corpus tokenizer train serve test eval host host-index clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt

corpus:
	$(PY) data/build_corpus.py --sources ../corpora --out data

tokenizer:
	$(PY) data/train_tokenizer.py --vocab-size 10000

train:
	$(PY) -m rayan.train --steps 1800 --batch-size 24 --block-size 256 \
		--layers 5 --heads 4 --embed 256 --lr 1.2e-3

serve:
	$(PY) web/server.py --host 0.0.0.0 --port 8000

test:
	$(PY) tests/gradcheck.py
	$(PY) -m unittest discover -s tests -p "test_*.py" -v

eval:
	$(PY) scripts/evaluate.py --checkpoint checkpoints/rayan-1-small.npz

host:
	$(PY) scripts/build_host_package.py

host-index:
	$(PY) scripts/build_host_package.py --with-index

clean:
	rm -rf __pycache__ rayan/__pycache__ tests/__pycache__
