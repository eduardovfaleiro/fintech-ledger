# 02 — Saldo: Index Only Scan

Agora, vamos para o caso 2. Vamos pegar o saldo de um usuário whale do banco, com 6.277 transações.

**Cenário:** PostgreSQL 18.4, tabela `transactions` com 10 milhões de linhas e cache quente.

| Cenário | Tempo | Heap | Tamanho do índice |
|---|---:|---:|---:|
| Índice original | 12,249 ms | 6.113 blocos acessados | 301 MB |
| Covering index | 2,780 ms | 0 heap fetches | 473 MB |

## A consulta

Para isso, vamos utilizar a consulta get_balance.sql:

```sql
select
      sum(amount) filter (where direction = 'credit')
    - sum(amount) filter (where direction = 'debit') as balance
  from
      transactions
  where
      account_id = 30362;
```

## O índice existente: acesso ao heap

Se rodarmos ela com o índice já existente (account_id, created_at), ela já será extremamente rápida:

```text
QUERY PLAN
--------------------------------------------------------------------------------------------------------------------------------------------------------------
Aggregate  (cost=1875.95..1875.96 rows=1 width=32) (actual time=12.203..12.204 rows=1.00 loops=1)
  Buffers: shared hit=6140
  ->  Bitmap Heap Scan on transactions  (cost=12.22..1871.07 rows=488 width=12) (actual time=1.932..9.555 rows=6277.00 loops=1)
        Recheck Cond: (account_id = 30362)
        Heap Blocks: exact=6113
        Buffers: shared hit=6140
        ->  Bitmap Index Scan on idx_transactions_account_id_created_at  (cost=0.00..12.10 rows=488 width=0) (actual time=0.759..0.759 rows=6277.00 loops=1)
              Index Cond: (account_id = 30362)
              Index Searches: 1
              Buffers: shared hit=27
Planning Time: 0.092 ms
Execution Time: 12.249 ms
```

Entretanto, perceba que, apesar do índice ser extremamente eficiente, ele ainda precisa acessar o heap, e as transações da conta estão fisicamente dispersas nele.

Por isso, o banco precisa acessar 6.113 blocos só para obter o valor das 6.277 transações. Quanto mais blocos acessados, menos o executor do banco consegue otimizar essa busca e mais acessos tem que fazer.

## Covering index: evitando o heap

Mas e se tivesse uma forma de fazer essa consulta sem nem acessar o heap? Tem como?
A resposta é que sim. Para isso, as colunas utilizadas na consulta devem estar todas inclusas na estrutura do índice.
Assim, tudo que o banco precisa é percorrer a árvore em um tempo O(log n + k), podendo evitar o acesso ao heap e as operações de I/O aleatório quando as páginas estão marcadas como `all-visible`.
Isso é chamado de um covering index, e no explain do PostgreSQL chama-se Index Only Scan.

Vamos ver como fica, agora incluindo amount e direction no índice:

```sql
drop index idx_transactions_account_id_created_at;

create index idx_transactions_account_id_created_at
      on transactions (account_id, created_at)
      include (amount, direction);
```

Repare no uso do "include": em vez de colocar os campos amount e direction como campos-chave no índice, no Postgres você consegue criar dessa forma para que os campos do include não estejam nos nós internos, ficando só nas leaf nodes. Isso economiza espaço em comparação a colocá-los como colunas-chave do índice.

Executando...

```text
QUERY PLAN
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Aggregate  (cost=25.98..26.00 rows=1 width=32) (actual time=2.749..2.749 rows=1.00 loops=1)
  Buffers: shared hit=4643
  ->  Index Only Scan using idx_transactions_account_id_created_at on transactions  (cost=0.56..21.10 rows=488 width=12) (actual time=0.020..1.623 rows=6277.00 loops=1)
        Index Cond: (account_id = 30362)
        Heap Fetches: 0
        Index Searches: 1
        Buffers: shared hit=4643
Planning Time: 0.112 ms
Execution Time: 2.780 ms
```

## O que mudou

Agora, o Bitmap Heap Scan sumiu e foi substituído pelo Index Only Scan.
A inclusão desses campos no índice tem alguns prós e contras:

### Contras

- Inserts terão custo extra na execução, já que precisam incluir esses campos também (updates não são inclusos aqui porque transactions é append-only)
- O índice é mais pesado para carregar em cache (301 MB vs 473 MB)

### Prós

- Não precisa fazer acesso ao heap quando as páginas estão marcadas como `all-visible` no visibility map. Neste caso, `Heap Fetches: 0` confirma que nenhum acesso foi necessário, reduzindo drasticamente o tempo de execução.

Nesse caso, se a consulta de saldo for frequente, vale a pena trocar o aumento de 57% no tamanho do índice pela redução de 12.249 ms para 2.780 ms no tempo de execução.
