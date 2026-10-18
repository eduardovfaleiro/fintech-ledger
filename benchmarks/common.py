import argparse
import datetime as dt
import json
import math
import os
import platform
import statistics
from pathlib import Path


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(values: list[float]) -> dict:
    if not values:
        raise ValueError("A lista de tempos não pode estar vazia.")

    return {
        "executions": len(values),
        "min_ms": round(min(values), 6),
        "p50_ms": round(percentile(values, 0.50), 6),
        "p95_ms": round(percentile(values, 0.95), 6),
        "p99_ms": round(percentile(values, 0.99), 6),
        "max_ms": round(max(values), 6),
        "mean_ms": round(statistics.fmean(values), 6),
    }


def environment_metadata(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("select version()")
        postgres_version = cur.fetchone()[0]

        cur.execute(
            """
            select name, setting, unit
            from pg_settings
            where name in (
                'effective_cache_size',
                'jit',
                'max_parallel_workers_per_gather',
                'random_page_cost',
                'shared_buffers',
                'work_mem'
            )
            order by name
            """
        )
        postgres_settings = {
            name: {"setting": setting, "unit": unit}
            for name, setting, unit in cur.fetchall()
        }

        cur.execute("select pg_database_size(current_database())")
        database_size_bytes = cur.fetchone()[0]

    page_size = os.sysconf("SC_PAGE_SIZE")
    physical_pages = os.sysconf("SC_PHYS_PAGES")

    return {
        "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
        "client": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
            "memory_bytes": page_size * physical_pages,
        },
        "database": {
            "version": postgres_version,
            "size_bytes": database_size_bytes,
            "settings": postgres_settings,
        },
    }


def write_json(path: str | Path, payload: dict) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
