.PHONY: setup test-unit test-integration test lint format typecheck eval up down logs seed clean

setup:
	uv sync --all-extras
	uv run pre-commit install

test-unit:
	uv run pytest tests/unit -v --tb=short

test-integration:
	uv run pytest tests/integration -v --tb=short

test:
	uv run pytest tests/ -v --tb=short

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/fides

eval:
	uv run pytest tests/evals -v --tb=short

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

seed:
	uv run python scripts/seed_graph.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
