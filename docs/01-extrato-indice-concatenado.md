# 01 — Extrato: índice concatenado

**Cenário:** PostgreSQL 18.4, tabela `transactions` com 10 milhões de linhas, distribuídas entre 100 mil contas.
Cada plano foi coletado com apenas o índice em questão existindo na tabela, e com o cache já quente (por isso os
`Buffers` aparecem majoritariamente como `hit` nos planos indexados).

| Cenário | Tempo | Blocos lidos | Volume |
|---|---|---|---|
| Sem índice (Seq Scan) | 220 ms | 114.654 | ~896 MB |
| Índice `(created_at, account_id)` | 17 ms | 3.655 | ~28,5 MB |
| Índice `(account_id, created_at)` | 0,060 ms | 11 | 88 KB |

## A consulta

Neste caso, foi testada a consulta [get_statement.sql](../db/queries/get_statement.sql):
```sql
select
	id,
	created_at,
	amount,
	direction,
	status,
	category,
	counterparty_id
from
	transactions
where
	account_id = 47
	and created_at >= '2025-01-01'
	and created_at < '2025-04-01'
order by
	created_at desc;
```
O intervalo é semiaberto: inclui o instante inicial e exclui o final. Assim, o limite superior não inclui acidentalmente a meia-noite do dia seguinte. Este caso não pagina resultados; a ordenação determinística usada na paginação é tratada no [caso 03](03-paginacao-offset-vs-keyset-pagination.md).

Os planos abaixo são artefatos da execução de referência, coletada antes desse ajuste de fronteira com o intervalo inclusivo equivalente para a massa usada. Essa diferença não altera a comparação dos caminhos de acesso.

## Sem índice nenhum

Se rodarmos esta consulta sem índice nenhum, o banco vai precisar fazer um Seq Scan na tabela inteira pelas duas condições.

Além disso, vai precisar aplicar um algoritmo de sort para ordenar por created_at, assim como mostrado abaixo:

```sql
explain (analyze, buffers)
select
	id,
	created_at,
	amount,
	direction,
	status,
	category,
	counterparty_id
from
	transactions
where
	account_id = 47
	and created_at >= '2025-01-01'
	and created_at < '2025-04-01'
order by
	created_at desc;
```

```text
                                                                                       QUERY PLAN                                                                                        
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Gather Merge  (cost=188493.05..188498.29 rows=45 width=61) (actual time=200.328..204.925 rows=5.00 loops=1)
   Workers Planned: 2
   Workers Launched: 2
   Buffers: shared hit=2579 read=112075
   ->  Sort  (cost=187493.02..187493.07 rows=19 width=61) (actual time=187.914..187.915 rows=1.67 loops=3)
         Sort Key: created_at DESC
         Sort Method: quicksort  Memory: 25kB
         Buffers: shared hit=2579 read=112075
         Worker 0:  Sort Method: quicksort  Memory: 25kB
         Worker 1:  Sort Method: quicksort  Memory: 25kB
         ->  Parallel Seq Scan on transactions  (cost=0.00..187492.62 rows=19 width=61) (actual time=84.043..187.852 rows=1.67 loops=3)
               Filter: ((created_at >= '2025-01-01 00:00:00+00'::timestamp with time zone) AND (created_at < '2025-04-01 00:00:00+00'::timestamp with time zone) AND (account_id = 47))
               Rows Removed by Filter: 3333332
               Buffers: shared hit=2503 read=112075
 Planning:
   Buffers: shared hit=117
 Planning Time: 0.304 ms
 JIT:
   Functions: 6
   Options: Inlining false, Optimization false, Expressions true, Deforming true
   Timing: Generation 0.697 ms (Deform 0.250 ms), Inlining 0.000 ms, Optimization 0.567 ms, Emission 7.885 ms, Total 9.149 ms
 Execution Time: 220.180 ms
(22 rows)
```

Olhe o Rows Removed by Filter: 3333332. São 3,3 milhões de linhas descartadas por worker, 10 milhões no total, para devolver 5.
E os Buffers somam 114.654 blocos (hit=2579 + read=112075), ou seja, cerca de 896 MB lidos para entregar essas 5 linhas.

## O índice errado: (created_at, account_id)

Agora, vamos analisar no caso de adicionar índices. Nós poderíamos colocar um índice somente em account_id, o que já otimizaria muito a consulta.
Entretanto, como a busca pela conta e data andam de mãos dadas em extratos, é interessante que criemos um índice com ambos os campos, não acha?
Do contrário, o banco precisaria acessar cada transação no heap para saber se a data (não considerada no índice) pertence ao período pesquisado.

Em um primeiro momento, talvez você pense em criar o índice (created_at, account_id), por talvez achar que ordem da coluna em índice não importa.
Mas importa, e importa muito.

```sql
create index idx_transactions_created_at_account_id on transactions (created_at, account_id)
```

