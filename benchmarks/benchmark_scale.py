import argparse
import datetime as dt
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import (
    environment_metadata,
    non_negative_int,
    positive_int,
    summarize,
    write_json,
)
from db_connection import get_connection

TABLE_NAME = "benchmark_transactions"
INDEX_NAME = "idx_benchmark_transactions_account_created_at"

QUERY = f"""
select
    id,
    account_id,
    counterparty_id,
    amount,
    direction,
    status,
    category,
    created_at
from {TABLE_NAME}
where account_id = %s
  and created_at >= %s
  and created_at < %s
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


def maximum_copy_number(target_rows: int, source_rows: int) -> int:
    return math.ceil(target_rows / source_rows) - 1


def extend_table(
    cur,
    current_rows: int,
    target_rows: int,
    source_rows: int,
) -> None:
    rows_to_add = target_rows - current_rows
    if rows_to_add <= 0:
        raise ValueError("target_rows must be greater than current_rows")

    max_copy = maximum_copy_number(target_rows, source_rows)
    cur.execute(
        f"""
        insert into {TABLE_NAME}
        select
            t.id + (copies.copy_number * %s),
            t.account_id,
            t.counterparty_id,
            t.amount,
            t.direction,
            t.status,
            t.category,
            t.created_at + (copies.copy_number * interval '1 microsecond')
        from generate_series(0, %s) as copies(copy_number)
        cross join transactions t
        where t.id + (copies.copy_number * %s) > %s
          and t.id + (copies.copy_number * %s) <= %s
        """,
        (
            source_rows,
            max_copy,
            source_rows,
            current_rows,
            source_rows,
            target_rows,
        ),
    )
    if cur.rowcount != rows_to_add:
        raise RuntimeError(
            f"Expected to insert {rows_to_add} rows, inserted {cur.rowcount}."
        )

    cur.execute(f"analyze {TABLE_NAME}")


def create_index(cur) -> None:
    cur.execute(f"create index {INDEX_NAME} on {TABLE_NAME} (account_id, created_at)")
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


def iso_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must use the YYYY-MM-DD format") from exc
    return value


def main():
    parser = argparse.ArgumentParser(
        description="Mede a consulta de extrato em 1M, 10M e 50M de linhas."
    )
    parser.add_argument("--account-id", type=positive_int, default=47)
    parser.add_argument("--executions", type=positive_int, default=30)
    parser.add_argument("--warmup", type=non_negative_int, default=3)
    parser.add_argument("--start-date", type=iso_date, default="2025-01-01")
    parser.add_argument("--end-date", type=iso_date, default="2025-04-01")
    parser.add_argument(
        "--scales",
        nargs="+",
        type=positive_int,
        default=[1_000_000, 10_000_000, 50_000_000],
        metavar="ROWS",
        help="strictly increasing row counts (default: 1M 10M 50M)",
    )
    parser.add_argument("--keep-table", action="store_true")
    parser.add_argument(
        "--output",
        default="benchmarks/results/scale.json",
    )
    args = parser.parse_args()
    if args.scales != sorted(set(args.scales)):
        parser.error("--scales must contain unique values in increasing order")
    if args.start_date >= args.end_date:
        parser.error("--start-date must be earlier than --end-date")

    parameters = (args.account_id, args.start_date, args.end_date)

    with get_connection() as conn:
        conn.autocommit = True
        metadata = environment_metadata(conn)
        results = []

        try:
            with conn.cursor() as cur:
                cur.execute("select count(*), min(id), max(id) from transactions")
                source_rows, minimum_id, maximum_id = cur.fetchone()
                if source_rows == 0:
                    raise RuntimeError("The transactions table is empty.")
                if minimum_id != 1 or maximum_id != source_rows:
                    raise RuntimeError(
                        "The scale benchmark requires transaction IDs to be dense "
                        "and start at 1. Recreate the data set with `make reset`."
                    )

                create_table(cur)
                current_rows = 0

                for rows in args.scales:
                    print(f"==> preparando {rows:,} linhas", flush=True)
                    extend_table(cur, current_rows, rows, source_rows)
                    current_rows = rows

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
                                    round(value, 6) for value in without_index_samples
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

                    if rows != args.scales[-1]:
                        cur.execute(f"drop index {INDEX_NAME}")

            payload = {
                "benchmark": "statement_query_scalability",
                "methodology": {
                    "account_id": args.account_id,
                    "period": [args.start_date, args.end_date],
                    "scales": args.scales,
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
