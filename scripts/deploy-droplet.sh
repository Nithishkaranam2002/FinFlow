#!/usr/bin/env bash
# One-shot FinFlow production deploy for Ubuntu 24.04 (DigitalOcean, etc.)
# Run as root on the server (SSH or DigitalOcean web console):
#   curl -fsSL https://raw.githubusercontent.com/Nithishkaranam2002/FinFlow/main/scripts/deploy-droplet.sh | bash
#
# Optional env vars before running:
#   PUBLIC_HOST=159.203.83.172 OPENAI_API_KEY=sk-... bash deploy-droplet.sh
set -euo pipefail

FINFLOW_DIR="${FINFLOW_DIR:-/root/finflow}"
REPO_URL="${REPO_URL:-https://github.com/Nithishkaranam2002/FinFlow.git}"
PUBLIC_HOST="${PUBLIC_HOST:-$(curl -sf --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
DB_PASSWORD="${DB_PASSWORD:-finflow123}"
MINIO_SECRET="${MINIO_SECRET:-finflow123}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"

export DEBIAN_FRONTEND=noninteractive

echo "==> FinFlow deploy on ${PUBLIC_HOST}"

echo "==> Fixing packages (non-interactive)..."
dpkg --configure -a 2>/dev/null || true
apt-get update -qq
apt-get install -y -qq \
  -o Dpkg::Options::="--force-confdef" \
  -o Dpkg::Options::="--force-confold" \
  curl git openssl ca-certificates

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker..."
  curl -fsSL https://get.docker.com | sh
fi
apt-get install -y -qq docker-compose-plugin 2>/dev/null || true

echo "==> Docker: $(docker --version)"
echo "==> Compose: $(docker compose version)"

if [ ! -d "${FINFLOW_DIR}/.git" ]; then
  echo "==> Cloning FinFlow..."
  git clone "${REPO_URL}" "${FINFLOW_DIR}"
else
  echo "==> Updating FinFlow..."
  git -C "${FINFLOW_DIR}" pull --ff-only
fi

cd "${FINFLOW_DIR}"

echo "==> Writing .env..."
cat > .env <<EOF
APP_NAME=FinFlow
APP_ENV=production
APP_PORT=8000
SECRET_KEY=${SECRET_KEY}
DEBUG=false
CORS_ORIGINS=http://${PUBLIC_HOST}:8088,http://${PUBLIC_HOST}
APP_BASE_URL=http://${PUBLIC_HOST}:8088
USE_POSTGRES_CHECKPOINTER=true
ALLOW_REGISTRATION=false
RATE_LIMIT_ENABLED=true
LOG_LEVEL=info
METRICS_ENABLED=true
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=finflow
S3_SECRET_KEY=${MINIO_SECRET}
S3_BUCKET=finflow-documents
S3_REGION=us-east-1
S3_USE_SSL=false
DATABASE_URL=postgresql+asyncpg://finflow:${DB_PASSWORD}@postgres:5432/finflow_db
DATABASE_SYNC_URL=postgresql://finflow:${DB_PASSWORD}@postgres:5432/finflow_db
REDIS_URL=redis://redis:6379/0
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
TEMPORAL_ADDRESS=temporal:7233
TEMPORAL_ENABLED=true
QDRANT_URL=http://qdrant:6333
OPENAI_API_KEY=${OPENAI_API_KEY}
ANTHROPIC_API_KEY=
LITELLM_MASTER_KEY=${SECRET_KEY}
PRIMARY_MODEL=gpt-4o-mini
STANDARD_MODEL=gpt-4o-mini
PREMIUM_MODEL=gpt-4o
FALLBACK_MODEL=gpt-4o-mini
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
SECRETS_BACKEND=env
EOF

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo "==> Opening firewall ports 22, 8088..."
  ufw allow 22/tcp
  ufw allow 8088/tcp
fi

export SECRET_KEY
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo "==> Starting infrastructure..."
$COMPOSE up -d postgres redis zookeeper kafka qdrant minio
for i in $(seq 1 60); do
  $COMPOSE exec -T postgres pg_isready -U finflow -d finflow_db >/dev/null 2>&1 && break
  sleep 2
done
export COMPOSE
bash scripts/ensure-temporal-databases.sh

echo "==> Starting Temporal..."
$COMPOSE up -d temporal
for i in $(seq 1 60); do
  $COMPOSE exec -T temporal tctl --address 127.0.0.1:7233 cluster health >/dev/null 2>&1 && break
  sleep 5
done

echo "==> Building and starting full stack (this may take 10-15 min)..."
$COMPOSE up -d --build

echo "==> Waiting for API..."
for i in $(seq 1 90); do
  curl -sf "http://localhost:8000/live" >/dev/null 2>&1 && break
  sleep 5
done

echo "==> Running migrations and seed..."
$COMPOSE exec -T api uv run alembic upgrade head
$COMPOSE exec -T api uv run python scripts/generate_synthetic_data.py
$COMPOSE exec -T api uv run python scripts/seed_database.py --reset

echo ""
echo "=============================================="
echo "  FinFlow is live!"
echo "  App:  http://${PUBLIC_HOST}:8088"
echo "  API:  http://${PUBLIC_HOST}:8000/health"
echo "  Login: controller@acmecorp.com / Test1234!"
echo "=============================================="
if [ -z "${OPENAI_API_KEY}" ]; then
  echo "  NOTE: Set OPENAI_API_KEY in ${FINFLOW_DIR}/.env and restart api for AI features."
fi
