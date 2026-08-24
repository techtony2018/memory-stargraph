import unittest
from unittest import mock

from scripts.automation import benchmark_search
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

    def test_search_benchmark_prepares_product_like_read_path(self):
        store = mock.Mock()
        store.evidence_list_cache.wait_for_refresh.return_value = ()
        persistent = mock.Mock()
        persistent.status.return_value = {"ready": True, "busy": False}

        with mock.patch("scripts.automation.benchmark_search.server.PERSISTENT_GBRAIN_SEARCH", persistent):
            preparation = benchmark_search.prepare_benchmark_store(store, "persistent", timeout=1)

        store.prewarm_search_evidence.assert_called_once_with(timeout=1)
        self.assertEqual(
            store.evidence_list_cache.wait_for_refresh.call_count,
            len(benchmark_search.server.EVIDENCE_SEARCH_TYPES),
        )
        persistent.prewarm_async.assert_called_once_with(timeout=1)
        self.assertTrue(preparation["persistent_ready"])
        self.assertEqual(
            preparation["evidence_types_ready"],
            len(benchmark_search.server.EVIDENCE_SEARCH_TYPES),
        )


if __name__ == "__main__":
    unittest.main()
