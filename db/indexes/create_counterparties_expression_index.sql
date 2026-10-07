create index idx_counterparties_upper_name
    on counterparties (upper(name) text_pattern_ops);
