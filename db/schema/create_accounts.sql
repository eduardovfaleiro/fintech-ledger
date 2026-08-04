create table accounts:
    id bigint generated always as identity primary,
    customer_name text,
    opened_at timestamptz,
    status text