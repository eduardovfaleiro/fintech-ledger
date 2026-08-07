select
	*
from
	transactions
where
	account_id = 47
	and created_at between '2025-01-01' and '2025-04-01'
order by
	created_at desc;