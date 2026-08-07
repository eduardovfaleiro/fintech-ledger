import argparse
import datetime as dt

import numpy as np

from db_connection import get_connection

CATEGORIES = [
    "groceries", "transport", "entertainment", "utilities", "salary",
    "rent", "shopping", "dining", "health", "subscriptions", "transfer",
    "other",
]
CATEGORY_WEIGHTS = np.array(
    [0.18, 0.12, 0.08, 0.06, 0.02, 0.03, 0.15, 0.14, 0.05, 0.05, 0.09, 0.03]
)

STATUSES = np.array(["settled", "pending", "flagged"])
STATUS_WEIGHTS = np.array([0.95, 0.04, 0.01])

DIRECTIONS = np.array(["debit", "credit"])
DIRECTION_WEIGHTS = np.array([0.85, 0.15])

CREATED_START = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
CREATED_END = dt.datetime(2026, 8, 6, tzinfo=dt.timezone.utc)


def fetch_ids(conn, table: str) -> np.ndarray:
    with conn.cursor() as cur:
        cur.execute(f"SELECT id FROM {table} ORDER BY id")
        return np.array([row[0] for row in cur.fetchall()], dtype=np.int64)


def build_account_weights(
    account_ids: np.ndarray, whale_fraction: float, whale_share: float,
    rng: np.random.Generator,
) -> np.ndarray:
    n_accounts = len(account_ids)
    n_whales = max(1, round(whale_fraction * n_accounts))
    whale_positions = rng.permutation(n_accounts)[:n_whales]

    weights = np.full(n_accounts, (1 - whale_share) / (n_accounts - n_whales))
    weights[whale_positions] = whale_share / n_whales

    cumulative = np.cumsum(weights)
    cumulative[-1] = 1.0
    return cumulative


def generate_batch(
    batch_size: int,
    account_ids: np.ndarray,
    account_cumweights: np.ndarray,
    counterparty_ids: np.ndarray,
    rng: np.random.Generator,
):
    account_idx = np.searchsorted(account_cumweights, rng.random(batch_size), side="right")
    account_idx = np.clip(account_idx, 0, len(account_ids) - 1)
    batch_account_ids = account_ids[account_idx]

    counterparty_idx = rng.integers(0, len(counterparty_ids), size=batch_size)
    batch_counterparty_ids = counterparty_ids[counterparty_idx]

    categories = rng.choice(CATEGORIES, size=batch_size, p=CATEGORY_WEIGHTS)
    directions = rng.choice(DIRECTIONS, size=batch_size, p=DIRECTION_WEIGHTS)
    directions[categories == "salary"] = "credit"

    statuses = rng.choice(STATUSES, size=batch_size, p=STATUS_WEIGHTS)

    amounts = np.round(np.clip(rng.lognormal(3.5, 1.0, size=batch_size), 0.01, 50_000), 2)

    span_seconds = int((CREATED_END - CREATED_START).total_seconds())
    offsets = rng.integers(0, span_seconds, size=batch_size)

    for i in range(batch_size):
        created_at = CREATED_START + dt.timedelta(seconds=int(offsets[i]))
        yield (
            int(batch_account_ids[i]),
            int(batch_counterparty_ids[i]),
            float(amounts[i]),
            directions[i],
            statuses[i],
            categories[i],
            created_at,
        )


def main():
    parser = argparse.ArgumentParser(description="Popula a tabela transactions.")
    parser.add_argument("--count", type=int, default=10_000_000)
    parser.add_argument("--batch-size", type=int, default=500_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--whale-fraction", type=float, default=0.01)
    parser.add_argument("--whale-share", type=float, default=0.60)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    with get_connection() as conn:
        account_ids = fetch_ids(conn, "accounts")
        counterparty_ids = fetch_ids(conn, "counterparties")
        account_cumweights = build_account_weights(
            account_ids, args.whale_fraction, args.whale_share, rng
        )

        inserted = 0
        with conn.cursor() as cur:
            with cur.copy(
                "COPY transactions "
                "(account_id, counterparty_id, amount, direction, status, category, created_at) "
                "FROM STDIN"
            ) as copy:
                while inserted < args.count:
                    batch_size = min(args.batch_size, args.count - inserted)
                    for row in generate_batch(
                        batch_size, account_ids, account_cumweights,
                        counterparty_ids, rng,
                    ):
                        copy.write_row(row)
                    inserted += batch_size
                    print(f"transactions: {inserted}/{args.count}")
        conn.commit()

    print(f"transactions: {args.count} linhas inseridas")


if __name__ == "__main__":
    main()
