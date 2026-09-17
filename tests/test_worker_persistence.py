import json
import tempfile
import unittest
from pathlib import Path

from scripts.automation import worker_persistence as persistence


RUN_MARKDOWN = """---
type: run
title: Worker Persistence Acceptance
tags:
  - active
  - capture-link
  - implementing
status: implementing
active_change: false
---

# Worker Persistence Acceptance
"""


class WorkerPersistenceTests(unittest.TestCase):
    def test_entity_save_response_accepts_durable_indexing_pending(self):
        payload = {
            "ok": True,
            "persisted": True,
            "persistence": {
                "persisted": True,
                "readback_verified": True,
                "mode": "durable_no_embed",
                "indexing_status": "pending",
                "degraded": True,
            },
        }

        result = persistence.entity_save_response_persistence(payload)

        self.assertEqual(result["indexing_status"], "pending")
        self.assertEqual(result["mode"], "durable_no_embed")
        self.assertTrue(result["degraded"])

    def test_entity_save_response_rejects_false_or_malformed_durability(self):
        self.assertIsNone(
            persistence.entity_save_response_persistence(
                {"ok": True, "persisted": False, "indexing_status": "pending"}
            )
        )
        self.assertIsNone(
            persistence.entity_save_response_persistence(
                {
                    "ok": True,
                    "persisted": True,
                    "persistence": {
                        "persisted": True,
                        "indexing_status": "eventually_maybe",
                    },
                }
            )
        )

    def test_route_candidates_prefer_configured_dashboard_route_over_loopback(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "deployment-targets.env"
            config.write_text(
                "MEMORY_STARGRAPH_DASHBOARD_URL='https://memory-stargraph.example.test'\n"
                "MEMORY_STARGRAPH_DASHBOARD_CURL_FLAGS='--connect-timeout 5'\n"
                "MEMORY_STARGRAPH_LOCAL_URL='https://127.0.0.1:8788'\n"
                "MEMORY_STARGRAPH_LOCAL_CURL_FLAGS='-k'\n",
                encoding="utf-8",
            )

            records = persistence.route_records(config)

        self.assertEqual(records[0]["base_url"], "https://memory-stargraph.example.test")
        self.assertEqual(records[0]["curl_flags"], ["--connect-timeout", "5"])
        self.assertTrue(str(records[0]["source"]).endswith(":MEMORY_STARGRAPH_DASHBOARD_URL"))
        self.assertFalse(records[0]["loopback"])
        self.assertTrue(records[1]["loopback"])

    def test_save_payload_safely_preserves_markdown_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "run.md"
            source.write_text('---\ntitle: "Quoted"\n---\n\n# Body\n{"x": "$HOME"}\n', encoding="utf-8")

            payload = persistence.save_payload(source)

        self.assertEqual(payload["content"], '---\ntitle: "Quoted"\n---\n\n# Body\n{"x": "$HOME"}\n')
        self.assertEqual(json.loads(json.dumps(payload))["content"], payload["content"])

    def test_tag_payload_requires_a_real_mutation(self):
        with self.assertRaisesRegex(persistence.WorkerPersistenceError, "at least one"):
            persistence.tag_payload([], [])

    def test_verify_tags_detects_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.json"
            raw.write_text(json.dumps({"content": RUN_MARKDOWN.replace("  - active\n", "")}), encoding="utf-8")

            result = persistence.verify_tags_payload(raw, add=["capture-link"], remove=["active"])

        self.assertTrue(result["ok"])
        self.assertIn("capture-link", result["tags"])
        self.assertNotIn("active", result["tags"])

    def test_prepare_save_emits_explicit_top_level_curl_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = tmp_path / "deployment-targets.env"
            config.write_text(
                "MEMORY_STARGRAPH_DASHBOARD_URL='https://100.100.126.85:8788'\n"
                "MEMORY_STARGRAPH_DASHBOARD_CURL_FLAGS='-k'\n"
                "MEMORY_STARGRAPH_LOCAL_URL='https://127.0.0.1:8788'\n",
                encoding="utf-8",
            )
            source = tmp_path / "run.md"
            source.write_text(RUN_MARKDOWN, encoding="utf-8")

            prepared = persistence.prepare_request(
                "save",
                "runs/curator-long-run",
                source_file=source,
                output_dir=tmp_path / "prepared",
                config_path=config,
            )

            self.assertTrue(prepared["ok"])
            self.assertEqual(prepared["route"]["base_url"], "https://100.100.126.85:8788")
            self.assertFalse(prepared["route"]["loopback"])
            self.assertEqual(prepared["encoded_slug"], "runs%2Fcurator-long-run")
            self.assertEqual(json.loads(Path(prepared["payload_file"]).read_text())["content"], RUN_MARKDOWN)
            commands = prepared["commands"]
            self.assertEqual([command["step"] for command in commands], ["save", "readback"])
            self.assertTrue(commands[0]["argv"][0] == "curl")
            self.assertIn("-k", commands[0]["argv"])
            self.assertIn("-d", commands[0]["argv"])
            self.assertIn(f"@{prepared['payload_file']}", commands[0]["argv"])
            self.assertIn("https://100.100.126.85:8788/api/entity-save/runs%2Fcurator-long-run", commands[0]["argv"])
            self.assertIn("curl -sS --fail -k", commands[0]["shell"])
            self.assertIn("verify-save", prepared["offline_verify"]["shell"])

    def test_prepare_tags_emits_payload_and_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = tmp_path / "deployment-targets.env"
            config.write_text("MEMORY_STARGRAPH_DASHBOARD_URL='https://dashboard.example.test'\n", encoding="utf-8")

            prepared = persistence.prepare_request(
                "tags",
                "runs/test-run",
                output_dir=tmp_path / "prepared",
                add=["completed"],
                remove=["active", "implementing"],
                config_path=config,
            )

            self.assertEqual(json.loads(Path(prepared["payload_file"]).read_text()), {
                "add": ["completed"],
                "remove": ["active", "implementing"],
            })
            self.assertIn("/api/entity-tags/runs%2Ftest-run", prepared["commands"][0]["shell"])
            self.assertIn("verify-tags", prepared["offline_verify"]["shell"])
            self.assertIn("--remove active", prepared["offline_verify"]["shell"])

    def test_prepare_refuses_loopback_only_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "deployment-targets.env"
            config.write_text("MEMORY_STARGRAPH_LOCAL_URL='https://127.0.0.1:8788'\n", encoding="utf-8")

            with self.assertRaisesRegex(persistence.WorkerPersistenceError, "non-loopback"):
                persistence.prepare_request("read", "runs/test-run", config_path=config)

    def test_save_accepts_canonicalized_frontmatter_order(self):
        expected = """---
type: run
status: completed
result: completed
tags:
  - completed
  - capture-link
---

# Same Body
"""
        actual = """---
result: completed
type: run
tags:
  - capture-link
  - completed
status: completed
---

# Same Body
"""

        self.assertTrue(persistence._raw_readback_matches(expected, actual))

    def test_save_accepts_long_folded_title_and_report_slug(self):
        expected = """---
type: run
title: Memory Stargraph Curator Empty Queue Enrichment Run With A Very Long Title That GBrain May Fold
report_slug: reports/memory-stargraph-capture-link-drain-2026-07-30-sg0171-empty-queue-enrichment-85
status: completed
tags:
  - completed
  - capture-link
---

# Curator Run
"""
        actual = """---
status: completed
report_slug: >-
  reports/memory-stargraph-capture-link-drain-2026-07-30-sg0171-empty-queue-enrichment-85
title: >-
  Memory Stargraph Curator Empty Queue Enrichment Run With A Very Long Title
  That GBrain May Fold
type: run
tags:
  - capture-link
  - completed
---

# Curator Run
"""

        self.assertTrue(persistence._raw_readback_matches(expected, actual))

    def test_save_accepts_timestamp_normalization(self):
        expected = """---
type: run
started_at: '2026-07-30T10:20:40-07:00'
completed_at: 2026-07-30 10:21:40-07:00
tags:
  - completed
---

# Timestamp Run
"""
        actual = """---
completed_at: '2026-07-30T10:21:40-07:00'
started_at: 2026-07-30 10:20:40-07:00
type: run
tags: [completed]
---

# Timestamp Run
"""

        self.assertTrue(persistence._raw_readback_matches(expected, actual))

    def test_save_accepts_equivalent_timestamp_offsets(self):
        expected = "---\nstarted_at: 2026-09-16T21:13:05-07:00\n---\n\n# Run\n"
        actual = "---\nstarted_at: '2026-09-17T04:13:05.000Z'\n---\n\n# Run\n"

        self.assertTrue(persistence._raw_readback_matches(expected, actual))

    def test_save_accepts_canonical_utc_midnight_for_bare_date(self):
        expected = "---\ncreated_at: 2026-09-17\n---\n\n# Run\n"
        actual = "---\ncreated_at: '2026-09-17T00:00:00.000Z'\n---\n\n# Run\n"

        self.assertTrue(persistence._raw_readback_matches(expected, actual))

    def test_save_accepts_reordered_tags(self):
        expected = """---
type: run
tags:
  - completed
  - capture-link
  - memory-stargraph
---

# Tags Run
"""
        actual = """---
type: run
tags:
  - memory-stargraph
  - completed
  - capture-link
---

# Tags Run
"""

        self.assertTrue(persistence._raw_readback_matches(expected, actual))

    def test_save_rejects_true_scalar_mismatch(self):
        expected = "---\ntype: run\nstatus: completed\n---\n\n# Scalar Run\n"
        actual = "---\ntype: run\nstatus: failed\n---\n\n# Scalar Run\n"

        self.assertFalse(persistence._raw_readback_matches(expected, actual))

    def test_save_rejects_true_body_mismatch(self):
        expected = "---\ntype: run\nstatus: completed\n---\n\n# Body Run\n\nExpected body.\n"
        actual = "---\ntype: run\nstatus: completed\n---\n\n# Body Run\n\nDifferent body.\n"

        self.assertFalse(persistence._raw_readback_matches(expected, actual))

    def test_body_policy_allows_only_one_optional_final_newline(self):
        expected = "---\ntype: run\n---\n\n# Body Run\n"
        actual = "---\ntype: run\n---\n\n# Body Run"
        extra = "---\ntype: run\n---\n\n# Body Run\n\n"

        self.assertTrue(persistence._raw_readback_matches(expected, actual))
        self.assertFalse(persistence._raw_readback_matches(expected, extra))


if __name__ == "__main__":
    unittest.main()
