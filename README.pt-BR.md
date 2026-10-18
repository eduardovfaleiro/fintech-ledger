# Fintech Ledger — Laboratório de Performance PostgreSQL

[![CI](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/eduardovfaleiro/fintech-ledger/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](README.md) | Português

Estudo de performance reproduzível em PostgreSQL sobre uma carga financeira sintética. O projeto aborda desenho de índices, análise de planos de execução, paginação, o problema N+1 e consumo concorrente de filas em uma base de 10 milhões de transações, além de um experimento de escala com 1M, 10M e 50M de linhas.

> Este repositório é um laboratório de performance de banco de dados, não um ledger de produção nem uma implementação contábil de partidas dobradas. O esquema e os dados foram reduzidos para manter cada experimento isolado; eles não modelam invariantes contábeis, conciliação, idempotência, autorização ou exigências regulatórias.

Cada caso segue o mesmo caminho: consulta lenta → evidência no plano de execução → mudança direcionada → plano melhor → resultado medido.

## Resultados

| Caso | Antes | Depois | Resultado principal |
|---|---:|---:|---|
| Extrato por conta e período | 220 ms | 0,060 ms | 11 blocos no lugar de 114.654 |
| Posição líquida sintética | 12,249 ms | 2,780 ms | `Index Only Scan` com 0 heap fetches |
| Página 100 do extrato | 6,184 ms | 0,115 ms | keyset pagination aproximadamente 54× mais rápida |
| Fila antifraude | 229,133 ms | 0,047 ms | índice parcial de 3.104 kB no lugar de 387 MB |
| Busca por estabelecimento | 1,175 ms | 0,036 ms | índice sobre `upper(name)` aproximadamente 33× mais rápido |
| Extrato com estabelecimento (p50) | 4,978 ms | 0,418 ms | um `JOIN` no lugar de 51 comandos; 11,9× mais rápido |
| Extrato em 50M de linhas (p50) | 1.148,094 ms | 0,202 ms | 14 blocos no lugar de 572.471; 5.672× mais rápido |
| Quatro workers na fila (p50) | 233,463 ms | 65,302 ms | `SKIP LOCKED`; 3,6× mais rápido, sem duplicidade |

Os tempos dos casos 6–8 são distribuições observadas pelo cliente, não execuções isoladas. A metodologia, os percentis, as limitações e o ambiente estão descritos em [`benchmarks/METHODOLOGY.md`](benchmarks/METHODOLOGY.md). As amostras brutas ficam em [`benchmarks/results/`](benchmarks/results/).

Esses números descrevem comparações feitas em uma máquina local com cache aquecido. Eles evidenciam as diferenças entre os caminhos de acesso, mas não representam capacidade ou garantia de latência em produção.

## Estudos de caso

- [01 — Extrato: índice concatenado](docs/01-extrato-indice-concatenado.md)
- [02 — Posição líquida sintética: Index Only Scan](docs/02-saldo-index-only-scan.md)
- [03 — Paginação do extrato: OFFSET vs. keyset pagination](docs/03-paginacao-offset-vs-keyset-pagination.md)
- [04 — Fila antifraude: índice parcial](docs/04-fila-antifraude-indice-parcial.md)
- [05 — Busca de estabelecimentos: índice sobre expressão](docs/05-busca-estabelecimento-indice-expressao.md)
- [06 — Extrato com estabelecimento: JOIN vs. N+1](docs/06-extrato-com-estabelecimento-join-vs-n1.md)
- [07 — Benchmark de escala: 1M vs. 10M vs. 50M](docs/07-benchmark-escala.md)
- [08 — Fila antifraude concorrente com SKIP LOCKED](docs/08-fila-antifraude-concorrente-skip-locked.md)

## Massa de dados

Por padrão, o gerador determinístico cria:

- 100 mil contas;
- 5 mil estabelecimentos;
- 10 milhões de transações;
- distribuição desigual, em que 1% das contas recebe aproximadamente 60% das transações;
- aproximadamente 1% das transações com o status `flagged`.

Os dados são sintéticos e foram desenhados para tornar caminhos de acesso ruins visíveis. Eles não representam estatisticamente uma instituição financeira real. Quantidades, tamanho dos lotes e parâmetros de distribuição são configuráveis.

## Como executar

Pré-requisitos:

- Docker com Compose v2;
- Python 3.12 ou mais recente;
- GNU Make;
- aproximadamente 3 GB livres em disco para a massa padrão de 10 milhões, o overhead do PostgreSQL e seus índices.

Inicie o PostgreSQL, crie o ambiente Python e carregue a massa padrão:

```bash
make up
make venv
make schema
make generate-data
make indexes
make test
```

O tempo de geração depende principalmente do armazenamento e da CPU. A carga completa de 10 milhões pode levar vários minutos. Para uma validação rápida, sobrescreva as variáveis do Make:

```bash
make generate-data N_ACCOUNTS=1000 N_COUNTERPARTIES=500 N_TRANSACTIONS=50000
make indexes
make test
```

Os geradores usam sementes fixas; um banco vazio e os mesmos parâmetros produzem a mesma carga. Não execute `make generate-data` repetidamente em uma base preenchida: o comando acrescenta outra massa. Para recomeçar, use:

```bash
make reset
```

`make reset` remove o volume PostgreSQL local do projeto e todos os dados armazenados nele, depois inicia uma instância vazia. Recrie esquema, dados e índices com os comandos acima. Como alternativa destrutiva em um único comando, `make setup` executa todo esse reset e carregamento.

Para remover somente os índices dos estudos, preservando os dados:

```bash
make drop-indexes
```

## Reprodução dos benchmarks

Depois de carregar a massa padrão de 10 milhões e criar os índices, execute:

```bash
make benchmark-n-plus-one
make benchmark-scale
make benchmark-skip-locked
```

O benchmark de escala precisa temporariamente de cerca de 6 GB para a tabela `UNLOGGED` de 50 milhões e seu índice, além do espaço da massa padrão (reserve cerca de 9 GB livres no total). Ele pode levar consideravelmente mais tempo que os outros casos. A tabela é descartável e a `transactions` original não é modificada. O benchmark concorrente também usa uma fila descartável e valida que cada item foi reservado exatamente uma vez.

Os resultados variam de acordo com hardware, configuração do PostgreSQL e carga da máquina. Compare as abordagens dentro da mesma execução e do mesmo ambiente, em vez de confrontar tempos absolutos com os resultados publicados.

## Arquitetura e qualidade

O documento [`ARCHITECTURE.md`](ARCHITECTURE.md) descreve o esquema, a carga, os limites dos benchmarks e a organização do projeto. O GitHub Actions inicia PostgreSQL 18.4, gera uma massa reduzida de 50 mil transações, aplica os índices e executa os testes de integração, incluindo o cenário concorrente com `SKIP LOCKED`.

## Estrutura

```text
benchmarks/   executores reproduzíveis, metodologia e resultados de referência
db/schema/    definição das tabelas e restrições de integridade
db/indexes/   índices avaliados nos estudos
db/queries/   versões executáveis das consultas documentadas
docs/         estudos, planos de execução e resultados medidos
tests/        testes de integração executados no CI
```

## Licença

Distribuído sob a [Licença MIT](LICENSE).
