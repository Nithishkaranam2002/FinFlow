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
| `make up` | Start all Docker services in the background |
| `make down` | Stop all Docker services |
| `make logs` | Tail logs from the API container |
| `make migrate` | Run `alembic upgrade head` inside the API container |
| `make seed` | Generate synthetic data and seed PostgreSQL |
| `make frontend` | Install deps and run Vite on port 5173 |
| `make test` | Run pytest inside the API container |
| `make fresh` | Full reset: remove volumes, start stack, migrate, seed |

**Note:** If you already run Postgres or Redis locally, FinFlow maps them to host ports **5434** (Postgres) and **6380** (Redis) to avoid conflicts. Inside Docker, services still connect on the standard internal ports.

## Stack

- **API:** FastAPI on port 8000
- **Frontend:** Vite + React on port 5173 (proxies `/api` → `localhost:8000`)
- **Data:** PostgreSQL, Redis, Kafka, Qdrant via `docker compose`
