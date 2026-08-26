from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.automation.compact_sg_todo_backlog import (
    ARCHIVE_SIZE,
    TODO_COLUMNS,
    gbrain_get,
    gbrain_link,
    gbrain_put,
    parse_todo_rows,
    plan_compaction,
    render_todo_table,
    render_failed_collection,
    worker_api_get,
    worker_api_post_json,
    worker_api_route,
)


def make_row(item_id, status):
    return {
        "id": item_id,
        "status": status,
        "priority": "P2",
        "title": f"Title {item_id}",
        "node": f"[[notes/memory-starmap-todo-list/{item_id.lower()}]]",
        "updated": "2026-07-15",
        "notes": f"Notes {item_id}",
    }


class TodoBacklogCompactionTests(unittest.TestCase):
    def test_todo_columns_remains_a_public_list(self):
        self.assertIsInstance(TODO_COLUMNS, list)

    def test_compactor_remains_directly_invocable(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/automation/compact_sg_todo_backlog.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Compact Memory Stargraph completed TODO rows", result.stdout)

    def test_plan_archives_only_full_completed_batches_and_keeps_active_light(self):
        rows = [make_row("SG-0123", "planned"), make_row("SG-0124", "failed")]
        rows.extend(make_row(f"SG-{index:04d}", "completed") for index in range(1, 127))

        plan = plan_compaction(rows, existing_archives={})

        self.assertEqual(ARCHIVE_SIZE, 50)
        self.assertEqual([archive["slug"] for archive in plan.archives_to_create], [
            "notes/memory-starmap-todo-list/completed-archive-0001",
            "notes/memory-starmap-todo-list/completed-archive-0002",
        ])
        self.assertEqual(len(plan.archives_to_create[0]["rows"]), 50)
        self.assertEqual(plan.archives_to_create[0]["rows"][0]["id"], "SG-0001")
        self.assertEqual(plan.archives_to_create[1]["rows"][-1]["id"], "SG-0100")
        self.assertEqual([row["id"] for row in plan.active_rows[:2]], ["SG-0123", "SG-0124"])
        self.assertEqual(plan.active_rows[2]["id"], "SG-0101")
        self.assertEqual(plan.active_rows[-1]["id"], "SG-0126")
        self.assertLessEqual(
            sum(1 for row in plan.active_rows if row["status"] == "completed"),
            ARCHIVE_SIZE - 1,
        )

    def test_existing_archives_are_not_recreated_but_their_rows_leave_active_root(self):
        rows = [make_row("SG-0123", "planned")]
        rows.extend(make_row(f"SG-{index:04d}", "completed") for index in range(1, 126))
        existing = {
            "notes/memory-starmap-todo-list/completed-archive-0001": [
                make_row(f"SG-{index:04d}", "completed") for index in range(1, 51)
            ]
        }

        plan = plan_compaction(rows, existing_archives=existing)

        self.assertEqual([archive["slug"] for archive in plan.archives_to_create], [
            "notes/memory-starmap-todo-list/completed-archive-0002"
        ])
        self.assertNotIn("SG-0001", [row["id"] for row in plan.active_rows])
        self.assertEqual(plan.active_rows[0]["id"], "SG-0123")
        self.assertEqual(plan.active_rows[1]["id"], "SG-0101")

    def test_todo_table_round_trips_pipe_escaped_rows(self):
        rows = [
            {
                **make_row("SG-0001", "completed"),
                "title": "Fix A | B",
                "notes": "Completed with A | B evidence",
            }
        ]

        parsed = parse_todo_rows(render_todo_table(rows))

        self.assertEqual(parsed[0]["title"], "Fix A | B")
        self.assertEqual(parsed[0]["notes"], "Completed with A | B evidence")

    def test_failed_collection_can_preserve_immutable_capture_time_on_refresh(self):
        rendered = render_failed_collection(
            [make_row("SG-0166", "failed")],
            captured_at="2026-08-26T10:43:05+00:00",
        )

        self.assertIn("captured_at: '2026-08-26T10:43:05+00:00'", rendered)

    def test_gbrain_operations_use_configured_tls_route_and_flags(self):
        calls = []

        def fake_run(cmd, input=None, text=None, capture_output=None, timeout=None, check=None):
            calls.append((cmd, input))
            if cmd[0] == "gbrain":
                return subprocess.CompletedProcess(cmd, 1, "", "mcp unavailable")
            if cmd[0] == "curl" and "entity-raw" in " ".join(cmd):
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    '{"slug":"notes/memory-starmap-todo-list","content":"# Todo\\n"}',
                    "",
                )
            if cmd[0] == "curl" and "-X" in cmd:
                return subprocess.CompletedProcess(cmd, 0, '{"ok":true}', "")
            raise AssertionError(cmd)

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "deployment-targets.env"
            config.write_text(
                "MEMORY_STARGRAPH_DASHBOARD_URL='https://dashboard.example.test'\n"
                "MEMORY_STARGRAPH_DASHBOARD_CURL_FLAGS='-k --connect-timeout 5'\n"
                "MEMORY_STARGRAPH_LOCAL_URL='http://127.0.0.1:8788'\n",
                encoding="utf-8",
            )
            with (
                mock.patch.dict(
                    "os.environ",
                    {
                        "MEMORY_STARGRAPH_AUTOMATION_CONFIG": str(config),
                        "MEMORY_STARGRAPH_WORKER_API_URL": "",
                        "MEMORY_STARGRAPH_WORKER_API_CURL_FLAGS": "",
                    },
                    clear=False,
                ),
                mock.patch("scripts.automation.compact_sg_todo_backlog.subprocess.run", side_effect=fake_run),
            ):
                self.assertEqual(gbrain_get("notes/memory-starmap-todo-list"), "# Todo\n")
                gbrain_put("notes/memory-starmap-todo-list", "# Todo\n")
                self.assertTrue(gbrain_link("notes/root", "notes/child", "has_todo"))

        flattened = [" ".join(command) for command, _ in calls]
        curl_calls = [command for command, _ in calls if command[0] == "curl"]
        self.assertTrue(curl_calls)
        self.assertTrue(all("-k" in command for command in curl_calls))
        self.assertTrue(all("--connect-timeout" in command for command in curl_calls))
        self.assertTrue(all("https://dashboard.example.test" in " ".join(command) for command in curl_calls))
        self.assertTrue(any("/api/entity-raw/notes%2Fmemory-starmap-todo-list" in call for call in flattened))
        self.assertTrue(any("/api/entity-save/notes%2Fmemory-starmap-todo-list" in call for call in flattened))
        self.assertTrue(any("/api/entity-link/notes%2Froot" in call for call in flattened))

    def test_worker_route_honors_explicit_environment_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "deployment-targets.env"
            config.write_text(
                "MEMORY_STARGRAPH_DASHBOARD_URL='https://configured.example.test'\n"
                "MEMORY_STARGRAPH_DASHBOARD_CURL_FLAGS='-k'\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                "os.environ",
                {
                    "MEMORY_STARGRAPH_AUTOMATION_CONFIG": str(config),
                    "MEMORY_STARGRAPH_WORKER_API_URL": "https://explicit.example.test/",
                    "MEMORY_STARGRAPH_WORKER_API_CURL_FLAGS": "--cacert /tmp/public-test-ca.pem",
                },
                clear=False,
            ):
                route = worker_api_route()

        self.assertEqual(route.base_url, "https://explicit.example.test")
        self.assertEqual(route.curl_flags, ("--cacert", "/tmp/public-test-ca.pem"))
        self.assertEqual(route.source, "MEMORY_STARGRAPH_WORKER_API_URL")

    def test_configured_tls_route_wins_over_plaintext_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "deployment-targets.env"
            config.write_text(
                "MEMORY_STARGRAPH_DASHBOARD_URL='https://dashboard.example.test'\n"
                "MEMORY_STARGRAPH_DASHBOARD_CURL_FLAGS='-k'\n"
                "MEMORY_STARGRAPH_LOCAL_URL='http://127.0.0.1:8788'\n",
                encoding="utf-8",
            )
            with (
                mock.patch.dict(
                    "os.environ",
                    {"MEMORY_STARGRAPH_AUTOMATION_CONFIG": str(config)},
                    clear=False,
                ),
                mock.patch.dict(
                    "os.environ",
                    {
                        "MEMORY_STARGRAPH_WORKER_API_URL": "",
                        "MEMORY_STARGRAPH_WORKER_API_CURL_FLAGS": "",
                    },
                    clear=False,
                ),
            ):
                route = worker_api_route()

        self.assertEqual(route.base_url, "https://dashboard.example.test")
        self.assertEqual(route.curl_flags, ("-k",))

    def test_save_fails_closed_when_http_readback_is_unavailable(self):
        with (
            mock.patch("scripts.automation.compact_sg_todo_backlog.worker_api_post_json", return_value=True),
            mock.patch("scripts.automation.compact_sg_todo_backlog.worker_api_get", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP readback failed"):
                gbrain_put("notes/private-route-is-not-reported", "# Updated\n")

    def test_save_fails_closed_when_http_readback_differs(self):
        with (
            mock.patch("scripts.automation.compact_sg_todo_backlog.worker_api_post_json", return_value=True),
            mock.patch("scripts.automation.compact_sg_todo_backlog.worker_api_get", return_value="# Different\n"),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP readback mismatch"):
                gbrain_put("notes/private-route-is-not-reported", "# Updated\n")

    def test_transport_failure_does_not_expose_route_details(self):
        with mock.patch("scripts.automation.compact_sg_todo_backlog.worker_api_post_json", return_value=False):
            with self.assertRaises(RuntimeError) as raised:
                gbrain_put("notes/safe-slug", "# Updated\n")

        message = str(raised.exception)
        self.assertEqual(message, "Memory Stargraph HTTP save failed for notes/safe-slug")
        self.assertNotIn("https://", message)
        self.assertNotIn("127.0.0.1", message)


if __name__ == "__main__":
    unittest.main()
