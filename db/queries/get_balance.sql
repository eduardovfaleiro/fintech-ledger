select
	  sum(amount) filter (where direction = 'credit')
	- sum(amount) filter (where direction = 'debit') as balance
from
	transactions
where
	account_id = 30362;
