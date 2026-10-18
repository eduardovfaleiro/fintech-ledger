import argparse
import datetime as dt

import numpy as np

from db_connection import get_connection

CATEGORIES = [
    "groceries",
    "transport",
    "entertainment",
    "utilities",
    "salary",
    "rent",
    "shopping",
    "dining",
    "health",
    "subscriptions",
    "transfer",
    "other",
]
CATEGORY_WEIGHTS = np.array(
    [0.18, 0.12, 0.08, 0.06, 0.02, 0.03, 0.15, 0.14, 0.05, 0.05, 0.09, 0.03]
)

STATUSES = np.array(["settled", "pending", "flagged"])
STATUS_WEIGHTS = np.array([0.95, 0.04, 0.01])

DIRECTIONS = np.array(["debit", "credit"])
DIRECTION_WEIGHTS = np.array([0.85, 0.15])

CREATED_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
CREATED_END = dt.datetime(2026, 8, 6, tzinfo=dt.UTC)

ALLOWED_TABLES = {"accounts", "counterparties"}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def fraction(value: str) -> float:
    parsed = float(value)
    if not 0 < parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than zero and less than one")
    return parsed


def fetch_ids(conn, table: str) -> np.ndarray:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"unsupported table: {table}")
    with conn.cursor() as cur:
        cur.execute(f"select id from {table} order by id")
        return np.array([row[0] for row in cur.fetchall()], dtype=np.int64)


def fetch_accounts(conn) -> tuple[np.ndarray, np.ndarray]:
    with conn.cursor() as cur:
        cur.execute("select id, opened_at from accounts order by id")
        rows = cur.fetchall()

    account_ids = np.array([row[0] for row in rows], dtype=np.int64)
    opened_at = np.array(
        [int(row[1].timestamp()) for row in rows],
        dtype=np.int64,
    )
    return account_ids, opened_at


def build_account_weights(
    account_ids: np.ndarray,
    whale_fraction: float,
    whale_share: float,
    rng: np.random.Generator,
) -> np.ndarray:
    n_accounts = len(account_ids)
    if n_accounts < 2:
        raise ValueError("at least two accounts are required")
    if not 0 < whale_fraction < 1:
        raise ValueError("whale_fraction must be between zero and one")
    if not 0 < whale_share < 1:
        raise ValueError("whale_share must be between zero and one")
    if whale_share <= whale_fraction:
        raise ValueError("whale_share must be greater than whale_fraction")

    n_whales = max(1, round(whale_fraction * n_accounts))
    n_whales = min(n_whales, n_accounts - 1)
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
    account_opened_at: np.ndarray | None = None,
):
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if len(counterparty_ids) == 0:
        raise ValueError("at least one counterparty is required")

    account_idx = np.searchsorted(
        account_cumweights, rng.random(batch_size), side="right"
    )
    account_idx = np.clip(account_idx, 0, len(account_ids) - 1)
    batch_account_ids = account_ids[account_idx]

    counterparty_idx = rng.integers(0, len(counterparty_ids), size=batch_size)
    batch_counterparty_ids = counterparty_ids[counterparty_idx]

    categories = rng.choice(CATEGORIES, size=batch_size, p=CATEGORY_WEIGHTS)
    directions = rng.choice(DIRECTIONS, size=batch_size, p=DIRECTION_WEIGHTS)
    directions[categories == "salary"] = "credit"

    statuses = rng.choice(STATUSES, size=batch_size, p=STATUS_WEIGHTS)

    amounts = np.round(
        np.clip(rng.lognormal(3.5, 1.0, size=batch_size), 0.01, 50_000), 2
    )

    if account_opened_at is not None:
        if len(account_opened_at) != len(account_ids):
            raise ValueError("account_opened_at must align with account_ids")
        if np.any(account_opened_at >= int(CREATED_START.timestamp())):
            raise ValueError("every account must be opened before CREATED_START")

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
    parser.add_argument("--count", type=positive_int, default=10_000_000)
    parser.add_argument("--batch-size", type=positive_int, default=500_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--whale-fraction", type=fraction, default=0.01)
    parser.add_argument("--whale-share", type=fraction, default=0.60)
    args = parser.parse_args()
    if args.whale_share <= args.whale_fraction:
        parser.error("--whale-share must be greater than --whale-fraction")

    rng = np.random.default_rng(args.seed)

    with get_connection() as conn:
        account_ids, account_opened_at = fetch_accounts(conn)
        counterparty_ids = fetch_ids(conn, "counterparties")
        account_cumweights = build_account_weights(
            account_ids, args.whale_fraction, args.whale_share, rng
        )

        inserted = 0
        with (
            conn.cursor() as cur,
            cur.copy(
                "COPY transactions "
                "(account_id, counterparty_id, amount, direction, status, category, created_at) "
                "FROM STDIN"
            ) as copy,
        ):
            while inserted < args.count:
                batch_size = min(args.batch_size, args.count - inserted)
                for row in generate_batch(
                    batch_size,
                    account_ids,
                    account_cumweights,
                    counterparty_ids,
                    rng,
                    account_opened_at,
                ):
                    copy.write_row(row)
                inserted += batch_size
                print(f"transactions: {inserted}/{args.count}")
        conn.commit()

    print(f"transactions: {args.count} linhas inseridas")


if __name__ == "__main__":
    main()
