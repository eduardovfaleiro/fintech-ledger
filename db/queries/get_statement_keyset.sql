select
    id,
    created_at,
    amount,
    direction,
    category
from
    transactions
where
    account_id = %s
    and (created_at, id) < (%s, %s)
order by
    created_at desc,
    id desc
limit %s;
