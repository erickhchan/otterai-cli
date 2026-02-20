.PHONY: init-dev format lint test

init-dev:
	uv venv || true
	uv pip install .[dev]

format:
	uv run ruff format .

lint:
	uv run ruff check .

test:
	rm -f cov.xml ||:
	uv run pytest -s --cov=src/otterai \
		--cov-report=lcov:lcov.info \
		--cov-report=xml:cov.xml \
		tests/
	rm -f lcov.info .coverage ||:
