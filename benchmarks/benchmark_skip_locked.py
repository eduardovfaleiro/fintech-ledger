import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import environment_metadata, summarize, write_json
from db_connection import get_connection


TABLE_NAME = "antifraud_queue_demo"

CLAIM_WITH_LOCK = f"""
with next_batch as (
    select transaction_id
    from {TABLE_NAME}
    where status = 'queued'
    order by created_at, transaction_id
    for update
    limit %s
)
update {TABLE_NAME} queue
set
    status = 'processing',
    worker_id = %s,
    claimed_at = clock_timestamp()
from next_batch
where queue.transaction_id = next_batch.transaction_id
returning queue.transaction_id
"""

CLAIM_WITH_SKIP_LOCKED = CLAIM_WITH_LOCK.replace(
    "for update\n",
    "for update skip locked\n",
)


def setup_queue(conn, jobs: int) -> int:
    with conn.cursor() as cur:
        cur.execute(f"drop table if exists {TABLE_NAME}")
        cur.execute(
            f"""
            create unlogged table {TABLE_NAME} (
                transaction_id bigint primary key,
                created_at timestamptz not null,
                status text not null check (status in ('queued', 'processing')),
                worker_id text,
                claimed_at timestamptz
            )
            """
        )
        cur.execute(
            f"""
            insert into {TABLE_NAME} (transaction_id, created_at, status)
            select id, created_at, 'queued'
            from transactions
            where status = 'flagged'
            order by created_at, id
            limit %s
            """,
            (jobs,),
        )
        inserted = cur.rowcount
        cur.execute(
            f"""
            create index idx_antifraud_queue_demo_queued
                on {TABLE_NAME} (created_at, transaction_id)
                where status = 'queued'
            """
        )
    conn.commit()
    return inserted


def reset_queue(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            update {TABLE_NAME}
            set status = 'queued', worker_id = null, claimed_at = null
            """
        )
    conn.commit()


def worker(
    conn,
    barrier: threading.Barrier,
    worker_id: str,
    query: str,
    batch_size: int,
    processing_delay_ms: float,
) -> list[int]:
    claimed = []
    barrier.wait()

    with conn.cursor() as cur:
        while True:
            cur.execute(query, (batch_size, worker_id))
            transaction_ids = [row[0] for row in cur.fetchall()]

            if not transaction_ids:
                conn.rollback()
                break

            if processing_delay_ms:
                time.sleep(processing_delay_ms / 1_000)

            conn.commit()
            claimed.extend(transaction_ids)

    return claimed


def run_workers(
    query: str,
    workers: int,
    batch_size: int,
    processing_delay_ms: float,
) -> tuple[float, list[int]]:
    connections = [get_connection() for _ in range(workers)]
    barrier = threading.Barrier(workers)

    try:
        started_at = time.perf_counter_ns()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    worker,
                    connection,
                    barrier,
                    f"worker-{position + 1}",
                    query,
                    batch_size,
                    processing_delay_ms,
                )
                for position, connection in enumerate(connections)
            ]
            claimed = [
                transaction_id
                for future in futures
                for transaction_id in future.result()
            ]
        elapsed = (time.perf_counter_ns() - started_at) / 1_000_000
    finally:
        for connection in connections:
            connection.close()

    return elapsed, claimed


def validate_claims(claimed: list[int], expected_jobs: int) -> None:
    if len(claimed) != expected_jobs:
        raise RuntimeError(
            f"Esperava {expected_jobs} jobs processados, mas recebeu {len(claimed)}."
        )
    if len(set(claimed)) != expected_jobs:
        raise RuntimeError("O mesmo job foi processado mais de uma vez.")


def measure_mode(conn, query: str, args) -> list[float]:
    samples = []
    total_executions = args.warmup + args.executions

    for execution in range(total_executions):
        reset_queue(conn)
        elapsed, claimed = run_workers(
            query,
            args.workers,
            args.batch_size,
            args.processing_delay_ms,
        )
        validate_claims(claimed, args.jobs)

        if execution >= args.warmup:
            samples.append(elapsed)

    return samples


def print_summary(name: str, summary: dict) -> None:
    print(
        f"{name}: p50={summary['p50_ms']:.3f} ms "
        f"p95={summary['p95_ms']:.3f} ms "
        f"p99={summary['p99_ms']:.3f} ms"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compara FOR UPDATE com FOR UPDATE SKIP LOCKED."
    )
    parser.add_argument("--jobs", type=int, default=1_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--processing-delay-ms", type=float, default=5)
    parser.add_argument("--executions", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument(
        "--output",
        default="benchmarks/results/skip_locked.json",
    )
    args = parser.parse_args()

    with get_connection() as conn:
        metadata = environment_metadata(conn)
        try:
            inserted = setup_queue(conn, args.jobs)
            if inserted != args.jobs:
                raise RuntimeError(
                    f"A base possui somente {inserted} transações flagged disponíveis."
                )

            without_skip_samples = measure_mode(conn, CLAIM_WITH_LOCK, args)
            with_skip_samples = measure_mode(conn, CLAIM_WITH_SKIP_LOCKED, args)
        finally:
            with conn.cursor() as cur:
                cur.execute(f"drop table if exists {TABLE_NAME}")
            conn.commit()

    summaries = {
        "for_update": summarize(without_skip_samples),
        "for_update_skip_locked": summarize(with_skip_samples),
    }
    speedup = (
        summaries["for_update"]["p50_ms"]
        / summaries["for_update_skip_locked"]["p50_ms"]
    )
    payload = {
        "benchmark": "antifraud_queue_concurrency",
        "methodology": {
            "jobs_per_execution": args.jobs,
            "workers": args.workers,
            "batch_size": args.batch_size,
            "processing_delay_ms_inside_transaction": args.processing_delay_ms,
            "warmup_executions": args.warmup,
            "measured_executions_per_scenario": args.executions,
            "measurement": "client wall-clock time to drain the queue",
            "outlier_removal": "none",
            "correctness_check": "every job claimed exactly once",
        },
        "environment": metadata,
        "results": summaries,
        "p50_speedup": round(speedup, 3),
        "samples_ms": {
            "for_update": [round(value, 6) for value in without_skip_samples],
            "for_update_skip_locked": [
                round(value, 6) for value in with_skip_samples
            ],
        },
    }
    write_json(args.output, payload)

    print(f"jobs por execução: {args.jobs}")
    print_summary("FOR UPDATE", summaries["for_update"])
    print_summary("FOR UPDATE SKIP LOCKED", summaries["for_update_skip_locked"])
    print(f"diferença no p50: {speedup:.1f}x")
    print("correção: todos os jobs foram processados exatamente uma vez")
    print(f"resultado bruto: {args.output}")


if __name__ == "__main__":
    main()
