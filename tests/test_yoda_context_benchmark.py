import unittest
from unittest import mock

from scripts.automation import benchmark_yoda_context as benchmark


class YodaContextBenchmarkTests(unittest.TestCase):
    def test_default_matrix_has_ten_grounded_questions(self):
        self.assertGreaterEqual(len(benchmark.DEFAULT_CASES), 10)
        self.assertGreaterEqual(
            len({(case["slug"], case["depth"]) for case in benchmark.DEFAULT_CASES}),
            2,
        )
        self.assertTrue(any(case.get("force_slow_graph") for case in benchmark.DEFAULT_CASES))
        self.assertTrue(any(case.get("expire_cache_before_cold") for case in benchmark.DEFAULT_CASES))
        for case in benchmark.DEFAULT_CASES:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["slug"])
                self.assertTrue(case["cold_question"])
                self.assertTrue(case["warm_question"])
                self.assertGreaterEqual(len(case["expected_targets"]), 1)

    def test_grounding_recall_counts_expected_targets_without_exposing_prompt(self):
        result = benchmark.grounding_result(
            "Selected node: people/tony-guan\n## products/memory-stargraph",
            ["people/tony-guan", "products/memory-stargraph"],
        )

        self.assertEqual(result, {"expected": 2, "matched": 2, "recall": 1.0})

    def test_summary_reports_median_improvement_and_cache_coverage(self):
        summary = benchmark.summarize_results(
            [
                {"cold_prompt_ms": 10000, "warm_cache_hit": True, "grounding": {"recall": 1.0}},
                {"cold_prompt_ms": 20000, "warm_cache_hit": True, "grounding": {"recall": 0.5}},
                {"cold_prompt_ms": 30000, "warm_cache_hit": False, "grounding": {"recall": 1.0}},
            ],
            baseline_ms=33375,
        )

        self.assertEqual(summary["median_cold_prompt_ms"], 20000)
        self.assertEqual(summary["p95_cold_prompt_ms"], 30000)
        self.assertAlmostEqual(summary["improvement_percent"], 40.07, places=2)
        self.assertEqual(summary["warm_cache_hits"], 2)
        self.assertAlmostEqual(summary["mean_grounding_recall"], 0.8333, places=4)

    def test_health_probe_failure_is_reported_without_losing_benchmark_results(self):
        with mock.patch.object(benchmark.urllib.request, "urlopen", side_effect=ConnectionResetError):
            health = benchmark.read_health("http://127.0.0.1:8788")

        self.assertEqual(health, {"ok": False, "error": "ConnectionResetError"})

    def test_forced_slow_graph_case_is_optional_timeout_but_grounded(self):
        case = {
            "id": "forced-slow",
            "slug": "people/tony-guan",
            "depth": 4,
            "cold_question": "What should Tony know?",
            "warm_question": "What changed?",
            "expected_targets": ["people/tony-guan"],
            "force_slow_graph": True,
        }

        def gbrain_result(tool_name, payload=None, timeout=30):
            del timeout
            if tool_name == "get_page":
                return {"content": "# Tony Guan"}
            if tool_name in {"get_backlinks", "query", "search", "list_pages"}:
                return []
            if tool_name == "get_tags":
                return []
            raise AssertionError((tool_name, payload))

        with mock.patch.object(
            benchmark.server, "yoda_gbrain_call_tool", side_effect=gbrain_result
        ):
            result = benchmark.run_case(case, store=benchmark.server.GraphStore())

        self.assertFalse(result["cold_context_degraded"])
        self.assertEqual(result["cold_degraded_reason"], "")
        self.assertEqual(result["cold_broad_graph_status"], "optional_timeout")
        self.assertEqual(result["cold_broad_graph_unavailable_reason"], "broad_graph_timeout")
        self.assertEqual(result["grounding"]["recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
