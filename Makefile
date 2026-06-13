COMPOSE := docker compose
COMPOSE_PROD := $(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml
API_SERVICE := api
API_CONTAINER := finflow-api
WORKER_SERVICES := invoice-worker reconciliation-worker celery-worker celery-beat

.PHONY: up down prod logs logs-workers seed migrate frontend test fresh wait-api

# Starts the full stack: infra, API, and Kafka workers (no compose profiles).
up:
	$(COMPOSE) up -d

prod:
	$(COMPOSE_PROD) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f $(API_SERVICE)

logs-workers:
	$(COMPOSE) logs -f $(WORKER_SERVICES)

migrate:
	$(COMPOSE) exec $(API_SERVICE) uv run alembic upgrade head

seed:
	$(COMPOSE) exec $(API_SERVICE) uv run python scripts/generate_synthetic_data.py
	$(COMPOSE) exec $(API_SERVICE) uv run python scripts/seed_database.py --reset

frontend:
	cd frontend && npm install && npm run dev

test:
	uv run pytest tests/ -v

wait-api:
	@echo "Waiting for API health check..."
	@for i in $$(seq 1 40); do \
		if curl -sf http://localhost:8000/health >/dev/null 2>&1; then \
			echo "API is healthy."; \
			exit 0; \
		fi; \
		sleep 3; \
	done; \
	echo "API did not become healthy in time."; \
	exit 1

fresh:
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build
	$(MAKE) wait-api
	$(MAKE) migrate
	$(MAKE) seed
