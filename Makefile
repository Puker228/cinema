.PHONY: format run

format:
	uv run ruff check --fix
	uv run ruff format

run:
	uv run cinema
