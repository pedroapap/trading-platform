.DEFAULT_GOAL := help
.PHONY: help setup dev down test lint fmt db-shell migrate revision

BACKEND := backend
COMPOSE := docker compose

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install backend dependencies
	cd $(BACKEND) && uv sync

dev: ## Run db + api with auto-reload
	$(COMPOSE) up --build

down: ## Stop containers
	$(COMPOSE) down

test: ## Run backend tests (starts the db if needed)
	$(COMPOSE) up -d --wait db
	cd $(BACKEND) && uv run pytest

lint: ## Lint and check formatting
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

fmt: ## Fix lint issues and format
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .

migrate: ## Apply database migrations
	$(COMPOSE) up -d --wait db
	cd $(BACKEND) && uv run alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add trades"
	cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(m)"

db-shell: ## Open psql in the db container
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
