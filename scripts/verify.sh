#!/usr/bin/env bash
# Run every quality gate in the same order as CI.
set -euo pipefail

uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run mypy --platform win32
uv run pytest
uv build
