import argparse
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_connection import get_connection


GET_TRANSACTIONS = """
select
    id,
    created_at,
    amount,
    direction,
    category,
    counterparty_id
from transactions
where account_id = 30362
order by created_at desc, id desc
limit 50
"""

GET_COUNTERPARTY = """
select name
from counterparties
where id = %s
"""

GET_STATEMENT_WITH_COUNTERPARTY = """
select
    t.id,
    t.created_at,
    t.amount,
    t.direction,
    t.category,
    c.name
from transactions t
join counterparties c on c.id = t.counterparty_id
where t.account_id = 30362
order by t.created_at desc, t.id desc
limit 50
"""


def run_n_plus_one(cur):
    cur.execute(GET_TRANSACTIONS)
    transactions = cur.fetchall()

    for transaction in transactions:
        cur.execute(GET_COUNTERPARTY, (transaction[5],))
        cur.fetchone()


def run_join(cur):
    cur.execute(GET_STATEMENT_WITH_COUNTERPARTY)
    cur.fetchall()


def measure(cur, executions: int):
    n_plus_one_times = []
    join_times = []

    for _ in range(executions):
        started_at = time.perf_counter_ns()
        run_n_plus_one(cur)
        n_plus_one_times.append((time.perf_counter_ns() - started_at) / 1_000_000)

        started_at = time.perf_counter_ns()
        run_join(cur)
        join_times.append((time.perf_counter_ns() - started_at) / 1_000_000)

    return statistics.median(n_plus_one_times), statistics.median(join_times)


def main():
    parser = argparse.ArgumentParser(description="Compara N+1 com um único JOIN.")
    parser.add_argument("--executions", type=int, default=1_000)
    parser.add_argument("--warmup", type=int, default=20)
    args = parser.parse_args()

    with get_connection() as conn:
        with conn.cursor() as cur:
            for _ in range(args.warmup):
                run_n_plus_one(cur)
                run_join(cur)

            n_plus_one, join = measure(cur, args.executions)

    print(f"execuções: {args.executions}")
    print(f"N+1 (mediana): {n_plus_one:.3f} ms")
    print(f"JOIN (mediana): {join:.3f} ms")
    print(f"diferença: {n_plus_one / join:.1f}x")


if __name__ == "__main__":
    main()
