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
    account_id = %s
    and created_at >= %s
    and created_at < %s
order by
    created_at desc;
