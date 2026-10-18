# 02 — Posição líquida sintética: Index Only Scan

Este caso calcula a posição líquida sintética de uma conta com 6.277 transações. Ela serve para estudar acesso ao heap e não representa saldo contábil ou saldo disponível de um produto financeiro.

**Cenário:** PostgreSQL 18.4, tabela `transactions` com 10 milhões de linhas e cache quente.

| Cenário | Tempo | Heap | Tamanho do índice |
|---|---:|---:|---:|
| Índice original | 12,249 ms | 6.113 blocos acessados | 301 MB |
| Covering index | 2,780 ms | 0 heap fetches | 473 MB |

## A consulta

Para isso, usamos [`get_balance.sql`](../db/queries/get_balance.sql):

```sql
select
	coalesce(sum(
		case direction
			when 'credit' then amount
			when 'debit' then -amount
		end
	), 0)::numeric(15, 2) as balance
from
	transactions
where
	account_id = 30362;
```

O `coalesce` devolve zero para uma conta sem transações e a expressão funciona também quando existem somente créditos ou somente débitos. O status não participa deste cálculo de propósito: o objetivo isolado é medir um covering index sobre `account_id`, `amount` e `direction`, e não definir uma regra de saldo disponível.

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

- Inserções terão custo extra, pois também precisam manter essas colunas no índice. A tabela bloqueia `UPDATE` e `DELETE`; correções são representadas por novos eventos.
- O índice é mais pesado para carregar em cache (301 MB contra 473 MB).

### Prós

- Não precisa fazer acesso ao heap quando as páginas estão marcadas como `all-visible` no visibility map. Neste caso, `Heap Fetches: 0` confirma que nenhum acesso foi necessário, reduzindo o tempo de execução.

Neste workload, o aumento de 57% no tamanho do índice reduziu o tempo da consulta de 12,249 ms para 2,780 ms. A decisão em outro sistema dependeria da frequência de leitura, da taxa de escrita e da pressão de cache; o benchmark não torna esse índice automaticamente recomendável.
