import argparse
import datetime as dt

import numpy as np

from db_connection import get_connection

FIRST_NAMES = [
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Fabio", "Gabriela", "Hugo",
    "Isabela", "Joao", "Karina", "Lucas", "Mariana", "Nelson", "Otavio",
    "Patricia", "Rafael", "Sofia", "Thiago", "Vanessa",
]
LAST_NAMES = [
    "Almeida", "Barbosa", "Costa", "Duarte", "Esteves", "Ferreira", "Gomes",
    "Henriques", "Junqueira", "Lima", "Martins", "Nogueira", "Oliveira",
    "Pereira", "Ribeiro", "Santos", "Teixeira", "Vieira",
]
STATUSES = np.array(["active", "closed"])
STATUS_WEIGHTS = np.array([0.9, 0.1])

OPENED_START = dt.datetime(2019, 1, 1, tzinfo=dt.timezone.utc)
OPENED_END = dt.datetime(2026, 8, 6, tzinfo=dt.timezone.utc)


def generate_rows(count: int, rng: np.random.Generator):
    first_idx = rng.integers(0, len(FIRST_NAMES), size=count)
    last_idx = rng.integers(0, len(LAST_NAMES), size=count)
    statuses = rng.choice(STATUSES, size=count, p=STATUS_WEIGHTS)
    span_seconds = int((OPENED_END - OPENED_START).total_seconds())
    offsets = rng.integers(0, span_seconds, size=count)

    for i in range(count):
        name = f"{FIRST_NAMES[first_idx[i]]} {LAST_NAMES[last_idx[i]]}"
        opened_at = OPENED_START + dt.timedelta(seconds=int(offsets[i]))
        yield (name, opened_at, statuses[i])


def main():
    parser = argparse.ArgumentParser(description="Popula a tabela accounts.")
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    with get_connection() as conn:
        with conn.cursor() as cur:
            with cur.copy(
                "COPY accounts (customer_name, opened_at, status) FROM STDIN"
            ) as copy:
                for row in generate_rows(args.count, rng):
                    copy.write_row(row)
        conn.commit()

    print(f"accounts: {args.count} linhas inseridas")


if __name__ == "__main__":
    main()
