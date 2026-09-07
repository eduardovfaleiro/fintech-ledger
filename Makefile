DB_HOST := localhost
DB_PORT := 5435
DB_NAME := fintech_ledger
DB_USER := postgres

PSQL := PGPASSWORD=postgres psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME) -v ON_ERROR_STOP=1

SCHEMA_FILES := db/schema/create_accounts.sql \
                db/schema/create_counterparties.sql \
                db/schema/create_transactions.sql

INDEX_FILES := db/indexes/create_transactions_indexes.sql

INDEX_NAMES := idx_transactions_account_id_created_at

VENV := .venv
PYTHON := $(VENV)/bin/python3

N_ACCOUNTS := 100000
N_COUNTERPARTIES := 5000
N_TRANSACTIONS := 10000000

.PHONY: schema indexes drop-indexes venv generate-data

schema:
	@for f in $(SCHEMA_FILES); do \
		echo "==> $$f"; \
		$(PSQL) -f $$f; \
	done

indexes:
	@for f in $(INDEX_FILES); do \
		echo "==> $$f"; \
		$(PSQL) -f $$f; \
	done

drop-indexes:
	@for i in $(INDEX_NAMES); do \
		echo "==> drop $$i"; \
		$(PSQL) -c "drop index if exists $$i;"; \
	done

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet -r requirements.txt

generate-data:
	PGHOST=$(DB_HOST) PGPORT=$(DB_PORT) PGDATABASE=$(DB_NAME) PGUSER=$(DB_USER) PGPASSWORD=postgres \
		$(PYTHON) generate_accounts.py --count $(N_ACCOUNTS)
	PGHOST=$(DB_HOST) PGPORT=$(DB_PORT) PGDATABASE=$(DB_NAME) PGUSER=$(DB_USER) PGPASSWORD=postgres \
		$(PYTHON) generate_counterparties.py --count $(N_COUNTERPARTIES)
	PGHOST=$(DB_HOST) PGPORT=$(DB_PORT) PGDATABASE=$(DB_NAME) PGUSER=$(DB_USER) PGPASSWORD=postgres \
		$(PYTHON) generate_transactions.py --count $(N_TRANSACTIONS)
