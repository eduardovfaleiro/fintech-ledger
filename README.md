# Fintech Ledger — PostgreSQL Performance Lab

[![CI](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

English | [Português](README.pt-BR.md)

A reproducible PostgreSQL performance case study built on a synthetic fintech workload. It covers index design, execution-plan analysis, pagination, the N+1 query pattern and concurrent queue consumption across 10 million transactions, with an additional scalability experiment at 1M, 10M and 50M rows.

> This repository is a database performance lab, not a production ledger or a double-entry accounting implementation. The schema and generated data are intentionally small enough to keep each experiment focused; they do not model accounting invariants, reconciliation, idempotency, authorization or regulatory requirements.

Each case follows the same path: slow query → execution-plan evidence → targeted change → improved plan → measured result.

## Results

| Case | Before | After | Main result |
|---|---:|---:|---|
| Statement by account and period | 220 ms | 0.060 ms | 11 blocks instead of 114,654 |
| Synthetic net position | 12.249 ms | 2.780 ms | `Index Only Scan` with 0 heap fetches |
| Statement page 100 | 6.184 ms | 0.115 ms | keyset pagination was about 54× faster |
| Antifraud queue lookup | 229.133 ms | 0.047 ms | 3,104 kB partial index instead of a 387 MB full index |
| Counterparty search | 1.175 ms | 0.036 ms | `upper(name)` expression index was about 33× faster |
| Statement with counterparty (p50) | 4.978 ms | 0.418 ms | one `JOIN` instead of 51 commands; 11.9× faster |
| Statement at 50M rows (p50) | 1,148.094 ms | 0.202 ms | 14 blocks instead of 572,471; 5,672× faster |
| Four queue workers (p50) | 233.463 ms | 65.302 ms | `SKIP LOCKED`; 3.6× faster with no duplicate claims |

Cases 6–8 report client-observed latency distributions rather than isolated runs. The protocol, percentiles, limitations and reference environment are documented in [`benchmarks/METHODOLOGY.md`](benchmarks/METHODOLOGY.md). Raw samples and plans are versioned in [`benchmarks/results/`](benchmarks/results/).

These figures describe comparisons made on one local machine with a warm cache. They are evidence for the access-path differences—not production capacity or latency guarantees.

## Case studies

The detailed write-ups are in Portuguese and include the SQL, execution plans and the reasoning behind each change.

- [01 — Statement: multicolumn index](docs/01-extrato-indice-concatenado.md)
- [02 — Synthetic net position: Index Only Scan](docs/02-saldo-index-only-scan.md)
- [03 — Statement pagination: OFFSET vs. keyset](docs/03-paginacao-offset-vs-keyset-pagination.md)
- [04 — Antifraud queue: partial index](docs/04-fila-antifraude-indice-parcial.md)
- [05 — Counterparty search: expression index](docs/05-busca-estabelecimento-indice-expressao.md)
- [06 — Statement with counterparty: JOIN vs. N+1](docs/06-extrato-com-estabelecimento-join-vs-n1.md)
- [07 — Scalability benchmark: 1M vs. 10M vs. 50M](docs/07-benchmark-escala.md)
- [08 — Concurrent antifraud queue with SKIP LOCKED](docs/08-fila-antifraude-concorrente-skip-locked.md)

## Data set

The seeded generator creates, by default:

- 100,000 accounts;
- 5,000 counterparties;
- 10 million transactions;
- a skewed distribution in which 1% of accounts receive about 60% of transactions;
- about 1% of transactions with the `flagged` status.

The data is deterministic for a given seed, synthetic and designed to expose poor access paths. It is not statistically representative of a real financial institution. Counts, batch sizes and distribution parameters are configurable.

## Run locally

Requirements:

- Docker with Compose v2;
- Python 3.12 or newer;
- GNU Make;
- approximately 3 GB of free disk space for the default 10-million-row data set, PostgreSQL overhead and its indexes.

Start PostgreSQL, create the virtual environment and load the default data set:

```bash
make up
make venv
make schema
make generate-data
make indexes
make test
```

Data generation time depends heavily on storage and CPU. The full 10-million-row load can take several minutes. For a quick validation, override the Make variables:

```bash
make generate-data N_ACCOUNTS=1000 N_COUNTERPARTIES=500 N_TRANSACTIONS=50000
make indexes
make test
```

The generators are seeded, so a clean database and the same parameters produce the same workload. Do not run `make generate-data` repeatedly against an already populated database: it appends another data set. To start over, use:

```bash
make reset
```

`make reset` removes the project's local PostgreSQL volume and all data stored in it, then starts a fresh instance. Recreate the schema, data and indexes with the commands above. As a destructive all-in-one alternative, `make setup` performs that complete reset and load.

Remove only the case-study indexes, while keeping the data, with:

```bash
make drop-indexes
```

## Reproduce the benchmarks

After loading the default 10-million-row data set and indexes, run:

```bash
make benchmark-n-plus-one
make benchmark-scale
make benchmark-skip-locked
```

The scale benchmark temporarily needs roughly 6 GB for its 50-million-row `UNLOGGED` table and index, in addition to the default data set (allow about 9 GB free in total). It can take substantially longer than the other cases. The table is disposable and the original `transactions` table is not modified. The concurrent benchmark also uses a disposable queue and verifies that every item is claimed exactly once.

Benchmark output will vary across hardware, PostgreSQL settings and system load. Compare the approaches within the same run and environment instead of comparing absolute numbers with the published results.

## Design and quality checks

[`ARCHITECTURE.md`](ARCHITECTURE.md) explains the schema, workload, benchmark boundaries and project layout. GitHub Actions starts PostgreSQL 18.4, generates a reduced 50,000-transaction data set, applies the indexes and runs the integration tests, including the concurrent `SKIP LOCKED` scenario.

## Repository structure

```text
benchmarks/   reproducible runners, methodology and raw reference results
db/schema/    table definitions and integrity constraints
db/indexes/   indexes evaluated by the case studies
db/queries/   executable versions of the documented queries
docs/         case studies, execution plans and measured results
tests/        database integration tests executed in CI
```

## License

Released under the [MIT License](LICENSE).
