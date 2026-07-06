import json
import types
import unittest
from unittest import mock

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

    def ask_yoda(self, slug, question, history=None):
        self.calls.append(("ask_yoda", slug, question, tuple(history or [])))
        return {"output": "yoda answer", "source": "fallback"}

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
                ("/api/entity-ask-yoda/people%2Ftony-guan", {"question": "What should I know?", "history": [{"role": "user", "content": "Hi"}]}),
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

        def raw_fallback(slug, question, history=None):
            fake_store.calls.append(("ask_yoda", slug, question, tuple(history or [])))
            return {
                "output": "OpenClaw agent unavailable; using deterministic GBrain retrieval fallback.\n\nQuestion-specific gbrain retrieval:\nRAW QUERY DUMP",
                "source": "fallback",
                "prompt": "Direct relationship context:\nRAW PROMPT",
            }

        fake_store.ask_yoda = raw_fallback
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-ask-yoda/people%2Ftony-guan",
                {"question": "What should I know?", "history": [{"role": "user", "content": "Hi"}]},
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn("output", data)
        self.assertNotIn("Question-specific gbrain retrieval", data["output"])
        self.assertNotIn("Direct relationship context", data["output"])
        self.assertNotIn("RAW QUERY DUMP", data["output"])
        self.assertNotIn("prompt", data)

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
        self.assertEqual(
            endpoints,
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
            },
        )


if __name__ == "__main__":
    unittest.main()
