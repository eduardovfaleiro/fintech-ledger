# 06 — Extrato com estabelecimento: `JOIN` vs. N+1

Agora, vamos para o caso 6. Vamos buscar as 50 transações mais recentes de uma conta junto com o nome de cada estabelecimento.

**Cenário:** PostgreSQL 18.4, tabela `transactions` com 10 milhões de linhas, conta `30362`, páginas de 50 itens e cache quente. Depois de 20 aquecimentos, foram realizadas 1.000 execuções de cada abordagem pelo mesmo cliente local. A ordem foi alternada a cada execução e nenhuma amostra foi removida.

| Abordagem | Comandos por página | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| N+1 | 51 | 4,978 ms | 5,931 ms | 8,414 ms |
| `JOIN` | 1 | 0,418 ms | 0,601 ms | 0,746 ms |

## O problema N+1

Imagine que o ORM carregue primeiro as 50 transações da página:

```sql
select
    id,
    created_at,
    amount,
    direction,
    category,
    counterparty_id
from
    transactions
where
    account_id = 30362
order by
    created_at desc,
    id desc
limit 50;
```

Depois, ao acessar o nome do estabelecimento de cada transação, ele executa mais uma consulta:

```sql
select
    name
from
    counterparties
where
    id = 170;
```

Essa segunda consulta será repetida 50 vezes, uma para cada transação. Assim, uma página que parece precisar de uma consulta acaba executando 51: uma consulta inicial + outras 50 consultas para buscar os nomes.

Daí vem o nome N+1.

## Mas cada consulta é rápida

Talvez você olhe para a busca do estabelecimento e pense que não existe problema, já que ela utiliza a chave primária:

```text
QUERY PLAN
----------------------------------------------------------------------------------------------------------------------------------------
Index Scan using counterparties_pkey on counterparties  (cost=0.28..8.30 rows=1 width=20) (actual time=0.005..0.005 rows=1.00 loops=1)
  Index Cond: (id = 170)
  Index Searches: 1
  Buffers: shared hit=3
Planning Time: 0.021 ms
Execution Time: 0.010 ms
```

De fato, isoladamente ela é extremamente rápida: apenas 0,010 ms.

Entretanto, o tempo do banco não é o único custo. Cada consulta precisa ser enviada pelo cliente, interpretada, planejada, executada e devolvida. Repetir esse processo 50 vezes custa mais do que fazer os mesmos acessos dentro de um único plano de execução.

No benchmark, a abordagem N+1 levou um p50 de 4,978 ms por página. No p99, em que as execuções mais lentas começam a aparecer, chegou a 8,414 ms.

## Uma única consulta com `JOIN`

Podemos buscar as transações e os nomes dos estabelecimentos em um único comando:

```sql
select
    t.id,
    t.created_at,
    t.amount,
    t.direction,
    t.category,
    c.name as counterparty_name
from
    transactions t
join
    counterparties c on c.id = t.counterparty_id
where
    t.account_id = 30362
order by
    t.created_at desc,
    t.id desc
limit 50;
```

A consulta também está disponível em [`get_statement_with_counterparty.sql`](../db/queries/get_statement_with_counterparty.sql).

Executando:

```text
QUERY PLAN
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Limit  (cost=0.84..250.09 rows=50 width=57) (actual time=0.022..0.132 rows=50.00 loops=1)
  Buffers: shared hit=204
  ->  Nested Loop  (cost=0.84..2448.45 rows=491 width=57) (actual time=0.021..0.127 rows=50.00 loops=1)
        Buffers: shared hit=204
        ->  Index Scan Backward using idx_transactions_account_pagination on transactions t  (cost=0.56..1981.15 rows=491 width=45) (actual time=0.017..0.043 rows=50.00 loops=1)
              Index Cond: (account_id = 30362)
              Index Searches: 1
              Buffers: shared hit=54
        ->  Index Scan using counterparties_pkey on counterparties c  (cost=0.28..0.95 rows=1 width=28) (actual time=0.001..0.001 rows=1.00 loops=50)
              Index Cond: (id = t.counterparty_id)
              Index Searches: 50
              Buffers: shared hit=150
Planning Time: 0.130 ms
Execution Time: 0.144 ms
```

Repare que o PostgreSQL escolheu um `Nested Loop`. Primeiro, ele utilizou o índice de paginação para encontrar as 50 transações da conta. Depois, para cada transação, fez um `Index Scan` na chave primária de `counterparties`.

Ou seja, o banco também realizou 50 buscas pelo estabelecimento. A diferença é que todas elas aconteceram dentro do mesmo plano, sem voltar 50 vezes para a aplicação.

## `Nested Loop` não é N+1

Os dois padrões parecem iguais quando olhamos somente para a quantidade de buscas, mas acontecem em lugares diferentes:

- no N+1, a aplicação envia 51 comandos independentes ao banco;
- no `Nested Loop`, a aplicação envia um comando e o banco executa o laço internamente.

O `Nested Loop` é uma boa escolha quando o lado externo possui poucas linhas e o lado interno tem um índice eficiente. Neste caso, são apenas 50 linhas e cada estabelecimento é encontrado pela chave primária.

Se removêssemos o `LIMIT` e juntássemos milhões de transações, o otimizador poderia escolher outro algoritmo, como um `Hash Join`. Não existe um algoritmo de join que seja sempre melhor; a escolha depende da quantidade de linhas processadas em cada lado.

## O que mudou

Com N+1, uma única página exigiu 51 comandos e levou um p50 de 4,978 ms. Com o `JOIN`, a mesma página exigiu um comando e levou 0,418 ms, sendo aproximadamente 11,9 vezes mais rápida no p50.

O ganho não veio de eliminar as 50 buscas na chave primária. O plano mostra que elas continuam existindo. O ganho veio de entregar esse trabalho ao banco de uma vez, eliminando 50 viagens entre a aplicação e o PostgreSQL.

O benchmark pode ser reproduzido com [`benchmark_n_plus_one.py`](../benchmarks/benchmark_n_plus_one.py). As amostras brutas e os metadados do ambiente estão em [`n_plus_one.json`](../benchmarks/results/n_plus_one.json), e o protocolo utilizado está descrito em [`METHODOLOGY.md`](../benchmarks/METHODOLOGY.md).
