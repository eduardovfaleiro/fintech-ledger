# 03 — Paginação do extrato: `OFFSET` vs. keyset pagination

Agora, vamos para o caso 3. Vamos comparar duas formas de paginar o extrato de um usuário whale: `OFFSET` e keyset pagination.

**Cenário:** PostgreSQL 18.4, tabela `transactions` com 10 milhões de linhas, conta `30362` com 6.277 transações, páginas de 50 itens e cache quente.

## Paginação com `OFFSET`

Para paginar os extratos do nosso sistema bancário, talvez você pense em utilizar em um primeiro momento o `OFFSET`, uma cláusula bastante comum em consultas SQL.

A sintaxe é simples:
```sql
select
    id,
    created_at,
    amount,
    direction,
    category
from transactions
where account_id = 30362
order by created_at desc, id desc
limit 50
offset 5000;
```

A consulta também está disponível em [`get_statement_offset.sql`](../db/queries/get_statement_offset.sql).

Isso não estaria errado e é uma alternativa válida. Entretanto, ele tem dois contras:

- quanto maior o salto, mais lenta a busca fica;
- se transações forem adicionadas ou removidas durante a paginação, as posições das linhas mudam. Com isso, uma transação pode aparecer novamente em outra página ou ser pulada durante a navegação.

Mas então, por que a busca fica mais lenta quanto maior o salto?

Isso acontece porque o `OFFSET` não pula diretamente para a posição solicitada. O banco precisa ler todas as linhas anteriores, descartá-las, e só depois devolver os resultados da página atual.

## Keyset pagination

Então, que alternativa temos?
Podemos utilizar keyset pagination, que seria assim para a mesma consulta:
```sql
select
    id,
    created_at,
    amount,
    direction,
    category
from transactions
where account_id = 30362
  and (created_at, id) < (:last_created_at, :last_id)
order by created_at desc, id desc
limit 50;
```

Uma versão executável com um cursor real da base está disponível em [`get_statement_keyset.sql`](../db/queries/get_statement_keyset.sql).

Por exemplo, se a última transação da página anterior tiver sido criada em 12/08/2025, às 14h35 e 22 segundos, e tiver ID de 7843921, a consulta será:
```sql
select
    id,
    created_at,
    amount,
    direction,
    category
from transactions
where account_id = 30362
  and (created_at, id) <
      ('2025-08-12 14:35:22+00', 7843921)
order by created_at desc, id desc
limit 50;
```

## Ordenação determinística

Repare, agora, que incluímos, além do `created_at`, o ID da transação. Isso é proposital, pois várias transações podem ter o mesmo `created_at`. Nesse caso, ordenar somente por essa coluna não garante uma ordem fixa entre os valores empatados. Por isso, utilizamos o `id` como desempate. Sem ele, uma transação poderia mudar de página entre duas execuções da mesma consulta, fazendo com que fosse repetida ou pulada durante a paginação.

## O índice

Entretanto, se só usássemos keyset pagination sem a criação de índices, o banco precisaria percorrer a tabela inteira para executar o `WHERE` da consulta. Assim, precisamos criar um índice para realizar a paginação:

```sql
create index idx_transactions_account_pagination on transactions (account_id, created_at, id);
```

O índice também está disponível em [`create_pagination_index.sql`](../db/indexes/create_pagination_index.sql).

Dessa forma, o banco consegue utilizar um algoritmo de busca em uma árvore B para realizar a paginação.

Porém nem tudo são flores: keyset pagination não permite saltar para uma página específica. Nesse caso, o `OFFSET` continua sendo útil.

Com os conceitos apresentados, vamos fazer um benchmark do tempo de execução, para ver se realmente vale a pena. Começaremos por consultas nas primeiras páginas e então partiremos para consultas nas últimas páginas.

## Benchmark

O benchmark foi feito com cache quente, páginas de 50 itens e a conta 30362, que possui 6.277 transações. Foram realizadas 6.500 execuções com `pgbench`, alternando aleatoriamente entre `OFFSET` e keyset pagination. Os números abaixo são a mediana do tempo de execução.

O mesmo índice foi utilizado nos dois métodos. Os cursores foram obtidos antes da medição, pois em uma aplicação real eles viriam da página anterior.

| Página | `OFFSET` | Tempo com `OFFSET` | Tempo com keyset pagination |
|---:|---:|---:|---:|
| 1 | 0 | 0,111 ms | 0,111 ms |
| 2 | 50 | 0,136 ms | 0,117 ms |
| 5 | 200 | 0,202 ms | 0,125 ms |
| 10 | 450 | 5,567 ms | 0,121 ms |
| 20 | 950 | 5,739 ms | 0,136 ms |
| 50 | 2450 | 6,002 ms | 0,120 ms |
| 100 | 4950 | 6,184 ms | 0,115 ms |

Na primeira página, os tempos são iguais porque ainda não existe cursor e os dois métodos executam a mesma consulta.

## O que mudou

Nas primeiras páginas, a diferença é pequena. Na página 10, o PostgreSQL muda o plano de execução porque estima apenas 472 transações para essa conta, embora existam 6.277. Com o novo plano, ele passa a ler e ordenar todas as transações da conta para executar o `OFFSET`. Por isso, a consulta passa de 0,202 ms na página 5 para 5,567 ms na página 10.

A consulta com keyset pagination continuou lendo somente as 50 transações solicitadas, independentemente da página. Na página 100, ela levou 0,115 ms contra 6,184 ms do `OFFSET`, sendo aproximadamente 54 vezes mais rápida.
