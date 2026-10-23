.PHONY: install lint format typecheck test check sample clean

install:
	pip install -e ".[dev,spark]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy src

test:
	pytest -m "not network"

check: lint typecheck test

sample:
	nyc-lake run 2024-01 2024-03 --sample --sample-zones

clean:
	rm -rf lake .pytest_cache .mypy_cache .ruff_cache .coverage
