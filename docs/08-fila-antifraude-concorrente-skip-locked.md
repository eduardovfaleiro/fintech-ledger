# 08 — Fila antifraude concorrente com `SKIP LOCKED`

Agora, vamos voltar à fila antifraude do caso 4. O índice parcial resolveu o custo para encontrar as transações pendentes, mas ainda falta responder outra pergunta: o que acontece quando vários workers tentam consumir a mesma fila ao mesmo tempo?

**Cenário:** PostgreSQL 18.4, 1.000 itens na fila, quatro workers, lotes de 25 itens e cache quente. Cada worker manteve a transação aberta por 5 ms para representar o processamento feito antes do commit. Depois de dois aquecimentos, cada abordagem foi medida 30 vezes e nenhuma amostra foi removida.

| Abordagem | p50 | p95 | p99 |
|---|---:|---:|---:|
| `FOR UPDATE` | 233,463 ms | 238,653 ms | 240,940 ms |
| `FOR UPDATE SKIP LOCKED` | 65,302 ms | 66,410 ms | 68,634 ms |

## O problema da fila sem `SKIP LOCKED`

Uma forma natural de reservar o próximo lote é selecionar as primeiras linhas com `FOR UPDATE` e, em seguida, alterar seu status:

```sql
with next_batch as (
    select transaction_id
    from antifraud_queue_demo
    where status = 'queued'
    order by created_at, transaction_id
    for update
    limit 25
)
update antifraud_queue_demo queue
set
    status = 'processing',
    worker_id = 'worker-1',
    claimed_at = clock_timestamp()
from next_batch
where queue.transaction_id = next_batch.transaction_id
returning queue.transaction_id;
```

O bloqueio evita que dois workers processem a mesma transação. Entretanto, todos começam pelo início da fila. Enquanto o primeiro worker mantém as linhas bloqueadas, os outros ficam esperando justamente pelo mesmo lote.

Temos concorrência na aplicação, mas o início da fila acaba serializando o trabalho.

## Pulando linhas que já estão bloqueadas

Para uma fila, não precisamos esperar pelo primeiro item disponível. Podemos pular as linhas que outro worker já reservou e buscar o próximo lote livre:

```sql
for update skip locked
limit 25
```

Com essa mudança, o primeiro worker bloqueia os itens 1 a 25, o segundo segue para os itens 26 a 50 e assim por diante. O `UPDATE` continua fazendo parte do mesmo comando por meio da CTE, então a reserva e a mudança de status acontecem atomicamente.

A consulta completa está em [`claim_antifraud_batch.sql`](../db/queries/claim_antifraud_batch.sql).

## Correção antes de velocidade

O benchmark abre uma conexão independente para cada worker. Ao final de cada execução, ele reúne todos os identificadores devolvidos pelo `RETURNING` e verifica duas condições:

- os 1.000 itens foram processados;
- nenhum identificador apareceu mais de uma vez.

As duas condições passaram em todas as execuções. Isso é importante porque um benchmark de fila que termina rápido, mas perde ou duplica trabalho, não representa uma otimização válida.

## O que mudou

Com `FOR UPDATE`, drenar a fila levou um p50 de 233,463 ms. Com `SKIP LOCKED`, o p50 caiu para 65,302 ms, uma diferença de aproximadamente 3,6 vezes. O p99 também caiu de 240,940 ms para 68,634 ms.

O ganho veio de permitir que os quatro workers trabalhassem em lotes diferentes, sem esperar pela cabeça da fila. `SKIP LOCKED`, porém, produz uma visão inconsistente dos dados bloqueados. Isso é desejável em uma fila, mas não deve ser usado para consultas em que todas as linhas visíveis precisam fazer parte do resultado.

O cenário pode ser reproduzido com [`benchmark_skip_locked.py`](../benchmarks/benchmark_skip_locked.py). A tabela `UNLOGGED` usada no teste é descartável e removida ao final. As amostras estão em [`skip_locked.json`](../benchmarks/results/skip_locked.json).
