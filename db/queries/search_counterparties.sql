select
    id,
    name
from
    counterparties
where
    upper(name) like upper(%s) || '%%'
order by
    name,
    id
limit %s;
