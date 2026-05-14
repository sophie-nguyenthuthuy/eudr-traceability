.PHONY: help install up down logs migrate revision seed test lint fmt typecheck shell psql clean keys

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python deps into a local venv (for IDE, not Docker)
	python3.12 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

up:  ## Start all services (api, worker, postgres, redis, minio)
	docker compose up -d --build

down:  ## Stop all services
	docker compose down

logs:  ## Tail api logs
	docker compose logs -f api

migrate:  ## Apply alembic migrations
	docker compose run --rm api alembic upgrade head

revision:  ## Create a new alembic revision: make revision m="add foo"
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

seed:  ## Insert demo data (Đắk Lắk coffee cooperative)
	docker compose run --rm api python -m scripts.seed_demo

test:  ## Run pytest inside the api container
	docker compose run --rm api pytest

lint:  ## Ruff lint
	ruff check src tests

fmt:  ## Ruff format
	ruff format src tests
	ruff check --fix src tests

typecheck:  ## mypy
	mypy src

shell:  ## Python shell with app context
	docker compose run --rm api python

psql:  ## Open psql against the running postgres
	docker compose exec postgres psql -U eudr -d eudr

keys:  ## Generate local JWT signing keys into ./secrets
	mkdir -p secrets
	openssl genrsa -out secrets/jwt-private.pem 2048
	openssl rsa -in secrets/jwt-private.pem -pubout -out secrets/jwt-public.pem
	@echo "Keys written to ./secrets — do NOT commit"

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
