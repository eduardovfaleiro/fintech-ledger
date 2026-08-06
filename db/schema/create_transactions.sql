create table transactions (
    id bigint generated always as identity primary key,
    account_id bigint not null references accounts (id),
    counterparty_id bigint not null references counterparties (id),
    amount numeric(15, 2) not null,
    direction text not null check (direction in ('debit', 'credit')),
    status text not null check (status in ('settled', 'pending', 'flagged')),
    category text not null,
    created_at timestamptz not null
)