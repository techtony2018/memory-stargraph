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


if __name__ == "__main__":
    unittest.main()
