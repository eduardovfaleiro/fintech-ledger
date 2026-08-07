Neste caso, foi testado a consulta [get_statement.sql](../db/queries/get_statement.sql):
```sql
select
	*
from
	transactions
where
	account_id = 47
	and created_at between '2025-01-01' and '2025-04-01'
order by
	created_at desc;
```
Repare que existem duas condições para o where: account_id e created_at, além do order by.
Se rodarmos esta consulta sem índice nenhum, o banco vai precisar fazer um Seq Scan na tabela inteira pelas duas condições.

Além disso, vai precisar aplicar um algoritmo de sort para ordenar por created_at, assim como mostrado abaixo:

```sql
explain (analyze, buffers)
select
	*
from
	transactions
where
	account_id = 47
	and created_at between '2025-01-01' and '2025-04-01'
order by
	created_at desc;
```

```text
                                                                                       QUERY PLAN                                                                                        
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Gather Merge  (cost=188509.09..188514.45 rows=46 width=61) (actual time=387.216..400.837 rows=5.00 loops=1)
   Workers Planned: 2
   Workers Launched: 2
   Buffers: shared hit=13080 read=101588
   ->  Sort  (cost=187509.07..187509.12 rows=19 width=61) (actual time=363.158..363.160 rows=1.67 loops=3)
         Sort Key: created_at DESC
         Sort Method: quicksort  Memory: 25kB
         Buffers: shared hit=13080 read=101588
         Worker 0:  Sort Method: quicksort  Memory: 25kB
         Worker 1:  Sort Method: quicksort  Memory: 25kB
         ->  Parallel Seq Scan on transactions  (cost=0.00..187508.67 rows=19 width=61) (actual time=68.934..363.049 rows=1.67 loops=3)
               Filter: ((created_at >= '2025-01-01 00:00:00+00'::timestamp with time zone) AND (created_at <= '2025-04-01 00:00:00+00'::timestamp with time zone) AND (account_id = 47))
               Rows Removed by Filter: 3333332
               Buffers: shared hit=13004 read=101588
 Planning:
   Buffers: shared hit=117
 Planning Time: 0.717 ms
 JIT:
   Functions: 6
   Options: Inlining false, Optimization false, Expressions true, Deforming true
   Timing: Generation 1.348 ms (Deform 0.478 ms), Inlining 0.000 ms, Optimization 1.248 ms, Emission 14.805 ms, Total 17.400 ms
 Execution Time: 429.709 ms
(22 rows)
```

Agora, vamos analisar no caso de adicionar índices. Nós poderíamos colocar um índice somente em account_id ou somente no created_at, já otimizariam muito a consulta. Entretanto, como a busca pela conta e data andam de mãos dados em extratos, é interessante que criemos um índice com ambos os campos, não acha?

Em um primeiro momento, talvez você pense em criar o índice (created_at, account_id), afinal, created_at seria um índice mais seletivo que account_id:
```sql
create index idx_transactions_created_at_account_id on transactions (created_at, account_id)
```