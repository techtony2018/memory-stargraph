import tempfile
import unittest
from pathlib import Path

from scripts.automation import source_sync_preflight


class SourceSyncPreflightTests(unittest.TestCase):
    def make_checkout(self, *, files=(), dirty=False):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        git = root / ".git"
        git.mkdir()
        for relative in files:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# present\n")
        return temp, source_sync_preflight.CheckoutSnapshot(
            root=root,
            head="old",
            origin_main="new",
            dashboard_ui_version="V1.0.151",
            required_paths=("scripts/automation/yoda_gap_evaluator.py",),
            dirty=dirty,
            divergent=False,
        )

    def test_clean_stale_checkout_requires_fast_forward_sync(self):
        temp, snapshot = self.make_checkout()
        self.addCleanup(temp.cleanup)

        decision = source_sync_preflight.decide_source_sync(snapshot)

        self.assertEqual(decision.status, "stale_clean_fast_forward_required")
        self.assertEqual(decision.action, "fast_forward_sync")
        self.assertIn("scripts/automation/yoda_gap_evaluator.py", decision.missing_paths)

    def test_clean_current_checkout_uses_workspace_script(self):
        temp, snapshot = self.make_checkout(
            files=("scripts/automation/yoda_gap_evaluator.py",)
        )
        self.addCleanup(temp.cleanup)
        snapshot = snapshot._replace(head="new")

        decision = source_sync_preflight.decide_source_sync(snapshot)

        self.assertEqual(decision.status, "current")
        self.assertEqual(decision.action, "use_workspace")
        self.assertEqual(decision.script_path, "scripts/automation/yoda_gap_evaluator.py")

    def test_dirty_stale_checkout_records_blocker_and_preserves_user_changes(self):
        temp, snapshot = self.make_checkout(dirty=True)
        self.addCleanup(temp.cleanup)

        decision = source_sync_preflight.decide_source_sync(snapshot)

        self.assertEqual(decision.status, "stale_dirty_blocked")
        self.assertEqual(decision.action, "use_verified_service_copy")
        self.assertIn("preserve unrelated changes", decision.reason)

    def test_divergent_checkout_records_blocker_without_sync(self):
        temp, snapshot = self.make_checkout()
        self.addCleanup(temp.cleanup)
        snapshot = snapshot._replace(divergent=True)

        decision = source_sync_preflight.decide_source_sync(snapshot)

        self.assertEqual(decision.status, "divergent_blocked")
        self.assertEqual(decision.action, "use_verified_service_copy")


if __name__ == "__main__":
    unittest.main()
