import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import environment_metadata, summarize, write_json
from db_connection import get_connection


TABLE_NAME = "benchmark_transactions"
INDEX_NAME = "idx_benchmark_transactions_account_created_at"

QUERY = f"""
select *
from {TABLE_NAME}
where account_id = %s
  and created_at between %s and %s
order by created_at desc
"""


def execute_query(cur, parameters) -> None:
    cur.execute(QUERY, parameters)
    cur.fetchall()


def measure(cur, parameters, warmup: int, executions: int) -> list[float]:
    for _ in range(warmup):
        execute_query(cur, parameters)

    samples = []
    for _ in range(executions):
        started_at = time.perf_counter_ns()
        execute_query(cur, parameters)
        samples.append((time.perf_counter_ns() - started_at) / 1_000_000)

    return samples


def explain(cur, parameters):
    cur.execute(
        "explain (analyze, buffers, settings, format json) " + QUERY,
        parameters,
    )
    return cur.fetchone()[0][0]


def create_table(cur) -> None:
    cur.execute(f"drop table if exists {TABLE_NAME}")
    cur.execute(
        f"""
        create unlogged table {TABLE_NAME} (
            id bigint not null,
            account_id bigint not null,
            counterparty_id bigint not null,
            amount numeric(15, 2) not null,
            direction text not null,
            status text not null,
            category text not null,
            created_at timestamptz not null
        )
        """
    )


def extend_table(cur, rows: int) -> None:
    if rows == 1_000_000:
        cur.execute(
            f"insert into {TABLE_NAME} select * from transactions where id <= 1000000"
        )
    elif rows == 10_000_000:
        cur.execute(
            f"insert into {TABLE_NAME} select * from transactions where id > 1000000"
        )
    elif rows == 50_000_000:
        cur.execute(
            f"""
            insert into {TABLE_NAME}
            select
                t.id + (copies.copy_number * 10000000),
                t.account_id,
                t.counterparty_id,
                t.amount,
                t.direction,
                t.status,
                t.category,
                t.created_at + (copies.copy_number * interval '1 microsecond')
            from transactions t
            cross join generate_series(1, 4) as copies(copy_number)
            """
        )
    else:
        raise ValueError(f"Escala não suportada: {rows}")

    cur.execute(f"analyze {TABLE_NAME}")


def create_index(cur) -> None:
    cur.execute(
        f"create index {INDEX_NAME} on {TABLE_NAME} (account_id, created_at)"
    )
    cur.execute(f"analyze {TABLE_NAME}")


def relation_sizes(cur) -> dict:
    cur.execute(
        "select pg_relation_size(%s), pg_relation_size(%s)",
        (TABLE_NAME, INDEX_NAME),
    )
    table_size, index_size = cur.fetchone()
    return {
        "table_bytes": table_size,
        "index_bytes": index_size,
    }


def print_summary(rows: int, scenario: str, summary: dict) -> None:
    print(
        f"{rows:,} {scenario}: "
        f"p50={summary['p50_ms']:.3f} ms "
        f"p95={summary['p95_ms']:.3f} ms "
        f"p99={summary['p99_ms']:.3f} ms",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Mede a consulta de extrato em 1M, 10M e 50M de linhas."
    )
    parser.add_argument("--account-id", type=int, default=47)
    parser.add_argument("--executions", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--end-date", default="2025-04-01")
    parser.add_argument("--keep-table", action="store_true")
    parser.add_argument(
        "--output",
        default="benchmarks/results/scale.json",
    )
    args = parser.parse_args()
    parameters = (args.account_id, args.start_date, args.end_date)

    with get_connection() as conn:
        conn.autocommit = True
        metadata = environment_metadata(conn)
        results = []

        try:
            with conn.cursor() as cur:
                cur.execute("select count(*) from transactions")
                source_rows = cur.fetchone()[0]
                if source_rows < 10_000_000:
                    raise RuntimeError(
                        "O benchmark de escala exige ao menos 10 milhões de transações."
                    )

                create_table(cur)

                for rows in (1_000_000, 10_000_000, 50_000_000):
                    print(f"==> preparando {rows:,} linhas", flush=True)
                    extend_table(cur, rows)

                    without_index_samples = measure(
                        cur,
                        parameters,
                        args.warmup,
                        args.executions,
                    )
                    without_index = summarize(without_index_samples)
                    without_index_plan = explain(cur, parameters)
                    print_summary(rows, "sem índice", without_index)

                    create_index(cur)
                    with_index_samples = measure(
                        cur,
                        parameters,
                        args.warmup,
                        args.executions,
                    )
                    with_index = summarize(with_index_samples)
                    with_index_plan = explain(cur, parameters)
                    sizes = relation_sizes(cur)
                    print_summary(rows, "com índice", with_index)

                    results.append(
                        {
                            "rows": rows,
                            **sizes,
                            "without_index": without_index,
                            "with_index": with_index,
                            "p50_speedup": round(
                                without_index["p50_ms"] / with_index["p50_ms"],
                                3,
                            ),
                            "samples_ms": {
                                "without_index": [
                                    round(value, 6)
                                    for value in without_index_samples
                                ],
                                "with_index": [
                                    round(value, 6) for value in with_index_samples
                                ],
                            },
                            "plans": {
                                "without_index": without_index_plan,
                                "with_index": with_index_plan,
                            },
                        }
                    )

                    if rows != 50_000_000:
                        cur.execute(f"drop index {INDEX_NAME}")

            payload = {
                "benchmark": "statement_query_scalability",
                "methodology": {
                    "account_id": args.account_id,
                    "period": [args.start_date, args.end_date],
                    "warmup_executions": args.warmup,
                    "measured_executions_per_scenario": args.executions,
                    "measurement": "client wall-clock time",
                    "outlier_removal": "none",
                    "table": "UNLOGGED copy with the same row shape as transactions",
                },
                "environment": metadata,
                "results": results,
            }
            write_json(args.output, payload)
            print(f"resultado bruto: {args.output}")
        finally:
            if not args.keep_table:
                with conn.cursor() as cur:
                    cur.execute(f"drop table if exists {TABLE_NAME}")


if __name__ == "__main__":
    main()