Isso seria um erro. Basta analisar a estrutura de uma B tree para descobrir por quê:
Para fazer a travessia, da raiz até as folhas, o banco se baseia no primeiro campo do índice: created_at.
Na nossa consulta, você faria a busca incluindo transações entre 01/01/2025 e 01/04/2025. 3 meses de transações no total, de todas as contas, seriam incluídas nisso.
Ao chegar nas folhas no range que você definiu para o created_at, você vai perceber que os account_id só estão ordenados para os casos em que o created_at
for igual.
Ou seja, quase nunca, já que created_at inclui hora, minuto e segundo. Dessa forma, para achar os dados com account_id corretos nesses 3 meses de transação,
você vai ter que percorrer tupla a tupla, folha por folha, para achar as transações com account_id = 47.

Assim, a ordem de criação dos campos do índice fez com que account_id deixasse de delimitar a busca e virasse um mero filtro, aplicado linha a linha. E esse índice, goste ou não, continua ocupando espaço no disco do servidor e adiciona tempo em inserções e updates da tabela de transações.

```text
                                                                                   QUERY PLAN                                                                                    
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Index Scan Backward using idx_transactions_created_at_account_id on transactions  (cost=0.43..25883.90 rows=45 width=61) (actual time=1.974..16.989 rows=5.00 loops=1)
   Index Cond: ((created_at >= '2025-01-01 00:00:00+00'::timestamp with time zone) AND (created_at < '2025-04-01 00:00:00+00'::timestamp with time zone) AND (account_id = 47))
   Index Searches: 1
   Buffers: shared hit=3655
 Planning:
   Buffers: shared hit=137
 Planning Time: 0.314 ms
 Execution Time: 17.021 ms
(8 rows)
```

Repare que aqui não aparece Rows Removed by Filter nenhum, mas o descarte acontece do mesmo jeito. Ele fica implícito, porque o filtro roda dentro do Index Scan
e o PostgreSQL não reporta isso.

O motivo é que o Index Cond mostra dois tipos de predicado sob o mesmo rótulo. O access predicate define onde a varredura começa e onde termina. O filter predicate
só descarta linhas durante a varredura, sem encurtá-la. Aqui, created_at é access e account_id = 47 é filter, já que uma coluna que vem depois de um range no índice
não delimita mais nada. No plano seguinte, as mesmas três condições vão ser todas access.

Como o plano não diferencia os dois, a única forma de saber qual é qual é comparar o Index Cond com a definição do índice.

## O índice certo: (account_id, created_at)

Agora, imaginemos o cenário do índice (account_id, created_at):
```sql
create index idx_transactions_account_id_created_at on transactions (account_id, created_at)
```

Para fazer a mesma consulta, você faria a busca na B tree somente para as transações da conta account_id = 47. Você chegaria nas folhas,
e teria todas as datas ordenadas, já que você só está buscando as transações de uma conta específica, a 47. Com isso, o banco desce direto até a primeira transação
da conta 47 em 01/01/2025 e lê as folhas em sequência, parando assim que a data passa de 01/04/2025. Nenhuma linha lida é descartada.

Neste padrão de consulta, a coluna usada com igualdade vem antes da coluna de intervalo. Essa ordem não é uma regra universal: ela deriva dos predicados e da ordenação que este índice precisa atender.

```text
                                                                                   QUERY PLAN                                                                                    
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Index Scan Backward using idx_transactions_account_id_created_at on transactions  (cost=0.43..189.47 rows=46 width=61) (actual time=0.027..0.030 rows=5.00 loops=1)
   Index Cond: ((account_id = 47) AND (created_at >= '2025-01-01 00:00:00+00'::timestamp with time zone) AND (created_at < '2025-04-01 00:00:00+00'::timestamp with time zone))
   Index Searches: 1
   Buffers: shared hit=11
 Planning:
   Buffers: shared hit=140
 Planning Time: 0.324 ms
 Execution Time: 0.060 ms
(8 rows)
```

## O que mudou

Repare também no que sumiu do plano. Lá no começo, sem índice nenhum, o banco precisava de um nó Sort para atender o order by created_at desc.
Nos dois planos com índice esse nó não aparece mais, e no lugar dele vem Index Scan Backward. Como o índice já guarda os created_at ordenados
dentro de cada conta, o banco não precisa ordenar nada. Ele só lê as folhas ao contrário. O order by saiu de graça, junto com o resto.

Agora, perceba a diferença gritante das duas execuções, só trocando as ordens dos índices. Na primeira, com (created_at, account_id), o executor teve que ler 3655 blocos do banco de dados (Buffers: shared hit=3655). Repare que o número que importa é a soma de hit e read, e não só o read. Os dois são blocos que o executor precisou ler, e o hit apenas indica que aquele bloco já estava em cache. Considerando que um bloco é a menor unidade possível de um banco e que possui 8 KB cada, isso equivale a 28,5 MB. Enquanto isso, na segunda execução, com (account_id, created_at), o executor leu apenas 11 blocos, equivalendo a míseros 88 KB.

Isso impactou diretamente o tempo de execução: 17 ms contra 0,060 ms.
