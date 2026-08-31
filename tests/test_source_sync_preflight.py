import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

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
            dirty_paths=("server.py",) if dirty else (),
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
        self.assertEqual(decision.action, "defer_preserve_local_changes")
        self.assertIn("preserve unrelated changes", decision.reason)
        self.assertEqual(decision.dirty_paths, ("server.py",))

    def test_dirty_current_checkout_blocks_before_current_decision(self):
        temp, snapshot = self.make_checkout(
            files=("scripts/automation/yoda_gap_evaluator.py",), dirty=True
        )
        self.addCleanup(temp.cleanup)
        snapshot = snapshot._replace(head="new")

        decision = source_sync_preflight.decide_source_sync(snapshot)

        self.assertEqual(decision.status, "dirty_worktree_blocked")
        self.assertEqual(decision.action, "defer_preserve_local_changes")
        self.assertTrue(decision.dirty_worktree)

    def test_untracked_artifacts_are_reported_without_blocking_current_checkout(self):
        temp, snapshot = self.make_checkout(
            files=("scripts/automation/yoda_gap_evaluator.py",)
        )
        self.addCleanup(temp.cleanup)
        snapshot = snapshot._replace(
            head="new",
            untracked_paths=("config/tailscale-certs/local.crt", "var/runtime.json"),
        )

        decision = source_sync_preflight.decide_source_sync(snapshot)

        self.assertEqual(decision.status, "current")
        self.assertFalse(decision.dirty_worktree)
        self.assertEqual(decision.untracked_paths, snapshot.untracked_paths)

    def test_porcelain_parser_separates_tracked_and_untracked_paths(self):
        dirty, untracked = source_sync_preflight.parse_porcelain_status(
            " M server.py\nA  tests/new.py\n?? config/tailscale-certs/local.crt\n"
        )

        self.assertEqual(dirty, ("server.py", "tests/new.py"))
        self.assertEqual(untracked, ("config/tailscale-certs/local.crt",))

    def test_run_git_preserves_porcelain_leading_status_column(self):
        completed = mock.Mock(returncode=0, stdout=" M server.py\n", stderr="")
        with mock.patch.object(source_sync_preflight.subprocess, "run", return_value=completed):
            output = source_sync_preflight.run_git(Path("."), "status", "--porcelain")

        self.assertEqual(output, " M server.py")

    def test_json_payload_exposes_machine_readable_dirty_evidence(self):
        temp, snapshot = self.make_checkout(
            files=("scripts/automation/yoda_gap_evaluator.py",), dirty=True
        )
        self.addCleanup(temp.cleanup)
        snapshot = snapshot._replace(head="new")
        output = StringIO()

        with mock.patch.object(source_sync_preflight, "snapshot_checkout", return_value=snapshot), redirect_stdout(output):
            exit_code = source_sync_preflight.main(["--root", temp.name, "--json"])

        self.assertEqual(exit_code, 1)
        payload = __import__("json").loads(output.getvalue())
        self.assertTrue(payload["dirty_worktree"])
        self.assertEqual(payload["dirty_state"], "tracked_changes")
        self.assertEqual(payload["dirty_paths"], ["server.py"])

    def test_divergent_checkout_records_blocker_without_sync(self):
        temp, snapshot = self.make_checkout()
        self.addCleanup(temp.cleanup)
        snapshot = snapshot._replace(divergent=True)

        decision = source_sync_preflight.decide_source_sync(snapshot)

        self.assertEqual(decision.status, "divergent_blocked")
        self.assertEqual(decision.action, "use_verified_service_copy")


if __name__ == "__main__":
    unittest.main()
