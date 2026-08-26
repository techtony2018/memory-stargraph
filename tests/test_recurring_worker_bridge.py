import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.automation import recurring_worker_bridge as bridge


class RecurringWorkerBridgeTests(unittest.TestCase):
    def make_request(self, **overrides):
        payload = bridge.make_request(
            overrides.pop("role", "daily_learning_intake"),
            overrides.pop("operation", "evidence"),
            overrides.pop("invocation_id", "learning-bridge-test-0001"),
            overrides.pop("expected_commit", "abc123"),
            nonce=overrides.pop("nonce", "nonce-bridge-0001"),
            synthetic=overrides.pop("synthetic", True),
            bundle_file=overrides.pop("bundle_file", None),
            expected_evidence_schema=overrides.pop("expected_evidence_schema", None),
        )
        payload.update(overrides)
        return payload

    def test_role_and_operation_allowlists_reject_cross_role_work(self):
        with self.assertRaisesRegex(bridge.BridgeError, "unsupported role"):
            bridge.make_request("product_owner", "evidence", "bad-role-0001", "abc123")
        with self.assertRaisesRegex(bridge.BridgeError, "unsupported operation"):
            bridge.make_request("daily_learning_intake", "remediate", "bad-op-0001", "abc123")
        with self.assertRaisesRegex(bridge.BridgeError, "unsafe identifier"):
            bridge.make_request("daily_learning_intake", "evidence", "bad-Upper-0001", "abc123")

    def test_submit_is_offline_idempotent_and_replay_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self.make_request()
            first = bridge.submit_request(root, request)
            second = bridge.submit_request(root, dict(request))
            self.assertEqual(first["status"], "submitted")
            self.assertEqual(second["status"], "already_submitted")
            changed = dict(request)
            changed["expected_commit"] = "def456"
            with self.assertRaisesRegex(bridge.BridgeError, "replay"):
                bridge.submit_request(root, changed)

    def test_submit_cli_preserves_weekly_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = bridge.main([
                "--runtime-dir", str(root),
                "submit",
                "--role", "sre_daily_reliability",
                "--operation", "evidence",
                "--invocation-id", "sg0196-weekly-cli-0001",
                "--expected-commit", "abc123",
                "--expected-evidence-schema", "memory-stargraph-sre-numeric-evidence-v1",
                "--mode", "weekly_resilience",
                "--nonce", "sg0196-weekly-cli-evidence",
                "--synthetic",
                "--json",
            ])
            self.assertEqual(result, 0)
            request = json.loads(next((root / "incoming").glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(request["mode"], "weekly_resilience")
            self.assertEqual(request["expected_evidence_schema"], "memory-stargraph-sre-numeric-evidence-v1")

    def test_write_bundle_stamps_sre_persist_identity_for_daily_and_weekly(self):
        for mode in ("daily_reliability", "weekly_resilience"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                invocation_id = f"sg0201-{mode.replace('_', '-')}-0001"
                bundle = {
                    "decision_type": "report_only",
                    "artifacts": [
                        {
                            "kind": "run",
                            "slug": f"runs/memory-stargraph-sre-sg0201-{mode.replace('_', '-')}-0001",
                            "markdown": f"---\nstatus: completed\nmode: {mode}\n---\n# SG-0201 {mode}\n",
                        }
                    ],
                }
                with mock.patch("sys.stdin", io.StringIO(json.dumps(bundle))):
                    result = bridge.main([
                        "--runtime-dir", str(root),
                        "write-bundle",
                        "--filename", f"{invocation_id}-decision.json",
                        "--role", "sre_daily_reliability",
                        "--invocation-id", invocation_id,
                        "--json",
                    ])
                self.assertEqual(result, 0)
                written = json.loads((root / "bundles" / f"{invocation_id}-decision.json").read_text(encoding="utf-8"))
                self.assertEqual(written["role"], "sre_daily_reliability")
                self.assertEqual(written["invocation_id"], invocation_id)
                self.assertEqual(written["operation"], "persist")
                values = bridge.validate_request(self.make_request(
                    role="sre_daily_reliability",
                    operation="persist",
                    invocation_id=invocation_id,
                    bundle_file=str(root / "bundles" / f"{invocation_id}-decision.json"),
                ))
                with mock.patch.object(bridge, "gbrain_put"):
                    persisted = bridge.persist_decision(root, values)
                self.assertEqual(persisted["artifact_count"], 1)

    def test_write_bundle_rejects_sre_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = {
                "role": "daily_learning_intake",
                "invocation_id": "wrong-invocation-0001",
                "operation": "evidence",
                "decision_type": "report_only",
                "artifacts": [],
            }
            with mock.patch("sys.stdin", io.StringIO(json.dumps(bundle))):
                result = bridge.main([
                    "--runtime-dir", str(root),
                    "write-bundle",
                    "--filename", "sg0201-mismatch-decision.json",
                    "--role", "sre_daily_reliability",
                    "--invocation-id", "sg0201-sre-identity-0001",
                    "--json",
                ])
            self.assertEqual(result, 1)
            self.assertFalse((root / "bundles" / "sg0201-mismatch-decision.json").exists())

    def test_write_bundle_normalizes_manual_cli_notice_to_no_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invocation_id = "sre-cli-version-assessment-sg0204-0001"
            bundle = {
                "decision_type": "cli_version_notice_assessment",
                "assessment_type": "manual_read_only_cli_notice",
                "decision": "compatible_no_action_defer_to_authorized_maintenance_window",
                "terminal_status": "completed_no_action_cli_update_notice_deferred",
                "incident": False,
                "remediation": "no-op",
                "todo_created_or_updated": False,
                "artifacts": [
                    {
                        "kind": "run",
                        "slug": "runs/memory-stargraph-sre-sg0204-cli-version-assessment",
                        "markdown": "---\nstatus: completed\n---\n# SG-0204 CLI Version Assessment\n",
                    }
                ],
            }
            with mock.patch("sys.stdin", io.StringIO(json.dumps(bundle))):
                result = bridge.main([
                    "--runtime-dir", str(root),
                    "write-bundle",
                    "--filename", f"{invocation_id}-decision.json",
                    "--role", "sre_daily_reliability",
                    "--invocation-id", invocation_id,
                    "--json",
                ])
            self.assertEqual(result, 0)
            written = json.loads((root / "bundles" / f"{invocation_id}-decision.json").read_text(encoding="utf-8"))
            self.assertEqual(written["decision_type"], "no_action")
            self.assertEqual(written["decision_type_normalized_from"], "cli_version_notice_assessment")
            values = bridge.validate_request(self.make_request(
                role="sre_daily_reliability",
                operation="persist",
                invocation_id=invocation_id,
                bundle_file=str(root / "bundles" / f"{invocation_id}-decision.json"),
            ))
            with mock.patch.object(bridge, "gbrain_put"):
                persisted = bridge.persist_decision(root, values)
            self.assertEqual(persisted["decision_type"], "no_action")
            self.assertEqual(persisted["artifact_count"], 1)

    def test_write_bundle_rejects_unknown_sre_decision_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = {
                "decision_type": "manual_custom_assessment",
                "assessment_type": "manual_read_only_cli_notice",
                "decision": "compatible_no_action",
                "incident": False,
                "remediation": "no-op",
                "todo_created_or_updated": False,
                "artifacts": [],
            }
            with mock.patch("sys.stdin", io.StringIO(json.dumps(bundle))):
                result = bridge.main([
                    "--runtime-dir", str(root),
                    "write-bundle",
                    "--filename", "sg0204-unknown-decision.json",
                    "--role", "sre_daily_reliability",
                    "--invocation-id", "sre-cli-version-assessment-sg0204-0002",
                    "--json",
                ])
            self.assertEqual(result, 1)
            self.assertFalse((root / "bundles" / "sg0204-unknown-decision.json").exists())

    def test_learning_evidence_bundle_has_required_slots_and_phase_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = bridge.validate_request(self.make_request())
            with (
                mock.patch.object(bridge, "local_health", return_value={"ok": True, "ui_version": "V1.0.174"}),
                mock.patch.object(bridge, "gbrain_get", return_value=(True, "body")),
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED": "1"}),
            ):
                evidence = bridge.gather_learning_evidence(root, values)
            self.assertEqual(evidence["evidence_schema"], "memory-stargraph-learning-evidence-v1")
            self.assertEqual(evidence["evaluator"]["question_count"], 10)
            self.assertEqual(evidence["retrieval_quality_benchmark"]["summary"]["question_count"], 10)
            self.assertTrue(all(evidence["retrieval_quality_benchmark"]["gate"].values()))
            self.assertFalse(evidence["resolver_metrics"]["approval_required"])
            state = bridge.read_state(root)
            self.assertIn("heartbeat_at", state)
            self.assertEqual(state["active_role"], "daily_learning_intake")

    def test_sre_evidence_is_read_only_and_has_incident_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = bridge.validate_request(self.make_request(role="sre_daily_reliability"))
            numeric = {
                "schema": "memory-stargraph-sre-numeric-evidence-v1",
                "health_latency": {"local_health_ms": bridge.numeric_sample(12, "ms")},
                "resources": {
                    "cpu": {"load_average_1m": bridge.numeric_sample(0.1, "load")},
                    "memory": {"available_mb": bridge.numeric_sample(2048, "MiB")},
                    "disk": {"free_bytes": bridge.numeric_sample(1000, "bytes")},
                    "cache": {"graph_cache_bytes": bridge.numeric_sample(100, "bytes")},
                    "open_files": {"current_process_open_fd_count": bridge.numeric_sample(10, "count")},
                },
                "queue_backlog": {"todo_counts": {"planned": bridge.numeric_sample(0, "count")}},
                "latency_baselines": {"search_7_day": {}, "search_30_day": {}, "health_7_day": {}, "health_30_day": {}},
                "backup": {"status": "ok"},
                "restore_rehearsal": {"status": "ok"},
                "evidence_gaps": [],
            }
            with (
                mock.patch.object(bridge, "local_health", return_value={"ok": True, "ui_version": "V1.0.174", "latency_ms": 12}),
                mock.patch.object(bridge, "collect_sre_numeric_evidence", return_value=numeric),
            ):
                evidence = bridge.gather_sre_evidence(root, values)
            self.assertEqual(evidence["evidence_schema"], "memory-stargraph-sre-evidence-v1")
            self.assertFalse(evidence["incident_classification"]["incident"])
            self.assertFalse(evidence["incident_classification"]["remediation_attempted"])
            self.assertEqual(evidence["metrics"]["resolver"]["events_created"], 0)
            baseline = evidence["metrics"]["retrieval_quality_baseline"]
            self.assertEqual(baseline["summary"]["question_count"], 10)
            self.assertTrue(all(baseline["gate"].values()))
            self.assertEqual(evidence["numeric_sre_evidence"]["schema"], "memory-stargraph-sre-numeric-evidence-v1")
            self.assertEqual(evidence["metrics"]["backup"]["status"], "ok")
            self.assertIn("latency_baselines", evidence["metrics"])

    def test_sre_numeric_evidence_has_units_thresholds_and_read_only_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_dirs(root)
            values = bridge.validate_request(self.make_request(role="sre_daily_reliability", mode="weekly_resilience"))
            backup_text = "- Run timestamp UTC: 2026-08-09T10:00:01Z\n- Resolver events exported: 7\n- Link rows exported: 9\n"
            with (
                mock.patch.object(bridge, "gbrain_get", side_effect=[(True, "| SG-0196 | planned | P1 | Title | [[notes/x]] | 2026-08-09 | Note |\n"), (True, backup_text)]),
                mock.patch.object(bridge, "parse_latency_baselines", return_value={"search_7_day": {"max_ms": bridge.numeric_sample(10000, "ms")}, "search_30_day": {"max_ms": bridge.numeric_sample(11000, "ms")}}),
                mock.patch.object(bridge, "parse_restore_rehearsal", return_value={"status": "ok", "recency_seconds": bridge.numeric_sample(3600, "seconds"), "checksum_matched": True}),
                mock.patch.object(bridge, "collect_resource_storage_samples", return_value={
                    "cpu": {"normalized_load_1m": bridge.numeric_sample(0.1, "ratio", threshold={"warn_above": 0.75})},
                    "memory": {"available_mb": bridge.numeric_sample(4096, "MiB", threshold={"warn_below_mb": 1024})},
                    "disk": {"free_bytes": bridge.numeric_sample(1_000_000, "bytes")},
                    "cache": {"graph_cache_age_seconds": bridge.numeric_sample(60, "seconds")},
                    "open_files": {"current_process_open_fd_count": bridge.numeric_sample(12, "count")},
                    "bridge_spool": {"incoming_count": bridge.numeric_sample(0, "count")},
                }),
                mock.patch.object(bridge, "iso_now", return_value="2026-08-10T09:00:00-07:00"),
            ):
                evidence = bridge.collect_sre_numeric_evidence(root, values, {"latency_ms": 25})
            self.assertEqual(evidence["schema"], "memory-stargraph-sre-numeric-evidence-v1")
            self.assertTrue(evidence["read_only"])
            self.assertEqual(evidence["mode"], "weekly_resilience")
            self.assertEqual(evidence["health_latency"]["local_health_ms"]["unit"], "ms")
            self.assertIn("threshold", evidence["resources"]["memory"]["available_mb"])
            self.assertEqual(evidence["backup"]["status"], "ok")
            self.assertEqual(evidence["restore_rehearsal"]["status"], "ok")
            self.assertFalse(evidence["prohibited_actions"]["backup_mutation"])
            self.assertEqual(evidence["queue_backlog"]["todo_counts"]["planned"]["value"], 1)

    def test_sre_numeric_evidence_records_schema_valid_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = bridge.validate_request(self.make_request(role="sre_daily_reliability"))
            with (
                mock.patch.object(bridge, "gbrain_get", side_effect=[(False, "todo unavailable"), (False, "backup unavailable")]),
                mock.patch.object(bridge, "collect_resource_storage_samples", return_value={"cpu": {}, "memory": {}, "disk": {}, "cache": {}, "open_files": {}, "bridge_spool": {}}),
                mock.patch.object(bridge, "parse_latency_baselines", return_value={}),
                mock.patch.object(bridge, "parse_restore_rehearsal", return_value={"status": "missing"}),
            ):
                evidence = bridge.collect_sre_numeric_evidence(root, values, {"latency_ms": None})
            self.assertEqual(evidence["backup"]["status"], "missing")
            self.assertIn("todo_backlog", evidence["evidence_gaps"])
            self.assertIn("backup_latest", evidence["evidence_gaps"])

    def test_decision_bundle_validates_slug_prefixes_and_todo_duplicate_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_dirs(root)
            bundle_path = root / "bundles" / "decision.json"
            bundle = {
                "role": "daily_learning_intake",
                "operation": "persist",
                "invocation_id": "learning-bridge-test-0001",
                "decision_type": "todo_planned",
                "artifacts": [
                    {
                        "kind": "todo",
                        "slug": "notes/memory-starmap-todo-list/bridge-test-todo",
                        "duplicate_policy": {"dedupe_key": "bridge-test", "checked_existing": True},
                        "markdown": "---\ntype: task\nstatus: planned\n---\n# Bridge Test\n",
                    }
                ],
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            values = bridge.validate_request(self.make_request(operation="persist", bundle_file=str(bundle_path)))
            with mock.patch.object(bridge, "gbrain_put") as put:
                result = bridge.persist_decision(root, values)
            self.assertEqual(result["artifact_count"], 1)
            put.assert_called_once()

    def test_sre_decision_bundle_accepts_numeric_summary_and_keeps_old_schema_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_dirs(root)
            bundle_path = root / "bundles" / "decision.json"
            bundle = {
                "role": "sre_daily_reliability",
                "operation": "persist",
                "invocation_id": "learning-bridge-test-0001",
                "decision_type": "report_only",
                "numeric_sre_evidence_summary": {"schema": "memory-stargraph-sre-numeric-evidence-v1", "status": "ok"},
                "artifacts": [{
                    "kind": "run",
                    "slug": "runs/memory-stargraph-sre-bridge-test",
                    "markdown": "---\nstatus: completed\n---\n# SRE Bridge Test\n",
                }],
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            values = bridge.validate_request(self.make_request(role="sre_daily_reliability", operation="persist", bundle_file=str(bundle_path)))
            with mock.patch.object(bridge, "gbrain_put"):
                result = bridge.persist_decision(root, values)
            self.assertEqual(result["numeric_sre_evidence_summary"]["schema"], "memory-stargraph-sre-numeric-evidence-v1")

            old_bundle = dict(bundle)
            old_bundle.pop("numeric_sre_evidence_summary")
            bundle_path.write_text(json.dumps(old_bundle), encoding="utf-8")
            with mock.patch.object(bridge, "gbrain_put"):
                old_result = bridge.persist_decision(root, values)
            self.assertNotIn("numeric_sre_evidence_summary", old_result)

    def test_persist_rejects_raw_manual_cli_notice_alias_if_writer_bypassed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_dirs(root)
            bundle_path = root / "bundles" / "decision.json"
            bundle = {
                "role": "sre_daily_reliability",
                "operation": "persist",
                "invocation_id": "sre-cli-version-assessment-sg0204-0003",
                "decision_type": "cli_version_notice_assessment",
                "assessment_type": "manual_read_only_cli_notice",
                "decision": "compatible_no_action",
                "incident": False,
                "remediation": "no-op",
                "todo_created_or_updated": False,
                "artifacts": [{
                    "kind": "run",
                    "slug": "runs/memory-stargraph-sre-sg0204-raw-alias",
                    "markdown": "---\nstatus: completed\n---\n# SG-0204 Raw Alias\n",
                }],
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            values = bridge.validate_request(self.make_request(
                role="sre_daily_reliability",
                operation="persist",
                invocation_id="sre-cli-version-assessment-sg0204-0003",
                bundle_file=str(bundle_path),
            ))
            with self.assertRaisesRegex(bridge.BridgePhaseError, "unsupported decision_type"):
                bridge.persist_decision(root, values)

    def test_gbrain_put_falls_back_to_stargraph_save_and_raw_readback(self):
        calls = []

        def fake_run_cmd(args, **kwargs):
            calls.append(args)
            if args[:3] == ["gbrain", "put", "runs/memory-stargraph-learning-test"]:
                return bridge.subprocess.CompletedProcess(args, 1, "", "cli failed")
            if "/api/entity-save/runs%2Fmemory-stargraph-learning-test" in args[-1]:
                return bridge.subprocess.CompletedProcess(args, 0, json.dumps({"ok": True}), "")
            if "/api/entity-raw/runs%2Fmemory-stargraph-learning-test" in args[-1]:
                return bridge.subprocess.CompletedProcess(args, 0, json.dumps({"content": "---\nstatus: completed\n---\nBody"}), "")
            return bridge.subprocess.CompletedProcess(args, 1, "", "unexpected")

        with mock.patch.object(bridge, "run_cmd", side_effect=fake_run_cmd):
            bridge.gbrain_put("runs/memory-stargraph-learning-test", "---\nstatus: completed\n---\nBody")

        self.assertTrue(any("/api/entity-save/runs%2Fmemory-stargraph-learning-test" in call[-1] for call in calls))
        self.assertTrue(any("/api/entity-raw/runs%2Fmemory-stargraph-learning-test" in call[-1] for call in calls))

    def test_gbrain_get_and_put_prefer_stargraph_api(self):
        markdown = "---\nstatus: completed\n---\nBody"
        with (
            mock.patch.object(bridge, "stargraph_raw", return_value=markdown),
            mock.patch.object(bridge, "stargraph_save", return_value=True),
            mock.patch.object(bridge, "run_cmd") as cli,
        ):
            self.assertEqual(bridge.gbrain_get("runs/example"), (True, markdown))
            bridge.gbrain_put("runs/example", markdown)
        cli.assert_not_called()

    def test_markdown_readback_allows_normalized_frontmatter_but_rejects_body_change(self):
        expected = "---\ntype: run\nstatus: completed\ntags:\n- synthetic\n- sg0179\n---\n# Title\n\nBody\n"
        normalized = "---\ntype: run\ntitle: Title\nstatus: completed\ntags:\n  - sg0179\n  - synthetic\n---\n# Title\n\nBody\n"
        changed = "---\ntype: run\nstatus: completed\ntags:\n  - synthetic\n---\n# Title\n\nChanged\n"
        self.assertTrue(bridge.markdown_readback_matches(expected, normalized))
        self.assertFalse(bridge.markdown_readback_matches(expected, changed))

    def test_decision_bundle_rejects_unsafe_slug_and_missing_duplicate_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_dirs(root)
            bundle_path = root / "bundles" / "decision.json"
            bundle = {
                "role": "daily_learning_intake",
                "operation": "persist",
                "invocation_id": "learning-bridge-test-0001",
                "decision_type": "todo_planned",
                "artifacts": [{"kind": "todo", "slug": "secrets/outside", "markdown": "---\nstatus: planned\n---\n# Bad\n"}],
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            values = bridge.validate_request(self.make_request(operation="persist", bundle_file=str(bundle_path)))
            with self.assertRaisesRegex(bridge.BridgePhaseError, "slug outside role allowlist"):
                bridge.persist_decision(root, values)

    def test_decision_bundle_rejects_uppercase_artifact_slugs_before_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_dirs(root)
            bundle_path = root / "bundles" / "decision.json"
            bundle = {
                "role": "daily_learning_intake",
                "operation": "persist",
                "invocation_id": "learning-bridge-test-0001",
                "decision_type": "no_action",
                "artifacts": [{
                    "kind": "run",
                    "slug": "runs/memory-stargraph-learning-Bad",
                    "markdown": "---\nstatus: completed\n---\n# Bad\n",
                }],
            }
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            values = bridge.validate_request(self.make_request(operation="persist", bundle_file=str(bundle_path)))
            with self.assertRaisesRegex(bridge.BridgePhaseError, "lowercase"):
                bridge.persist_decision(root, values)

    def test_process_one_evidence_terminalizes_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.submit_request(root, self.make_request(expected_commit="abc123"))
            with (
                mock.patch.object(bridge, "current_commit", return_value="abc123"),
                mock.patch.object(bridge, "gather_learning_evidence", return_value={"evidence_schema": "memory-stargraph-learning-evidence-v1"}),
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED": "1"}),
            ):
                processed = bridge.process_one(root)
            self.assertEqual(processed["status"], "processed")
            result = bridge.read_status(root, "learning-bridge-test-0001", "evidence")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["result"], "evidence_bundle_completed")
            self.assertEqual(result["runner_identity"]["runner_host_commit"], "abc123")
            self.assertTrue(result["runner_identity"]["deployed_source_match"])
            self.assertIn("memory-stargraph-learning-evidence-v1", result["runner_identity"]["supported_evidence_schemas"])
            self.assertFalse(bridge.lock_path(root).exists())

    def test_process_one_fails_closed_when_runner_commit_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.submit_request(root, self.make_request(expected_commit="newcommit"))
            with (
                mock.patch.object(bridge, "current_commit", return_value="oldcommit"),
                mock.patch.object(bridge, "gather_learning_evidence") as gather,
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED": "1"}),
            ):
                processed = bridge.process_one(root)
            self.assertEqual(processed["status"], "processed")
            gather.assert_not_called()
            result = bridge.read_status(root, "learning-bridge-test-0001", "evidence")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["result"], "runner_identity_failed")
            self.assertEqual(result["evidence"]["failed_phase"], "runner_identity")
            self.assertTrue(result["runner_identity"]["stale_runner"])
            self.assertIn("expected_commit_mismatch", result["runner_identity"]["stale_reason"])
            self.assertFalse(bridge.lock_path(root).exists())

    def test_process_one_fails_closed_when_expected_schema_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self.make_request(
                role="sre_daily_reliability",
                expected_commit="abc123",
                expected_evidence_schema="memory-stargraph-sre-evidence-v0",
            )
            bridge.submit_request(root, request)
            with (
                mock.patch.object(bridge, "current_commit", return_value="abc123"),
                mock.patch.object(bridge, "gather_sre_evidence") as gather,
                mock.patch.dict(os.environ, {"MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED": "1"}),
            ):
                processed = bridge.process_one(root)
            self.assertEqual(processed["status"], "processed")
            gather.assert_not_called()
            result = bridge.read_status(root, "learning-bridge-test-0001", "evidence")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["result"], "runner_identity_failed")
            self.assertIn("expected_evidence_schema_unsupported", result["runner_identity"]["stale_reason"])
            self.assertFalse(bridge.lock_path(root).exists())

    def test_crash_recovery_terminalizes_stale_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge.ensure_dirs(root)
            request = self.make_request()
            processing = bridge.processing_path(root, request["nonce"])
            processing.write_text(json.dumps(request), encoding="utf-8")
            old = bridge.time.time() - bridge.PROCESSING_TIMEOUT_SECONDS - 5
            os.utime(processing, (old, old))
            recovered = bridge.recover_stale_processing(root)
            self.assertEqual(recovered, ["learning-bridge-test-0001"])
            result = bridge.read_status(root, "learning-bridge-test-0001", "evidence")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["result"], "processing_timeout_recovered")

    def test_bridge_disabled_by_default_and_health_reports_102_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(bridge.BridgeError, "disabled"):
                bridge.run_loop(root, max_iterations=1)
            health = bridge.health(root)
            self.assertFalse(health["current_process_runner_enabled"])
            self.assertIn("daily_learning_intake", health["allowed_roles"])
            self.assertIn("runner_host_commit", health["runner_identity"])
            self.assertIn("memory-stargraph-sre-numeric-evidence-v1", health["runner_identity"]["supported_evidence_schemas"])
            self.assertTrue((health["daemon_state"] or {}).get("configured_remote_runner_disabled", True))


if __name__ == "__main__":
    unittest.main()
