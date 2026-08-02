#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> black -l 96 yt-synchro/"
uv run black -l 96 yt-synchro/

echo "==> isort ."
uv run isort yt-synchro/

echo "==> flake8 --max-line-length=96"
uv run flake8 --max-line-length=96

echo "==> lint OK"
