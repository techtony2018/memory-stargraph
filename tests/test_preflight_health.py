import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/automation/preflight.sh"


class PreflightHealthTests(unittest.TestCase):
    def run_preflight(self, routes):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            bin_dir = home / ".bun/bin"
            bin_dir.mkdir(parents=True)
            curl = bin_dir / "curl"
            curl.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    url="${!#}"
                    case "$url" in
                      http://direct.local/*) exit 7 ;;
                      http://authoritative.local/*)
                        [[ "${FAKE_AUTHORITATIVE_TRANSPORT_FAILURE:-0}" == "1" ]] && exit 7
                        code="${FAKE_AUTHORITATIVE_CODE:-200}"
                        ;;
                      http://corroboration.local/*)
                        [[ "${FAKE_CORROBORATION_TRANSPORT_FAILURE:-0}" == "1" ]] && exit 7
                        code="${FAKE_CORROBORATION_CODE:-200}"
                        ;;
                      *) exit 7 ;;
                    esac
                    if [[ "$*" == *'%{http_code}'* ]]; then
                      printf '%s' "$code"
                    else
                      printf '{"status":"ok"}'
                    fi
                    """
                )
            )
            curl.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "MEMORY_STARGRAPH_AUTOMATION_CONFIG": str(home / "missing.env"),
                    "MEMORY_STARGRAPH_LOCAL_URL": "http://direct.local",
                    "MEMORY_STARGRAPH_DASHBOARD_URL": "",
                    "MEMORY_STARGRAPH_REMOTE_HEALTH_URLS": "",
                    **routes,
                }
            )
            return subprocess.run(
                ["bash", str(PREFLIGHT)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            ).stdout

    def test_transport_failure_is_unverified_without_authoritative_route(self):
        output = self.run_preflight({})
        self.assertIn("health_state=unverified target=local_service", output)
        self.assertNotIn("health_state=unhealthy target=local_service", output)

    def test_authoritative_host_retry_can_verify_health(self):
        output = self.run_preflight(
            {
                "MEMORY_STARGRAPH_AUTHORITATIVE_LOCAL_HEALTH_URL":
                    "http://authoritative.local/api/health",
            }
        )
        self.assertIn(
            "health_state=healthy target=local_service source=authoritative_host",
            output,
        )

    def test_unhealthy_requires_authoritative_failure_and_corroboration(self):
        output = self.run_preflight(
            {
                "MEMORY_STARGRAPH_AUTHORITATIVE_LOCAL_HEALTH_URL":
                    "http://authoritative.local/api/health",
                "MEMORY_STARGRAPH_LOCAL_CORROBORATION_URL":
                    "http://corroboration.local/health",
                "FAKE_AUTHORITATIVE_CODE": "503",
                "FAKE_CORROBORATION_CODE": "503",
            }
        )
        self.assertIn(
            "health_state=unhealthy target=local_service "
            "source=authoritative_host corroboration=independent",
            output,
        )

    def test_two_transport_failures_remain_unverified(self):
        output = self.run_preflight(
            {
                "MEMORY_STARGRAPH_AUTHORITATIVE_LOCAL_HEALTH_URL":
                    "http://authoritative.local/api/health",
                "MEMORY_STARGRAPH_LOCAL_CORROBORATION_URL":
                    "http://corroboration.local/health",
                "FAKE_AUTHORITATIVE_TRANSPORT_FAILURE": "1",
                "FAKE_CORROBORATION_TRANSPORT_FAILURE": "1",
            }
        )
        self.assertIn(
            "health_state=unverified target=local_service "
            "reason=authoritative_or_corroboration_transport_unverified",
            output,
        )
        self.assertNotIn("health_state=unhealthy target=local_service", output)

    def test_transport_plus_http_failure_remains_unverified(self):
        output = self.run_preflight(
            {
                "MEMORY_STARGRAPH_AUTHORITATIVE_LOCAL_HEALTH_URL":
                    "http://authoritative.local/api/health",
                "MEMORY_STARGRAPH_LOCAL_CORROBORATION_URL":
                    "http://corroboration.local/health",
                "FAKE_AUTHORITATIVE_TRANSPORT_FAILURE": "1",
                "FAKE_CORROBORATION_CODE": "503",
            }
        )
        self.assertIn(
            "health_state=unverified target=local_service "
            "reason=authoritative_or_corroboration_transport_unverified",
            output,
        )
        self.assertNotIn("health_state=unhealthy target=local_service", output)


if __name__ == "__main__":
    unittest.main()
