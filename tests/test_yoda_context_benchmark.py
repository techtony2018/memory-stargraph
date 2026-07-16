import unittest

from scripts.automation import benchmark_yoda_context as benchmark


class YodaContextBenchmarkTests(unittest.TestCase):
    def test_default_matrix_has_ten_grounded_questions(self):
        self.assertGreaterEqual(len(benchmark.DEFAULT_CASES), 10)
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
        self.assertAlmostEqual(summary["improvement_percent"], 40.07, places=2)
        self.assertEqual(summary["warm_cache_hits"], 2)
        self.assertAlmostEqual(summary["mean_grounding_recall"], 0.8333, places=4)


if __name__ == "__main__":
    unittest.main()
