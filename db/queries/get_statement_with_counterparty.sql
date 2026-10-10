select
    t.id,
    t.created_at,
    t.amount,
    t.direction,
    t.category,
    c.name as counterparty_name
from
    transactions t
join
    counterparties c on c.id = t.counterparty_id
where
    t.account_id = 30362
order by
    t.created_at desc,
    t.id desc
limit 50;
