import datetime as dt
import decimal
import unittest

from psycopg.errors import (
    CheckViolation,
    ObjectNotInPrerequisiteState,
    UniqueViolation,
)

from db_connection import get_connection
from query_loader import load_query

EXPECTED_INDEXES = {
    "idx_transactions_account_id_created_at",
    "idx_transactions_account_pagination",
    "idx_transactions_flagged_queue",
    "idx_counterparties_upper_name",
}


class DatabaseIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = get_connection()
        with cls.conn.cursor() as cur:
            cur.execute(
                """
                select account_id
                from transactions
                group by account_id
                order by count(*) desc
                limit 1
                """
            )
            row = cur.fetchone()
            if row is None:
                raise unittest.SkipTest("integration tests require generated data")
            cls.account_id = row[0]
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def _create_account(self, customer_name="Test Customer"):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into accounts (customer_name, opened_at, status)
                values (%s, %s, 'active')
                returning id
                """,
                (customer_name, dt.datetime(2020, 1, 1, tzinfo=dt.UTC)),
            )
            return cur.fetchone()[0]

    def _counterparty_id(self):
        with self.conn.cursor() as cur:
            cur.execute("select id from counterparties order by id limit 1")
            return cur.fetchone()[0]

    def _insert_transaction(
        self,
        account_id,
        *,
        amount,
        direction,
        status="settled",
        created_at=None,
    ):
        created_at = created_at or dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                insert into transactions (
                    account_id,
                    counterparty_id,
                    amount,
                    direction,
                    status,
                    category,
                    created_at
                )
                values (%s, %s, %s, %s, %s, 'other', %s)
                returning id
                """,
                (
                    account_id,
                    self._counterparty_id(),
                    amount,
                    direction,
                    status,
                    created_at,
                ),
            )
            return cur.fetchone()[0]

    def test_expected_indexes_exist(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                select indexname
                from pg_indexes
                where schemaname = 'public'
                """
            )
            indexes = {row[0] for row in cur.fetchall()}

        self.assertTrue(EXPECTED_INDEXES.issubset(indexes))

    def test_net_position_includes_all_statuses_and_defaults_to_zero(self):
        account_id = self._create_account()
        empty_account_id = self._create_account("Empty Account")
        self._insert_transaction(account_id, amount="100.00", direction="credit")
        self._insert_transaction(account_id, amount="30.00", direction="debit")
        self._insert_transaction(
            account_id,
            amount="999.00",
            direction="credit",
            status="pending",
        )

        with self.conn.cursor() as cur:
            cur.execute(load_query("get_balance.sql"), (account_id,))
            balance = cur.fetchone()[0]
            cur.execute(load_query("get_balance.sql"), (empty_account_id,))
            empty_balance = cur.fetchone()[0]

        self.assertEqual(balance, decimal.Decimal("1069.00"))
        self.assertEqual(empty_balance, decimal.Decimal("0.00"))

    def test_statement_uses_a_half_open_period(self):
        account_id = self._create_account()
        start = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
        end = dt.datetime(2025, 2, 1, tzinfo=dt.UTC)
        included_id = self._insert_transaction(
            account_id,
            amount="10.00",
            direction="debit",
            created_at=start,
        )
        excluded_id = self._insert_transaction(
            account_id,
            amount="20.00",
            direction="debit",
            created_at=end,
        )

        with self.conn.cursor() as cur:
            cur.execute(
                load_query("get_statement.sql"),
                (account_id, start, end),
            )
            ids = [row[0] for row in cur.fetchall()]

        self.assertIn(included_id, ids)
        self.assertNotIn(excluded_id, ids)

    def test_keyset_page_matches_offset_page(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                select created_at, id
                from transactions
                where account_id = %s
                order by created_at desc, id desc
                offset 9 limit 1
                """,
                (self.account_id,),
            )
            cursor = cur.fetchone()
            self.assertIsNotNone(cursor)

            cur.execute(
                load_query("get_statement_offset.sql"),
                (self.account_id, 10, 10),
            )
            offset_ids = [row[0] for row in cur.fetchall()]

            cur.execute(
                load_query("get_statement_keyset.sql"),
                (self.account_id, *cursor, 10),
            )
            keyset_ids = [row[0] for row in cur.fetchall()]

        self.assertEqual(offset_ids, keyset_ids)

    def test_join_query_returns_counterparty_names(self):
        with self.conn.cursor() as cur:
            cur.execute(
                load_query("get_statement_with_counterparty.sql"),
                (self.account_id, 20),
            )
            join_rows = cur.fetchall()

            expected_rows = []
            for row in join_rows:
                cur.execute(
                    "select name from counterparties where id = "
                    "(select counterparty_id from transactions where id = %s)",
                    (row[0],),
                )
                expected_rows.append((*row[:5], cur.fetchone()[0]))

        self.assertEqual(join_rows, expected_rows)

    def test_counterparty_search_query_is_prefix_based(self):
        with self.conn.cursor() as cur:
            cur.execute("select name from counterparties order by id limit 1")
            expected_name = cur.fetchone()[0]
            prefix = expected_name[: max(1, len(expected_name) // 2)]

            cur.execute(
                load_query("search_counterparties.sql"),
                (prefix.swapcase(), 25),
            )
            rows = cur.fetchall()

        self.assertTrue(rows)
        self.assertIn(expected_name, {row[1] for row in rows})
        self.assertTrue(all(row[1].upper().startswith(prefix.upper()) for row in rows))

    def test_flagged_query_returns_oldest_flagged_transactions(self):
        with self.conn.cursor() as cur:
            cur.execute(load_query("get_flagged_transactions.sql"), (10,))
            actual_ids = [row[0] for row in cur.fetchall()]
            cur.execute(
                """
                select id
                from transactions
                where status = 'flagged'
                order by created_at, id
                limit 10
                """
            )
            expected_ids = [row[0] for row in cur.fetchall()]

        self.assertEqual(actual_ids, expected_ids)

    def test_claim_query_claims_distinct_queued_jobs(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                create temporary table antifraud_queue_demo (
                    transaction_id bigint primary key,
                    created_at timestamptz not null,
                    status text not null,
                    worker_id text,
                    claimed_at timestamptz
                ) on commit drop
                """
            )
            cur.execute(
                """
                insert into antifraud_queue_demo
                    (transaction_id, created_at, status)
                select id, created_at, 'queued'
                from transactions
                order by created_at, id
                limit 5
                """
            )
            cur.execute(
                load_query("claim_antifraud_batch.sql"),
                (3, "integration-test"),
            )
            claimed = [row[0] for row in cur.fetchall()]
            cur.execute(
                """
                select count(*)
                from antifraud_queue_demo
                where status = 'processing'
                  and worker_id = 'integration-test'
                  and claimed_at is not null
                """
            )
            processed = cur.fetchone()[0]

        self.assertEqual(len(claimed), 3)
        self.assertEqual(len(set(claimed)), 3)
        self.assertEqual(processed, 3)

    def test_transactions_reject_invalid_amounts(self):
        account_id = self._create_account()

        with self.assertRaisesRegex(CheckViolation, "transactions_amount_check"):
            self._insert_transaction(
                account_id,
                amount="0.00",
                direction="debit",
            )

    def test_accounts_reject_unknown_statuses(self):
        with (
            self.conn.cursor() as cur,
            self.assertRaisesRegex(CheckViolation, "accounts_status_check"),
        ):
            cur.execute(
                """
                insert into accounts (customer_name, opened_at, status)
                values ('Invalid Account', now(), 'unknown')
                """
            )

    def test_counterparty_names_are_unique(self):
        with self.conn.cursor() as cur:
            cur.execute("select name from counterparties order by id limit 1")
            existing_name = cur.fetchone()[0]

            with self.assertRaises(UniqueViolation):
                cur.execute(
                    "insert into counterparties (name) values (%s)",
                    (existing_name,),
                )

    def test_transactions_are_append_only(self):
        with self.conn.cursor() as cur:
            cur.execute("select id from transactions order by id limit 1")
            transaction_id = cur.fetchone()[0]

            with self.assertRaisesRegex(
                ObjectNotInPrerequisiteState,
                "append-only",
            ):
                cur.execute(
                    "update transactions set amount = amount where id = %s",
                    (transaction_id,),
                )

        self.conn.rollback()

        with (
            self.conn.cursor() as cur,
            self.assertRaisesRegex(
                ObjectNotInPrerequisiteState,
                "append-only",
            ),
        ):
            cur.execute(
                "delete from transactions where id = %s",
                (transaction_id,),
            )


if __name__ == "__main__":
    unittest.main()
