import unittest

from scripts.automation.backlog_compaction import BacklogSpec, parse_rows, plan_compaction, render_table


CAPTURE = BacklogSpec(
    root_slug="notes/memory-starmap-capture-list",
    section_heading="Capture Items",
    columns=("id", "status", "source kind", "source", "target", "node", "updated", "notes"),
    completed_status="completed",
    archive_size=50,
    archive_prefix="notes/memory-starmap-capture-list/completed-archive-",
)


def capture_row(number: int, status: str) -> dict[str, str]:
    item = f"CAP-{number:04d}"
    return {
        "id": item,
        "status": status,
        "source kind": "url",
        "source": f"https://example.com/{number}",
        "target": "",
        "node": f"[[notes/memory-starmap-capture-list/{item.lower()}]]",
        "updated": "2026-07-15T09:00:00-07:00",
        "notes": "queued",
    }


class GenericBacklogCompactionTests(unittest.TestCase):
    def test_generic_capture_compaction_archives_full_oldest_batches(self):
        rows = [capture_row(200, "planned"), capture_row(201, "failed")]
        rows += [capture_row(index, "completed") for index in range(1, 127)]
        plan = plan_compaction(rows, {}, CAPTURE)
        self.assertEqual([archive["slug"] for archive in plan.archives_to_create], [
            "notes/memory-starmap-capture-list/completed-archive-0001",
            "notes/memory-starmap-capture-list/completed-archive-0002",
        ])
        self.assertEqual([row["id"] for row in plan.active_rows[:2]], ["CAP-0200", "CAP-0201"])
        self.assertEqual([row["id"] for row in plan.active_rows[2:]], [f"CAP-{i:04d}" for i in range(101, 127)])

    def test_generic_table_round_trips_escaped_cells(self):
        row = capture_row(1, "planned")
        row["notes"] = "A | B"
        self.assertEqual(parse_rows(render_table([row], CAPTURE), CAPTURE)[0]["notes"], "A | B")


if __name__ == "__main__":
    unittest.main()
