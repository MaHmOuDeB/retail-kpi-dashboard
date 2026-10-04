.PHONY: setup data build serve test lint

setup:
	python -m pip install -r requirements.txt

data:
	python src/download.py
	python src/prepare.py

build:
	python src/build_data.py

serve:
	python -m http.server -d docs 8000

test:
	python -m pytest -q

lint:
	python -m ruff check .
