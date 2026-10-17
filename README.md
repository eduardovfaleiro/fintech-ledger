# Fintech Ledger

[![CI](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml)

English | [Português](README.pt-BR.md)

A PostgreSQL performance case study built around a realistic fintech ledger. It demonstrates indexing, execution-plan analysis and concurrent queue processing on 10 million transactions, with an additional scalability benchmark at 1M, 10M and 50M rows.

Each case follows the same reasoning path: slow query → execution-plan evidence → targeted change → improved plan → measured result.

## Results

| Case | Before | After | Main result |
|---|---:|---:|---|
| Statement by account and period | 220 ms | 0.060 ms | 11 blocks instead of 114,654 |
| Account balance | 12.249 ms | 2.780 ms | `Index Only Scan` with 0 heap fetches |
| Statement page 100 | 6.184 ms | 0.115 ms | keyset pagination was about 54× faster |
| Antifraud queue lookup | 229.133 ms | 0.047 ms | 3,104 kB partial index instead of a 387 MB full index |
| Counterparty search | 1.175 ms | 0.036 ms | `upper(name)` expression index was about 33× faster |
| Statement with counterparty (p50) | 4.978 ms | 0.418 ms | one `JOIN` instead of 51 commands; 11.9× faster |
| Statement at 50M rows (p50) | 1,142.238 ms | 0.150 ms | 14 blocks instead of 572,471; 7,630× faster |
| Four queue workers (p50) | 233.463 ms | 65.302 ms | `SKIP LOCKED`; 3.6× faster with no duplicate claims |

Cases 6–8 report client-observed latency distributions rather than isolated runs. The protocol, percentiles, limitations and reference environment are documented in [`benchmarks/METHODOLOGY.md`](benchmarks/METHODOLOGY.md). Raw samples and plans are versioned in [`benchmarks/results/`](benchmarks/results/).

## Case studies

The detailed write-ups are in Portuguese and include the SQL, execution plans and the reasoning behind each change.

- [01 — Statement: multicolumn index](docs/01-extrato-indice-concatenado.md)
- [02 — Balance: Index Only Scan](docs/02-saldo-index-only-scan.md)
- [03 — Statement pagination: OFFSET vs. keyset](docs/03-paginacao-offset-vs-keyset-pagination.md)
- [04 — Antifraud queue: partial index](docs/04-fila-antifraude-indice-parcial.md)
- [05 — Counterparty search: expression index](docs/05-busca-estabelecimento-indice-expressao.md)
- [06 — Statement with counterparty: JOIN vs. N+1](docs/06-extrato-com-estabelecimento-join-vs-n1.md)
- [07 — Scalability benchmark: 1M vs. 10M vs. 50M](docs/07-benchmark-escala.md)
- [08 — Concurrent antifraud queue with SKIP LOCKED](docs/08-fila-antifraude-concorrente-skip-locked.md)

## Data set

The generator creates:

- 100,000 accounts;
- 5,000 counterparties;
- 10 million transactions by default;
- a skewed distribution where 1% of accounts owns about 60% of transactions;
- 1% of transactions with the `flagged` status.

The volumes and batch sizes are configurable. This makes poor access paths visible instead of benchmarking only small tables where almost every query looks fast.

## Run locally

Requirements: Docker, Python 3.12+ and `make`.

```bash
docker compose up -d
make venv
make schema
make generate-data
make indexes
make test
```

Remove only the case-study indexes with:

```bash
make drop-indexes
```

## Reproduce the benchmarks

```bash
make benchmark-n-plus-one
make benchmark-scale
make benchmark-skip-locked
```

The scale benchmark creates and removes a disposable `UNLOGGED` table. At 50 million rows, the table and its index require about 6 GB. The original `transactions` table is never modified. The concurrent benchmark also uses a disposable queue and checks that every item is claimed exactly once.

## Continuous integration

GitHub Actions starts PostgreSQL 18.4, generates a reduced 50,000-transaction data set, applies every index, runs integration tests and exercises the concurrent `SKIP LOCKED` scenario.

## Repository structure

```text
benchmarks/   reproducible scripts, methodology and raw results
db/schema/    table definitions
db/indexes/   final indexes used by the case studies
db/queries/   queries discussed in the case studies
docs/         execution plans, explanations and measured results
tests/        database integration tests executed in CI
```
