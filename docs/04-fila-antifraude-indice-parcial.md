# 04 — Fila antifraude: índice parcial

Agora, vamos para o caso 4. Vamos buscar as 100 transações sinalizadas há mais tempo para compor uma fila de análise antifraude.

**Cenário:** PostgreSQL 18.4, tabela `transactions` com 10 milhões de linhas, sendo 100.194 delas com o status `flagged`, e cache quente.

| Cenário | Tempo | Blocos acessados | Tamanho do índice |
|---|---:|---:|---:|
| Sem índice para a fila | 229,133 ms | 114.670 | — |
| Índice completo `(status, created_at, id)` | 0,071 ms | 104 | 387 MB |
| Índice parcial `(created_at, id) where status = 'flagged'` | 0,047 ms | 103 | 3.104 kB |

## A consulta

Para a fila, queremos primeiro as transações que estão esperando há mais tempo. Por isso, ordenamos por `created_at` em ordem crescente e buscamos somente as 100 primeiras:

```sql
select
    id,
    account_id,
    counterparty_id,
    amount,
    direction,
    category,
    created_at
from
    transactions
where
    status = 'flagged'
order by
    created_at,
    id
limit 100;
```

Repare que utilizamos o `id` como desempate. Se duas transações tiverem o mesmo `created_at`, ele garante uma ordem determinística entre elas.

## Sem índice nenhum

Se executarmos essa consulta sem um índice para a fila, o banco precisa percorrer a tabela inteira para encontrar todas as transações com o status `flagged`.

Só depois disso ele pode descobrir quais são as 100 mais antigas:

```text
QUERY PLAN
----------------------------------------------------------------------------------------------------------------------------------------------------
Limit  (cost=169105.41..169117.05 rows=100 width=53) (actual time=223.663..228.834 rows=100.00 loops=1)
  Buffers: shared hit=912 read=113758
  ->  Gather Merge  (cost=169105.41..179665.07 rows=90667 width=53) (actual time=221.458..226.622 rows=100.00 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=912 read=113758
        ->  Sort  (cost=168105.38..168199.83 rows=37778 width=53) (actual time=208.029..208.040 rows=79.67 loops=3)
              Sort Key: created_at, id
              Sort Method: top-N heapsort  Memory: 47kB
              Buffers: shared hit=912 read=113758
              Worker 0:  Sort Method: top-N heapsort  Memory: 49kB
              Worker 1:  Sort Method: top-N heapsort  Memory: 48kB
              ->  Parallel Seq Scan on transactions  (cost=0.00..166661.54 rows=37778 width=53) (actual time=2.460..201.730 rows=33398.00 loops=3)
                    Filter: (status = 'flagged'::text)
                    Rows Removed by Filter: 3299935
                    Buffers: shared hit=820 read=113758
Planning Time: 0.091 ms
Execution Time: 229.133 ms
```

O `Parallel Seq Scan` dividiu o trabalho entre três processos. Cada um descartou, em média, 3.299.935 linhas para encontrar aproximadamente 33 mil transações `flagged`.

Mesmo com o `LIMIT 100`, o banco não pode simplesmente parar ao encontrar 100 linhas. Sem um índice que entregue os resultados na ordem de `created_at, id`, ele precisa encontrar todos os candidatos e utilizar o `top-N heapsort` para decidir quais são os 100 mais antigos.

No total, foram acessados 114.670 blocos, aproximadamente 896 MB, para devolver 100 transações.

## Uma primeira alternativa: índice completo

Em um primeiro momento, poderíamos criar um índice começando pelo status e seguido pelos campos utilizados na ordenação:

```sql
create index idx_transactions_status_queue
    on transactions (status, created_at, id);
```

Como `status` é utilizado com `=` no `where`, todas as transações `flagged` ficam juntas no índice. Dentro desse conjunto, `created_at` e `id` já estão na ordem solicitada pela consulta.

Executando novamente:

