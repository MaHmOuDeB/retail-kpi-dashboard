.PHONY: setup data build export serve test lint

DATA_DIR ?= data

setup:
	uv sync --locked

data:
	uv run python src/download.py
	uv run python src/prepare.py

build:
	uv run python src/build_data.py $(DATA_DIR)/online_retail_ii.parquet

export:
	uv run python src/export_site.py $(DATA_DIR)

serve:
	python -m http.server -d docs 8000

test:
	uv run pytest -q

lint:
	uv run ruff check .
