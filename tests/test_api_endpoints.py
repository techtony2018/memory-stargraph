import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import server
from server import MemoryStargraphHandler


TEST_GRAPH = {
    "title": "Memory Stargraph",
    "source": {"mode": "test", "status": "ok"},
    "stats": {"nodes": 1, "edges": 0},
    "nodes": [
        {
            "slug": "people/tony-guan",
            "label": "Tony Guan",
            "type": "person",
            "category": "people",
            "summary": "Test node",
            "links": [],
            "degree": 0,
        }
    ],
    "edges": [],
}


class FakeStore:
    def __init__(self):
        self.calls = []
        self.graph = TEST_GRAPH

    def get_seed_graph(self, force=False):
        self.calls.append(("get_seed_graph", force))
        return TEST_GRAPH

    def create_entity(self, name, description="", category="entities"):
        self.calls.append(("create_entity", name, description, category))
        return "people/new-person"

    def add_relationship(self, source_slug, target_slug, link_type, context=""):
        self.calls.append(("add_relationship", source_slug, target_slug, link_type, context))

    def remove_relationship(self, source_slug, target_slug, link_type=""):
        self.calls.append(("remove_relationship", source_slug, target_slug, link_type))

    def update_tags(self, slug, add_tags=None, remove_tags=None):
        self.calls.append(("update_tags", slug, tuple(add_tags or []), tuple(remove_tags or [])))

    def add_timeline_event(self, slug, date, summary, detail="", source=""):
        self.calls.append(("add_timeline_event", slug, date, summary, detail, source))

    def timeline(self, slug):
        self.calls.append(("timeline", slug))
        return "# Timeline\n\n- 2026-06-29: Updated node ops"

    def ask_gbrain(self, slug, question):
        self.calls.append(("ask_gbrain", slug, question))
        return "answer"

    def ask_yoda(self, slug, question, history=None, depth=4):
        self.calls.append(("ask_yoda", slug, question, tuple(history or []), depth))
        return {"output": "yoda answer", "source": "fallback", "timings": {"total_ms": 12}}

    def backlinks(self, slug):
        self.calls.append(("backlinks", slug))
        return "backlinks"

    def graph_query(self, slug, link_type="", direction="both", depth="1"):
        self.calls.append(("graph_query", slug, link_type, direction, depth))
        return "graph query"

    def attach_file(self, slug, file_path, description=""):
        self.calls.append(("attach_file", slug, file_path, description))

    def history(self, slug):
        self.calls.append(("history", slug))
        return "history"

    def refresh_embedding(self, slug):
        self.calls.append(("refresh_embedding", slug))

    def get_entity_media(self, slug):
        self.calls.append(("get_entity_media", slug))
        return [{"kind": "image", "url": "https://example.com/cover.jpg", "label": "Cover", "embeddable": True}]

    def list_take_proposals(self, filters=None):
        self.calls.append(("list_take_proposals", dict(filters or {})))
        return {
            "proposals": [
                {
                    "id": "tp-1",
                    "claim": "Memory Stargraph needs take review",
                    "holder": "people/tony-guan",
                    "source_page_slug": "notes/source",
                    "source_exists": True,
                }
            ],
            "counts": {"pending": 1},
            "next_cursor": "cursor-2",
        }

    def review_take_proposal(self, proposal_id, action, payload=None):
        self.calls.append(("review_take_proposal", proposal_id, action, dict(payload or {})))
        return {"ok": True, "proposal_id": proposal_id, "action": action, "acted_by": payload.get("acted_by")}

    def bulk_review_take_proposals(self, payload=None):
        self.calls.append(("bulk_review_take_proposals", dict(payload or {})))
        return {"ok": True, "results": [{"id": item, "status": payload.get("action")} for item in payload.get("ids", [])]}

    def list_takes(self, filters=None):
        self.calls.append(("list_takes", dict(filters or {})))
        holder = filters.get("holder") or filters.get("page_slug") or "people/tony-guan"
        takes = [
            {"id": f"take-{index}", "claim": f"Existing take {index}", "holder": holder}
            for index in range(1, 20)
        ]
        return {"takes": takes}


