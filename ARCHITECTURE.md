# Architecture

## Purpose and boundaries

This repository is a PostgreSQL performance laboratory. A small financial domain supplies recognizable access patterns—statements, balances, counterparty lookup and an antifraud queue—while the case studies isolate database behavior that can be measured and explained.

It is deliberately not a production ledger. In particular, it has no double-entry journal, account-level currency, idempotency keys, reconciliation flow, authorization model, audit log or regulatory controls. The `transactions` table represents generated events for query experiments, not an accounting source of truth.

## Components

```text
Seeded Python generators
          │
          ▼
PostgreSQL schema ─── SQL queries in db/queries/
          │                       │
          ├── indexes             ├── integration tests
          │                       │
          └── disposable benchmark tables/queues
                                      │
                                      ▼
                       plans + client latency samples
```

- `generate_*.py` creates deterministic synthetic rows in batches and loads them through PostgreSQL `COPY`.
- `db/schema/` defines the persistent tables and their integrity constraints.
- `db/queries/` contains the executable queries discussed in the case studies.
- `db/indexes/` keeps index definitions separate so indexed and unindexed plans can be compared.
- `benchmarks/` contains the runners, common measurement code, methodology and reference results.
- `tests/` checks query behavior, index use and concurrent queue correctness against a real PostgreSQL instance.
- `docs/` explains the observed plans, trade-offs and results.

The Makefile is the public entry point for setup, data loading, tests and benchmarks. Docker Compose provides the local PostgreSQL instance used by the documented workflow and by CI.

## Data model

### `accounts`

Synthetic account holders, their opening timestamp and lifecycle status. Accounts exist only to provide ownership and skew for the transaction workload.

### `counterparties`

Synthetic merchant-like names used by the expression-index search and the JOIN-versus-N+1 experiment. Generated names are unique inside the data set, but they are labels rather than stable business identifiers.

### `transactions`

Generated debit and credit events linked to an account and a counterparty. Amounts are positive; `direction` provides the sign. `status` distinguishes `settled`, `pending` and `flagged` events, while `category` supports a plausible statement payload.

A demonstration trigger rejects `UPDATE` and `DELETE` on this table and requires corrections to be inserted as new events. This protects the exercise from accidental mutation; it is not an authorization boundary or a complete financial audit design.

The balance case study calculates a demonstration net position from all generated rows:

```text
sum(credits) - sum(debits)
```

Statuses are intentionally ignored in this case so the experiment remains focused on covering-index behavior. This aggregation is not an available balance, an accounting balance or a replacement for a double-entry journal.

## Workload design

The default data set contains 100,000 accounts, 5,000 counterparties and 10 million transactions. Fixed random seeds make clean runs reproducible. One percent of accounts receives approximately 60% of transactions, creating “whale” accounts with enough rows to make pagination and balance access paths visible.

The generated data is intentionally synthetic. Its distributions and business relationships should not be read as a statistical model of a bank. The useful property is controlled scale: an inefficient scan has enough work to expose itself while indexed queries remain inspectable.

## Index strategy

The project keeps each index tied to a demonstrated access pattern:

| Access pattern | Index idea |
|---|---|
| Statement by account and period | equality column before range column |
| Synthetic net-position aggregation | covering columns through `INCLUDE` |
| Stable statement pagination | `(account_id, created_at, id)` cursor order |
| Small antifraud work set | partial index on the queued status |
| Case-insensitive prefix search | expression index on `upper(name)` |

These indexes are not presented as a universal production set. Every additional index consumes disk, competes for cache and adds write maintenance. The case studies state the query being optimized so the trade-off remains explicit.

## Benchmark isolation

Cases 1–5 use `EXPLAIN (ANALYZE, BUFFERS)` to compare access paths. Cases 6–8 also capture complete client-observed latency distributions.

The larger experiments avoid mutating the base data:

- the scale runner creates a disposable `UNLOGGED` table, expands it to 50 million rows and drops it afterward;
- the concurrency runner creates a disposable queue and verifies that each item is claimed exactly once;
- the original `transactions` table remains unchanged by both runners.

Published measurements use a warm cache and a local client. Absolute timings depend on hardware and database settings, so conclusions are based on paired approaches in the same environment. The complete protocol is in [`benchmarks/METHODOLOGY.md`](benchmarks/METHODOLOGY.md).

## Reproducibility and lifecycle

`make up` waits for PostgreSQL to become healthy. Schema creation, data generation and index creation are explicit steps so experiments can be run in the required order. The generators append rows; `make reset` is therefore the supported way to return to a known-empty database. It removes the local Docker volume and its contents.

CI uses the same schema, query and index files with a smaller 50,000-row data set. This keeps feedback fast while exercising PostgreSQL rather than replacing database behavior with mocks. Performance numbers are not asserted in CI because shared runners cannot provide stable latency guarantees.

## Production considerations intentionally out of scope

A production financial ledger would require a different domain model and operational design, including at least:

- balanced journal entries and explicit currencies;
- immutable audit semantics enforced through privileges or database rules;
- idempotent commands and transaction boundaries for money movement;
- reconciliation, correction and dispute workflows;
- authorization, encryption, retention and observability;
- backup, recovery, replication and capacity planning.

Keeping these concerns explicit prevents benchmark shortcuts from being mistaken for production architecture.
