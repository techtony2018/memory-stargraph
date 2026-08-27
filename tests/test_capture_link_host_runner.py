import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.automation import capture_link_host_runner as runner


class CaptureLinkHostRunnerTests(unittest.TestCase):
    def make_request(self, **overrides):
        payload = runner.make_request(
            overrides.pop("invocation_id", "sg0176-test-0001"),
            overrides.pop("expected_commit", "abc123"),
            overrides.pop("mode", "auto"),
            overrides.pop("nonce", "nonce-0001"),
        )
        payload.update(overrides)
        return payload

    def lifecycle_mocks(self):
        def terminal_markdown(slug):
            if slug.startswith("runs/"):
                return """---
type: run
status: completed
result: completed_empty_snapshot_no_eligible_candidates
curator_lease: false
active_change: false
tags:
  - capture-link
  - completed
  - curator
  - host-runner
---
# Completed run
"""
            return """---
type: report
status: completed
result: completed_empty_snapshot_no_eligible_candidates
active_change: false
tags:
  - capture-link
  - completed
  - curator
  - host-runner
---
# Completed report
"""
        return (
            mock.patch.object(runner, "put_entity"),
            mock.patch.object(runner, "mutate_tag"),
            mock.patch.object(runner, "read_tags", return_value=["capture-link", "curator", "host-runner", "completed"]),
            mock.patch.object(runner, "get_entity", side_effect=terminal_markdown),
            mock.patch.object(runner, "global_active_tag_readback", return_value={
                "source": runner.GLOBAL_ACTIVE_TAG_READBACK_SOURCE,
                "readback_at": "2026-08-08T08:00:00-07:00",
                "attempt": 1,
                "active_tag_count": 0,
                "active_tag_pages": [],
                "active_tags_clear": True,
            }),
        )

    def gbrain_entity_mocks(self, pages):
        page_store = dict(pages)

        def fake_get(slug):
            if slug not in page_store:
                raise runner.RunnerError(f"missing {slug}")
            return page_store[slug]

        def fake_put(slug, markdown):
            page_store[slug] = markdown

        return page_store, mock.patch.object(runner, "get_entity", side_effect=fake_get), mock.patch.object(runner, "put_entity", side_effect=fake_put)

    def test_submit_writes_atomic_confined_request_and_status_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = runner.submit_request(root, self.make_request())

            self.assertEqual(result["status"], "submitted")
            self.assertTrue((root / "incoming" / "nonce-0001.json").exists())
            self.assertEqual(runner.read_status(root, "sg0176-test-0001")["status"], "pending")

    def test_schema_rejects_unsupported_operation_and_old_request(self):
        old = (runner.pacific_now() - dt.timedelta(hours=7)).isoformat()
        with self.assertRaisesRegex(runner.RunnerError, "unsupported operation"):
            runner.validate_request(self.make_request(operation="shell"))
        with self.assertRaisesRegex(runner.RunnerError, "freshness"):
            runner.validate_request(self.make_request(created_at=old))

    def test_rejects_path_escape_identifiers_and_large_request(self):
        with self.assertRaisesRegex(runner.RunnerError, "unsafe identifier"):
            runner.validate_request(self.make_request(invocation_id="../escape"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "incoming" / "huge.json"
            runner.ensure_dirs(root)
            path.write_text("x" * (runner.MAX_REQUEST_BYTES + 1), encoding="utf-8")
            with mock.patch.object(runner, "acquire_lock", return_value=os.open(root / "test.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY)):
                with self.assertRaises(runner.RunnerError):
                    runner.process_one(root)

    def test_duplicate_nonce_same_payload_is_idempotent_and_replay_diff_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self.make_request()
            first = runner.submit_request(root, request)
            second = runner.submit_request(root, dict(request))
            self.assertEqual(first["status"], "submitted")
            self.assertEqual(second["status"], "already_submitted")
            changed = dict(request)
            changed["mode"] = "capture_drain"
            with self.assertRaisesRegex(runner.RunnerError, "replay"):
                runner.submit_request(root, changed)

    def test_runner_lock_prevents_concurrent_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.ensure_dirs(root)
            fd = runner.acquire_lock(root)
            try:
                with self.assertRaisesRegex(runner.RunnerError, "already active"):
                    runner.acquire_lock(root)
            finally:
                runner.release_lock(root, fd)

    def test_stale_empty_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.ensure_dirs(root)
            lock = runner.lock_path(root)
            lock.write_text("", encoding="utf-8")
            old = runner.pacific_now().timestamp() - runner.STALE_LOCK_SECONDS - 5
            os.utime(lock, (old, old))
            fd = runner.acquire_lock(root)
            try:
                self.assertEqual(lock.read_text(encoding="utf-8"), str(os.getpid()))
            finally:
                runner.release_lock(root, fd)

    def test_crash_recovery_terminalizes_stale_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.ensure_dirs(root)
            request = self.make_request()
            processing = runner.processing_path(root, request["nonce"])
            processing.write_text(json.dumps(request), encoding="utf-8")
            old = runner.pacific_now().timestamp() - runner.PROCESSING_TIMEOUT_SECONDS - 10
            os.utime(processing, (old, old))

            recovered = runner.recover_stale_processing(root)

            self.assertEqual(recovered, ["sg0176-test-0001"])
            result = runner.read_status(root, "sg0176-test-0001")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["result"], "processing_timeout_recovered")

    def test_run_once_empty_snapshot_compacts_snapshots_and_releases_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self.make_request(expected_commit="abc123")
            runner.submit_request(root, request)
            with (
                mock.patch.object(runner, "current_commit", return_value="abc123"),
                mock.patch.object(runner.capture, "apply_compaction", side_effect=[
                    {"created_archives": [], "active_rows": 0, "failed_rows": 0},
                    {"created_archives": [], "active_rows": 0, "failed_rows": 0},
                ]),
                mock.patch.object(runner.capture, "create_snapshot", return_value={
                    "invocation_id": "sg0176-test-0001",
                    "started_at": "2026-07-30T11:59:00-07:00",
                    "rows": [],
                }),
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED": "1"}),
                self.lifecycle_mocks()[0] as put_entity,
                self.lifecycle_mocks()[1] as mutate_tag,
                self.lifecycle_mocks()[2],
                self.lifecycle_mocks()[3],
                self.lifecycle_mocks()[4],
                mock.patch.object(runner, "inspect_enrichment_candidates", return_value={
                    "selection_version": runner.ENRICHMENT_SELECTION_VERSION,
                    "inspected_scope": [],
                    "inspected_count": 0,
                    "candidate_count": 0,
                    "scope_complete": True,
                    "total_scope_count": 0,
                    "inspected_count": 0,
                    "uninspected_count": 0,
                    "selection_truncated": False,
                    "evidence_display_truncated": False,
                    "exclusion_counts": {"not_public_or_no_reliable_public_source": 2},
                    "ordered_candidates": [],
                    "selected_candidates": [],
                    "no_eligible_candidate": True,
                    "no_eligible_candidate_within_inspected_scope": False,
                }),
            ):
                processed = runner.process_one(root)

            self.assertEqual(processed["status"], "processed")
            result = runner.read_status(root, "sg0176-test-0001")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["result"], "completed_empty_snapshot_no_eligible_candidates")
            self.assertTrue(result["evidence"]["enrichment"]["no_eligible_candidate"])
            self.assertTrue(result["evidence"]["enrichment"]["selection"]["scope_complete"])
            self.assertEqual(result["evidence"]["enrichment"]["selection"]["candidate_count"], 0)
            self.assertTrue(result["evidence"]["lifecycle_tags_released"])
            self.assertEqual(result["evidence"]["runner_ownership"]["runner_host_role"], ".85-authoritative")
            self.assertTrue(result["evidence"]["runner_ownership"]["configured_remote_runner_disabled"])
            self.assertIn("run_slug", result["evidence"])
            self.assertIn("report_slug", result["evidence"])
            self.assertEqual(put_entity.call_count, 5)
            report_slug = result["evidence"]["report_slug"]
            mutate_tag.assert_has_calls([
                mock.call("runs/memory-stargraph-capture-link-drain-sg0176-test-0001", "active", "add"),
                mock.call("runs/memory-stargraph-capture-link-drain-sg0176-test-0001", "active", "remove"),
                mock.call("runs/memory-stargraph-capture-link-drain-sg0176-test-0001", "implementing", "remove"),
                mock.call(report_slug, "active", "remove"),
                mock.call(report_slug, "implementing", "remove"),
            ])
            lifecycle = result["evidence"]["entities"]
            self.assertEqual(lifecycle["runs/memory-stargraph-capture-link-drain-sg0176-test-0001"]["stale_lifecycle_tags"], [])
            self.assertTrue((root / "logs" / "runner.jsonl").exists())

    def test_empty_snapshot_enriches_two_candidates_after_reservation_readback(self):
        values = runner.validate_request(self.make_request())
        run_slug, report_slug = runner.lifecycle_slugs(values)
        pages, get_patch, put_patch = self.gbrain_entity_mocks({
            run_slug: f"active {values['invocation_id']} people/a people/b",
            "people/a": "---\ntype: person\npublic: true\n---\n# A\n\nhttps://example.com/a\n",
            "people/b": "---\ntype: person\npublic: true\n---\n# B\n\nhttps://example.com/b\n",
        })
        selection = {
            "selection_version": runner.ENRICHMENT_SELECTION_VERSION,
            "inspected_scope": [{"type": "person", "limit": 500}],
            "inspected_count": 2,
            "candidate_count": 2,
            "scope_complete": False,
            "total_scope_count": 4,
            "inspected_count": 2,
            "uninspected_count": 2,
            "selection_truncated": True,
            "evidence_display_truncated": False,
            "exclusion_counts": {},
            "ordered_candidates": [
                {"slug": "people/a", "type": "person", "title": "A", "deficiencies": ["missing_biography_or_summary"], "selection_order": 1},
                {"slug": "people/b", "type": "person", "title": "B", "deficiencies": ["missing_roles_or_projects"], "selection_order": 2},
            ],
            "selected_candidates": [
                {"slug": "people/a", "type": "person", "title": "A", "deficiencies": ["missing_biography_or_summary"], "selection_order": 1},
                {"slug": "people/b", "type": "person", "title": "B", "deficiencies": ["missing_roles_or_projects"], "selection_order": 2},
            ],
            "no_eligible_candidate": False,
            "no_eligible_candidate_within_inspected_scope": False,
        }
        with (
            get_patch,
            put_patch as put_entity,
            mock.patch.object(runner, "inspect_enrichment_candidates", return_value=selection),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                evidence = runner.run_empty_queue_enrichment(Path(tmp), values, run_slug, report_slug, {"snapshot": {"rows": []}})
        self.assertEqual(evidence["metrics"]["attempted_enrichments"], 2)
        self.assertEqual(evidence["metrics"]["successful_enrichments"], 2)
        self.assertEqual(len(evidence["reservations"]), 2)
        self.assertIn("Capture Link Enrichment Review", pages["people/a"])
        self.assertIn("Capture Link Enrichment Review", pages["people/b"])
        self.assertGreaterEqual(put_entity.call_count, 4)

    def test_empty_snapshot_enriches_one_candidate(self):
        values = runner.validate_request(self.make_request())
        run_slug, report_slug = runner.lifecycle_slugs(values)
        pages, get_patch, put_patch = self.gbrain_entity_mocks({
            run_slug: f"active {values['invocation_id']} people/solo",
            "people/solo": "---\ntype: person\npublic: true\n---\n# Solo\n\nhttps://example.com/solo\n",
        })
        selection = {
            "selection_version": runner.ENRICHMENT_SELECTION_VERSION,
            "inspected_scope": [],
            "inspected_count": 1,
            "candidate_count": 1,
            "scope_complete": True,
            "total_scope_count": 1,
            "inspected_count": 1,
            "uninspected_count": 0,
            "selection_truncated": False,
            "evidence_display_truncated": False,
            "exclusion_counts": {},
            "ordered_candidates": [{"slug": "people/solo", "type": "person", "title": "Solo", "deficiencies": [], "selection_order": 1}],
            "selected_candidates": [{"slug": "people/solo", "type": "person", "title": "Solo", "deficiencies": [], "selection_order": 1}],
            "no_eligible_candidate": False,
            "no_eligible_candidate_within_inspected_scope": False,
        }
        with get_patch, put_patch, mock.patch.object(runner, "inspect_enrichment_candidates", return_value=selection):
            with tempfile.TemporaryDirectory() as tmp:
                evidence = runner.run_empty_queue_enrichment(Path(tmp), values, run_slug, report_slug, {"snapshot": {"rows": []}})
        self.assertEqual(evidence["metrics"]["attempted_enrichments"], 1)
        self.assertEqual(evidence["metrics"]["successful_enrichments"], 1)
        self.assertIn("people/solo", pages)

    def test_already_sufficient_enrichment_records_exclusion_receipt(self):
        values = runner.validate_request(self.make_request())
        pages, get_patch, put_patch = self.gbrain_entity_mocks({
            "organizations/repeated": (
                "---\n"
                "type: organization\n"
                "public: true\n"
                "---\n"
                "# Repeated\n\n"
                "https://example.com/repeated\n\n"
                "## Capture Link Enrichment Review\n\n"
                "<!-- capture-link-enrichment-reviewed-at: 2026-07-01T00:00:00-07:00 -->\n\n"
                "## Description\n\nAlready reviewed.\n"
            ),
        })
        candidate = {
            "slug": "organizations/repeated",
            "type": "organization",
            "deficiencies": ["missing_roles_or_projects"],
        }
        with get_patch, put_patch as put_entity:
            outcome = runner.apply_entity_enrichment(values, candidate)

        self.assertEqual(outcome["result"], "already_sufficient")
        self.assertTrue(outcome["receipt_recorded"])
        self.assertFalse(outcome["content_mutation"])
        self.assertTrue(outcome["verification"]["body_changed"])
        self.assertTrue(outcome["verification"]["review_marker_present"])
        self.assertIn("Capture Link Already-Sufficient Review Receipt", pages["organizations/repeated"])
        self.assertIn("already_sufficient_existing_enrichment_review", pages["organizations/repeated"])
        self.assertIsNotNone(runner.recent_enrichment_review(pages["organizations/repeated"]))
        self.assertEqual(put_entity.call_count, 1)

    def test_recent_already_sufficient_receipt_excludes_repeat_selection(self):
        page = (
            "---\n"
            "type: organization\n"
            "public: true\n"
            "---\n"
            "# Reviewed\n\n"
            "https://example.com/reviewed\n\n"
            "## Capture Link Enrichment Review\n\n"
            "<!-- capture-link-enrichment-reviewed-at: 2026-07-01T00:00:00-07:00 -->\n\n"
            "## Capture Link Already-Sufficient Review Receipt\n\n"
            "<!-- capture-link-enrichment-reviewed-at: 2026-08-17T08:00:00-07:00 -->\n"
        )

        def fake_list(entity_type, limit=runner.MAX_ENRICHMENT_CANDIDATES):
            return [{"slug": "organizations/reviewed", "type": "organization", "updated": "", "title": "Reviewed"}] if entity_type == "organization" else []

        with (
            mock.patch.object(runner, "list_entities", side_effect=fake_list),
            mock.patch.object(runner, "get_entity", return_value=page),
        ):
            selection = runner.inspect_enrichment_candidates(now=dt.datetime.fromisoformat("2026-08-18T08:00:00-07:00"))

        self.assertEqual(selection["candidate_count"], 0)
        self.assertEqual(selection["exclusion_counts"]["reviewed_within_30_days"], 1)
        self.assertTrue(selection["no_eligible_candidate"])

    def test_zero_candidate_selection_records_deterministic_exclusions(self):
        with (
            mock.patch.object(runner, "list_entities", return_value=[{"slug": "people/private", "type": "person", "updated": "", "title": "Private"}]),
            mock.patch.object(runner, "get_entity", return_value="---\ntype: person\nvisibility: private\n---\n# Private\n"),
        ):
            selection = runner.inspect_enrichment_candidates()
        self.assertTrue(selection["no_eligible_candidate"])
        self.assertFalse(selection["no_eligible_candidate_within_inspected_scope"])
        self.assertTrue(selection["scope_complete"])
        self.assertEqual(selection["total_scope_count"], 7)
        self.assertEqual(selection["uninspected_count"], 0)
        self.assertEqual(selection["candidate_count"], 0)
        self.assertEqual(selection["exclusion_counts"]["not_public_or_no_reliable_public_source"], 7)
        self.assertEqual(selection["selection_version"], runner.ENRICHMENT_SELECTION_VERSION)

    def test_truncated_bounded_scope_cannot_claim_global_no_candidate(self):
        rows = [
            {"slug": f"people/private-{index:02d}", "type": "person", "updated": "", "title": f"Private {index:02d}"}
            for index in range(runner.MAX_ENRICHMENT_INSPECTIONS + 5)
        ]
        with (
            mock.patch.object(runner, "list_entities", return_value=rows),
            mock.patch.object(runner, "get_entity", return_value="---\ntype: person\nvisibility: private\n---\n# Private\n") as get_entity,
        ):
            selection = runner.inspect_enrichment_candidates(max_inspections=runner.MAX_ENRICHMENT_INSPECTIONS)
        self.assertEqual(get_entity.call_count, runner.MAX_ENRICHMENT_INSPECTIONS)
        self.assertTrue(selection["selection_truncated"])
        self.assertEqual(selection["inspection_limit"], runner.MAX_ENRICHMENT_INSPECTIONS)
        self.assertFalse(selection["no_eligible_candidate"])
        self.assertTrue(selection["no_eligible_candidate_within_inspected_scope"])
        self.assertGreater(selection["uninspected_count"], 0)

    def test_candidate_beyond_first_twenty_is_found(self):
        rows = [
            {"slug": f"people/private-{index:02d}", "type": "person", "updated": "", "title": f"Private {index:02d}"}
            for index in range(runner.MAX_ENRICHMENT_INSPECTIONS)
        ] + [{"slug": "people/public-21", "type": "person", "updated": "", "title": "Public 21"}]

        def fake_list(entity_type, limit=runner.MAX_ENRICHMENT_CANDIDATES):
            return rows if entity_type == "person" else []

        def fake_get(slug, timeout=120):
            if slug == "people/public-21":
                return "---\ntype: person\npublic: true\n---\n# Public\n\nhttps://example.com/public\n"
            return "---\ntype: person\nvisibility: private\n---\n# Private\n"

        with mock.patch.object(runner, "list_entities", side_effect=fake_list), mock.patch.object(runner, "get_entity", side_effect=fake_get):
            selection = runner.inspect_enrichment_candidates()
        self.assertFalse(selection["no_eligible_candidate"])
        self.assertEqual(selection["candidate_count"], 1)
        self.assertEqual(selection["selected_candidates"][0]["slug"], "people/public-21")
        self.assertEqual(selection["inspected_count"], runner.MAX_ENRICHMENT_INSPECTIONS + 1)

    def test_enrichment_partial_failure_is_terminal_evidence(self):
        values = runner.validate_request(self.make_request())
        run_slug, report_slug = runner.lifecycle_slugs(values)
        selection = {
            "selection_version": runner.ENRICHMENT_SELECTION_VERSION,
            "inspected_scope": [],
            "inspected_count": 1,
            "candidate_count": 1,
            "scope_complete": True,
            "total_scope_count": 1,
            "inspected_count": 1,
            "uninspected_count": 0,
            "selection_truncated": False,
            "evidence_display_truncated": False,
            "exclusion_counts": {},
            "ordered_candidates": [{"slug": "people/fail", "type": "person", "title": "Fail", "deficiencies": [], "selection_order": 1}],
            "selected_candidates": [{"slug": "people/fail", "type": "person", "title": "Fail", "deficiencies": [], "selection_order": 1}],
            "no_eligible_candidate": False,
            "no_eligible_candidate_within_inspected_scope": False,
        }
        with (
            mock.patch.object(runner, "inspect_enrichment_candidates", return_value=selection),
            mock.patch.object(runner, "reserve_candidate", side_effect=runner.RunnerError("reservation failed")),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                evidence = runner.run_empty_queue_enrichment(Path(tmp), values, run_slug, report_slug, {"snapshot": {"rows": []}})
        self.assertEqual(evidence["metrics"]["failed_enrichments"], 1)
        self.assertEqual(evidence["failures"][0]["slug"], "people/fail")

    def test_curator_polling_accepts_four_minutes_with_fresh_progress(self):
        started = runner.pacific_now() - dt.timedelta(minutes=4, seconds=11)
        payload = {
            "status": "pending",
            "daemon_state": {
                "runner_instance_id": "runner-a",
                "heartbeat_at": runner.iso_now(),
                "phase": "entity_reads",
                "progress": {"processed": 20, "total": 75},
            },
        }
        decision = runner.curator_poll_decision(payload, started_at=started, expected_runner_instance_id="runner-a")
        self.assertEqual(decision["decision"], "continue")
        self.assertEqual(decision["reason"], "fresh_daemon_progress")

    def test_curator_polling_fails_stale_heartbeat_and_deadline(self):
        now = runner.pacific_now()
        stale_payload = {
            "status": "pending",
            "daemon_state": {
                "runner_instance_id": "runner-a",
                "heartbeat_at": (now - dt.timedelta(seconds=runner.RUNNER_HEARTBEAT_STALE_SECONDS + 1)).isoformat(),
            },
        }
        stale = runner.curator_poll_decision(stale_payload, started_at=now - dt.timedelta(minutes=2), now=now, expected_runner_instance_id="runner-a")
        self.assertEqual(stale["decision"], "fail")
        self.assertEqual(stale["reason"], "stale_daemon_heartbeat")
        deadline = runner.curator_poll_decision({"status": "pending", "daemon_state": None}, started_at=now - dt.timedelta(seconds=runner.CURATOR_POLL_MAX_SECONDS + 1), now=now)
        self.assertEqual(deadline["decision"], "fail")
        self.assertEqual(deadline["reason"], "overall_deadline_exceeded")

    def test_phase_failure_after_run_creation_terminalizes_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.submit_request(root, self.make_request(expected_commit="abc123"))
            with (
                mock.patch.object(runner, "current_commit", return_value="abc123"),
                mock.patch.object(runner.capture, "apply_compaction", side_effect=runner.RunnerPhaseError("compaction_before_snapshot", "gbrain timed out")),
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED": "1"}),
                self.lifecycle_mocks()[0],
                self.lifecycle_mocks()[1] as mutate_tag,
                self.lifecycle_mocks()[2],
                self.lifecycle_mocks()[3],
                self.lifecycle_mocks()[4],
            ):
                runner.process_one(root)
            result = runner.read_status(root, "sg0176-test-0001")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["result"], "compaction_before_snapshot_failed")
            self.assertEqual(result["evidence"]["failed_phase"], "compaction_before_snapshot")
            self.assertFalse(runner.lock_path(root).exists())
            self.assertTrue((root / "failed" / "nonce-0001.json").exists())
            mutate_tag.assert_any_call("runs/memory-stargraph-capture-link-drain-sg0176-test-0001", "active", "remove")

    def test_run_loop_is_disabled_by_default_and_processes_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(runner.RunnerError, "disabled"):
                runner.run_loop(root, max_iterations=1)
            with (
                mock.patch.object(runner, "process_one", return_value={"ok": True, "status": "idle"}),
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED": "1"}),
            ):
                result = runner.run_loop(root, poll_seconds=0, max_iterations=2)
            self.assertEqual(result["iterations"], 2)
            self.assertEqual(result["processed"], 0)

    def test_health_distinguishes_submitter_context_from_daemon_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.write_runner_state(root, "idle", {"runner_enabled": True})
            with mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED": "0"}):
                health = runner.health(root)
            self.assertEqual(health["context"], "submitter_offline")
            self.assertFalse(health["current_process_runner_enabled"])
            self.assertEqual(health["daemon_state"]["status"], "idle")

    def test_non_empty_snapshot_drains_frozen_row_with_reservation_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.submit_request(root, self.make_request())
            events = []

            def fake_transition(capture_id, expected, target, notes, now=None):
                events.append(("transition", capture_id, expected, target))
                return {
                    "capture_id": capture_id,
                    "status": target,
                    "child_slug": "notes/memory-starmap-capture-list/cap-0001-example",
                    "updated_at": runner.iso_now(),
                }

            def fake_put(slug, markdown):
                events.append(("put", slug))
                if "memory-stargraph-captures" in slug:
                    self.assertIn("Example Source", markdown)

            def fake_get(slug, timeout=120):
                if slug.startswith("runs/"):
                    return """---
type: run
status: completed
result: completed_non_empty_snapshot_drain
curator_lease: false
active_change: false
tags:
  - capture-link
  - completed
  - curator
  - host-runner
---
# Run
"""
                if slug.startswith("reports/"):
                    return """---
type: report
status: completed
result: completed_non_empty_snapshot_drain
active_change: false
tags:
  - capture-link
  - completed
  - curator
  - host-runner
---
# Report
"""
                return "---\ntype: capture\nstatus: capturing\n---\n# CAP\n\n## Capture Instructions\n\nCapture example source.\n"

            with (
                mock.patch.object(runner, "current_commit", return_value="abc123"),
                mock.patch.object(runner.capture, "apply_compaction", return_value={"created_archives": []}),
                mock.patch.object(runner.capture, "create_snapshot", return_value={
                    "invocation_id": "sg0176-test-0001",
                    "started_at": "2026-07-30T11:59:00-07:00",
                    "rows": [{
                        "id": "CAP-0001",
                        "status": "planned",
                        "source": "https://example.com/source",
                        "source kind": "url",
                        "node": "[[notes/memory-starmap-capture-list/cap-0001-example]]",
                        "target": "",
                        "notes": "Capture example source.",
                    }],
                }),
                mock.patch.object(runner.capture, "apply_transition", side_effect=fake_transition),
                mock.patch.object(runner, "get_entity", side_effect=fake_get),
                mock.patch.object(runner, "fetch_capture_source", return_value={
                    "status": "fetched",
                    "source_url": "https://example.com/source",
                    "bytes_read": 123,
                    "bytes_truncated": False,
                    "title": "Example Source",
                    "text_excerpt": "Example excerpt",
                    "text_truncated": False,
                }),
                mock.patch.object(runner, "put_entity", side_effect=fake_put),
                mock.patch.object(runner.capture, "link"),
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED": "1"}),
                self.lifecycle_mocks()[1],
                self.lifecycle_mocks()[2],
                self.lifecycle_mocks()[4],
            ):
                runner.process_one(root)

            result = runner.read_status(root, "sg0176-test-0001")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["result"], "completed_non_empty_snapshot_drain")
            drain = result["evidence"]["capture_drain"]
            self.assertEqual(drain["frozen_ids"], ["CAP-0001"])
            self.assertEqual(drain["metrics"]["completed_items"], 1)
            self.assertTrue(drain["all_frozen_terminal"])
            first_transition = events.index(("transition", "CAP-0001", "planned", "capturing"))
            first_put = next(index for index, event in enumerate(events) if event[0] == "put" and "memory-stargraph-captures" in event[1])
            completed_transition = events.index(("transition", "CAP-0001", "capturing", "completed"))
            self.assertLess(first_transition, first_put)
            self.assertLess(first_put, completed_transition)
            self.assertIn("notes/memory-stargraph-captures/cap-0001-example-source", drain["outcomes"][0]["target_slug"])

    def test_non_empty_snapshot_terminalizes_item_failure_after_reservation(self):
        values = runner.validate_request(self.make_request())
        run_slug, report_slug = runner.lifecycle_slugs(values)
        snapshot = {
            "invocation_id": "sg0176-test-0001",
            "rows": [{
                "id": "CAP-0001",
                "status": "planned",
                "source": "https://example.com/source",
                "source kind": "url",
                "node": "[[notes/memory-starmap-capture-list/cap-0001-example]]",
                "target": "",
                "notes": "Capture example source.",
            }],
        }
        transitions = []

        def fake_transition(capture_id, expected, target, notes, now=None):
            transitions.append((capture_id, expected, target))
            return {
                "capture_id": capture_id,
                "status": target,
                "child_slug": "notes/memory-starmap-capture-list/cap-0001-example",
                "updated_at": runner.iso_now(),
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch.object(runner.capture, "apply_transition", side_effect=fake_transition),
                mock.patch.object(runner, "get_entity", return_value="# CAP\n"),
                mock.patch.object(runner, "fetch_capture_source", side_effect=runner.RunnerError("fetch refused")),
                mock.patch.object(runner, "update_active_lifecycle"),
            ):
                evidence = runner.drain_frozen_capture_rows(root, values, run_slug, report_slug, snapshot, {"snapshot": snapshot})
        self.assertEqual(evidence["result"], "completed_non_empty_snapshot_drain_with_failures")
        self.assertEqual(evidence["metrics"]["failed_items"], 1)
        self.assertEqual(transitions, [("CAP-0001", "planned", "capturing"), ("CAP-0001", "capturing", "failed")])
        self.assertTrue(evidence["failures"][0]["readback_verified"])

    def test_non_empty_snapshot_processes_in_deterministic_order_and_rejects_stale_row(self):
        values = runner.validate_request(self.make_request())
        run_slug, report_slug = runner.lifecycle_slugs(values)
        good_rows = [
            {"id": "CAP-0002", "status": "planned", "source": "https://example.com/2", "node": "[[notes/cap-2]]", "target": "", "notes": ""},
            {"id": "CAP-0001", "status": "planned", "source": "https://example.com/1", "node": "[[notes/cap-1]]", "target": "", "notes": ""},
        ]
        order = []

        def fake_transition(capture_id, expected, target, notes, now=None):
            if expected == "planned":
                order.append(capture_id)
            return {"capture_id": capture_id, "status": target, "child_slug": f"notes/{capture_id.lower()}", "updated_at": runner.iso_now()}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch.object(runner.capture, "apply_transition", side_effect=fake_transition),
                mock.patch.object(runner, "get_entity", return_value="# CAP\n"),
                mock.patch.object(runner, "fetch_capture_source", return_value={"status": "fetched", "bytes_read": 1, "bytes_truncated": False, "title": "T", "text_excerpt": "E", "text_truncated": False}),
                mock.patch.object(runner, "put_entity"),
                mock.patch.object(runner.capture, "link"),
                mock.patch.object(runner, "update_active_lifecycle"),
            ):
                runner.drain_frozen_capture_rows(root, values, run_slug, report_slug, {"rows": good_rows}, {"snapshot": {"rows": good_rows}})
        self.assertEqual(order, ["CAP-0001", "CAP-0002"])

        stale = {"rows": [{"id": "CAP-0003", "status": "capturing", "source": "https://example.com/3", "node": "[[notes/cap-3]]"}]}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(runner.RunnerPhaseError, "not planned"):
                runner.drain_frozen_capture_rows(Path(tmp), values, run_slug, report_slug, stale, {"snapshot": stale})

    def test_cap0012_shape_builds_bounded_capture_artifact(self):
        values = runner.validate_request(self.make_request(invocation_id="capture-link-drain-20260803t074152-0700-recovery-85"))
        row = {
            "id": "CAP-0012",
            "status": "planned",
            "source": "https://www.salesforce.com/news/stories/toward-self-improving-agents/",
            "source kind": "url",
            "node": "[[notes/memory-starmap-capture-list/cap-0012-https-www-salesforce-com-news-stories-toward-self-improv]]",
            "target": "",
            "notes": "queued",
        }
        child = """---
type: capture
status: planned
---
# CAP-0012

## Capture Instructions

Capture the Salesforce article 'Toward Self-Improving Agents' with source provenance and preserve its key concepts on governed recursive self-improvement, frozen-weight agent optimization, verification, and reward-hacking risks.
"""
        fetched = {
            "status": "fetched",
            "source_url": row["source"],
            "bytes_read": 9000,
            "bytes_truncated": False,
            "title": "Toward Self-Improving Agents",
            "text_excerpt": "Self-improving agents need verification and safeguards against reward hacking.",
            "text_truncated": False,
        }
        slug, artifact = runner.build_capture_artifact(row, child, fetched, values)
        self.assertEqual(slug, "notes/memory-stargraph-captures/cap-0012-toward-self-improving-agents")
        self.assertIn("governed recursive self-improvement", artifact)
        self.assertIn("reward-hacking risks", artifact)
        self.assertIn("https://www.salesforce.com/news/stories/toward-self-improving-agents/", artifact)
        self.assertIn("Self-improving agents need verification", artifact)

    def test_terminalize_lifecycle_clears_active_and_implementing_tags_on_completed_run_and_report(self):
        values = runner.validate_request(self.make_request())
        run_slug = "runs/memory-stargraph-capture-link-drain-sg0176-test-0001"
        report_slug = "reports/memory-stargraph-capture-link-drain-2026-08-08-sg0176-test-0001"

        def fake_get(slug):
            if slug == run_slug:
                return """---
type: run
status: completed
result: completed_empty_snapshot_enrichment
curator_lease: false
active_change: false
tags:
  - capture-link
  - completed
  - curator
  - host-runner
---
# Run
"""
            return """---
type: report
status: completed
result: completed_empty_snapshot_enrichment
active_change: false
tags:
  - capture-link
  - completed
  - curator
  - host-runner
---
# Report
"""

        with (
            mock.patch.object(runner, "put_entity") as put_entity,
            mock.patch.object(runner, "mutate_tag") as mutate_tag,
            mock.patch.object(runner, "read_tags", return_value=["capture-link", "completed", "curator", "host-runner"]),
            mock.patch.object(runner, "get_entity", side_effect=fake_get),
            mock.patch.object(runner, "global_active_tag_readback", return_value={
                "source": runner.GLOBAL_ACTIVE_TAG_READBACK_SOURCE,
                "readback_at": "2026-08-08T08:00:00-07:00",
                "attempt": 1,
                "active_tag_count": 0,
                "active_tag_pages": [],
                "active_tags_clear": True,
            }),
        ):
            evidence = runner.terminalize_lifecycle(
                values,
                run_slug,
                report_slug,
                "completed",
                "completed_empty_snapshot_enrichment",
                {"snapshot": {"rows": []}},
            )

        self.assertTrue(evidence["lifecycle_tags_released"])
        self.assertTrue(evidence["global_active_tag_readback"]["active_tags_clear"])
        self.assertEqual(evidence["global_active_tag_readback"]["active_tag_count"], 0)
        self.assertTrue(evidence["final_terminal_readback"]["global_active_tag_readback"]["active_tags_clear"])
        self.assertEqual(evidence["entities"][run_slug]["stale_lifecycle_tags"], [])
        self.assertEqual(evidence["entities"][report_slug]["stale_lifecycle_tags"], [])
        self.assertIn('"global_active_tag_readback"', put_entity.call_args_list[-2].args[1])
        self.assertIn('"active_tags_clear": true', put_entity.call_args_list[-2].args[1])
        mutate_tag.assert_has_calls([
            mock.call(run_slug, "active", "remove"),
            mock.call(run_slug, "implementing", "remove"),
            mock.call(report_slug, "active", "remove"),
            mock.call(report_slug, "implementing", "remove"),
        ])

    def test_terminalize_lifecycle_clears_lifecycle_tags_on_failed_path(self):
        values = runner.validate_request(self.make_request())
        run_slug = "runs/memory-stargraph-capture-link-drain-sg0176-test-0001"
        report_slug = "reports/memory-stargraph-capture-link-drain-2026-08-08-sg0176-test-0001"

        def fake_get(slug):
            frontmatter = "curator_lease: false\n" if slug == run_slug else ""
            return f"""---
type: {'run' if slug == run_slug else 'report'}
status: failed
result: compaction_before_snapshot_failed
{frontmatter}active_change: false
tags:
  - capture-link
  - failed
  - curator
  - host-runner
---
# Terminal
"""

        with (
            mock.patch.object(runner, "put_entity"),
            mock.patch.object(runner, "mutate_tag"),
            mock.patch.object(runner, "read_tags", return_value=["capture-link", "failed", "curator", "host-runner"]),
            mock.patch.object(runner, "get_entity", side_effect=fake_get),
            mock.patch.object(runner, "global_active_tag_readback", return_value={
                "source": runner.GLOBAL_ACTIVE_TAG_READBACK_SOURCE,
                "readback_at": "2026-08-08T08:00:00-07:00",
                "attempt": 1,
                "active_tag_count": 0,
                "active_tag_pages": [],
                "active_tags_clear": True,
            }),
        ):
            evidence = runner.terminalize_lifecycle(
                values,
                run_slug,
                report_slug,
                "failed",
                "compaction_before_snapshot_failed",
                {"snapshot": {"rows": []}},
            )
        self.assertTrue(evidence["entities"][run_slug]["terminal_lease_fields_verified"])
        self.assertEqual(evidence["entities"][run_slug]["stale_lifecycle_tags"], [])
        self.assertTrue(evidence["global_active_tag_readback"]["active_tags_clear"])

    def test_terminalize_lifecycle_retries_delayed_tag_readback_before_reporting_completion(self):
        values = runner.validate_request(self.make_request())
        run_slug = "runs/memory-stargraph-capture-link-drain-sg0176-test-0001"
        report_slug = "reports/memory-stargraph-capture-link-drain-2026-08-08-sg0176-test-0001"
        tag_reads = [
            ["active", "implementing", "capture-link", "completed"],
            ["capture-link", "completed"],
            ["capture-link", "completed"],
            ["capture-link", "completed"],
            ["capture-link", "completed"],
        ]

        def fake_get(slug):
            return f"""---
type: {'run' if slug == run_slug else 'report'}
status: completed
result: completed_empty_snapshot_enrichment
curator_lease: false
active_change: false
tags:
  - capture-link
  - completed
---
# Terminal
"""

        with (
            mock.patch.object(runner, "put_entity"),
            mock.patch.object(runner, "mutate_tag"),
            mock.patch.object(runner, "read_tags", side_effect=tag_reads),
            mock.patch.object(runner, "get_entity", side_effect=fake_get),
            mock.patch.object(runner, "global_active_tag_readback", return_value={
                "source": runner.GLOBAL_ACTIVE_TAG_READBACK_SOURCE,
                "readback_at": "2026-08-08T08:00:00-07:00",
                "attempt": 1,
                "active_tag_count": 0,
                "active_tag_pages": [],
                "active_tags_clear": True,
            }),
            mock.patch.object(runner.time, "sleep") as sleep,
        ):
            evidence = runner.terminalize_lifecycle(
                values,
                run_slug,
                report_slug,
                "completed",
                "completed_empty_snapshot_enrichment",
                {"snapshot": {"rows": []}},
            )
        self.assertEqual(evidence["entities"][run_slug]["attempt"], 2)
        sleep.assert_called_once_with(runner.TERMINAL_LIFECYCLE_READBACK_DELAY_SECONDS)

    def test_global_active_tag_readback_parses_empty_and_active_rows(self):
        empty = runner.subprocess.CompletedProcess(["gbrain", "list", "--tag", "active"], 0, "No pages found.\n", "")
        active = runner.subprocess.CompletedProcess(
            ["gbrain", "list", "--tag", "active"],
            0,
            "runs/a\trun\t2026-08-08\tActive A\nreports/b\treport\t2026-08-08\tActive B\n",
            "",
        )
        with (
            mock.patch.object(runner.capture, "worker_api_get_json", return_value=None),
            mock.patch.object(runner, "run_gbrain", return_value=empty),
        ):
            self.assertEqual(runner.list_active_tag_pages(), [])
            evidence = runner.global_active_tag_readback()
            self.assertTrue(evidence["active_tags_clear"])
            self.assertEqual(evidence["active_tag_count"], 0)
        with (
            mock.patch.object(runner.capture, "worker_api_get_json", return_value=None),
            mock.patch.object(runner, "run_gbrain", return_value=active),
        ):
            self.assertEqual(
                runner.list_active_tag_pages(),
                [
                    {"slug": "runs/a", "type": "run", "updated": "2026-08-08", "title": "Active A"},
                    {"slug": "reports/b", "type": "report", "updated": "2026-08-08", "title": "Active B"},
                ],
            )

    def test_global_active_tag_readback_fails_closed_when_non_empty_or_unavailable(self):
        active = runner.subprocess.CompletedProcess(
            ["gbrain", "list", "--tag", "active"],
            0,
            "runs/stale\trun\t2026-08-08\tStale Active\n",
            "",
        )
        unavailable = runner.subprocess.CompletedProcess(
            ["gbrain", "list", "--tag", "active"],
            1,
            "",
            "transport unavailable",
        )
        with (
            mock.patch.object(runner.capture, "worker_api_get_json", return_value=None),
            mock.patch.object(runner, "run_gbrain", return_value=active),
            mock.patch.object(runner.time, "sleep"),
        ):
            with self.assertRaisesRegex(runner.RunnerError, "global active tag readback not clear"):
                runner.global_active_tag_readback()
        with (
            mock.patch.object(runner.capture, "worker_api_get_json", return_value=None),
            mock.patch.object(runner, "run_gbrain", return_value=unavailable),
        ):
            with self.assertRaisesRegex(runner.RunnerError, "gbrain active tag list failed"):
                runner.global_active_tag_readback()

    def test_terminalize_lifecycle_rejects_stale_active_or_implementing_tag_readback(self):
        values = runner.validate_request(self.make_request())
        with (
            mock.patch.object(runner, "put_entity"),
            mock.patch.object(runner, "mutate_tag"),
            mock.patch.object(runner, "read_tags", return_value=["active", "implementing", "capture-link"]),
            mock.patch.object(runner, "get_entity", return_value="""---
type: run
status: completed
result: completed_empty_snapshot_enrichment
curator_lease: false
active_change: false
tags:
  - active
  - implementing
  - capture-link
---
# Run
"""),
            mock.patch.object(runner.time, "sleep"),
        ):
            with self.assertRaisesRegex(runner.RunnerError, "terminal lifecycle readback failed"):
                runner.terminalize_lifecycle(
                    values,
                    "runs/memory-stargraph-capture-link-drain-sg0176-test-0001",
                    "reports/memory-stargraph-capture-link-drain-2026-07-30-sg0176-test-0001",
                    "completed",
                    "completed_empty_snapshot_enrichment",
                    {"snapshot": {"rows": []}},
                )

    def test_read_tags_accepts_comma_separated_gbrain_output(self):
        completed = runner.subprocess.CompletedProcess(
            ["gbrain", "tags", "slug"],
            0,
            "capture-link, completed, curator, host-runner\n",
            "",
        )
        with (
            mock.patch.object(runner.capture, "worker_api_get_json", return_value=None),
            mock.patch.object(runner, "run_gbrain", return_value=completed),
        ):
            self.assertEqual(
                runner.read_tags("slug"),
                ["capture-link", "completed", "curator", "host-runner"],
            )

    def test_read_tags_and_page_list_prefer_worker_api(self):
        with (
            mock.patch.object(
                runner.capture,
                "worker_api_get_json",
                side_effect=[
                    {"ok": True, "tags": ["active", "capture-link"]},
                    {
                        "ok": True,
                        "pages": [
                            {
                                "slug": "runs/a",
                                "type": "run",
                                "updated_at": "2026-08-25T10:00:00Z",
                                "title": "Run A",
                            }
                        ],
                    },
                ],
            ),
            mock.patch.object(runner, "run_gbrain") as gbrain,
        ):
            self.assertEqual(runner.read_tags("runs/a"), ["active", "capture-link"])
            self.assertEqual(
                runner.list_active_tag_pages(),
                [{"slug": "runs/a", "type": "run", "updated": "2026-08-25", "title": "Run A"}],
            )
        gbrain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
