create table accounts (
    id bigint generated always as identity primary key,
    customer_name text not null,
    opened_at timestamptz not null,
    status text not null
)