class SingleRowTakeStore(FakeStore):
    def list_takes(self, filters=None):
        self.calls.append(("list_takes", dict(filters or {})))
        return {
            "id": 240,
            "page_slug": "blogs/tony-guan/msn/20051115-28-e7b3f54e",
            "claim": "Existing single-row take",
            "kind": "take",
            "holder": "people/tony-guan",
            "takes": [],
        }


class ApiEndpointTests(unittest.TestCase):
    def dispatch_post(self, path, payload=None):
        handler = object.__new__(MemoryStargraphHandler)
        handler.path = path
        captured = {}

        def read_json_body(self):
            return payload or {}

        def end_json(self, response_payload, status=200):
            captured["status"] = int(status)
            captured["payload"] = json.loads(json.dumps(response_payload))
            return captured["payload"]

        handler.read_json_body = types.MethodType(read_json_body, handler)
        handler.end_json = types.MethodType(end_json, handler)
        MemoryStargraphHandler.do_POST(handler)
        return captured["status"], captured["payload"]

    def dispatch_get(self, path):
        handler = object.__new__(MemoryStargraphHandler)
        handler.path = path
        captured = {}

        def end_json(self, response_payload, status=200):
            captured["status"] = int(status)
            captured["payload"] = json.loads(json.dumps(response_payload))
            return captured["payload"]

        handler.end_json = types.MethodType(end_json, handler)
        MemoryStargraphHandler.do_GET(handler)
        return captured["status"], captured["payload"]

    def test_all_node_operation_endpoints_are_routed(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            cases = [
                ("/api/entity-link/people%2Ftony-guan", {"target": "companies/azul-systems", "link_type": "employed by", "context": "past role"}),
                ("/api/entity-unlink/people%2Ftony-guan", {"target": "companies/azul-systems", "link_type": "employed by"}),
                ("/api/entity-tags/people%2Ftony-guan", {"add": ["founder"], "remove": ["old"]}),
                ("/api/entity-timeline/people%2Ftony-guan", {"date": "2026-06-29", "summary": "Updated node ops", "detail": "Details", "source": "test"}),
                ("/api/entity-create", {"name": "New Person", "description": "A new test node", "category": "people"}),
                ("/api/entity-ask-yoda/people%2Ftony-guan", {"question": "What should I know?", "history": [{"role": "user", "content": "Hi"}], "depth": 4}),
                ("/api/entity-backlinks/people%2Ftony-guan", {}),
                ("/api/entity-graph-query/people%2Ftony-guan", {"link_type": "employed by", "direction": "both", "depth": "1"}),
                ("/api/entity-attach-file/people%2Ftony-guan", {"file_path": "/tmp/example.pdf", "description": "Example file"}),
                ("/api/entity-history/people%2Ftony-guan", {}),
                ("/api/entity-embed/people%2Ftony-guan", {}),
            ]

            for path, payload in cases:
                with self.subTest(path=path):
                    status, data = self.dispatch_post(path, payload)
                    self.assertEqual(status, 200)
                    self.assertTrue(data["ok"])
                    expected_slug = "people/new-person" if path == "/api/entity-create" else "people/tony-guan"
                    self.assertEqual(data["slug"], expected_slug)

        call_names = [call[0] for call in fake_store.calls]
        self.assertIn("add_relationship", call_names)
        self.assertIn("remove_relationship", call_names)
        self.assertIn("update_tags", call_names)
        self.assertIn("add_timeline_event", call_names)
        self.assertIn("create_entity", call_names)
        self.assertIn("ask_yoda", call_names)
        self.assertIn("backlinks", call_names)
        self.assertIn("graph_query", call_names)
        self.assertIn("attach_file", call_names)
        self.assertIn("history", call_names)
        self.assertIn("refresh_embedding", call_names)

    def test_entity_create_does_not_create_relationships_from_ui_context(self):
        fake_store = FakeStore()
        payload = {
            "name": "ERFA Reporting",
            "description": "node created via Memory Stargraph UI",
            "category": "projects",
            "source_slug": "products/memory-stargraph",
            "context_slug": "products/memory-stargraph",
            "link_type": "source",
        }

        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post("/api/entity-create", payload)

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn(("create_entity", "ERFA Reporting", "node created via Memory Stargraph UI", "projects"), fake_store.calls)
        self.assertNotIn("add_relationship", [call[0] for call in fake_store.calls])

    def test_entity_media_endpoint_returns_detected_media(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/entity-media/people%2Ftony-guan")

        self.assertEqual(status, 200)
        self.assertEqual(data["slug"], "people/tony-guan")
        self.assertEqual(data["media"][0]["kind"], "image")
        self.assertIn(("get_entity_media", "people/tony-guan"), fake_store.calls)

    def test_entity_timeline_view_endpoint_is_read_only(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/entity-timeline-view/people%2Ftony-guan")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["slug"], "people/tony-guan")
        self.assertIn("Timeline", data["output"])
        self.assertIn(("timeline", "people/tony-guan"), fake_store.calls)
        self.assertNotIn("add_timeline_event", [call[0] for call in fake_store.calls])

    def test_ask_yoda_endpoint_returns_conversational_answer_without_raw_context(self):
        fake_store = FakeStore()

        def raw_fallback(slug, question, history=None, depth=4):
            fake_store.calls.append(("ask_yoda", slug, question, tuple(history or []), depth))
            return {
                "output": "OpenClaw agent unavailable; using deterministic GBrain retrieval fallback.\n\nQuestion-specific gbrain retrieval:\nRAW QUERY DUMP",
                "source": "fallback",
                "prompt": "Direct relationship context:\nRAW PROMPT",
                "timings": {"total_ms": 42},
            }

        fake_store.ask_yoda = raw_fallback
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-ask-yoda/people%2Ftony-guan",
                {"question": "What should I know?", "history": [{"role": "user", "content": "Hi"}], "depth": 6},
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("output", data)
        self.assertNotIn("Question-specific gbrain retrieval", data["output"])
        self.assertNotIn("Direct relationship context", data["output"])
        self.assertNotIn("RAW QUERY DUMP", data["output"])
        self.assertNotIn("prompt", data)
        self.assertEqual(data["timings"]["total_ms"], 42)
        self.assertIn(("ask_yoda", "people/tony-guan", "What should I know?", ({"role": "user", "content": "Hi"},), 6), fake_store.calls)

    def test_ask_yoda_endpoint_preserves_hidden_raw_fallback_output(self):
        fake_store = FakeStore()

        def raw_fallback(slug, question, history=None, depth=4):
            fake_store.calls.append(("ask_yoda", slug, question, tuple(history or []), depth))
            return {
                "output": "OpenClaw agent unavailable; using deterministic GBrain retrieval fallback.\n\nQuestion-specific gbrain retrieval:\nRAW QUERY DUMP",
                "source": "fallback",
                "timings": {"total_ms": 42},
                "diagnostics": {"fallback_used": True, "source": "fallback"},
            }

        fake_store.ask_yoda = raw_fallback
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-ask-yoda/people%2Ftony-guan",
                {"question": "What should I know?", "depth": 4},
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("fallback_output", data)
        self.assertIn("RAW QUERY DUMP", data["fallback_output"])
        self.assertNotIn("RAW QUERY DUMP", data["output"])
        self.assertTrue(data["diagnostics"]["fallback_used"])

    def test_ask_yoda_endpoint_returns_safe_diagnostics_for_view_log(self):
        fake_store = FakeStore()

        def diagnostic_answer(slug, question, history=None, depth=4):
            fake_store.calls.append(("ask_yoda", slug, question, tuple(history or []), depth))
            return {
                "output": "diagnostic answer",
                "source": "fallback",
                "timings": {"prompt_ms": 5, "model_ms": 45, "total_ms": 50},
                "diagnostics": {
                    "request_id": "yoda-test-1",
                    "selected_slug": slug,
                    "depth": depth,
                    "source": "fallback",
                    "fallback_used": True,
                    "model_status": "unavailable",
                    "openclaw_status": "not_configured",
                    "error_summary": "OpenClaw agent unavailable",
                    "stdout_preview": "safe stdout",
                    "stderr_preview": "safe stderr",
                },
            }

        fake_store.ask_yoda = diagnostic_answer
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-ask-yoda/people%2Ftony-guan",
                {"question": "What should I know?", "depth": 4},
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["request_id"], "yoda-test-1")
        self.assertTrue(data["diagnostics"]["fallback_used"])
        self.assertEqual(data["diagnostics"]["selected_slug"], "people/tony-guan")
        self.assertEqual(data["diagnostics"]["model_status"], "unavailable")

    def test_yoda_model_config_endpoint_reads_and_writes_local_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "local.json"
            config_path.write_text(json.dumps({"host": "127.0.0.1", "port": 8788, "yoda_backend": "openclaw"}))
            with mock.patch("server.config_path", return_value=config_path), mock.patch.dict("os.environ", {}, clear=True):
                status, data = self.dispatch_get("/api/yoda-model-config")
                self.assertEqual(status, 200)
                self.assertTrue(data["ok"])
                self.assertEqual(data["backend"], "openclaw")
                self.assertIn("openai_compatible", data["backends"])

                status, data = self.dispatch_post(
                    "/api/yoda-model-config",
                    {
                        "backend": "openai_compatible",
                        "model": "custom/model",
                        "base_url": "http://127.0.0.1:8080/v1",
                        "api_key_env": "LOCAL_MODEL_API_KEY",
                        "agent": "",
                        "timeout_seconds": 90,
                    },
                )

            self.assertEqual(status, 200)
            self.assertTrue(data["ok"])
            self.assertEqual(data["backend"], "openai_compatible")
            self.assertEqual(data["model"], "custom/model")
            saved = json.loads(config_path.read_text())
            self.assertEqual(saved["yoda_backend"], "openai_compatible")
            self.assertEqual(saved["yoda_model"], "custom/model")
            self.assertEqual(saved["yoda_base_url"], "http://127.0.0.1:8080/v1")
            self.assertEqual(saved["yoda_api_key_env"], "LOCAL_MODEL_API_KEY")
            self.assertEqual(saved["yoda_timeout_seconds"], 90)

    def test_ask_yoda_endpoint_clamps_depth(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-ask-yoda/people%2Ftony-guan",
                {"question": "What should I know?", "depth": 99},
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn(("ask_yoda", "people/tony-guan", "What should I know?", (), 6), fake_store.calls)

    def test_graph_query_rejects_invalid_direction_and_depth(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-graph-query/people%2Ftony-guan",
                {"direction": "sideways", "depth": "1"},
            )
            self.assertEqual(status, 400)
            self.assertIn("direction", data["error"])

            status, data = self.dispatch_post(
                "/api/entity-graph-query/people%2Ftony-guan",
                {"direction": "both", "depth": "9"},
            )
            self.assertEqual(status, 400)
            self.assertIn("depth", data["error"])

        self.assertNotIn("graph_query", [call[0] for call in fake_store.calls])

    def test_node_operation_manifest_lists_all_operation_endpoints(self):
        status, data = self.dispatch_get("/api/node-operations")

        self.assertEqual(status, 200)
        endpoints = {item["endpoint"] for item in data["operations"]}
        self.assertTrue(
            {
                "/api/entity-ask-yoda/<slug>",
                "/api/entity-create",
                "/api/entity-media/<slug>",
                "/api/entity-timeline-view/<slug>",
                "/api/entity-backlinks/<slug>",
                "/api/entity-graph-query/<slug>",
                "/api/entity-history/<slug>",
                "/api/entity-link/<slug>",
                "/api/entity-unlink/<slug>",
                "/api/entity-tags/<slug>",
                "/api/entity-timeline/<slug>",
                "/api/entity-attach-file/<slug>",
                "/api/entity-embed/<slug>",
                "/api/take-proposals",
                "/api/take-proposals/<id>/accept",
                "/api/take-proposals/<id>/reject",
                "/api/take-proposals/<id>/defer",
                "/api/take-proposals/bulk",
                "/api/takes",
            }.issubset(endpoints)
        )

    def test_take_proposals_endpoint_bounds_filters_and_returns_counts(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/take-proposals?status=pending&holder=people%2Ftony-guan&limit=500&q=memory")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["counts"]["pending"], 1)
        self.assertEqual(data["proposals"][0]["id"], "tp-1")
        call = fake_store.calls[-1]
        self.assertEqual(call[0], "list_take_proposals")
        self.assertEqual(call[1]["limit"], 100)
        self.assertEqual(call[1]["holder"], "people/tony-guan")
        self.assertEqual(call[1]["query"], "memory")

    def test_hosting_take_proposals_alias_uses_same_store_proxy(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/hosting/take-proposals?limit=2")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn(("list_take_proposals", {"status": "pending", "holder": "", "source_slug": "", "query": "", "limit": 2}), fake_store.calls)

    def test_take_proposal_actions_pass_audit_and_idempotency_payload(self):
        fake_store = FakeStore()
        payload = {"acted_by": "memory-stargraph-ui", "idempotency_key": "abc-123", "reason": "reviewed"}
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post("/api/take-proposals/tp-1/accept", payload)

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["action"], "accept")
        self.assertIn(("review_take_proposal", "tp-1", "accept", payload), fake_store.calls)

    def test_bulk_take_review_rejects_missing_ids_before_store_call(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post("/api/take-proposals/bulk", {"action": "accept", "ids": []})

        self.assertEqual(status, 400)
        self.assertIn("ids", data["error"])
        self.assertNotIn("bulk_review_take_proposals", [call[0] for call in fake_store.calls])

    def test_existing_takes_endpoint_reads_selected_node_takes(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/takes?slug=people%2Ftony-guan&limit=12")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["takes"][0]["claim"], "Existing take 1")
        self.assertEqual(fake_store.calls[-1][0], "list_takes")
        self.assertEqual(fake_store.calls[-1][1]["page_slug"], "people/tony-guan")
        self.assertEqual(fake_store.calls[-1][1]["limit"], 500)

    def test_existing_takes_endpoint_paginates_and_returns_range_metadata(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/takes?holder=people%2Ftony-guan&limit=10&offset=10")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["takes"]), 9)
        self.assertEqual(data["takes"][0]["id"], "take-11")
        self.assertEqual(data["total"], 19)
        self.assertEqual(data["offset"], 10)
        self.assertEqual(data["limit"], 10)
        self.assertIsNone(data["next_offset"])
        self.assertEqual(data["previous_offset"], 0)

    def test_existing_takes_endpoint_normalizes_single_row_response(self):
        fake_store = SingleRowTakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/takes?holder=people%2Ftony-guan&status=all&limit=10&offset=0")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["takes"]), 1)
        self.assertEqual(data["takes"][0]["claim"], "Existing single-row take")
        self.assertEqual(data["holder_filter"], "people/tony-guan")

    def test_wildcard_holder_filters_are_expanded_for_takes(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/takes?holder=tony*&limit=10")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["total"], 19)
        call = fake_store.calls[-1]
        self.assertEqual(call[0], "list_takes")
        self.assertNotIn("holder", call[1])

    def test_gbrain_tool_proxy_collapses_unknown_tool_migration_noise(self):
        noisy = "Schema version 1 -> 119\n  [69] take_proposals_v0_36...\nUnknown tool: take_proposals_list"
        with mock.patch("server.run_gbrain", side_effect=RuntimeError(noisy)):
            with self.assertRaisesRegex(RuntimeError, "GBrain backend does not expose take_proposals_list"):
                server.gbrain_call_tool("take_proposals_list", {"limit": 2})

    def test_gbrain_tool_proxy_preserves_array_responses(self):
        output = '[{"id": 1, "claim": "First"}, {"id": 2, "claim": "Second"}]'
        with mock.patch("server.run_gbrain", return_value=output):
            result = server.gbrain_call_tool("takes_list", {"limit": 2})

        self.assertIsInstance(result, list)
        self.assertEqual([row["id"] for row in result], [1, 2])

    def test_yoda_system_prompt_api_persists_and_resets_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with mock.patch("server.DATA_DIR", data_dir), mock.patch("server.YODA_SETTINGS_PATH", data_dir / "yoda_settings.json"):
                status, data = self.dispatch_get("/api/yoda-system-prompt")
                self.assertEqual(status, 200)
                self.assertFalse(data["override"])
                self.assertIn("classify the question intent", data["prompt"])

                status, data = self.dispatch_post("/api/yoda-system-prompt", {"prompt": "Custom resolver prompt"})
                self.assertEqual(status, 200)
                self.assertTrue(data["override"])
                self.assertEqual(data["prompt"], "Custom resolver prompt")

                status, data = self.dispatch_post("/api/yoda-system-prompt", {"reset": True})
                self.assertEqual(status, 200)
                self.assertFalse(data["override"])
                self.assertIn("avoid unconstrained graph-query --depth 4", data["prompt"])

    def test_yoda_log_store_is_bounded_and_read_by_slug(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with mock.patch("server.DATA_DIR", data_dir), mock.patch("server.YODA_LOG_PATH", data_dir / "yoda_logs.json"):
                for index in range(25):
                    server.append_yoda_log("people/tony-guan", {"request_id": f"r-{index}", "diagnostics": {"source": "fallback"}})

                status, data = self.dispatch_get("/api/yoda-logs?slug=people%2Ftony-guan&limit=8")

        self.assertEqual(status, 200)
        self.assertEqual(data["slug"], "people/tony-guan")
        self.assertEqual(len(data["entries"]), 8)
        self.assertEqual(data["entries"][0]["request_id"], "r-24")
        self.assertEqual(data["entries"][-1]["request_id"], "r-17")

    def test_ask_yoda_endpoint_logs_resolver_event_and_persistent_log(self):
        fake_store = FakeStore()
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with (
                mock.patch("server.DATA_DIR", data_dir),
                mock.patch("server.YODA_LOG_PATH", data_dir / "yoda_logs.json"),
                mock.patch("server.RESOLVER_EVENTS_PATH", data_dir / "resolver_dispatch_events.json"),
                mock.patch("server.STORE", fake_store),
            ):
                status, data = self.dispatch_post(
                    "/api/entity-ask-yoda/people%2Ftony-guan",
                    {"question": "Which ACA7 writing matters?", "depth": 4},
                )
                logs_status, logs = self.dispatch_get("/api/yoda-logs?slug=people%2Ftony-guan&limit=2")
                events_status, events = self.dispatch_get("/api/resolver/events?limit=2")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(logs_status, 200)
        self.assertEqual(logs["entries"][0]["request_id"], data["request_id"])
        self.assertEqual(events_status, 200)
        self.assertEqual(events["events"][0]["surface"], "Ask Yoda")
        self.assertEqual(events["events"][0]["selected_context"], "people/tony-guan")
        self.assertIn("ACA7", events["events"][0]["intent_summary"])
        self.assertNotIn("Which ACA7 writing matters?", json.dumps(events["events"][0]))

    def test_resolver_events_api_sanitizes_and_bounds_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with mock.patch("server.DATA_DIR", data_dir), mock.patch("server.RESOLVER_EVENTS_PATH", data_dir / "resolver_dispatch_events.json"):
                for index in range(3):
                    status, data = self.dispatch_post(
                        "/api/resolver/events",
                        {
                            "surface": "Stargraph UI",
                            "user_intent": "token sk-secret should not be stored in full",
                            "selected_skill": "Ask Yoda",
                            "result_status": "timeout",
                            "fallback_used": True,
                            "related_slug": "people/tony-guan",
                        },
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(data["ok"])
                status, data = self.dispatch_get("/api/resolver/events?limit=2")

        self.assertEqual(status, 200)
        self.assertEqual(len(data["events"]), 2)
        serialized = json.dumps(data["events"])
        self.assertNotIn("sk-secret", serialized)
        self.assertIn("[redacted]", serialized)

    def test_resolver_proposal_generation_review_apply_and_impact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with (
                mock.patch("server.DATA_DIR", data_dir),
                mock.patch("server.RESOLVER_EVENTS_PATH", data_dir / "resolver_dispatch_events.json"),
                mock.patch("server.RESOLVER_PROPOSALS_PATH", data_dir / "resolver_proposals.json"),
                mock.patch("server.run_gbrain", return_value="ok"),
            ):
                for intent in ["find ACA7 writing", "find ACA7 writing", "find ACA7 writing"]:
                    server.append_resolver_event({"surface": "Ask Yoda", "user_intent": intent, "result_status": "timeout", "fallback_used": True})
                status, generated = self.dispatch_post("/api/resolver/proposals/generate", {})
                self.assertEqual(status, 200)
                self.assertEqual(generated["created"], 1)

                status, listed = self.dispatch_get("/api/resolver/proposals?status=pending")
                self.assertEqual(status, 200)
                proposal = listed["proposals"][0]
                self.assertEqual(proposal["kind"], "add_trigger")
                self.assertIn("impact", proposal)

                status, accepted = self.dispatch_post(f"/api/resolver/proposals/{proposal['id']}/accept", {"reason": "looks useful"})
                self.assertEqual(status, 200)
                self.assertEqual(accepted["proposal"]["status"], "accepted")

                status, applied = self.dispatch_post(f"/api/resolver/proposals/{proposal['id']}/apply", {})
                self.assertEqual(status, 200)
                self.assertEqual(applied["proposal"]["status"], "applied")
                self.assertEqual(applied["validation"]["gbrain_check_resolvable"], "passed")

                status, impact = self.dispatch_post(f"/api/resolver/proposals/{proposal['id']}/impact", {"after_events": [{"result_status": "success"}]})
                self.assertEqual(status, 200)
                self.assertEqual(impact["proposal"]["impact"]["after"]["success_count"], 1)

    def test_resolver_dream_phase_generates_summary_without_apply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with (
                mock.patch("server.DATA_DIR", data_dir),
                mock.patch("server.RESOLVER_EVENTS_PATH", data_dir / "resolver_dispatch_events.json"),
                mock.patch("server.RESOLVER_PROPOSALS_PATH", data_dir / "resolver_proposals.json"),
                mock.patch("server.RESOLVER_DREAM_LOG_PATH", data_dir / "resolver_dream_runs.json"),
            ):
                server.append_resolver_event({"surface": "Ask Yoda", "user_intent": "manual skill for tax writing", "result_status": "no_match"})
                server.append_resolver_event({"surface": "Ask Yoda", "user_intent": "manual skill for tax writing", "result_status": "no_match"})
                status, data = self.dispatch_post("/api/resolver/dream", {"enabled": True})

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["summary"]["events_scanned"], 2)
        self.assertEqual(data["summary"]["proposals_created"], 1)
        self.assertEqual(data["summary"]["applied"], 0)


if __name__ == "__main__":
    unittest.main()
