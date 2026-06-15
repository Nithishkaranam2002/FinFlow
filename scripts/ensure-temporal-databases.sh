#!/usr/bin/env bash
# Create Temporal databases on an existing FinFlow Postgres volume (run once if Temporal fails to start).
set -euo pipefail

docker compose exec -T postgres psql -U finflow -d finflow_db <<'SQL'
ALTER USER finflow CREATEDB;
SELECT 'CREATE DATABASE temporal OWNER finflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')\gexec
SELECT 'CREATE DATABASE temporal_visibility OWNER finflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_visibility')\gexec
SQL

echo "Temporal databases ready. Restart: docker compose up -d temporal temporal-worker api"
