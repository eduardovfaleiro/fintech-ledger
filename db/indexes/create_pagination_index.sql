create index idx_transactions_account_pagination
    on transactions (account_id, created_at, id);
