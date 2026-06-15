#!/usr/bin/env bash
set -euo pipefail

if [ "${APP_ENV:-development}" = "development" ] && command -v uv >/dev/null 2>&1; then
  echo "Syncing Python dependencies (development)..."
  uv sync
fi

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting application..."
exec "$@"
