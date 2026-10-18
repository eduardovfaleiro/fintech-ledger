select
    coalesce(sum(
        case direction
            when 'credit' then amount
            when 'debit' then -amount
        end
    ), 0)::numeric(15, 2) as balance
from
    transactions
where
    account_id = %s;
