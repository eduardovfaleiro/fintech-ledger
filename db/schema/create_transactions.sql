create table transactions (
    id bigint generated always as identity primary key,
    account_id bigint not null references accounts (id),
    counterparty_id bigint not null references counterparties (id),
    amount numeric(15, 2) not null check (amount > 0),
    direction text not null check (direction in ('debit', 'credit')),
    status text not null check (status in ('settled', 'pending', 'flagged')),
    category text not null,
    created_at timestamptz not null
);

comment on table transactions is
    'Append-only financial events. Corrections must be recorded as new transactions.';

create function prevent_transaction_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'transactions is append-only; insert a compensating transaction instead'
        using errcode = '55000';
end;
$$;

create trigger transactions_append_only
before update or delete on transactions
for each row
execute function prevent_transaction_mutation();
