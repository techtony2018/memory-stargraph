import unittest

from scripts.automation.benchmark_search_transport import percentile, timing_summary


class SearchTransportBenchmarkTests(unittest.TestCase):
    def test_percentile_and_timing_summary_are_deterministic(self):
        rows = [
            {"elapsed": 100},
            {"elapsed": 200},
            {"elapsed": 300},
            {"elapsed": 400},
        ]

        self.assertEqual(percentile([400, 100, 300, 200], 0.95), 400)
        self.assertEqual(
            timing_summary(rows, "elapsed"),
            {"median_ms": 250, "p95_ms": 400, "mean_ms": 250},
        )


if __name__ == "__main__":
    unittest.main()
