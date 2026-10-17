# 07 — Benchmark de escala: 1M vs. 10M vs. 50M

Agora, vamos verificar como a consulta de extrato do caso 1 se comporta conforme a tabela cresce de 1 milhão para 50 milhões de transações.

**Cenário:** PostgreSQL 18.4, cache quente, conta `47`, período de 01/01/2025 a 01/04/2025 e tabelas com o mesmo formato de `transactions`. Depois de três aquecimentos, cada cenário foi executado 30 vezes pelo cliente local e nenhuma amostra foi removida.

| Linhas | Tabela | Cenário | p50 | p95 | p99 | Blocos | Índice |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 milhão | 90 MB | sem índice | 46,766 ms | 51,139 ms | 52,095 ms | 11.458 | — |
| 1 milhão | 90 MB | com índice | 0,106 ms | 0,132 ms | 0,136 ms | 4 | 30 MB |
| 10 milhões | 895 MB | sem índice | 296,245 ms | 316,996 ms | 327,137 ms | 114.654 | — |
| 10 milhões | 895 MB | com índice | 0,118 ms | 0,182 ms | 0,222 ms | 8 | 301 MB |
| 50 milhões | 4.472 MB | sem índice | 1.142,238 ms | 1.415,840 ms | 1.583,933 ms | 572.471 | — |
| 50 milhões | 4.472 MB | com índice | 0,150 ms | 0,174 ms | 0,185 ms | 14 | 1.504 MB |

![Tempo da consulta em 1M, 10M e 50M de transações](assets/benchmark-escala.svg)

## A consulta

Utilizamos a mesma consulta do caso 1:

```sql
select
    *
from
    benchmark_transactions
where
    account_id = 47
    and created_at between '2025-01-01' and '2025-04-01'
order by
    created_at desc;
```

Para cada volume, a consulta foi medida primeiro sem índice e depois com o índice correto:

```sql
create index idx_benchmark_transactions_account_created_at
    on benchmark_transactions (account_id, created_at);
```

Além das medições observadas pelo cliente, um plano foi coletado com `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` em cada cenário.

## Como as amostras foram criadas

A amostra de 1 milhão utiliza o primeiro milhão de transações da base. Depois, ela é completada com as demais linhas para chegar aos 10 milhões.

Para chegar aos 50 milhões sem alterar a base original, as 10 milhões de transações são repetidas quatro vezes em uma tabela `UNLOGGED`, deslocando o `id` e o `created_at` de cada cópia:

```sql
insert into benchmark_transactions
select
    t.id + (copies.copy_number * 10000000),
    t.account_id,
    t.counterparty_id,
    t.amount,
    t.direction,
    t.status,
    t.category,
    t.created_at + (copies.copy_number * interval '1 microsecond')
from
    transactions t
cross join
    generate_series(1, 4) as copies(copy_number);
```

O deslocamento de microssegundos é importante. Sem ele, as cinco cópias teriam a mesma combinação de `account_id, created_at`, e o PostgreSQL poderia deduplicar essas chaves nas folhas da B tree. Isso produziria um índice artificialmente menor do que um índice com 50 milhões de chaves distintas.

## Sem índice

Com 1 milhão de linhas, o PostgreSQL utilizou um `Parallel Seq Scan`, acessou 11.458 blocos e levou um p50 de 46,766 ms. Com 10 milhões, passou para 114.654 blocos e 296,245 ms. Com 50 milhões, chegou a 572.471 blocos e 1.142,238 ms.

O crescimento dos blocos é praticamente linear. A tabela de 50 milhões possui 50 vezes mais linhas que a de 1 milhão e exigiu quase 50 vezes mais blocos.

Esse é o problema de uma consulta que depende de `Seq Scan`: cada nova transação aumenta o trabalho necessário, mesmo que pertença a outra conta ou esteja fora do período pesquisado.

## Com índice

Com o índice `(account_id, created_at)`, o plano muda para `Index Scan Backward`. O p50 ficou entre 0,106 ms e 0,150 ms nas três escalas. Mesmo no p99, o cenário de 50 milhões levou 0,185 ms.

Isso não significa que buscar em uma B tree tenha custo constante. A travessia cresce em O(log n), mas a altura da árvore muda devagar. Entre 1 milhão e 50 milhões de linhas, o executor precisou acessar apenas 4, 8 e 14 blocos para encontrar e devolver as transações correspondentes.

## O que mudou

Sem índice, multiplicar a tabela por 50 elevou o p50 de 46,766 ms para 1.142,238 ms. Com o índice, o PostgreSQL não percorre as transações das outras contas: ele desce diretamente até `account_id = 47`, encontra o início do período e lê somente as entradas necessárias.

No cenário de 50 milhões de linhas, o p50 caiu de 1.142,238 ms para 0,150 ms, uma diferença de aproximadamente 7.630 vezes no mesmo ambiente.

O benchmark pode ser reproduzido com [`benchmark_scale.py`](../benchmarks/benchmark_scale.py). A tabela criada por ele é descartável e removida ao final da execução. As amostras, planos e metadados estão em [`scale.json`](../benchmarks/results/scale.json).
