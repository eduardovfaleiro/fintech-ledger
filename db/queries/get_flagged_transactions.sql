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
