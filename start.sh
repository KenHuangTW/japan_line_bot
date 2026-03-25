#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="${CONDA_ENV_NAME:-nihon-line-bot}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"

cd "$ROOT_DIR"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda is required but was not found in PATH." >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "Missing .env. Copy .env.example to .env and fill in LINE settings first." >&2
  exit 1
fi

CMD=(
  conda run
  --no-capture-output
  -n "$ENV_NAME"
  python -m uvicorn
  app.main:app
  --host "$HOST"
  --port "$PORT"
)

if [[ "$RELOAD" == "true" ]]; then
  CMD+=(--reload)
fi

echo "Starting Nihon LINE Bot on http://$HOST:$PORT using conda env '$ENV_NAME'"
exec "${CMD[@]}"
