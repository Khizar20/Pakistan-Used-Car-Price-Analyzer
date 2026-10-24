ifeq ($(OS),Windows_NT)
PYTHON ?= .venv/Scripts/python.exe
PYTHON310 ?= py -3.10
else
PYTHON ?= .venv/bin/python
PYTHON310 ?= python3.10
endif

.PHONY: setup scrape analyze export test lint typecheck check

setup:
	$(PYTHON310) -m venv .venv
	$(PYTHON) -m pip install --upgrade pip==25.0.1
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps --no-build-isolation -e .
	$(PYTHON) --version

scrape:
	$(PYTHON) -m tracker.cli scrape

analyze:
	$(PYTHON) -m tracker.cli analyze

export:
	$(PYTHON) -m tracker.cli export

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src

check: lint typecheck test
