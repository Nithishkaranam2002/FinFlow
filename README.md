# FinFlow

Agentic invoice-to-reconciliation platform: FastAPI backend, LangGraph agents, React dashboard, and AI quality evals.

## Running Locally

1. Copy `.env.example` to `.env` and fill in API keys (at minimum `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` for live extraction).
2. Run:

```bash
make fresh
```

3. In a separate terminal, start the frontend dev server:

```bash
make frontend
```

4. Open the URLs below in your browser.

### Local URLs

| URL | What you see |
|-----|----------------|
| [http://localhost:5173](http://localhost:5173) | FinFlow React app — login, dashboard, invoices, reconciliation, settings |
| [http://localhost:8000/docs](http://localhost:8000/docs) | FastAPI Swagger UI — interactive API documentation |
| [http://localhost:8000/health](http://localhost:8000/health) | API health check JSON (database connectivity) |
| [http://localhost:8080](http://localhost:8080) | Kafka UI — browse topics, consumer groups, and messages |
| [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Qdrant dashboard — vector collections used for fuzzy reconciliation |

### Make commands

| Command | Description |
|---------|-------------|
| `make up` | Start all Docker services (API, workers, infra) in the background |
| `make down` | Stop all Docker services |
| `make logs` | Tail logs from the API container |
| `make logs-workers` | Tail logs from invoice and reconciliation workers |
| `make migrate` | Run `alembic upgrade head` inside the API container |
| `make seed` | Generate synthetic data and seed PostgreSQL |
| `make frontend` | Install deps and run Vite on port 5173 |
| `make test` | Run pytest inside the API container |
| `make fresh` | Full reset: remove volumes, start full stack (incl. workers), migrate, seed |

**Note:** If you already run Postgres or Redis locally, FinFlow maps them to host ports **5434** (Postgres) and **6380** (Redis) to avoid conflicts. Inside Docker, services still connect on the standard internal ports.

### Rebuild workers only (no migrate/seed)

```bash
docker compose up -d --build invoice-worker reconciliation-worker
docker compose logs -f invoice-worker reconciliation-worker
```

## Stack

- **API:** FastAPI on port 8000
- **Frontend:** Vite + React on port 5173 (proxies `/api` → `localhost:8000`)
- **Data:** PostgreSQL, Redis, Kafka, Qdrant via `docker compose`

## Production Deployment

FinFlow includes production-oriented defaults for checkpoint persistence, health monitoring, resilient reconciliation, and a polished enterprise UI.

### Required environment variables

| Variable | Production value |
|----------|------------------|
| `APP_ENV` | `production` |
| `SECRET_KEY` | Strong random secret (required; app refuses weak default) |
| `DEBUG` | `false` (auto-set when `APP_ENV=production`) |
| `OPENAI_API_KEY` | Valid key for extraction, embeddings, LLM reconciliation |
| `CORS_ORIGINS` | Your frontend origin(s), comma-separated |
| `USE_POSTGRES_CHECKPOINTER` | `true` (auto-enabled in production) |
| `DATABASE_URL` / `DATABASE_SYNC_URL` | Managed PostgreSQL |
| `RESEND_API_KEY` | Optional; approval email notifications |

### Deploy full stack (production)

```bash
export SECRET_KEY="$(openssl rand -hex 32)"
make prod

# First deploy only
make migrate
make seed
```

This starts API (4 workers), Kafka workers, Celery worker + beat, and nginx frontend on port **8088**.

### Deploy backend only

```bash
export SECRET_KEY="$(openssl rand -hex 32)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build \
  api invoice-worker reconciliation-worker celery-worker celery-beat
```

### Deploy frontend

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build frontend
# UI: http://localhost:8088  (proxies /api to backend)
```

Or build manually:

```bash
cd frontend && npm ci && npm run build
# Serve dist/ behind nginx; see nginx/nginx.conf
```

### Health & smoke test

```bash
curl http://localhost:8000/health
curl http://localhost:8000/live
curl http://localhost:8000/ready
chmod +x scripts/e2e_smoke.sh && ./scripts/e2e_smoke.sh
```

### Production features

- **PostgreSQL LangGraph checkpoints** — approval workflows survive API restarts
- **Resilient reconciliation** — fuzzy/LLM failures still complete with partial matches
- **Extended `/health`, `/live`, `/ready`** — database, Redis, Qdrant, and Kafka checks
- **Security hardening** — rate limiting, security headers, upload size caps, docs disabled in prod
- **Stale invoice recovery** — Celery re-queues invoices stuck in `received`/`extracting`
- **Kafka DLQ** — failed invoice messages routed to `invoice.received.dlq`
- **Payment seeding** — approved/matched invoices get payment records for reconciliation
- **Frontend nginx container** — SPA + API reverse proxy with caching headers
- **CI pipeline** — unit tests, frontend build, Docker image builds on every PR

### Test credentials (after seed)

| Email | Password | Role |
|-------|----------|------|
| `controller@acmecorp.com` | `Test1234!` | Controller |
| `approver@acmecorp.com` | `Test1234!` | Approver |
| `clerk@acmecorp.com` | `Test1234!` | AP Clerk |

