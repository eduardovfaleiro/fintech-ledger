# Fintech Ledger

Projeto de portfólio em PostgreSQL para demonstrar indexação e tuning de queries em volumes grandes de dados.

A ideia é simular um extrato bancário / carteira digital e, a partir de consultas reais desse domínio, documentar o caminho completo: query lenta → plano de execução ruim → índice criado → plano bom → ganho medido.

Os benchmarks utilizam 10 milhões de transações, com uma etapa adicional de escala em 1M, 10M e 50M. Todos os planos foram coletados com PostgreSQL 18.4 e `EXPLAIN (ANALYZE, BUFFERS)`.

## Resultados

| Caso | Antes | Depois | Resultado principal |
|---|---:|---:|---|
| Extrato por conta e período | 220 ms | 0,060 ms | 11 blocos no lugar de 114.654 |
| Saldo da conta | 12,249 ms | 2,780 ms | `Index Only Scan` com 0 heap fetches |
| Página 100 do extrato | 6,184 ms | 0,115 ms | keyset pagination aproximadamente 54x mais rápida |
| Fila antifraude | 229,133 ms | 0,047 ms | índice parcial de 3.104 kB no lugar de 387 MB |
| Busca por estabelecimento | 1,175 ms | 0,036 ms | índice sobre `upper(name)` aproximadamente 33x mais rápido |
| Extrato com estabelecimento | 5,001 ms | 0,307 ms | um `JOIN` no lugar de 51 comandos |
| Extrato em 50M de linhas | 936,632 ms | 0,015 ms | 10 blocos no lugar de 573.017 |

## Estudos de caso

- [01 — Extrato: índice concatenado](docs/01-extrato-indice-concatenado.md)
- [02 — Saldo: Index Only Scan](docs/02-saldo-index-only-scan.md)
- [03 — Paginação do extrato: OFFSET vs. keyset pagination](docs/03-paginacao-offset-vs-keyset-pagination.md)
- [04 — Fila antifraude: índice parcial](docs/04-fila-antifraude-indice-parcial.md)
- [05 — Busca de estabelecimentos: índice sobre expressão](docs/05-busca-estabelecimento-indice-expressao.md)
- [06 — Extrato com estabelecimento: JOIN vs. N+1](docs/06-extrato-com-estabelecimento-join-vs-n1.md)
- [07 — Benchmark de escala: 1M vs. 10M vs. 50M](docs/07-benchmark-escala.md)

## Massa de dados

O gerador cria:

- 100 mil contas;
- 5 mil estabelecimentos;
- 10 milhões de transações por padrão;
- distribuição desigual, em que 1% das contas concentra aproximadamente 60% das transações;
- 1% das transações com o status `flagged`.

O volume de transações e o tamanho dos lotes são parametrizáveis. Assim, os problemas de indexação aparecem em uma escala mais próxima de um sistema real, e não somente em tabelas pequenas em que qualquer consulta parece rápida.

## Como executar

Suba o PostgreSQL:

```bash
docker compose up -d
```

Crie o ambiente Python, o schema e a massa de dados:

```bash
make venv
make schema
make generate-data
```

Crie os índices finais utilizados pelos estudos:

```bash
make indexes
```

Para remover somente esses índices:

```bash
make drop-indexes
```

## Reprodução dos benchmarks

O benchmark de N+1 executa 1.000 vezes as duas abordagens e compara a mediana observada pelo cliente:

```bash
make benchmark-n-plus-one
```

O benchmark de escala cria uma tabela `UNLOGGED` descartável, mede a consulta em 1M, 10M e 50M de linhas e remove a tabela ao final:

```bash
make benchmark-scale
```

Na escala de 50 milhões, a tabela temporária e seu índice ocupam aproximadamente 6 GB. A tabela `transactions` original não é modificada.

## Estrutura

```text
benchmarks/   scripts dos benchmarks reproduzíveis
db/schema/    definição das tabelas
db/indexes/   índices finais dos estudos
db/queries/   consultas utilizadas nos casos
docs/         planos, explicações e resultados medidos
```
