from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AutomationContractTests(unittest.TestCase):
    def test_every_worker_uses_dst_aware_pacific_reporting(self):
        workers = (
            "gbrain-x-intelligence-capture",
            "memory-stargraph-daily-learning-intake",
            "memory-stargraph-wish-to-reallity",
            "memory-stargraph-divergent-product-discovery",
            "memory-stargraph-goal-steward-daily-review",
            "memory-stargraph-capture-link-drain",
        )
        required = (
            "America/Los_Angeles",
            "timezone-aware ISO 8601",
            "PDT in summer",
            "PST in winter",
            "Do not use a fixed UTC-8 offset",
        )
        for worker in workers:
            prompt = (ROOT / "automations" / worker / "prompt.md").read_text()
            for phrase in required:
                self.assertIn(phrase, prompt, f"{worker} missing {phrase}")

    def test_capture_worker_is_persistent_midnight_and_manually_triggerable(self):
        definition = tomllib.loads(
            (
                ROOT
                / "automations/memory-stargraph-capture-link-drain/automation.toml"
            ).read_text()
        )
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()
        self.assertEqual(definition["id"], "memory-stargraph-capture-link-drain")
        self.assertEqual(
            definition["rrule"], "FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0"
        )
        self.assertEqual(definition["timezone"], "America/Los_Angeles")
        self.assertEqual(definition["destination"], "thread")
        self.assertIn("{{CAPTURE_LINK_THREAD_ID}}", definition["target_thread_id"])
        self.assertIn("manual", prompt.lower())
        self.assertIn("there is no fixed cutoff", prompt.lower())

    def test_capture_worker_freezes_and_drains_every_selected_item(self):
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()
        self.assertIn("first authoritative snapshot", prompt)
        self.assertIn("planned` to `capturing", prompt)
        self.assertIn("every frozen item", prompt)
        self.assertIn("completed` or `failed", prompt)
        self.assertIn("created after the frozen snapshot", prompt)

    def test_capture_worker_routes_to_most_specific_local_skill_and_reuses_media(self):
        prompt = (
            ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md"
        ).read_text()
        self.assertIn("~/.codex/skills/<skill>/SKILL.md", prompt)
        self.assertIn("~/.openclaw/skills/<skill>/SKILL.md", prompt)
        self.assertIn("gbrain-capture-link", prompt)
        self.assertIn("gbrain-pdf-capture", prompt)
        self.assertIn("gb-capture-linkedin", prompt)
        self.assertIn("must not upload or copy the bytes again", prompt)

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
