#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ACTION="${1:-up}"

cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but was not found in PATH." >&2
  exit 1
fi

case "$ACTION" in
  up)
    docker compose -f "$COMPOSE_FILE" up -d mongo
    echo "MongoDB is starting on mongodb://127.0.0.1:27017"
    ;;
  down)
    docker compose -f "$COMPOSE_FILE" stop mongo
    ;;
  restart)
    docker compose -f "$COMPOSE_FILE" restart mongo
    ;;
  logs)
    docker compose -f "$COMPOSE_FILE" logs -f mongo
    ;;
  *)
    echo "Usage: ./mongo.sh [up|down|restart|logs]" >&2
    exit 1
    ;;
esac
