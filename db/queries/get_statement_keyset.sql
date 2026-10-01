select
    id,
    created_at,
    amount,
    direction,
    category
from
    transactions
where
    account_id = 30362
    and (created_at, id) < ('2024-07-15 02:17:35+00', 9133625)
order by
    created_at desc,
    id desc
limit 50;
