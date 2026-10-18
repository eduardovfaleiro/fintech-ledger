import unittest

from benchmarks.benchmark_scale import maximum_copy_number


class ScaleBenchmarkTest(unittest.TestCase):
    def test_maximum_copy_number_covers_exact_and_partial_copies(self):
        cases = (
            (1_000_000, 10_000_000, 0),
            (10_000_000, 10_000_000, 0),
            (50_000_000, 10_000_000, 4),
            (25_000, 10_000, 2),
        )

        for target_rows, source_rows, expected in cases:
            with self.subTest(target_rows=target_rows, source_rows=source_rows):
                self.assertEqual(
                    maximum_copy_number(target_rows, source_rows),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
