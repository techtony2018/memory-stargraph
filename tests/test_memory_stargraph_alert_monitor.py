import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
import shutil


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/automation/memory_stargraph_alert_monitor.py"


class MemoryStargraphAlertMonitorTests(unittest.TestCase):
    def make_fake_curl(self, bin_dir: Path, *, cached=False, fail_health=False, omit_source=False):
        curl = bin_dir / "curl"
        source_mode = "cache" if cached else "gbrain"
        source_status = "cached" if cached else "lazy-root"
        curl.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                url="${{@: -1}}"
                if [[ "$url" == *"/api/health" ]]; then
                  if [[ "{'1' if fail_health else '0'}" == "1" ]]; then
                    printf 'unavailable\\n503'
                    exit 0
                  fi
                  if [[ "{'1' if omit_source else '0'}" == "1" ]]; then
                    printf '{{"ok":true,"ui_version":"V1.0.test"}}\\n200'
                  else
                    printf '{{"ok":true,"ui_version":"V1.0.test","source":{{"mode":"{source_mode}","status":"{source_status}","updated_at":"2026-07-22T16:00:00Z"}}}}\\n200'
                  fi
                  exit 0
                fi
                if [[ "$url" == *"/api/entity-raw/index" ]]; then
                  printf '{{"slug":"index","content":"# Index"}}\\n200'
                  exit 0
                fi
                exit 7
                """
            )
        )
        curl.chmod(0o755)

    def run_monitor(self, home: Path, *, dry_run=True, extra_env=None, extra_args=None, script: Path = SCRIPT):
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "CODEX_HOME": str(home / ".codex"),
                "PATH": f"{home / 'bin'}:{env.get('PATH', '')}",
                "MEMORY_STARGRAPH_AUTOMATION_CONFIG": str(home / "missing.env"),
                "MEMORY_STARGRAPH_MONITOR_TARGETS": "local=http://local.test:8788 remote_a=http://remote-a.test:8788 remote_b=http://remote-b.test:8788",
                "MEMORY_STARGRAPH_ALERT_EMAIL_TO": "tony@example.test",
            }
        )
        if extra_env:
            env.update(extra_env)
        args = [
            sys.executable,
            str(script),
            "once",
            "--json",
            "--failure-threshold",
            "1",
        ]
        if dry_run:
            args.append("--dry-run")
        if extra_args:
            args.extend(extra_args)
        return subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, check=False)

    def test_cached_gbrain_source_is_alertable_problem(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            bin_dir = home / "bin"
            bin_dir.mkdir()
            self.make_fake_curl(bin_dir, cached=True)

            result = self.run_monitor(home)

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["target_count"], 3)
            self.assertEqual(payload["persistent_failing_count"], 3)
            self.assertEqual(payload["email_status"], "dry_run")
            self.assertIn("GBrain source mode is cache", payload["targets"][0]["issues"])
            self.assertIn("GBrain source status is cached", payload["targets"][0]["issues"])

    def test_suppression_prevents_email_but_records_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            bin_dir = home / "bin"
            bin_dir.mkdir()
            self.make_fake_curl(bin_dir, cached=True)
            suppress_file = home / ".codex/state/memory-stargraph-alert-suppression.json"
            suppress_file.parent.mkdir(parents=True)
            suppress_file.write_text(
                json.dumps(
                    {
                        "suppress_until": "2099-01-01T00:00:00-07:00",
                        "reason": "normal deploy",
                    }
                )
            )

            result = self.run_monitor(home)

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["suppressed"])
            self.assertEqual(payload["email_status"], "not_needed")

    def test_repeated_identical_issue_is_not_emailed_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            bin_dir = home / "bin"
            bin_dir.mkdir()
            self.make_fake_curl(bin_dir, cached=True)

            first = self.run_monitor(home)
            second = self.run_monitor(home)

            self.assertEqual(first.returncode, 2, first.stderr)
            self.assertEqual(second.returncode, 2, second.stderr)
            self.assertEqual(json.loads(first.stdout)["email_status"], "dry_run")
            self.assertEqual(json.loads(second.stdout)["email_status"], "not_needed")

    def test_healthy_targets_return_ok(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            bin_dir = home / "bin"
            bin_dir.mkdir()
            self.make_fake_curl(bin_dir, cached=False)

            result = self.run_monitor(home)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["failing_count"], 0)
            self.assertEqual(payload["email_status"], "not_needed")

    def test_missing_health_source_is_ok_when_index_readback_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            bin_dir = home / "bin"
            bin_dir.mkdir()
            self.make_fake_curl(bin_dir, omit_source=True)

            result = self.run_monitor(home)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(
                payload["targets"][0]["health_source_details"],
                "missing_but_index_readback_verified",
            )

    def test_failover_hook_runs_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            bin_dir = home / "bin"
            bin_dir.mkdir()
            self.make_fake_curl(bin_dir, cached=True)
            isolated_dir = home / "monitor"
            isolated_dir.mkdir()
            monitor_copy = isolated_dir / "memory_stargraph_alert_monitor.py"
            failover_copy = isolated_dir / "memory_stargraph_failover.py"
            shutil.copy2(SCRIPT, monitor_copy)
            shutil.copy2(ROOT / "scripts/automation/memory_stargraph_failover.py", failover_copy)

            result = self.run_monitor(
                home,
                script=monitor_copy,
                extra_env={
                    "MEMORY_STARGRAPH_FAILOVER_ON_ALERT": "1",
                    "MEMORY_STARGRAPH_MASTER_URL": "http://master.test",
                    "MEMORY_STARGRAPH_SLAVE_URL": "http://slave.test",
                    "MEMORY_STARGRAPH_SLAVE_RESTORE_COMMAND": "true",
                    "MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND": "true",
                    "MEMORY_STARGRAPH_FLEET_CHECK_URLS": "http://slave.test",
                },
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["failover_result"]["enabled"])
            self.assertNotEqual(payload["failover_result"]["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
