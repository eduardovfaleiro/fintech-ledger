\set ON_ERROR_STOP on
\timing on

drop table if exists benchmark_transactions;

create unlogged table benchmark_transactions (
    id bigint not null,
    account_id bigint not null,
    counterparty_id bigint not null,
    amount numeric(15, 2) not null,
    direction text not null,
    status text not null,
    category text not null,
    created_at timestamptz not null
);

\echo '==> 1 milhão de linhas'

insert into benchmark_transactions
select *
from transactions
where id <= 1000000;

analyze benchmark_transactions;

\o /dev/null
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;
\o

explain (analyze, buffers)
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;

create index idx_benchmark_transactions_account_created_at
    on benchmark_transactions (account_id, created_at);

analyze benchmark_transactions;

\o /dev/null
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;
\o

explain (analyze, buffers)
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;

drop index idx_benchmark_transactions_account_created_at;

\echo '==> 10 milhões de linhas'

insert into benchmark_transactions
select *
from transactions
where id > 1000000;

analyze benchmark_transactions;

\o /dev/null
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;
\o

explain (analyze, buffers)
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;

create index idx_benchmark_transactions_account_created_at
    on benchmark_transactions (account_id, created_at);

analyze benchmark_transactions;

\o /dev/null
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;
\o

explain (analyze, buffers)
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;

drop index idx_benchmark_transactions_account_created_at;

\echo '==> 50 milhões de linhas'

insert into benchmark_transactions
select
    t.id + (copies.copy_number * 10000000),
    t.account_id,
    t.counterparty_id,
    t.amount,
    t.direction,
    t.status,
    t.category,
    t.created_at + (copies.copy_number * interval '1 microsecond')
from
    transactions t
cross join
    generate_series(1, 4) as copies(copy_number);

analyze benchmark_transactions;

\o /dev/null
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;
\o

explain (analyze, buffers)
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;

create index idx_benchmark_transactions_account_created_at
    on benchmark_transactions (account_id, created_at);

analyze benchmark_transactions;

\o /dev/null
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;
\o

explain (analyze, buffers)
select *
from benchmark_transactions
where account_id = 47
  and created_at between '2025-01-01' and '2025-04-01'
order by created_at desc;

select
    pg_size_pretty(pg_total_relation_size('benchmark_transactions')) as table_size,
    pg_size_pretty(pg_relation_size('idx_benchmark_transactions_account_created_at')) as index_size;

drop table benchmark_transactions;