```text
QUERY PLAN
-----------------------------------------------------------------------------------------------------------------------------------------------------------------
Limit  (cost=0.56..159.84 rows=100 width=53) (actual time=0.019..0.060 rows=100.00 loops=1)
  Buffers: shared hit=104
  ->  Index Scan using idx_transactions_status_queue on transactions  (cost=0.56..144411.93 rows=90667 width=53) (actual time=0.019..0.054 rows=100.00 loops=1)
        Index Cond: (status = 'flagged'::text)
        Index Searches: 1
        Buffers: shared hit=104
Planning Time: 0.037 ms
Execution Time: 0.071 ms
```

O `Parallel Seq Scan` e o `Sort` sumiram. Agora, o banco desce na B tree até o primeiro `status = 'flagged'` e lê as folhas na ordem de `created_at, id`. Assim que encontra as primeiras 100 entradas, o `Limit` interrompe a execução.

A consulta caiu de 229,133 ms para 0,071 ms. Entretanto, esse índice possui um problema: ele também armazena todas as transações `settled` e `pending`, embora elas nunca sejam utilizadas na fila antifraude.

Das 10 milhões de transações, somente 100.194, aproximadamente 1%, possuem o status que nos interessa. Mesmo assim, o índice completo ocupa 387 MB para armazenar todas elas.

## Índice parcial

Mas e se pudéssemos criar um índice somente com as transações que pertencem à fila?

No PostgreSQL, podemos fazer isso com um índice parcial:

```sql
create index idx_transactions_flagged_queue
    on transactions (created_at, id)
    where status = 'flagged';
```

Repare que `status` não precisa fazer parte das colunas do índice. O próprio índice já contém somente linhas em que `status = 'flagged'`, então todas as suas entradas satisfazem essa condição.

As colunas-chave ficam sendo apenas `created_at` e `id`, justamente a ordem em que a fila precisa ser lida:

```text
QUERY PLAN
------------------------------------------------------------------------------------------------------------------------------------------------------------------
Limit  (cost=0.42..290.05 rows=100 width=53) (actual time=0.007..0.037 rows=100.00 loops=1)
  Buffers: shared hit=103
  ->  Index Scan using idx_transactions_flagged_queue on transactions  (cost=0.42..262604.12 rows=90667 width=53) (actual time=0.007..0.032 rows=100.00 loops=1)
        Index Searches: 1
        Buffers: shared hit=103
Planning Time: 0.046 ms
Execution Time: 0.047 ms
```

O plano continua utilizando um `Index Scan`, sem precisar ordenar os resultados, e acessou praticamente a mesma quantidade de blocos do índice completo: 103 contra 104.

A maior diferença aparece no tamanho:

```sql
select
    pg_size_pretty(pg_relation_size('idx_transactions_status_queue')) as full_index_size,
    pg_size_pretty(pg_relation_size('idx_transactions_flagged_queue')) as partial_index_size;
```

```text
 full_index_size | partial_index_size
-----------------+-------------------
 387 MB          | 3104 kB
```

O índice parcial ocupa apenas 0,78% do espaço do índice completo, porque não carrega os outros 99% das transações.

## O que mudou

Sem índice, o banco leu aproximadamente 896 MB da tabela, descartou quase 10 milhões de linhas e ainda precisou ordená-las com um `top-N heapsort`. A consulta levou 229,133 ms.

Com os dois índices, o banco conseguiu entregar os dados na ordem solicitada e interromper a leitura depois das primeiras 100 linhas. Por isso, os tempos do índice completo e do parcial ficaram próximos: 0,071 ms e 0,047 ms.

Então, por que utilizar o parcial?

Porque ele entrega o mesmo caminho de acesso ocupando 3.104 kB em vez de 387 MB. Além de ser mais fácil de manter em cache, ele não precisa ser atualizado quando uma transação `settled` ou `pending` é inserida. Neste caso, a principal vantagem não está nos 0,024 ms economizados na busca, mas em não manter um índice 127 vezes maior sem necessidade.

Existe apenas um cuidado: o PostgreSQL só pode utilizar um índice parcial quando consegue provar que o `where` da consulta satisfaz o predicado do índice. Por isso, a consulta deve manter explicitamente `status = 'flagged'`. Em uma prepared statement com `status = $1`, por exemplo, um plano genérico pode não utilizar esse índice, já que o valor do parâmetro não é conhecido no momento do planejamento.
