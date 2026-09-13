PYTHON ?= python
UV ?= uv

.PHONY: setup ingest align db corpus eval ask format-check lint test test-unit test-contract test-integration test-e2e test-all

setup:
	$(UV) sync --extra dev
	$(UV) run $(PYTHON) -m project_tasks init-dirs

ingest:
	$(UV) run $(PYTHON) -m ingest.fetch

align:
	$(UV) run $(PYTHON) -m align.crosswalk

db:
	$(UV) run $(PYTHON) -m ingest.build_db

corpus:
	$(UV) run $(PYTHON) -m text2sql.corpus

eval:
	$(UV) run $(PYTHON) -m eval.run_eval

ask:
	$(UV) run powerquery

format-check:
	$(UV) run ruff format --check .

lint:
	$(UV) run ruff check .

test:
	$(UV) run pytest

test-unit:
	$(UV) run pytest -m "not contract and not integration and not e2e"

test-contract:
	$(UV) run pytest -m contract

test-integration:
	$(UV) run pytest -m integration

test-e2e:
	$(UV) run pytest -m e2e

test-all: format-check lint test

