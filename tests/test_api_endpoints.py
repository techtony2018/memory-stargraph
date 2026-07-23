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
    def dispatch_post(self, path, payload=None, *, allow_resolver_submit=False):
        handler = object.__new__(MemoryStargraphHandler)
        handler.path = path
        captured = {}
        request_payload = dict(payload or {})
        if path.startswith("/api/entity-ask-yoda/"):
            request_payload.setdefault("environment", "test")
            request_payload.setdefault("synthetic", True)
            request_payload.setdefault("test_run", True)
            request_payload.setdefault("pair_id", f"unit:{self.__class__.__name__}.{self._testMethodName}")

        def read_json_body(self):
            return request_payload

        def end_json(self, response_payload, status=200):
            captured["status"] = int(status)
            captured["payload"] = json.loads(json.dumps(response_payload))
            return captured["payload"]

        handler.read_json_body = types.MethodType(read_json_body, handler)
        handler.end_json = types.MethodType(end_json, handler)
        if path.startswith("/api/entity-ask-yoda/") and not allow_resolver_submit:
            with mock.patch("server.resolver_submit_event", return_value={"event": {"event_id": "unit-suppressed"}}):
                MemoryStargraphHandler.do_POST(handler)
        else:
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

    def dispatch_put(self, path, payload=None):
        handler = object.__new__(MemoryStargraphHandler)
        handler.path = path
        captured = {}

        def read_json_body(self):
            return dict(payload or {})

        def end_json(self, response_payload, status=200):
            captured["status"] = int(status)
            captured["payload"] = json.loads(json.dumps(response_payload))
            return captured["payload"]

        handler.read_json_body = types.MethodType(read_json_body, handler)
        handler.end_json = types.MethodType(end_json, handler)
        MemoryStargraphHandler.do_PUT(handler)
        return captured["status"], captured["payload"]

    def test_api_test_harness_marks_ask_yoda_requests_as_synthetic_tests(self):
        fake_store = FakeStore()
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.gbrain_call_tool", return_value={"event": {"event_id": "test-event"}}) as fake_gbrain_call,
        ):
            status, data = self.dispatch_post(
                "/api/entity-ask-yoda/people%2Ftony-guan",
                {"question": "Harness provenance regression"},
                allow_resolver_submit=True,
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        submitted = fake_gbrain_call.call_args.args[1]
        self.assertEqual(submitted["environment"], "test")
        self.assertTrue(submitted["synthetic"])
        self.assertTrue(submitted["test_run"])
        self.assertEqual(
            submitted["pair_id"],
            "unit:ApiEndpointTests.test_api_test_harness_marks_ask_yoda_requests_as_synthetic_tests",
        )

    def test_api_test_harness_suppresses_live_resolver_submission_by_default(self):
        fake_store = FakeStore()
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.gbrain_call_tool") as fake_gbrain_call,
        ):
            status, data = self.dispatch_post(
                "/api/entity-ask-yoda/people%2Ftony-guan",
                {"question": "No external unit-test side effect"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        fake_gbrain_call.assert_not_called()

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

    def test_gbrain_backend_config_exposes_primary_and_persists_validated_selection(self):
        fake_store = FakeStore()
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "gbrain_path": "/tmp/gbrain-primary",
                        "gbrain_backend_choices": [
                            {
                                "id": "primary",
                                "label": "Primary",
                                "role": "primary",
                                "gbrain_path": "/tmp/gbrain-primary",
                                "write_authority": "primary",
                            }
                        ],
                    }
                )
            )
            with (
                mock.patch.dict("os.environ", {"MEMORY_STARGRAPH_CONFIG": str(config_path)}),
                mock.patch("server.run_gbrain_binary", return_value="# Index\n"),
                mock.patch("server.validate_memory_stargraph_service", return_value={"ok": True, "skipped": True}),
                mock.patch("server.STORE", fake_store),
            ):
                status, data = self.dispatch_get("/api/gbrain-backend-config")
                self.assertEqual(status, 200)
                self.assertTrue(data["ok"])
                self.assertEqual(data["current_backend"]["label"], "Primary")

                status, data = self.dispatch_post("/api/gbrain-backend-config", {"backend_id": "primary"})

            self.assertEqual(status, 200)
            self.assertTrue(data["ok"])
            saved = json.loads(config_path.read_text())
            self.assertEqual(saved["gbrain_backend_id"], "primary")
            self.assertEqual(saved["gbrain_path"], "/tmp/gbrain-primary")
            self.assertTrue(data["validation"]["gbrain_cli_readback"])

    def test_gbrain_backend_config_requires_ack_for_non_primary_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "local.json"
            config_path.write_text(json.dumps({"gbrain_path": "/tmp/gbrain-primary"}))
            with mock.patch.dict("os.environ", {"MEMORY_STARGRAPH_CONFIG": str(config_path)}):
                status, data = self.dispatch_post(
                    "/api/gbrain-backend-config",
                    {"backend_id": "custom", "custom_label": "Secondary test", "custom_gbrain_path": "/tmp/gbrain-secondary"},
                )

        self.assertEqual(status, 400)
        self.assertIn("split-brain", data["error"])

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

    def test_yoda_diagnostic_sanitizer_persists_only_privacy_safe_context_metrics(self):
        safe = server.sanitize_diagnostics(
            {
                "context_cache_hit": True,
                "context_subphases_ms": {
                    "selected_node": 10,
                    "graph": 20,
                    "backlinks": 30,
                    "search": 40,
                    "direct_reads": 50,
                    "assembly": 1,
                },
                "context_counts": {
                    "prompt_chars": 1200,
                    "history_messages": 2,
                    "search_results": 5,
                    "direct_reads": 3,
                },
                "context_degraded": True,
                "context_degraded_reason": "broad_graph_timeout",
                "broad_graph_budget_ms": 8000,
                "prompt": "private prompt body",
                "context_source_slugs": ["private/node"],
            }
        )

        self.assertTrue(safe["context_cache_hit"])
        self.assertEqual(safe["context_subphases_ms"]["graph"], 20)
        self.assertEqual(safe["context_counts"]["prompt_chars"], 1200)
        self.assertTrue(safe["context_degraded"])
        self.assertEqual(safe["context_degraded_reason"], "broad_graph_timeout")
        self.assertEqual(safe["broad_graph_budget_ms"], 8000)
        self.assertNotIn("prompt", safe)
        self.assertNotIn("context_source_slugs", safe)

    def test_yoda_prompt_reconciles_present_operational_gaps_with_completed_todos(self):
        store = server.GraphStore()
        root = "\n".join(
            [
                "| id | status | priority | title | node | updated | notes |",
                "| --- | --- | --- | --- | --- | --- | --- |",
                "| SG-0128 | completed | P1 | Separate synthetic resolver probe telemetry | [[notes/memory-starmap-todo-list/separate-synthetic-resolver-probe-telemetry]] | 2026-07-16T03:10:00-07:00 | Completed: synthetic/test probes are isolated from production learning clusters. |",
                "| SG-0139 | completed | P1 | Add broad graph timeout telemetry | [[notes/memory-starmap-todo-list/add-broad-graph-timeout-telemetry]] | 2026-07-17T02:10:00-07:00 | Completed: yoda logs expose context_degraded and broad_graph_timeout. |",
                "| SG-0149 | planned | P1 | Reconcile Ask Yoda operational recommendations with resolved incident state | [[notes/memory-starmap-todo-list/reconcile-ask-yoda-operational-recommendations-with-resolved-incident-st]] | 2026-07-19T01:14:12-07:00 | Planned current gap. |",
            ]
        )
        children = {
            "notes/memory-starmap-todo-list/separate-synthetic-resolver-probe-telemetry": "Status: completed\nCompletion Evidence: live resolver dry run excluded synthetic probes; auto_applied=0.",
            "notes/memory-starmap-todo-list/add-broad-graph-timeout-telemetry": "Status: completed\nCompletion Evidence: /api/yoda-logs exposes context_degraded and broad_graph_timeout.",
        }

        def fake_raw(slug):
            if slug == "notes/memory-starmap-todo-list":
                return root
            return children.get(slug, "")

        store.get_entity_raw = fake_raw
        stable = {"selected_node": "", "graph": "", "backlinks": "", "timings": {}}
        with mock.patch("server.run_gbrain", return_value=""):
            prompt = store.build_yoda_prompt(
                "notes/memory-starmap-todo-list",
                "What current operational gaps remain around synthetic provenance and broad graph timeout?",
                stable_context=stable,
            )

        self.assertIn("Operational remediation status reconciliation", prompt)
        self.assertIn("Do not restate completed remediation as a current blocker", prompt)
        self.assertIn("SG-0128", prompt)
        self.assertIn("completed", prompt)
        self.assertIn("live resolver dry run excluded synthetic probes", prompt)

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
                        "graph_query_timeout_seconds": 25,
                    },
                )

            self.assertEqual(status, 200)
            self.assertTrue(data["ok"])
            self.assertEqual(data["graph_query_timeout_seconds"], 25)
            saved = json.loads(config_path.read_text())
            self.assertEqual(saved["yoda_graph_query_timeout_seconds"], 25)
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

    def test_setup_diagnostics_is_redacted_and_actionable(self):
        fake_store = FakeStore()
        fake_store.graph = {
            "source": {"mode": "gbrain", "status": "live", "warnings": []},
            "nodes": [{"slug": "index", "degree": 3}],
        }
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.GBRAIN") as gbrain_path,
            mock.patch("server.GBRAIN_FILE_STORE_ROOTS", []),
            mock.patch("server.GBRAIN_FILE_BASE_URLS", []),
        ):
            gbrain_path.exists.return_value = True
            status, data = self.dispatch_get("/api/setup-diagnostics")

        self.assertEqual(status, 200)
        self.assertFalse(data["ok"])
        self.assertEqual(data["source_mode"], "gbrain")
        self.assertIn("checks", data)
        self.assertIn("next_action", data)
        self.assertIn("config_keys_present", data)
        self.assertNotIn("config_values", data)
        self.assertNotIn("api_key", json.dumps(data).lower())
        attachment = next(check for check in data["checks"] if check["id"] == "attachment_storage")
        self.assertFalse(attachment["ok"])
        self.assertEqual(attachment["detail"], "durable storage unavailable")

    def test_sample_brain_endpoint_returns_privacy_safe_demo_graph(self):
        status, data = self.dispatch_get("/api/sample-brain")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["graph"]["source"]["mode"], "demo")
        self.assertEqual(data["graph"]["source"]["status"], "sample")
        self.assertTrue(data["privacy_safe"])
        self.assertIn("sample", data["label"].lower())
        self.assertNotIn("tony", json.dumps(data).lower())
        self.assertIn("sample-memory-hub", {node["slug"] for node in data["graph"]["nodes"]})

    def test_memory_value_digest_is_read_only_and_links_evidence(self):
        fake_store = FakeStore()
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.run_gbrain") as run_gbrain,
            mock.patch(
                "server.resolver_feedback_health",
                return_value={"events_24h": 3, "synthetic_test_events_24h": 1},
            ),
        ):
            run_gbrain.side_effect = [
                "| SG-0150 | completed | P1 | Done | [[notes/done]] | 2026-07-19 | Completed. |\n"
                "| SG-0151 | implementing | P1 | Current | [[notes/current]] | 2026-07-20 | Implementing. |",
                "# Learning\n\n- Reuse source-sync preflight.",
            ]
            status, data = self.dispatch_get("/api/memory-value-digest?window=day")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["window"], "day")
        self.assertTrue(data["read_only"])
        self.assertEqual(data["todo_movement"]["completed"], 1)
        self.assertEqual(data["todo_movement"]["implementing"], 1)
        self.assertIn("runs", data["evidence_links"])
        self.assertIn("learnings", data["evidence_links"])
        self.assertIn("next_action", data)
        self.assertEqual(fake_store.calls[-1], ("get_seed_graph", False))


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
            self.assertIn("Broad graph context may be truncated", data["prompt"])
            self.assertIn("Prefer targeted entity relationship evidence", data["prompt"])

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

    def test_yoda_chat_history_persists_and_clears_without_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            chat_path = data_dir / "yoda_chats.json"
            log_path = data_dir / "yoda_logs.json"
            with (
                mock.patch("server.DATA_DIR", data_dir),
                mock.patch("server.YODA_CHAT_PATH", chat_path),
                mock.patch("server.YODA_LOG_PATH", log_path),
            ):
                server.append_yoda_log("people/tony-guan", {"request_id": "diag-1", "diagnostics": {"source": "fallback"}})
                status, data = self.dispatch_post(
                    "/api/yoda-chat/people%2Ftony-guan",
                    {
                        "messages": [
                            {"role": "system", "content": "Ask Yoda about Tony", "timestamp": "now"},
                            {"role": "user", "content": "hello", "timestamp": "now"},
                            {"role": "assistant", "content": "## Answer\n\n- **First**\n- people/tony-guan", "fallbackOutput": "raw graph output", "timestamp": "now"},
                            {"role": "assistant", "content": "Thinking", "pending": True},
                        ]
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(len(data["messages"]), 3)

                status, data = self.dispatch_get("/api/yoda-chat/people%2Ftony-guan")
                self.assertEqual(status, 200)
                self.assertEqual([item["role"] for item in data["messages"]], ["system", "user", "assistant"])
                self.assertEqual(data["messages"][-1]["content"], "## Answer\n\n- **First**\n- people/tony-guan")
                self.assertEqual(data["messages"][-1]["fallbackOutput"], "raw graph output")

                status, data = self.dispatch_post("/api/yoda-chat/people%2Ftony-guan", {"clear": True})
                self.assertEqual(status, 200)
                self.assertEqual(data["messages"], [])

                status, data = self.dispatch_get("/api/yoda-logs?slug=people%2Ftony-guan&limit=5")

        self.assertEqual(status, 200)
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["request_id"], "diag-1")

    def test_yoda_chat_assigns_stable_answer_identity_for_new_and_legacy_answers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chat_path = Path(tmpdir) / "yoda_chats.json"
            with mock.patch("server.YODA_CHAT_PATH", chat_path):
                status, saved = self.dispatch_post(
                    "/api/yoda-chat/people%2Ftony-guan",
                    {
                        "messages": [
                            {"role": "assistant", "content": "New answer", "timestamp": "Jul 17, 9:00 AM", "request_id": "yoda-new"},
                            {"role": "assistant", "content": "Legacy answer", "timestamp": "Jul 17, 8:00 AM"},
                        ]
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(saved["messages"][0]["answer_id"], "yoda-new")
                legacy_id = saved["messages"][1]["answer_id"]
                self.assertTrue(legacy_id.startswith("legacy-yoda-"))

                status, restored = self.dispatch_get("/api/yoda-chat/people%2Ftony-guan")

        self.assertEqual(status, 200)
        self.assertEqual(restored["messages"][1]["answer_id"], legacy_id)

    def test_yoda_feedback_upserts_independently_of_chat_clear_and_isolates_tests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with (
                mock.patch("server.YODA_CHAT_PATH", data_dir / "yoda_chats.json"),
                mock.patch("server.YODA_FEEDBACK_PATH", data_dir / "yoda_feedback.json"),
            ):
                status, first = self.dispatch_put(
                    "/api/yoda-feedback/yoda-production-1",
                    {"request_id": "yoda-production-1", "slug": "people/tony-guan", "rating": "up", "comment": "Useful sk-test-secret"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(first["feedback"]["rating"], "up")
                self.assertIn("[redacted]", first["feedback"]["comment"])
                created_at = first["feedback"]["created_at"]

                status, updated = self.dispatch_put(
                    "/api/yoda-feedback/yoda-production-1",
                    {"request_id": "yoda-production-1", "slug": "people/tony-guan", "rating": "down", "comment": "Needs a backlink"},
                )
                self.assertEqual(updated["feedback"]["rating"], "down")
                self.assertEqual(updated["feedback"]["created_at"], created_at)

                status, _test = self.dispatch_put(
                    "/api/yoda-feedback/yoda-test-1",
                    {
                        "request_id": "yoda-test-1",
                        "slug": "people/tony-guan",
                        "rating": "down",
                        "comment": "Synthetic probe",
                        "environment": "test",
                        "synthetic": True,
                        "test_run": True,
                        "pair_id": "feedback-probe-1",
                    },
                )
                self.dispatch_post("/api/yoda-chat/people%2Ftony-guan", {"clear": True})
                status, production = self.dispatch_get("/api/yoda-feedback?slug=people%2Ftony-guan")
                status, auditable = self.dispatch_get("/api/yoda-feedback?slug=people%2Ftony-guan&include_test=true")

        self.assertEqual(status, 200)
        self.assertEqual([item["answer_id"] for item in production["feedback"]], ["yoda-production-1"])
        self.assertEqual(production["counts"], {"production": 1, "test": 1})
        self.assertEqual({item["answer_id"] for item in auditable["feedback"]}, {"yoda-production-1", "yoda-test-1"})
        probe = next(item for item in auditable["feedback"] if item["answer_id"] == "yoda-test-1")
        self.assertEqual(probe["pair_id"], "feedback-probe-1")
        self.assertTrue(probe["synthetic"])

    def test_yoda_feedback_validates_limits_and_review_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("server.YODA_FEEDBACK_PATH", Path(tmpdir) / "yoda_feedback.json"):
                status, invalid = self.dispatch_put("/api/yoda-feedback/a-1", {"slug": "people/tony-guan", "rating": "maybe"})
                self.assertEqual(status, 400)
                self.assertIn("rating", invalid["error"])
                status, too_long = self.dispatch_put("/api/yoda-feedback/a-1", {"slug": "people/tony-guan", "comment": "x" * 2001})
                self.assertEqual(status, 400)
                self.assertIn("2000", too_long["error"])

                self.dispatch_put("/api/yoda-feedback/a-1", {"slug": "people/tony-guan", "rating": "down"})
                review = {
                    "answer_ids": ["a-1"],
                    "review_run_slug": "runs/daily-review-1",
                    "decision": "data_quality_recommendation",
                    "related_todo_ids": [],
                    "related_learning_slugs": [],
                    "reviewed_at": "2026-07-17T09:00:00-07:00",
                }
                status, first = self.dispatch_post("/api/yoda-feedback/review", review)
                status, second = self.dispatch_post("/api/yoda-feedback/review", review)
                status, listed = self.dispatch_get("/api/yoda-feedback?review_status=reviewed")

        self.assertEqual(status, 200)
        self.assertEqual(first["updated"], 1)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(listed["feedback"][0]["decision"], "data_quality_recommendation")

    def test_ask_yoda_endpoint_logs_resolver_event_and_persistent_log(self):
        fake_store = FakeStore()
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with (
                mock.patch("server.DATA_DIR", data_dir),
                mock.patch("server.YODA_LOG_PATH", data_dir / "yoda_logs.json"),
                mock.patch("server.STORE", fake_store),
                mock.patch("server.gbrain_call_tool") as fake_gbrain_call,
            ):
                fake_gbrain_call.return_value = {"event": {"event_id": "evt-1"}, "idempotent": False}
                status, data = self.dispatch_post(
                    "/api/entity-ask-yoda/people%2Ftony-guan",
                    {"question": "Which ACA7 writing matters?", "depth": 4, "environment": "test", "synthetic": True, "test_run": True, "pair_id": "api-probe-1"},
                    allow_resolver_submit=True,
                )
                logs_status, logs = self.dispatch_get("/api/yoda-logs?slug=people%2Ftony-guan&limit=2")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(logs_status, 200)
        self.assertEqual(logs["entries"][0]["request_id"], data["request_id"])
        fake_gbrain_call.assert_called_with(
            "resolver_events_submit",
            mock.ANY,
            timeout=20,
        )
        submitted = fake_gbrain_call.call_args.args[1]
        self.assertEqual(submitted["producer"], "stargraph")
        self.assertEqual(submitted["selected_route"], "Ask Yoda")
        self.assertEqual(submitted["related_node_slug"], "people/tony-guan")
        self.assertIn("ACA7", submitted["intent_summary"])
        self.assertEqual(submitted["environment"], "test")
        self.assertTrue(submitted["synthetic"])
        self.assertTrue(submitted["test_run"])
        self.assertEqual(submitted["pair_id"], "api-probe-1")

    def test_resolver_events_api_proxies_to_hosted_gbrain(self):
        with mock.patch("server.gbrain_call_tool") as fake_gbrain_call:
            fake_gbrain_call.side_effect = [
                {"event": {"event_id": "stargraph-1"}, "idempotent": False},
                {"events": [{"event_id": "stargraph-1", "producer": "stargraph"}], "limit": 2},
            ]
            status, data = self.dispatch_post(
                "/api/resolver/events",
                {
                    "event_id": "stargraph-1",
                    "producer": "stargraph",
                    "user_intent": "token sk-secret should not be stored in full",
                    "selected_skill": "Ask Yoda",
                    "result_status": "timeout",
                    "fallback_used": True,
                    "related_slug": "people/tony-guan",
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(data["ok"])
            status, data = self.dispatch_get("/api/resolver/events?limit=2&producer=stargraph")

        self.assertEqual(status, 200)
        self.assertEqual(data["events"][0]["event_id"], "stargraph-1")
        self.assertEqual(fake_gbrain_call.call_args_list[0].args[0], "resolver_events_submit")
        submitted = fake_gbrain_call.call_args_list[0].args[1]
        self.assertEqual(submitted["environment"], "production")
        self.assertFalse(submitted["synthetic"])
        self.assertFalse(submitted["test_run"])
        self.assertEqual(submitted["pair_id"], "")
        self.assertEqual(fake_gbrain_call.call_args_list[1].args[0], "resolver_events_list")
        self.assertEqual(fake_gbrain_call.call_args_list[1].args[1], {"limit": 2, "producer": "stargraph"})

    def test_resolver_events_api_coerces_and_clamps_limits(self):
        cases = [
            ("/api/resolver/events", 50),
            ("/api/resolver/events?limit=50", 50),
            ("/api/resolver/events?limit=invalid", 50),
            ("/api/resolver/events?limit=-4", 1),
            ("/api/resolver/events?limit=9999", server.MAX_RESOLVER_EVENTS),
        ]
        for path, expected_limit in cases:
            with self.subTest(path=path), mock.patch("server.gbrain_call_tool", return_value={"events": []}) as fake_gbrain_call:
                status, data = self.dispatch_get(path)

            self.assertEqual(status, 200)
            self.assertTrue(data["ok"])
            payload = fake_gbrain_call.call_args.args[1]
            self.assertEqual(payload["limit"], expected_limit)
            self.assertIsInstance(payload["limit"], int)

        with mock.patch("server.gbrain_call_tool", return_value={"events": []}) as fake_gbrain_call:
            status, _data = self.dispatch_get("/api/resolver/events?limit=8&producer=codex&outcome=fallback")

        self.assertEqual(status, 200)
        self.assertEqual(fake_gbrain_call.call_args.args[1], {
            "limit": 8,
            "producer": "codex",
            "outcome": "fallback",
        })

    def test_resolver_proposals_api_normalizes_hosted_and_local_impact_payloads(self):
        hosted_impact = json.dumps({
            "before": {
                "event_count": 5,
                "fallback_count": 5,
                "timeout_count": 0,
                "success_count": 0,
                "manual_correction_count": 0,
            },
            "after": {},
        })
        local_impact = {
            "before": {"event_count": 3, "fallback_count": 1},
            "after": {"event_count": 2, "success_count": 2},
        }
        with mock.patch("server.gbrain_call_tool", return_value={
            "proposals": [
                {"id": "rp-hosted", "impact": hosted_impact, "evidence_count": 5},
                {"id": "rp-local", "impact": local_impact, "evidence": [{"event_id": "event-1"}]},
            ],
            "total": 2,
        }):
            status, data = self.dispatch_get("/api/resolver/proposals?status=pending")

        self.assertEqual(status, 200)
        hosted, local = data["proposals"]
        self.assertEqual(hosted["impact"]["before"]["event_count"], 5)
        self.assertEqual(hosted["impact"]["before"]["fallback_count"], 5)
        self.assertEqual(hosted["evidence_count"], 5)
        self.assertEqual(local["impact"], local_impact)
        self.assertEqual(local["evidence_count"], 1)

    def test_gbrain_call_tool_prefers_top_level_object_over_nested_lists(self):
        output = json.dumps({
            "created": 0,
            "proposals": [],
            "dream_run": {"auto_applied": 0},
        })
        with mock.patch("server.run_gbrain", return_value=output):
            data = server.gbrain_call_tool("resolver_proposals_generate", {})

        self.assertIsInstance(data, dict)
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["proposals"], [])

    def test_resolver_proposal_generation_review_apply_and_health_proxy(self):
        with mock.patch("server.gbrain_call_tool") as fake_gbrain_call:
            fake_gbrain_call.side_effect = [
                {"created": 1, "events_scanned": 3, "proposals": [{"id": "rp-1"}], "auto_applied": 0},
                {"proposals": [{"id": "rp-1", "kind": "resolver_route_update", "impact": {}}], "total": 1},
                {"proposal": {"id": "rp-1", "status": "accepted"}},
                {"proposals": [{"id": "rp-1", "cluster_key": "gbrain resolver lookup"}]},
                {"release": {"version": "resolver-20260714T000000Z", "active": True}, "distribution": [{"environment": "codex"}, {"environment": "openclaw"}]},
                {"proposal": {"id": "rp-1"}, "impact": {"after": {"success": 1}}},
                {"events_24h": 2, "proposal_counts": {"pending": 1}, "scheduled_loop": "observed"},
            ]
            status, generated = self.dispatch_post("/api/resolver/proposals/generate", {})
            self.assertEqual(status, 200)
            self.assertEqual(generated["created"], 1)

            status, listed = self.dispatch_get("/api/resolver/proposals?status=pending")
            self.assertEqual(status, 200)
            proposal = listed["proposals"][0]
            self.assertEqual(proposal["kind"], "resolver_route_update")

            status, accepted = self.dispatch_post(f"/api/resolver/proposals/{proposal['id']}/accept", {"reason": "looks useful"})
            self.assertEqual(status, 200)
            self.assertEqual(accepted["proposal"]["status"], "accepted")

            with mock.patch("server.run_gbrain", return_value="ok") as validate_command:
                status, applied = self.dispatch_post(f"/api/resolver/proposals/{proposal['id']}/apply", {})
            self.assertEqual(status, 200)
            self.assertTrue(applied["release"]["active"])
            self.assertEqual(validate_command.call_count, 2)

            status, impact = self.dispatch_post(f"/api/resolver/proposals/{proposal['id']}/impact", {})
            self.assertEqual(status, 200)
            self.assertEqual(impact["impact"]["after"]["success"], 1)

            status, health = self.dispatch_get("/api/resolver/health")
            self.assertEqual(status, 200)
            self.assertEqual(health["events_24h"], 2)

        self.assertEqual([call.args[0] for call in fake_gbrain_call.call_args_list], [
            "resolver_proposals_generate",
            "resolver_proposals_list",
            "resolver_proposals_update",
            "resolver_proposals_list",
            "resolver_releases_apply",
            "resolver_impact_measure",
            "resolver_feedback_health",
        ])
        apply_payload = fake_gbrain_call.call_args_list[4].args[1]
        self.assertEqual(apply_payload["validation"]["check_resolvable"], "passed")
        self.assertEqual(apply_payload["validation"]["routing_tests"], "passed")

    def test_resolver_dream_phase_generates_summary_without_apply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            with (
                mock.patch("server.DATA_DIR", data_dir),
                mock.patch("server.gbrain_call_tool") as fake_gbrain_call,
            ):
                fake_gbrain_call.return_value = {
                    "dream_run": {"events_scanned": 2, "proposals_created": 1, "auto_applied": 0},
                    "auto_applied": 0,
                }
                status, data = self.dispatch_post("/api/resolver/dream", {"enabled": True})

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["summary"]["events_scanned"], 2)
        self.assertEqual(data["summary"]["proposals_created"], 1)
        self.assertEqual(data["summary"]["auto_applied"], 0)


if __name__ == "__main__":
    unittest.main()
