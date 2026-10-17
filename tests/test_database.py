import unittest

from db_connection import get_connection


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
            cls.account_id = cur.fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

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

            cur.execute(
                """
                select id
                from transactions
                where account_id = %s
                order by created_at desc, id desc
                offset 10 limit 10
                """,
                (self.account_id,),
            )
            offset_ids = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                select id
                from transactions
                where account_id = %s
                  and (created_at, id) < (%s, %s)
                order by created_at desc, id desc
                limit 10
                """,
                (self.account_id, *cursor),
            )
            keyset_ids = [row[0] for row in cur.fetchall()]

        self.assertEqual(offset_ids, keyset_ids)

    def test_join_returns_the_same_statement_as_individual_queries(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                select id, counterparty_id
                from transactions
                where account_id = %s
                order by created_at desc, id desc
                limit 20
                """,
                (self.account_id,),
            )
            transactions = cur.fetchall()

            individual_rows = []
            for transaction_id, counterparty_id in transactions:
                cur.execute(
                    "select name from counterparties where id = %s",
                    (counterparty_id,),
                )
                individual_rows.append((transaction_id, cur.fetchone()[0]))

            cur.execute(
                """
                select t.id, c.name
                from transactions t
                join counterparties c on c.id = t.counterparty_id
                where t.account_id = %s
                order by t.created_at desc, t.id desc
                limit 20
                """,
                (self.account_id,),
            )
            join_rows = cur.fetchall()

        self.assertEqual(individual_rows, join_rows)


if __name__ == "__main__":
    unittest.main()
