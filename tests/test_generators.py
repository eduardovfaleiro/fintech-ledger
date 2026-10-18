import datetime as dt
import unittest

import numpy as np

from generate_counterparties import MAX_UNIQUE_NAMES, generate_rows
from generate_transactions import (
    CREATED_END,
    CREATED_START,
    build_account_weights,
    generate_batch,
)
from query_loader import load_query


class CounterpartyGeneratorTest(unittest.TestCase):
    def test_names_are_unique(self):
        rows = list(generate_rows(5_000, np.random.default_rng(42)))

        self.assertEqual(len(rows), 5_000)
        self.assertEqual(len(set(rows)), 5_000)

    def test_count_cannot_exceed_name_space(self):
        with self.assertRaisesRegex(ValueError, "available unique names"):
            list(
                generate_rows(
                    MAX_UNIQUE_NAMES + 1,
                    np.random.default_rng(42),
                )
            )


class TransactionGeneratorTest(unittest.TestCase):
    def test_distribution_requires_multiple_accounts(self):
        with self.assertRaisesRegex(ValueError, "at least two accounts"):
            build_account_weights(
                np.array([1]),
                0.01,
                0.60,
                np.random.default_rng(42),
            )

    def test_distribution_rejects_invalid_fractions(self):
        account_ids = np.arange(1, 11)
        for whale_fraction, whale_share in (
            (0, 0.6),
            (1, 0.6),
            (0.1, 1),
            (0.6, 0.1),
        ):
            with (
                self.subTest(
                    whale_fraction=whale_fraction,
                    whale_share=whale_share,
                ),
                self.assertRaises(ValueError),
            ):
                build_account_weights(
                    account_ids,
                    whale_fraction,
                    whale_share,
                    np.random.default_rng(42),
                )

    def test_transactions_never_predate_their_accounts(self):
        account_ids = np.array([10, 20], dtype=np.int64)
        account_opened_at = np.array(
            [
                int(dt.datetime(2020, 1, 1, tzinfo=dt.UTC).timestamp()),
                int(dt.datetime(2023, 12, 31, tzinfo=dt.UTC).timestamp()),
            ],
            dtype=np.int64,
        )
        cumulative_weights = np.array([0.5, 1.0])
        opened_by_id = dict(zip(account_ids, account_opened_at))

        rows = list(
            generate_batch(
                500,
                account_ids,
                cumulative_weights,
                np.array([1]),
                np.random.default_rng(42),
                account_opened_at,
            )
        )

        for row in rows:
            created_at = row[-1]
            self.assertGreaterEqual(
                int(created_at.timestamp()),
                opened_by_id[row[0]],
            )
            self.assertLess(created_at, CREATED_END)

    def test_transactions_reject_accounts_opened_during_the_event_period(self):
        with self.assertRaisesRegex(ValueError, "before CREATED_START"):
            list(
                generate_batch(
                    1,
                    np.array([10, 20], dtype=np.int64),
                    np.array([0.5, 1.0]),
                    np.array([1]),
                    np.random.default_rng(42),
                    np.array(
                        [
                            int(dt.datetime(2020, 1, 1, tzinfo=dt.UTC).timestamp()),
                            int(CREATED_START.timestamp()),
                        ],
                        dtype=np.int64,
                    ),
                )
            )


class QueryLoaderTest(unittest.TestCase):
    def test_loads_a_versioned_query(self):
        self.assertIn("select", load_query("get_balance.sql").lower())

    def test_rejects_paths_and_non_sql_files(self):
        for name in ("../README.md", "get_balance", "nested/query.sql"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                load_query(name)


if __name__ == "__main__":
    unittest.main()
