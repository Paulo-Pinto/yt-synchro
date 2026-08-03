#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> black -l 96 yt_synchro/ tests/"
uv run black -l 96 yt_synchro/ tests/

echo "==> isort yt_synchro/ tests/"
uv run isort yt_synchro/ tests/

echo "==> flake8 --max-line-length=96 yt_synchro/ tests/"
uv run flake8 --max-line-length=96 yt_synchro/ tests/

echo "==> lint OK"
