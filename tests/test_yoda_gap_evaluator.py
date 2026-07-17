import json
import tempfile
import unittest
from pathlib import Path

from scripts.automation import yoda_gap_evaluator


class YodaGapEvaluatorTests(unittest.TestCase):
    def test_default_suite_has_at_least_ten_daily_learning_questions(self):
        suite = yoda_gap_evaluator.default_question_suite()

        self.assertGreaterEqual(len(suite), 10)
        joined = "\n".join(f"{item['slug']} {item['question']} {item['intent']}" for item in suite)
        for phrase in (
            "daily dev",
            "monitoring",
            "TODO",
            "logs",
            "gap",
            "Ask Yoda",
        ):
            self.assertIn(phrase, joined)
        self.assertEqual(len({item["id"] for item in suite}), len(suite))

    def test_run_suite_posts_synthetic_yoda_requests_with_stable_pair_ids(self):
        suite = yoda_gap_evaluator.default_question_suite()[:10]
        calls = []

        def fake_post(slug, payload):
            calls.append((slug, payload))
            return {
                "ok": True,
                "request_id": f"req-{payload['pair_id'].rsplit(':', 1)[-1]}",
                "output": f"Yoda answer for {payload['question']}",
                "diagnostics": {"model_status": "ok"},
            }

        result = yoda_gap_evaluator.run_suite(
            suite,
            post_yoda=fake_post,
            run_id="20260717t120000-0700",
            depth=5,
        )

        self.assertEqual(len(result["questions"]), 10)
        self.assertEqual(len(calls), 10)
        for index, (slug, payload) in enumerate(calls, start=1):
            self.assertEqual(slug, suite[index - 1]["slug"])
            self.assertEqual(payload["environment"], "test")
            self.assertIs(payload["synthetic"], True)
            self.assertIs(payload["test_run"], True)
            self.assertEqual(payload["depth"], 5)
            self.assertEqual(payload["pair_id"], f"yoda-evaluator:20260717t120000-0700:{suite[index - 1]['id']}")
        self.assertEqual(result["metadata"]["question_count"], 10)

    def test_comparison_report_promotes_only_bounded_gap_candidates(self):
        snapshot = {
            "metadata": {"run_id": "run-1"},
            "questions": [
                {
                    "id": "q1",
                    "slug": "products/memory-stargraph",
                    "question": "What gap blocks product readiness?",
                    "intent": "product gap",
                    "yoda_answer": "Everything is fine.",
                    "codex_answer": "The answer misses restore rehearsal evidence and daily logs.",
                    "gap": {
                        "decision": "todo_candidate",
                        "title": "Add restore rehearsal evidence to Ask Yoda context",
                        "severity": "P1",
                        "summary": "Yoda missed a concrete reliability gap visible in daily SRE logs.",
                        "evidence": ["SRE logs mention no restore rehearsal", "Yoda omitted it"],
                    },
                },
                {
                    "id": "q2",
                    "slug": "notes/memory-starmap-todo-list",
                    "question": "Which TODO matters?",
                    "intent": "todo prioritization",
                    "yoda_answer": "SG-0143 matters.",
                    "codex_answer": "SG-0143 matters.",
                    "gap": {"decision": "no_action", "summary": "Answers agree."},
                },
            ],
        }

        report = yoda_gap_evaluator.build_comparison_report(snapshot)

        self.assertEqual(report["metadata"]["run_id"], "run-1")
        self.assertEqual(report["metadata"]["candidate_count"], 1)
        candidate = report["todo_candidates"][0]
        self.assertEqual(candidate["title"], "Add restore rehearsal evidence to Ask Yoda context")
        self.assertEqual(candidate["priority"], "P1")
        self.assertIn("Yoda missed", candidate["evidence_summary"])

    def test_cli_run_writes_snapshot(self):
        suite_path = None
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "snapshot.json"

            def fake_post(slug, payload):
                return {"ok": True, "request_id": payload["pair_id"], "output": "answer"}

            snapshot = yoda_gap_evaluator.run_suite(
                yoda_gap_evaluator.default_question_suite()[:10],
                post_yoda=fake_post,
                run_id="cli-test",
                output_path=output,
            )

            self.assertTrue(output.exists())
            saved = json.loads(output.read_text())
            self.assertEqual(saved["metadata"]["run_id"], "cli-test")
            self.assertEqual(len(saved["questions"]), len(snapshot["questions"]))
            self.assertIsNone(suite_path)


if __name__ == "__main__":
    unittest.main()
