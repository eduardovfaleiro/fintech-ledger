import argparse
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
from query_loader import load_query

GET_TRANSACTIONS = """
select
    id,
    created_at,
    amount,
    direction,
    category,
    counterparty_id
from transactions
where account_id = %s
order by created_at desc, id desc
limit %s
"""

GET_COUNTERPARTY = """
select name
from counterparties
where id = %s
"""

GET_STATEMENT_WITH_COUNTERPARTY = load_query("get_statement_with_counterparty.sql")


def run_n_plus_one(cur, account_id: int, page_size: int):
    cur.execute(GET_TRANSACTIONS, (account_id, page_size))
    transactions = cur.fetchall()

    for transaction in transactions:
        cur.execute(GET_COUNTERPARTY, (transaction[5],))
        cur.fetchone()


def run_join(cur, account_id: int, page_size: int):
    cur.execute(GET_STATEMENT_WITH_COUNTERPARTY, (account_id, page_size))
    cur.fetchall()


def elapsed_ms(operation, *args) -> float:
    started_at = time.perf_counter_ns()
    operation(*args)
    return (time.perf_counter_ns() - started_at) / 1_000_000


def measure(cur, account_id: int, page_size: int, executions: int):
    samples = {"n_plus_one": [], "join": []}

    for execution in range(executions):
        operations = (
            ("n_plus_one", run_n_plus_one),
            ("join", run_join),
        )
        if execution % 2:
            operations = reversed(operations)

        for name, operation in operations:
            samples[name].append(elapsed_ms(operation, cur, account_id, page_size))

    return samples


def print_summary(name: str, summary: dict) -> None:
    print(
        f"{name}: p50={summary['p50_ms']:.3f} ms "
        f"p95={summary['p95_ms']:.3f} ms "
        f"p99={summary['p99_ms']:.3f} ms"
    )


def main():
    parser = argparse.ArgumentParser(description="Compara N+1 com um único JOIN.")
    parser.add_argument("--account-id", type=positive_int, default=30362)
    parser.add_argument("--page-size", type=positive_int, default=50)
    parser.add_argument("--executions", type=positive_int, default=1_000)
    parser.add_argument("--warmup", type=non_negative_int, default=20)
    parser.add_argument(
        "--output",
        default="benchmarks/results/n_plus_one.json",
    )
    args = parser.parse_args()

    with get_connection() as conn:
        metadata = environment_metadata(conn)

        with conn.cursor() as cur:
            for _ in range(args.warmup):
                run_n_plus_one(cur, args.account_id, args.page_size)
                run_join(cur, args.account_id, args.page_size)

            samples = measure(
                cur,
                args.account_id,
                args.page_size,
                args.executions,
            )

    summaries = {name: summarize(values) for name, values in samples.items()}
    speedup = summaries["n_plus_one"]["p50_ms"] / summaries["join"]["p50_ms"]

    payload = {
        "benchmark": "n_plus_one_vs_join",
        "methodology": {
            "account_id": args.account_id,
            "page_size": args.page_size,
            "warmup_executions": args.warmup,
            "measured_executions": args.executions,
            "measurement": "client wall-clock time",
            "order": "alternated on every execution",
            "outlier_removal": "none",
        },
        "environment": metadata,
        "results": summaries,
        "p50_speedup": round(speedup, 3),
        "samples_ms": {
            name: [round(value, 6) for value in values]
            for name, values in samples.items()
        },
    }
    write_json(args.output, payload)

    print(f"execuções medidas: {args.executions}")
    print_summary("N+1", summaries["n_plus_one"])
    print_summary("JOIN", summaries["join"])
    print(f"diferença no p50: {speedup:.1f}x")
    print(f"resultado bruto: {args.output}")


if __name__ == "__main__":
    main()
