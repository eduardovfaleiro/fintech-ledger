# Fintech Ledger

[![CI](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml)

[English](README.md) | Português

Projeto de portfólio em PostgreSQL para demonstrar indexação, análise de planos e concorrência em um volume próximo ao de uma aplicação financeira real.

A ideia é simular um extrato bancário / carteira digital e documentar o caminho completo: query lenta → plano de execução ruim → mudança aplicada → plano melhor → ganho medido. A base padrão possui 10 milhões de transações, e o benchmark de escala chega a 50 milhões.

## Resultados

| Caso | Antes | Depois | Resultado principal |
|---|---:|---:|---|
| Extrato por conta e período | 220 ms | 0,060 ms | 11 blocos no lugar de 114.654 |
| Saldo da conta | 12,249 ms | 2,780 ms | `Index Only Scan` com 0 heap fetches |
| Página 100 do extrato | 6,184 ms | 0,115 ms | keyset pagination aproximadamente 54× mais rápida |
| Fila antifraude | 229,133 ms | 0,047 ms | índice parcial de 3.104 kB no lugar de 387 MB |
| Busca por estabelecimento | 1,175 ms | 0,036 ms | índice sobre `upper(name)` aproximadamente 33× mais rápido |
| Extrato com estabelecimento (p50) | 4,978 ms | 0,418 ms | um `JOIN` no lugar de 51 comandos; 11,9× mais rápido |
| Extrato em 50M de linhas (p50) | 1.142,238 ms | 0,150 ms | 14 blocos no lugar de 572.471; 7.630× mais rápido |
| Quatro workers na fila (p50) | 233,463 ms | 65,302 ms | `SKIP LOCKED`; 3,6× mais rápido, sem duplicidade |

Os tempos dos casos 6–8 são distribuições observadas pelo cliente, não execuções isoladas. A metodologia, os percentis, as limitações e o ambiente estão descritos em [`benchmarks/METHODOLOGY.md`](benchmarks/METHODOLOGY.md). As amostras brutas ficam em [`benchmarks/results/`](benchmarks/results/).

## Estudos de caso

- [01 — Extrato: índice concatenado](docs/01-extrato-indice-concatenado.md)
- [02 — Saldo: Index Only Scan](docs/02-saldo-index-only-scan.md)
- [03 — Paginação do extrato: OFFSET vs. keyset pagination](docs/03-paginacao-offset-vs-keyset-pagination.md)
- [04 — Fila antifraude: índice parcial](docs/04-fila-antifraude-indice-parcial.md)
- [05 — Busca de estabelecimentos: índice sobre expressão](docs/05-busca-estabelecimento-indice-expressao.md)
- [06 — Extrato com estabelecimento: JOIN vs. N+1](docs/06-extrato-com-estabelecimento-join-vs-n1.md)
- [07 — Benchmark de escala: 1M vs. 10M vs. 50M](docs/07-benchmark-escala.md)
- [08 — Fila antifraude concorrente com SKIP LOCKED](docs/08-fila-antifraude-concorrente-skip-locked.md)

## Massa de dados

O gerador cria:

- 100 mil contas;
- 5 mil estabelecimentos;
- 10 milhões de transações por padrão;
- distribuição desigual, em que 1% das contas concentra aproximadamente 60% das transações;
- 1% das transações com o status `flagged`.

O volume e o tamanho dos lotes são parametrizáveis. Assim, os problemas aparecem em uma escala em que uma escolha ruim de acesso realmente fica visível.

## Como executar

```bash
docker compose up -d
make venv
make schema
make generate-data
make indexes
make test
```

Para remover somente os índices dos estudos:

```bash
make drop-indexes
```

## Reprodução dos benchmarks

```bash
make benchmark-n-plus-one
make benchmark-scale
make benchmark-skip-locked
```

O benchmark de escala cria uma tabela `UNLOGGED` descartável. Na escala de 50 milhões, a tabela e seu índice ocupam aproximadamente 6 GB. A tabela original não é modificada. O benchmark concorrente também usa uma fila descartável e valida que cada item foi reservado exatamente uma vez.

## CI

O GitHub Actions sobe PostgreSQL 18.4, cria uma massa reduzida de 50 mil transações, aplica os índices, executa testes de integração e valida o cenário concorrente com `SKIP LOCKED`.

## Estrutura

```text
benchmarks/   scripts, metodologia e resultados brutos
db/schema/    definição das tabelas
db/indexes/   índices finais dos estudos
db/queries/   consultas utilizadas nos casos
docs/         planos, explicações e resultados medidos
tests/        testes de integração executados no CI
```
