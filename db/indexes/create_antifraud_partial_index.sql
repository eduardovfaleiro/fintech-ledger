create index idx_transactions_flagged_queue
    on transactions (created_at, id)
    where status = 'flagged';
