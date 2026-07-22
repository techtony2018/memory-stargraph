import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/automation/memory_stargraph_failover.py"


class MemoryStargraphFailoverTests(unittest.TestCase):
    def make_fake_curl(self, bin_dir: Path, *, master_healthy: bool, slave_healthy: bool):
        curl = bin_dir / "curl"
        curl.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                url="${{@: -1}}"
                if [[ "$url" == http://master.test* ]]; then
                  healthy={'1' if master_healthy else '0'}
                elif [[ "$url" == http://slave.test* ]]; then
                  healthy={'1' if slave_healthy else '0'}
                else
                  healthy=1
                fi
                if [[ "$url" == *"/api/health" ]]; then
                  if [[ "$healthy" == "1" ]]; then
                    printf '{{"ok":true,"ui_version":"V1.0.test","source":{{"mode":"gbrain","status":"lazy-root"}}}}\\n200'
                  else
                    printf 'down\\n503'
                  fi
                  exit 0
                fi
                if [[ "$url" == *"/api/entity-raw/index" ]]; then
                  if [[ "$healthy" == "1" ]]; then
                    printf '{{"slug":"index","content":"# Index"}}\\n200'
                  else
                    printf 'down\\n503'
                  fi
                  exit 0
                fi
                exit 7
                """
            )
        )
        curl.chmod(0o755)

    def base_env(self, home: Path):
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "CODEX_HOME": str(home / ".codex"),
                "PATH": f"{home / 'bin'}:{env.get('PATH', '')}",
                "MEMORY_STARGRAPH_AUTOMATION_CONFIG": str(home / "missing.env"),
                "MEMORY_STARGRAPH_MASTER_URL": "http://master.test",
                "MEMORY_STARGRAPH_SLAVE_URL": "http://slave.test",
                "MEMORY_STARGRAPH_SLAVE_RESTORE_COMMAND": "true",
                "MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND": "true",
                "MEMORY_STARGRAPH_FLEET_CHECK_URLS": "http://slave.test",
            }
        )
        return env

    def test_restore_marks_slave_ready_after_verified_probe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            (home / "bin").mkdir()
            self.make_fake_curl(home / "bin", master_healthy=True, slave_healthy=True)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "restore-slave", "--json"],
                cwd=ROOT,
                env=self.base_env(home),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            state = json.loads((home / ".codex/state/memory-stargraph-failover.json").read_text())
            self.assertTrue(state["slave_ready"])

    def test_promote_refuses_when_master_is_healthy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            (home / "bin").mkdir()
            self.make_fake_curl(home / "bin", master_healthy=True, slave_healthy=True)
            state_path = home / ".codex/state/memory-stargraph-failover.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text('{"slave_ready": true, "slave_restored_at": "2099-01-01T00:00:00-07:00"}')
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "promote-slave", "--json"],
                cwd=ROOT,
                env=self.base_env(home),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("master still healthy", payload["blockers"][0])

    def test_promote_succeeds_when_master_down_and_slave_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            (home / "bin").mkdir()
            self.make_fake_curl(home / "bin", master_healthy=False, slave_healthy=True)
            state_path = home / ".codex/state/memory-stargraph-failover.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text('{"slave_ready": true, "slave_restored_at": "2099-01-01T00:00:00-07:00"}')
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "promote-slave", "--json"],
                cwd=ROOT,
                env=self.base_env(home),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            state = json.loads(state_path.read_text())
            self.assertEqual(state["active_authoritative_role"], "slave")


if __name__ == "__main__":
    unittest.main()
