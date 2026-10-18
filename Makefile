DB_HOST ?= localhost
DB_PORT ?= 5435
DB_NAME ?= fintech_ledger
DB_USER ?= postgres
DB_PASSWORD ?= postgres

DOCKER_COMPOSE ?= docker compose
VENV ?= .venv
PYTHON ?= $(VENV)/bin/python3
PIP := $(VENV)/bin/pip
RUFF := $(PYTHON) -m ruff

PSQL := PGPASSWORD=$(DB_PASSWORD) psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME) -v ON_ERROR_STOP=1
DB_ENV := PGHOST=$(DB_HOST) PGPORT=$(DB_PORT) PGDATABASE=$(DB_NAME) PGUSER=$(DB_USER) PGPASSWORD=$(DB_PASSWORD)

SCHEMA_FILES := db/schema/create_accounts.sql \
                db/schema/create_counterparties.sql \
                db/schema/create_transactions.sql

INDEX_FILES := db/indexes/create_transactions_indexes.sql \
               db/indexes/create_pagination_index.sql \
               db/indexes/create_antifraud_partial_index.sql \
               db/indexes/create_counterparties_expression_index.sql

INDEX_NAMES := idx_transactions_account_id_created_at \
               idx_transactions_account_pagination \
               idx_transactions_flagged_queue \
               idx_counterparties_upper_name

N_ACCOUNTS ?= 100000
N_COUNTERPARTIES ?= 5000
N_TRANSACTIONS ?= 10000000

.DEFAULT_GOAL := help

.PHONY: help up down reset setup schema indexes drop-indexes venv generate-data \
	test lint format format-check check benchmark-n-plus-one benchmark-scale \
	benchmark-skip-locked

help: ## List available commands
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start PostgreSQL and wait until it is healthy
	$(DOCKER_COMPOSE) up -d --wait

down: ## Stop the local services without deleting data
	$(DOCKER_COMPOSE) down --remove-orphans

reset: ## Recreate PostgreSQL and permanently delete the local database volume
	$(DOCKER_COMPOSE) down --volumes --remove-orphans
	$(DOCKER_COMPOSE) up -d --wait

setup: venv ## Recreate the database, schema, sample data and indexes
	$(MAKE) reset
	$(MAKE) schema
	$(MAKE) generate-data
	$(MAKE) indexes

schema: ## Create the database schema
	@for f in $(SCHEMA_FILES); do \
		echo "==> $$f"; \
		$(PSQL) -f $$f; \
	done

indexes: ## Create the benchmark indexes
	@for f in $(INDEX_FILES); do \
		echo "==> $$f"; \
		$(PSQL) -f $$f; \
	done

drop-indexes: ## Remove the benchmark indexes
	@for i in $(INDEX_NAMES); do \
		echo "==> drop $$i"; \
		$(PSQL) -c "drop index if exists $$i;"; \
	done

venv: ## Create the virtual environment and install all development dependencies
	python3 -m venv $(VENV)
	$(PIP) install --quiet --requirement requirements-dev.txt

generate-data: ## Generate the configured synthetic data set
	$(DB_ENV) $(PYTHON) generate_accounts.py --count $(N_ACCOUNTS)
	$(DB_ENV) $(PYTHON) generate_counterparties.py --count $(N_COUNTERPARTIES)
	$(DB_ENV) $(PYTHON) generate_transactions.py --count $(N_TRANSACTIONS)

test: ## Run the test suite
	$(DB_ENV) $(PYTHON) -m unittest discover -s tests -v

lint: ## Run static analysis
	$(RUFF) check .

format: ## Apply safe lint fixes and format Python files
	$(RUFF) check --fix .
	$(RUFF) format .

format-check: ## Verify Python formatting without changing files
	$(RUFF) format --check .

check: lint format-check test ## Run all local quality checks

benchmark-n-plus-one: ## Compare N+1 queries with a JOIN
	$(DB_ENV) $(PYTHON) benchmarks/benchmark_n_plus_one.py

benchmark-scale: ## Run the 1M, 10M and 50M scalability benchmark
	$(DB_ENV) $(PYTHON) benchmarks/benchmark_scale.py

benchmark-skip-locked: ## Compare queue workers with and without SKIP LOCKED
	$(DB_ENV) $(PYTHON) benchmarks/benchmark_skip_locked.py
