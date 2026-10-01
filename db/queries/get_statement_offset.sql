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
order by
    created_at desc,
    id desc
limit 50
offset 5000;
