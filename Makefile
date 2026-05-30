"""Makefile with development helpers"""

.PHONY: help setup install dev test lint format docker-build docker-up docker-down clean

help:
	@echo "Trading Platform - Available Commands:"
	@echo "  make setup          - Install all dependencies"
	@echo "  make dev            - Start development environment"
	@echo "  make test           - Run all tests"
	@echo "  make lint           - Lint code"
	@echo "  make format         - Format code"
	@echo "  make docker-build   - Build Docker images"
	@echo "  make docker-up      - Start Docker containers"
	@echo "  make docker-down    - Stop Docker containers"
	@echo "  make clean          - Clean up generated files"

setup:
	@echo "Setting up development environment..."
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

install: setup

dev:
	@echo "Starting development servers..."
	docker-compose up

backend-dev:
	cd backend && python -m uvicorn app.main:app --reload

frontend-dev:
	cd frontend && npm start

test:
	@echo "Running tests..."
	cd backend && pytest
	cd frontend && npm test

lint:
	@echo "Linting code..."
	cd backend && flake8 app
	cd frontend && npm run lint

format:
	@echo "Formatting code..."
	cd backend && black app && isort app
	cd frontend && npx prettier --write src

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	cd frontend && rm -rf node_modules build dist
	cd backend && rm -rf .pytest_cache

db-init:
	docker-compose exec postgres psql -U trader -d trading_db -f /docker-entrypoint-initdb.d/init.sql

db-shell:
	docker-compose exec postgres psql -U trader -d trading_db
