select
    id,
    name
from
    counterparties
where
    upper(name) like upper('Mercado Central') || '%';
