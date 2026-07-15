from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AutomationContractTests(unittest.TestCase):
    def test_cdp_probe_reuses_matching_tab_and_only_closes_created_tab(self):
        probe = (ROOT / "scripts" / "automation" / "cdp_probe.mjs").read_text()
        self.assertIn("context.pages()", probe)
        self.assertIn("targetOrigin", probe)
        self.assertIn("createdPage", probe)
        self.assertIn("if (createdPage)", probe)
        self.assertNotIn("finally {\n  await page.close().catch", probe)

    def test_slug_link_and_browser_hygiene_contract_is_tracked(self):
        canonical = "http://127.0.0.1:8788/?slug=<URL-encoded-slug>"
        self.assertIn(canonical, (ROOT / "AGENTS.md").read_text())
        self.assertIn(canonical, (ROOT / "docs" / "automation-runbook.md").read_text())
        prompt = (ROOT / "automations" / "memory-stargraph-wish-to-reallity" / "prompt.md").read_text()
        self.assertIn("reuse", prompt.lower())
        self.assertIn("Markdown link", prompt)
        self.assertIn("in-app browser", prompt)
        self.assertIn("fall back to Chrome CDP", prompt)
        self.assertIn("Do not skip visual verification", prompt)

    def test_wish_worker_compacts_completed_todos_before_and_after_run(self):
        prompt = (ROOT / "automations" / "memory-stargraph-wish-to-reallity" / "prompt.md").read_text()
        runbook = (ROOT / "docs" / "automation-runbook.md").read_text()
        command = "python3 scripts/automation/compact_sg_todo_backlog.py --apply --json"

        self.assertGreaterEqual(prompt.count(command), 2)
        self.assertIn("full batch of 50 completed TODO rows", prompt)
        self.assertIn("TODO compaction/archive result", prompt)
        self.assertIn(command, runbook)
        self.assertIn("completed-archive-0001", runbook)
        self.assertIn("0-49 completed rows", runbook)

    def test_wish_worker_lands_pushed_work_on_main(self):
        prompt = (ROOT / "automations" / "memory-stargraph-wish-to-reallity" / "prompt.md").read_text()

        self.assertIn("Push the work branch to origin", prompt)
        self.assertIn("merge the pushed work into `main`", prompt)
        self.assertIn("push `main` to origin", prompt)
        self.assertIn("`main` merge/push result", prompt)


if __name__ == "__main__":
    unittest.main()
