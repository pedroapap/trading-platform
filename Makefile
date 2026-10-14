.DEFAULT_GOAL := help
.PHONY: help setup dev web down test lint fmt openapi db-shell migrate revision user import-csv

BACKEND := backend
FRONTEND := frontend
COMPOSE := docker compose

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install dependencies and create .env with a random JWT_SECRET
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci
	@test -f .env || { \
		sed "s/^JWT_SECRET=$$/JWT_SECRET=$$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')/" \
			.env.example > .env && echo "Created .env"; }

dev: ## Run db, api and the UI (on :5173) with auto-reload
	$(COMPOSE) up --build

web: ## Run the UI dev server on :5173; it forwards /api to the api on :8000
	cd $(FRONTEND) && npm run dev

down: ## Stop containers
	$(COMPOSE) down

test: ## Run backend and frontend tests (starts the db if needed)
	$(COMPOSE) up -d --wait db
	cd $(BACKEND) && uv run pytest
	cd $(FRONTEND) && npm test

lint: ## Lint, check formatting and typecheck
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
	cd $(FRONTEND) && npm run lint && npm run format:check && npm run typecheck

fmt: ## Fix lint issues and format
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .
	cd $(FRONTEND) && npm run lint -- --fix && npm run format

openapi: ## Snapshot the API schema and regenerate the frontend's types from it
	cd $(BACKEND) && uv run python -m app.cli openapi > ../$(FRONTEND)/src/api/openapi.json
	cd $(FRONTEND) && npm run api:types

migrate: ## Apply database migrations
	$(COMPOSE) up -d --wait db
	cd $(BACKEND) && uv run alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add trades"
	cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(m)"

user: ## Create the login account: make user email=you@example.com
	cd $(BACKEND) && uv run python -m app.cli create-user --email "$(email)"

import-csv: ## Import prices: make import-csv file=prices.csv symbol=BTCUSDT [timeframe=1m]
	cd $(BACKEND) && uv run python -m app.cli import-csv "$(abspath $(file))" --symbol "$(symbol)" \
		$(if $(timeframe),--timeframe $(timeframe))

db-shell: ## Open psql in the db container
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
