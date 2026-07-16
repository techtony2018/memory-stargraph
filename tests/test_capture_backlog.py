import datetime as dt
from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest import mock

from scripts.automation import manage_capture_backlog as capture


NOW = dt.datetime(2026, 7, 15, 12, 0, tzinfo=dt.timezone.utc)


def make_row(capture_id: str, status: str) -> dict[str, str]:
    return {
        "id": capture_id,
        "status": status,
        "source kind": "url",
        "source": f"https://example.com/{capture_id.lower()}",
        "target": "",
        "node": f"[[{capture.ROOT_SLUG}/{capture_id.lower()}]]",
        "updated": "2026-07-15T04:00:00-07:00",
        "notes": "queued",
    }


def child_markdown(capture_id: str, status: str) -> str:
    return f"""---
type: capture_request
capture_id: {capture_id}
status: {status}
updated_at: '2026-07-15T04:00:00-07:00'
---

# Capture Request {capture_id}

Status: {status}

## Attempt History
"""


class FakeGBrain:
    def __init__(self, nodes: dict[str, str] | None = None):
        self.nodes = dict(nodes or {})
        self.links: set[tuple[str, str, str]] = set()
        self.calls: list[tuple[str, ...]] = []

    @classmethod
    def with_one_request(cls, capture_id: str, status: str) -> "FakeGBrain":
        root = capture.replace_capture_table(capture.build_root(NOW), [make_row(capture_id, status)])
        child_slug = f"{capture.ROOT_SLUG}/{capture_id.lower()}"
        failed = [make_row(capture_id, status)] if status == "failed" else []
        return cls(
            {
                capture.ROOT_SLUG: root,
                child_slug: child_markdown(capture_id, status),
                capture.FAILED_COLLECTION_SLUG: capture.build_failed_collection(failed, NOW),
            }
        )

    @classmethod
    def with_completed_requests(cls, count: int) -> "FakeGBrain":
        rows = [make_row(f"CAP-{index:04d}", "completed") for index in range(1, count + 1)]
        root = capture.replace_capture_table(capture.build_root(NOW), rows)
        nodes = {
            capture.ROOT_SLUG: root,
            capture.FAILED_COLLECTION_SLUG: capture.build_failed_collection([], NOW),
        }
        nodes.update(
            {
                f"{capture.ROOT_SLUG}/{row['id'].lower()}": child_markdown(row["id"], "completed")
                for row in rows
            }
        )
        return cls(nodes)

    def __call__(
        self,
        args: list[str],
        input_text: str | None = None,
        timeout: int = 180,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        self.calls.append(tuple(args))
        command = args[0]
        if command == "get":
            slug = args[1]
            if slug not in self.nodes:
                return subprocess.CompletedProcess(args, 1, "", "not found")
            return subprocess.CompletedProcess(args, 0, self.nodes[slug], "")
        if command == "put":
            self.nodes[args[1]] = input_text or ""
            return subprocess.CompletedProcess(args, 0, "ok", "")
        if command == "graph":
            source = args[1]
            relation = args[args.index("--link-type") + 1]
            direction = args[args.index("--direction") + 1]
            edges = [
                {"from_slug": edge_source, "to_slug": edge_target, "link_type": edge_relation}
                for edge_source, edge_target, edge_relation in sorted(self.links)
                if edge_relation == relation
                and ((direction == "out" and edge_source == source) or (direction == "in" and edge_target == source))
            ]
            return subprocess.CompletedProcess(args, 0, json.dumps(edges), "")
        if command in {"link", "unlink"}:
            relation = args[args.index("--link-type") + 1]
            edge = (args[1], args[2], relation)
            if command == "link":
                self.links.add(edge)
            else:
                self.links.discard(edge)
            return subprocess.CompletedProcess(args, 0, "ok", "")
        return subprocess.CompletedProcess(args, 2, "", f"unsupported command: {command}")


class CaptureBacklogTests(unittest.TestCase):
    def test_root_has_exact_schema_and_pacific_timestamp(self):
        now = dt.datetime(2026, 7, 15, 12, 0, tzinfo=dt.timezone.utc)
        root = capture.build_root(now)
        self.assertIn("timezone: America/Los_Angeles", root)
        self.assertIn("| id | status | source kind | source | target | node | updated | notes |", root)
        self.assertIn("2026-07-15T05:00:00-07:00", root)

    def test_snapshot_is_oldest_first_and_only_planned(self):
        rows = [
            {"id": "CAP-0003", "status": "planned"},
            {"id": "CAP-0001", "status": "failed"},
            {"id": "CAP-0002", "status": "planned"},
        ]
        self.assertEqual([row["id"] for row in capture.freeze_snapshot(rows)], ["CAP-0002", "CAP-0003"])

    def test_transition_requires_expected_parent_state(self):
        root = capture.fixture_root("CAP-0001", "planned")
        updated = capture.transition(
            root,
            "CAP-0001",
            "planned",
            "capturing",
            "2026-07-15T05:01:00-07:00",
            "batch run-1",
        )
        self.assertIn("| CAP-0001 | capturing |", updated)
        with self.assertRaisesRegex(ValueError, "expected planned, found capturing"):
            capture.transition(
                updated,
                "CAP-0001",
                "planned",
                "completed",
                "2026-07-15T05:02:00-07:00",
                "bad",
            )

    def test_transition_rejects_unknown_status(self):
        with self.assertRaisesRegex(ValueError, "unsupported status"):
            capture.transition(
                capture.fixture_root("CAP-0001", "planned"),
                "CAP-0001",
                "planned",
                "implementing",
                "x",
                "x",
            )

    def test_transition_preserves_completed_archive_index(self):
        root = capture.fixture_root("CAP-0051", "planned")
        archive_index = [
            {
                "slug": f"{capture.ARCHIVE_PREFIX}0001",
                "sequence": 1,
                "first_id": "CAP-0001",
                "last_id": "CAP-0050",
                "count": 50,
            }
        ]
        root = capture.replace_capture_table(root, capture.parse_capture_rows(root), archive_index)

        updated = capture.transition(root, "CAP-0051", "planned", "capturing", "stamp", "run-1")

        self.assertIn(f"| [[{capture.ARCHIVE_PREFIX}0001]] | 1 | CAP-0001 | CAP-0050 | 50 |", updated)

    def test_renderers_include_rows_and_pacific_timestamp(self):
        row = make_row("CAP-0001", "failed")

        failed = capture.build_failed_collection([row], NOW)
        archive = capture.build_archive(f"{capture.ARCHIVE_PREFIX}0001", 1, [row], NOW)

        self.assertIn("2026-07-15T05:00:00-07:00", failed)
        self.assertIn("| CAP-0001 | failed |", failed)
        self.assertIn("Completed Capture Archive 0001", archive)
        self.assertIn("First capture: `CAP-0001`", archive)

    def test_init_apply_verifies_both_collections_and_bidirectional_links(self):
        backend = FakeGBrain()
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            result = capture.apply_init(NOW)

        self.assertEqual(result["root_slug"], capture.ROOT_SLUG)
        self.assertIn("# Memory Starmap Capture List", backend.nodes[capture.ROOT_SLUG])
        self.assertIn("# Memory Starmap Failed Capture Items", backend.nodes[capture.FAILED_COLLECTION_SLUG])
        self.assertIn(
            (capture.ROOT_SLUG, capture.FAILED_COLLECTION_SLUG, "has_failed_collection"),
            backend.links,
        )
        self.assertIn(
            (capture.FAILED_COLLECTION_SLUG, capture.ROOT_SLUG, "failed_collection_for"),
            backend.links,
        )

    def test_init_does_not_overwrite_existing_collections(self):
        backend = FakeGBrain.with_one_request("CAP-0001", "planned")
        before = dict(backend.nodes)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            capture.apply_init(NOW)

        self.assertEqual(backend.nodes, before)

    def test_optional_read_only_treats_not_found_as_absent(self):
        missing = subprocess.CompletedProcess(["get"], 1, "", "page_not_found")
        unavailable = subprocess.CompletedProcess(["get"], 1, "", "connection refused")
        with mock.patch.object(capture, "run_gbrain", return_value=missing):
            self.assertIsNone(capture.get_optional("missing"))
        with mock.patch.object(capture, "run_gbrain", return_value=unavailable):
            with self.assertRaisesRegex(RuntimeError, "connection refused"):
                capture.get_optional("unavailable")

    def test_snapshot_has_invocation_metadata_and_does_not_mutate(self):
        backend = FakeGBrain.with_one_request("CAP-0001", "planned")
        before = dict(backend.nodes)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            result = capture.create_snapshot(NOW, invocation_id="run-1")

        self.assertEqual(result["invocation_id"], "run-1")
        self.assertEqual(result["started_at"], "2026-07-15T05:00:00-07:00")
        self.assertEqual([row["id"] for row in result["rows"]], ["CAP-0001"])
        self.assertEqual(backend.nodes, before)
        self.assertEqual(backend.calls, [("get", capture.ROOT_SLUG)])

    def test_transition_apply_updates_parent_and_child_and_failed_collection(self):
        backend = FakeGBrain.with_one_request("CAP-0001", "capturing")
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            result = capture.apply_transition(
                "CAP-0001",
                "capturing",
                "failed",
                "source login required",
                NOW,
            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("status: failed", backend.nodes[result["child_slug"]])
        self.assertIn("CAP-0001", backend.nodes[capture.FAILED_COLLECTION_SLUG])
        self.assertIn(
            (capture.FAILED_COLLECTION_SLUG, result["child_slug"], "has_failed_capture"),
            backend.links,
        )
        self.assertIn(
            (result["child_slug"], capture.FAILED_COLLECTION_SLUG, "failed_capture_for"),
            backend.links,
        )

    def test_transition_leaving_failed_removes_failed_links_and_mirror_row(self):
        backend = FakeGBrain.with_one_request("CAP-0001", "failed")
        child_slug = f"{capture.ROOT_SLUG}/cap-0001"
        backend.links.update(
            {
                (capture.FAILED_COLLECTION_SLUG, child_slug, "has_failed_capture"),
                (child_slug, capture.FAILED_COLLECTION_SLUG, "failed_capture_for"),
            }
        )
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            capture.apply_transition("CAP-0001", "failed", "planned", "requeued", NOW)

        self.assertNotIn("| CAP-0001 |", backend.nodes[capture.FAILED_COLLECTION_SLUG])
        self.assertNotIn(
            (capture.FAILED_COLLECTION_SLUG, child_slug, "has_failed_capture"),
            backend.links,
        )
        self.assertNotIn(
            (child_slug, capture.FAILED_COLLECTION_SLUG, "failed_capture_for"),
            backend.links,
        )

    def test_transition_retry_repairs_partial_parent_child_mirror_and_link_writes(self):
        child_slug = f"{capture.ROOT_SLUG}/cap-0001"
        scenarios = []

        child_only = FakeGBrain.with_one_request("CAP-0001", "capturing")
        child_only.nodes[child_slug] = capture.update_child_status(
            child_only.nodes[child_slug],
            "capturing",
            "failed",
            "2026-07-15T05:00:00-07:00",
            "source login required",
        )
        scenarios.append(child_only)

        parent_only = FakeGBrain.with_one_request("CAP-0001", "capturing")
        parent_only.nodes[capture.ROOT_SLUG] = capture.transition(
            parent_only.nodes[capture.ROOT_SLUG],
            "CAP-0001",
            "capturing",
            "failed",
            "2026-07-15T05:00:00-07:00",
            "source login required",
        )
        scenarios.append(parent_only)

        states_only = FakeGBrain.with_one_request("CAP-0001", "capturing")
        states_only.nodes[capture.ROOT_SLUG] = capture.transition(
            states_only.nodes[capture.ROOT_SLUG],
            "CAP-0001",
            "capturing",
            "failed",
            "2026-07-15T05:00:00-07:00",
            "source login required",
        )
        states_only.nodes[child_slug] = capture.update_child_status(
            states_only.nodes[child_slug],
            "capturing",
            "failed",
            "2026-07-15T05:00:00-07:00",
            "source login required",
        )
        states_only.nodes[capture.FAILED_COLLECTION_SLUG] = capture.build_failed_collection([], NOW)
        scenarios.append(states_only)

        for backend in scenarios:
            with self.subTest(calls=len(backend.calls)):
                with mock.patch.object(capture, "run_gbrain", side_effect=backend):
                    capture.apply_transition(
                        "CAP-0001", "capturing", "failed", "source login required", NOW
                    )
                parent = capture.parse_capture_rows(backend.nodes[capture.ROOT_SLUG])
                failed = capture.parse_capture_rows(backend.nodes[capture.FAILED_COLLECTION_SLUG])
                self.assertEqual(parent[0]["status"], "failed")
                self.assertEqual(capture.child_status(backend.nodes[child_slug]), "failed")
                self.assertEqual([row["id"] for row in failed], ["CAP-0001"])
                self.assertIn(
                    (capture.FAILED_COLLECTION_SLUG, child_slug, "has_failed_capture"),
                    backend.links,
                )
                self.assertIn(
                    (child_slug, capture.FAILED_COLLECTION_SLUG, "failed_capture_for"),
                    backend.links,
                )

    def test_transition_retry_uses_metadata_from_already_written_parent(self):
        backend = FakeGBrain.with_one_request("CAP-0001", "capturing")
        child_slug = f"{capture.ROOT_SLUG}/cap-0001"
        original_stamp = "2026-07-15T05:00:00-07:00"
        backend.nodes[capture.ROOT_SLUG] = capture.transition(
            backend.nodes[capture.ROOT_SLUG],
            "CAP-0001",
            "capturing",
            "failed",
            original_stamp,
            "original attempt",
        )

        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            capture.apply_transition(
                "CAP-0001",
                "capturing",
                "failed",
                "retry must not replace metadata",
                NOW + dt.timedelta(hours=2),
            )

        child = backend.nodes[child_slug]
        self.assertIn(f"updated_at: '{original_stamp}'", child)
        self.assertIn(f"- {original_stamp}: capturing -> failed; original attempt", child)
        self.assertNotIn("retry must not replace metadata", child)

    def test_transition_inserts_attempt_inside_attempt_history_section_once(self):
        markdown = child_markdown("CAP-0001", "capturing") + "\n## Evidence\n\nKeep me last.\n"
        updated = capture.update_child_status(
            markdown,
            "capturing",
            "failed",
            "2026-07-15T05:00:00-07:00",
            "login required",
        )

        self.assertLess(updated.index("capturing -> failed"), updated.index("## Evidence"))
        self.assertTrue(updated.rstrip().endswith("Keep me last."))

    def test_child_transition_updates_the_heading_adjacent_visible_status(self):
        markdown = child_markdown("CAP-0001", "capturing") + "\n## Evidence\n\nStatus: source-specific\n"

        updated = capture.update_child_status(
            markdown,
            "capturing",
            "completed",
            "2026-07-15T05:00:00-07:00",
            "captured",
        )

        self.assertIn("# Capture Request CAP-0001\n\nStatus: completed\n", updated)
        self.assertIn("## Evidence\n\nStatus: source-specific", updated)
        self.assertEqual(updated.count("Status: completed"), 1)

    def test_visible_status_is_inserted_when_legacy_child_has_no_projection(self):
        markdown = child_markdown("CAP-0001", "completed").replace("\nStatus: completed\n", "")

        updated = capture.synchronize_visible_status(markdown)

        self.assertIn("# Capture Request CAP-0001\n\nStatus: completed\n\n## Attempt History", updated)

    def test_visible_status_projection_supports_every_capture_state_idempotently(self):
        for status in sorted(capture.ALLOWED_STATUSES):
            with self.subTest(status=status):
                markdown = child_markdown("CAP-0001", status)
                once = capture.synchronize_visible_status(markdown)
                twice = capture.synchronize_visible_status(once)
                self.assertIn(f"Status: {status}", once)
                self.assertEqual(once, twice)

    def test_reconcile_visible_status_repairs_terminal_children_without_changing_parent(self):
        backend = FakeGBrain.with_one_request("CAP-0001", "completed")
        child_slug = f"{capture.ROOT_SLUG}/cap-0001"
        backend.nodes[child_slug] = backend.nodes[child_slug].replace(
            "Status: completed", "Status: planned"
        )
        root_before = backend.nodes[capture.ROOT_SLUG]

        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            result = capture.apply_reconcile_visible_status()

        self.assertEqual(result["reconciled"], [child_slug])
        self.assertEqual(backend.nodes[capture.ROOT_SLUG], root_before)
        self.assertIn("Status: completed", backend.nodes[child_slug])
        self.assertNotIn("Status: planned", backend.nodes[child_slug])

    def test_all_operations_reject_unknown_stored_status(self):
        backend = FakeGBrain.with_one_request("CAP-0001", "planned")
        backend.nodes[capture.ROOT_SLUG] = backend.nodes[capture.ROOT_SLUG].replace(
            "| CAP-0001 | planned |", "| CAP-0001 | implementing |"
        )

        operations = [
            lambda: capture.list_backlog(),
            lambda: capture.create_snapshot(NOW),
            lambda: capture.apply_transition("CAP-0001", "planned", "capturing", "run", NOW),
            lambda: capture.apply_compaction(NOW),
        ]
        for operation in operations:
            with self.subTest(operation=operation):
                with mock.patch.object(capture, "run_gbrain", side_effect=backend):
                    with self.assertRaisesRegex(ValueError, "unsupported stored status implementing"):
                        operation()

    def test_compaction_is_idempotent_at_fifty_completed_rows(self):
        backend = FakeGBrain.with_completed_requests(50)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            first = capture.apply_compaction(NOW)
            archived_markdown = backend.nodes[f"{capture.ARCHIVE_PREFIX}0001"]
            second = capture.apply_compaction(NOW)
        self.assertEqual(first["created_archives"], [f"{capture.ARCHIVE_PREFIX}0001"])
        self.assertEqual(second["created_archives"], [])
        self.assertEqual(backend.nodes[f"{capture.ARCHIVE_PREFIX}0001"], archived_markdown)
        self.assertEqual(len(capture.parse_capture_rows(backend.nodes[capture.ROOT_SLUG])), 0)
        self.assertIn(
            (capture.ROOT_SLUG, f"{capture.ARCHIVE_PREFIX}0001", "has_completed_archive"),
            backend.links,
        )
        self.assertIn(
            (f"{capture.ARCHIVE_PREFIX}0001", capture.ROOT_SLUG, "completed_archive_for"),
            backend.links,
        )
        self.assertIn(
            (f"{capture.ARCHIVE_PREFIX}0001", f"{capture.ROOT_SLUG}/cap-0001", "contains_capture_request"),
            backend.links,
        )

    def test_compaction_refuses_to_overwrite_unindexed_archive(self):
        backend = FakeGBrain.with_completed_requests(50)
        archive_slug = f"{capture.ARCHIVE_PREFIX}0001"
        backend.nodes[archive_slug] = "immutable existing archive"

        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(RuntimeError, "already exists but is missing from the root index"):
                capture.apply_compaction(NOW)

        self.assertEqual(backend.nodes[archive_slug], "immutable existing archive")

    def test_compaction_resumes_matching_unindexed_immutable_archive(self):
        backend = FakeGBrain.with_completed_requests(50)
        archive_slug = f"{capture.ARCHIVE_PREFIX}0001"
        rows = capture.parse_capture_rows(backend.nodes[capture.ROOT_SLUG])
        backend.nodes[archive_slug] = capture.build_archive(archive_slug, 1, rows, NOW)

        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            result = capture.apply_compaction(NOW + dt.timedelta(hours=1))

        self.assertEqual(result["resumed_archives"], [archive_slug])
        self.assertEqual(capture.parse_archive_index(backend.nodes[capture.ROOT_SLUG])[0]["slug"], archive_slug)
        self.assertIn((capture.ROOT_SLUG, archive_slug, "has_completed_archive"), backend.links)
        self.assertIn((archive_slug, capture.ROOT_SLUG, "completed_archive_for"), backend.links)
        self.assertIn(
            (archive_slug, f"{capture.ROOT_SLUG}/cap-0001", "contains_capture_request"),
            backend.links,
        )

    def test_exact_readback_rejects_wrong_parent_row_despite_matching_marker_text(self):
        class CorruptingBackend(FakeGBrain):
            def __call__(self, args, input_text=None, timeout=180):
                result = super().__call__(args, input_text, timeout)
                if args[:2] == ["put", capture.ROOT_SLUG]:
                    self.nodes[capture.ROOT_SLUG] += "\n<!-- | CAP-0001 | failed | -->\n"
                    self.nodes[capture.ROOT_SLUG] = self.nodes[capture.ROOT_SLUG].replace(
                        "| CAP-0001 | failed |", "| CAP-0001 | capturing |", 1
                    )
                return result

        source = FakeGBrain.with_one_request("CAP-0001", "capturing")
        backend = CorruptingBackend(source.nodes)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(RuntimeError, "parent row readback mismatch"):
                capture.apply_transition("CAP-0001", "capturing", "failed", "login", NOW)

    def test_exact_readback_uses_child_frontmatter_not_body_marker(self):
        child_slug = f"{capture.ROOT_SLUG}/cap-0001"

        class CorruptingBackend(FakeGBrain):
            def __call__(self, args, input_text=None, timeout=180):
                result = super().__call__(args, input_text, timeout)
                if args[:2] == ["put", child_slug]:
                    self.nodes[child_slug] = self.nodes[child_slug].replace(
                        "status: failed", "status: capturing", 1
                    ) + "\nstatus: failed\n"
                return result

        source = FakeGBrain.with_one_request("CAP-0001", "capturing")
        backend = CorruptingBackend(source.nodes)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(RuntimeError, "child status readback mismatch"):
                capture.apply_transition("CAP-0001", "capturing", "failed", "login", NOW)

    def test_exact_readback_rejects_corrupted_child_transition_metadata(self):
        child_slug = f"{capture.ROOT_SLUG}/cap-0001"

        class CorruptingBackend(FakeGBrain):
            def __call__(self, args, input_text=None, timeout=180):
                result = super().__call__(args, input_text, timeout)
                if args[:2] == ["put", child_slug]:
                    self.nodes[child_slug] = self.nodes[child_slug].replace(
                        "updated_at: '2026-07-15T05:00:00-07:00'",
                        "updated_at: '1999-01-01T00:00:00-08:00'",
                    ).replace(
                        "- 2026-07-15T05:00:00-07:00: capturing -> failed; login\n",
                        "",
                    )
                return result

        source = FakeGBrain.with_one_request("CAP-0001", "capturing")
        backend = CorruptingBackend(source.nodes)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(RuntimeError, "child transition readback mismatch"):
                capture.apply_transition("CAP-0001", "capturing", "failed", "login", NOW)

    def test_exact_readback_rejects_corruption_of_other_parent_rows(self):
        rows = [make_row("CAP-0001", "capturing"), make_row("CAP-0002", "planned")]
        root = capture.replace_capture_table(capture.build_root(NOW), rows)
        child_slug = f"{capture.ROOT_SLUG}/cap-0001"

        class CorruptingBackend(FakeGBrain):
            def __call__(self, args, input_text=None, timeout=180):
                result = super().__call__(args, input_text, timeout)
                if args[:2] == ["put", capture.ROOT_SLUG]:
                    kept = [
                        row
                        for row in capture.parse_capture_rows(self.nodes[capture.ROOT_SLUG])
                        if row["id"] == "CAP-0001"
                    ]
                    self.nodes[capture.ROOT_SLUG] = capture.replace_capture_table(
                        self.nodes[capture.ROOT_SLUG], kept
                    )
                return result

        backend = CorruptingBackend(
            {
                capture.ROOT_SLUG: root,
                child_slug: child_markdown("CAP-0001", "capturing"),
                capture.FAILED_COLLECTION_SLUG: capture.build_failed_collection([], NOW),
            }
        )
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(RuntimeError, "parent row readback mismatch"):
                capture.apply_transition("CAP-0001", "capturing", "failed", "login", NOW)

    def test_exact_readback_rejects_failed_mirror_row_when_absence_expected(self):
        class CorruptingBackend(FakeGBrain):
            def __call__(self, args, input_text=None, timeout=180):
                result = super().__call__(args, input_text, timeout)
                if args[:2] == ["put", capture.FAILED_COLLECTION_SLUG]:
                    rows = [make_row("CAP-0001", "failed")]
                    self.nodes[capture.FAILED_COLLECTION_SLUG] = capture.build_failed_collection(rows, NOW)
                return result

        source = FakeGBrain.with_one_request("CAP-0001", "failed")
        backend = CorruptingBackend(source.nodes)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(RuntimeError, "failed mirror readback mismatch"):
                capture.apply_transition("CAP-0001", "failed", "planned", "requeued", NOW)

    def test_link_write_is_verified_by_exact_graph_readback(self):
        class DroppingLinkBackend(FakeGBrain):
            def __call__(self, args, input_text=None, timeout=180):
                if args[0] == "link":
                    return subprocess.CompletedProcess(args, 0, "ok", "")
                return super().__call__(args, input_text, timeout)

        source = FakeGBrain.with_one_request("CAP-0001", "capturing")
        backend = DroppingLinkBackend(source.nodes)
        with mock.patch.object(capture, "run_gbrain", side_effect=backend):
            with self.assertRaisesRegex(RuntimeError, "link readback mismatch"):
                capture.apply_transition("CAP-0001", "capturing", "failed", "login", NOW)

    def test_manager_remains_directly_invocable(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/automation/manage_capture_backlog.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Manage the Memory Stargraph capture backlog", result.stdout)
        self.assertIn("reconcile-visible-status", result.stdout)


if __name__ == "__main__":
    unittest.main()
