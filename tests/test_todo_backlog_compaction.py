from pathlib import Path
import subprocess
import sys
import unittest

from scripts.automation.compact_sg_todo_backlog import (
    ARCHIVE_SIZE,
    TODO_COLUMNS,
    parse_todo_rows,
    plan_compaction,
    render_todo_table,
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


if __name__ == "__main__":
    unittest.main()
