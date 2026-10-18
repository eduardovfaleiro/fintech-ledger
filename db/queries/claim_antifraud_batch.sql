with next_batch as (
    select
        transaction_id
    from
        antifraud_queue_demo
    where
        status = 'queued'
    order by
        created_at,
        transaction_id
    for update skip locked
    limit %s
)
update
    antifraud_queue_demo queue
set
    status = 'processing',
    worker_id = %s,
    claimed_at = clock_timestamp()
from
    next_batch
where
    queue.transaction_id = next_batch.transaction_id
returning
    queue.transaction_id;
