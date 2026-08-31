import datetime as dt
import asyncio
import email.utils
import gzip
import hashlib
import io
import json
import subprocess
import tempfile
import threading
import time
import types
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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

    def get_health_graph(self):
        self.calls.append(("get_health_graph",))
        return self.graph

    def create_entity(self, name, description="", category="entities"):
        self.calls.append(("create_entity", name, description, category))
        return "people/new-person"

    def save_entity_raw(self, slug, content):
        self.calls.append(("save_entity_raw", slug, content))

    def refresh_after_entity_save(self):
        self.calls.append(("refresh_after_entity_save",))
        return TEST_GRAPH

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

    def backlink_page(self, slug, page=0, limit=20):
        self.calls.append(("backlink_page", slug, page, limit))
        return {
            "items": [],
            "page": int(page),
            "limit": int(limit),
            "total": 0,
        }, None

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

    def list_autopilot_findings(self, filters=None):
        self.calls.append(("list_autopilot_findings", dict(filters or {})))
        return {
            "findings": [
                {
                    "id": 7,
                    "check_name": "sync_freshness",
                    "state": "blocked",
                    "severity": "high",
                    "rationale": "no repo configured",
                }
            ],
            "total": 1,
        }

    def acknowledge_autopilot_finding(self, finding_id):
        self.calls.append(("acknowledge_autopilot_finding", finding_id))
        return {
            "id": finding_id,
            "state": "blocked",
            "acknowledged_by": "memory-stargraph-ui",
        }


def ready_deployment_attestation():
    return {
        "status": "ready",
        "freshness": "current",
        "summary": "Configured targets have current durable deployment attestation.",
        "source_timestamp": "2026-08-10T10:00:00Z",
        "readback_at": "2026-08-10T10:05:00Z",
        "evidence_slugs": ["runs/memory-stargraph-wish-sg0199-test"],
        "counts": {
            "configured_target_count": 1,
            "verified_target_count": 1,
            "stale_target_count": 0,
            "missing_target_count": 0,
            "source_mismatch_count": 0,
            "local_attestation_present": 1,
        },
        "local": {"status": "current", "verified": True, "source_timestamp": "2026-08-10T10:00:00Z"},
        "configured_remote": {"status": "ready", "configured_target_count": 1, "verified_target_count": 1, "source_timestamp": "2026-08-10T10:00:00Z"},
    }


def ready_reranker_readiness():
    return {
        "schema_version": 1,
        "status": "ready",
        "freshness": "current",
        "state": "supported_override",
        "sunset_detected": False,
        "sunset_date": "2026-09-04",
        "days_until_sunset": 5,
        "configured_override": True,
        "observed_at": "2026-08-30T20:00:00Z",
        "source": "bounded_local_gbrain_cli_read_only",
        "summary": "GBrain has an explicit non-ZeroEntropy reranker override.",
        "operator_action": {
            "approval_required": True,
            "automatic_mutation": False,
            "apply_command": "gbrain config set search.reranker.model voyage:rerank-2.5",
            "verification_commands": ["gbrain doctor --json --fast", "gbrain search 'memory stargraph' --limit 1"],
        },
    }


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
    class _JsonResponse:
        def __init__(self, payload, *, content_type="application/json"):
            self.payload = payload
            self.headers = {"Content-Type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    class _RawResponse:
        def __init__(self, payload, *, content_type):
            self.payload = payload
            self.headers = {"Content-Type": content_type}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.payload.encode("utf-8")

    def render_json_response(self, payload, accept_encoding=""):
        handler = object.__new__(MemoryStargraphHandler)
        handler.headers = {"Accept-Encoding": accept_encoding}
        handler.wfile = io.BytesIO()
        statuses = []
        headers = {}
        handler.send_response = statuses.append
        handler.send_header = lambda key, value: headers.__setitem__(key, value)
        handler.end_headers = lambda: None
        handler.end_json(payload)
        return statuses, headers, handler.wfile.getvalue()

    def render_static_head(self, path, headers=None):
        handler = object.__new__(MemoryStargraphHandler)
        handler.path = path
        handler.headers = dict(headers or {})
        handler.directory = str(server.PUBLIC_DIR)
        statuses = []
        response_headers = {}
        handler.send_response = statuses.append
        handler.send_header = lambda key, value: response_headers.__setitem__(key, value)
        handler.end_headers = lambda: None
        stream = handler.send_head()
        return statuses, response_headers, stream

    def test_end_json_compresses_large_payload_when_client_accepts_gzip(self):
        payload = {"ok": True, "nodes": [{"slug": f"notes/example-{index}", "summary": "memory stargraph " * 20} for index in range(20)]}

        statuses, headers, body = self.render_json_response(payload, "br, gzip")

        self.assertEqual(statuses, [HTTPStatus.OK])
        self.assertEqual(headers["Content-Encoding"], "gzip")
        self.assertEqual(headers["Vary"], "Accept-Encoding")
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(json.loads(gzip.decompress(body)), payload)

    def test_end_json_keeps_small_or_gzip_refused_payloads_plain(self):
        small_statuses, small_headers, small_body = self.render_json_response({"ok": True}, "gzip")
        large_payload = {"content": "memory stargraph " * 200}
        large_statuses, large_headers, large_body = self.render_json_response(large_payload, "gzip;q=0, *;q=1")

        self.assertEqual(small_statuses, [HTTPStatus.OK])
        self.assertNotIn("Content-Encoding", small_headers)
        self.assertNotIn("Vary", small_headers)
        self.assertEqual(json.loads(small_body), {"ok": True})
        self.assertEqual(large_statuses, [HTTPStatus.OK])
        self.assertNotIn("Content-Encoding", large_headers)
        self.assertEqual(large_headers["Vary"], "Accept-Encoding")
        self.assertEqual(json.loads(large_body), large_payload)

    def test_send_head_compresses_large_static_assets_losslessly(self):
        statuses, headers, stream = self.render_static_head("/app.js?version=test", {"Accept-Encoding": "gzip"})

        try:
            body = stream.read()
        finally:
            stream.close()
        self.assertEqual(statuses, [HTTPStatus.OK])
        self.assertEqual(headers["Content-Encoding"], "gzip")
        self.assertEqual(headers["Vary"], "Accept-Encoding")
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(gzip.decompress(body), (server.PUBLIC_DIR / "app.js").read_bytes())

    def test_send_head_prefers_validated_brotli_static_assets(self):
        statuses, headers, stream = self.render_static_head(
            "/app.js?version=test",
            {"Accept-Encoding": "gzip, br"},
        )

        try:
            body = stream.read()
        finally:
            stream.close()
        manifest = json.loads(
            (server.PUBLIC_DIR / server.BROTLI_STATIC_DIR / "manifest.json").read_text()
        )
        entry = manifest["assets"]["app.js"]
        self.assertEqual(statuses, [HTTPStatus.OK])
        self.assertEqual(headers["Content-Encoding"], "br")
        self.assertEqual(headers["Vary"], "Accept-Encoding")
        self.assertEqual(len(body), entry["brotli_size"])
        self.assertEqual(
            entry["source_sha256"],
            hashlib.sha256((server.PUBLIC_DIR / "app.js").read_bytes()).hexdigest(),
        )

    def test_send_head_falls_back_when_brotli_sidecar_is_stale(self):
        with mock.patch("server.brotli_static_file", return_value=None):
            statuses, headers, stream = self.render_static_head(
                "/styles.css",
                {"Accept-Encoding": "br"},
            )

        try:
            body = stream.read()
        finally:
            stream.close()
        self.assertEqual(statuses, [HTTPStatus.OK])
        self.assertNotIn("Content-Encoding", headers)
        self.assertEqual(body, (server.PUBLIC_DIR / "styles.css").read_bytes())

    def test_send_head_honors_static_encoding_quality(self):
        statuses, headers, stream = self.render_static_head(
            "/styles.css",
            {"Accept-Encoding": "br;q=0, gzip;q=0.5"},
        )

        try:
            body = stream.read()
        finally:
            stream.close()
        self.assertEqual(statuses, [HTTPStatus.OK])
        self.assertEqual(headers["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(body), (server.PUBLIC_DIR / "styles.css").read_bytes())

    def test_send_head_preserves_static_conditional_requests(self):
        path = server.PUBLIC_DIR / "styles.css"
        modified = email.utils.formatdate(path.stat().st_mtime, usegmt=True)

        statuses, headers, stream = self.render_static_head(
            "/styles.css",
            {"Accept-Encoding": "gzip", "If-Modified-Since": modified},
        )

        self.assertEqual(statuses, [HTTPStatus.NOT_MODIFIED])
        self.assertEqual(headers["Vary"], "Accept-Encoding")
        self.assertIsNone(stream)

    def test_send_head_preserves_plain_static_fallback(self):
        statuses, headers, stream = self.render_static_head("/styles.css", {"Accept-Encoding": "identity"})

        try:
            body = stream.read()
        finally:
            stream.close()
        self.assertEqual(statuses, [HTTPStatus.OK])
        self.assertNotIn("Content-Encoding", headers)
        self.assertEqual(body, (server.PUBLIC_DIR / "styles.css").read_bytes())

    def test_gbrain_call_tool_uses_remote_mcp_instead_of_local_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "engine": "postgres",
                        "remote_mcp": {
                            "issuer_url": "https://auth.example",
                            "mcp_url": "https://mcp.example/mcp",
                            "oauth_client_id": "memory-stargraph",
                        },
                    }
                ),
                encoding="utf-8",
            )
            responses = iter(
                (
                    self._JsonResponse(
                        {"token_endpoint": "https://auth.example/token"}
                    ),
                    self._JsonResponse(
                        {"access_token": "private-access-token", "expires_in": 3600}
                    ),
                    self._JsonResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": "response",
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(
                                            {
                                                "slug": "agents/timmy",
                                                "type": "agent",
                                            }
                                        ),
                                    }
                                ]
                            },
                        }
                    ),
                )
            )
            requests = []

            def open_remote(request, **_kwargs):
                requests.append(request)
                return next(responses)

            with (
                mock.patch.dict(
                    server.os.environ,
                    {
                        "GBRAIN_HOME": str(home),
                        "GBRAIN_REMOTE_CLIENT_SECRET": "private-client-secret",
                    },
                    clear=False,
                ),
                mock.patch("server.urlopen", side_effect=open_remote),
                mock.patch("server.run_gbrain", return_value='{"source":"local"}') as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                result = server.gbrain_call_tool(
                    "get_page", {"slug": "agents/timmy"}
                )

            self.assertEqual(
                result,
                {"slug": "agents/timmy", "type": "agent"},
            )
            rpc = json.loads(requests[-1].data.decode("utf-8"))
            self.assertEqual(rpc["method"], "tools/call")
            self.assertEqual(rpc["params"]["name"], "get_page")
            self.assertEqual(
                rpc["params"]["arguments"], {"slug": "agents/timmy"}
            )
            self.assertEqual(
                requests[-1].headers["Authorization"],
                "Bearer private-access-token",
            )
            local.assert_not_called()

    def test_gbrain_call_tool_remote_config_missing_secret_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "remote_mcp": {
                            "issuer_url": "https://auth.example",
                            "mcp_url": "https://mcp.example/mcp",
                            "oauth_client_id": "memory-stargraph",
                            "oauth_client_secret": "must-not-be-read-from-config",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(
                    server.os.environ,
                    {"GBRAIN_HOME": str(home)},
                    clear=True,
                ),
                mock.patch("server.run_gbrain", return_value='{"source":"local"}') as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                with self.assertRaisesRegex(RuntimeError, "client secret"):
                    server.gbrain_call_tool("get_page", {"slug": "agents/timmy"})

            local.assert_not_called()

    def test_gbrain_call_tool_remote_tool_error_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "remote_mcp": {
                            "issuer_url": "https://auth.example",
                            "mcp_url": "https://mcp.example/mcp",
                            "oauth_client_id": "memory-stargraph",
                        }
                    }
                ),
                encoding="utf-8",
            )
            responses = iter(
                (
                    self._JsonResponse(
                        {"token_endpoint": "https://auth.example/token"}
                    ),
                    self._JsonResponse(
                        {"access_token": "private-access-token", "expires_in": 3600}
                    ),
                    self._JsonResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": "response",
                            "result": {
                                "isError": True,
                                "content": [
                                    {"type": "text", "text": "page_not_found"}
                                ],
                            },
                        }
                    ),
                )
            )
            with (
                mock.patch.dict(
                    server.os.environ,
                    {
                        "GBRAIN_HOME": str(home),
                        "GBRAIN_REMOTE_CLIENT_SECRET": "private-client-secret",
                    },
                    clear=False,
                ),
                mock.patch("server.urlopen", side_effect=lambda *_a, **_k: next(responses)),
                mock.patch("server.run_gbrain", return_value='{"source":"local"}') as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                with self.assertRaisesRegex(RuntimeError, "page_not_found"):
                    server.gbrain_call_tool("get_page", {"slug": "missing/page"})

            local.assert_not_called()

    def test_gbrain_call_tool_without_remote_config_prefers_local_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps({"engine": "postgres"}), encoding="utf-8"
            )
            with (
                mock.patch.dict(
                    server.os.environ,
                    {"GBRAIN_HOME": str(home)},
                    clear=True,
                ),
                mock.patch.object(
                    server.PERSISTENT_GBRAIN_SEARCH,
                    "call_tool",
                    return_value={"slug": "agents/timmy", "type": "agent"},
                ) as local_mcp,
                mock.patch(
                    "server.run_gbrain",
                    return_value='{"slug":"agents/timmy","type":"agent"}',
                ) as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                result = server.gbrain_call_tool(
                    "get_page", {"slug": "agents/timmy"}
                )

            self.assertEqual(result["slug"], "agents/timmy")
            local_mcp.assert_called_once_with(
                "get_page", {"slug": "agents/timmy"}, timeout=30
            )
            local.assert_not_called()

    def test_gbrain_call_tool_read_falls_back_to_local_cli_when_mcp_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps({"engine": "postgres"}), encoding="utf-8"
            )
            with (
                mock.patch.dict(server.os.environ, {"GBRAIN_HOME": str(home)}, clear=True),
                mock.patch.object(
                    server.PERSISTENT_GBRAIN_SEARCH,
                    "call_tool",
                    side_effect=RuntimeError("MCP unavailable"),
                ),
                mock.patch(
                    "server.run_gbrain",
                    return_value='{"slug":"agents/timmy","type":"agent"}',
                ) as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                result = server.gbrain_call_tool("get_page", {"slug": "agents/timmy"})

            self.assertEqual(result["slug"], "agents/timmy")
            local.assert_called_once()

    def test_gbrain_call_tool_write_fails_closed_without_cli_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps({"engine": "postgres"}), encoding="utf-8"
            )
            with (
                mock.patch.dict(server.os.environ, {"GBRAIN_HOME": str(home)}, clear=True),
                mock.patch.object(
                    server.PERSISTENT_GBRAIN_SEARCH,
                    "call_tool",
                    side_effect=TimeoutError("uncertain write result"),
                ),
                mock.patch("server.run_gbrain") as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                with self.assertRaisesRegex(TimeoutError, "uncertain write result"):
                    server.gbrain_call_tool(
                        "put_page", {"slug": "notes/example", "content": "# Example"}
                    )

            local.assert_not_called()

    def test_gbrain_call_tool_keeps_large_custom_reads_on_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps({"engine": "postgres"}), encoding="utf-8"
            )
            with (
                mock.patch.dict(server.os.environ, {"GBRAIN_HOME": str(home)}, clear=True),
                mock.patch.object(server.PERSISTENT_GBRAIN_SEARCH, "call_tool") as local_mcp,
                mock.patch(
                    "server.run_gbrain",
                    return_value='{"takes":[{"id":"take-1"}]}',
                ) as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                result = server.gbrain_call_tool("takes_list", {"limit": 500})

            self.assertEqual(result["takes"], [{"id": "take-1"}])
            local_mcp.assert_not_called()
            local.assert_called_once()

    def test_remote_gbrain_tool_caller_accepts_sse_json_rpc_response(self):
        response = self._RawResponse(
            'event: message\ndata: {"jsonrpc":"2.0","id":"one","result":{"ok":true}}\n\n',
            content_type="text/event-stream",
        )
        caller = server.RemoteGBrainToolCaller(Path("unused.json"))
        with mock.patch("server.urlopen", return_value=response):
            result = caller._read_json_response(Request("https://mcp.example/mcp"))

        self.assertEqual(result["result"], {"ok": True})

    def test_gbrain_call_tool_invalid_config_shape_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".gbrain"
            config_dir.mkdir()
            (config_dir / "config.json").write_text("[]", encoding="utf-8")
            with (
                mock.patch.dict(
                    server.os.environ,
                    {"GBRAIN_HOME": str(home)},
                    clear=True,
                ),
                mock.patch("server.run_gbrain", return_value='{"source":"local"}') as local,
            ):
                server._REMOTE_GBRAIN_TOOL_CALLER = None
                with self.assertRaisesRegex(RuntimeError, "config is unavailable"):
                    server.gbrain_call_tool("get_page", {"slug": "agents/timmy"})

            local.assert_not_called()

    def dispatch_post(self, path, payload=None, *, allow_resolver_submit=False, headers=None):
        handler = object.__new__(MemoryStargraphHandler)
        handler.path = path
        handler.headers = dict(headers or {})
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

    def dispatch_get(self, path, *, headers=None):
        handler = object.__new__(MemoryStargraphHandler)
        handler.path = path
        handler.headers = dict(headers or {})
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

    def test_exact_todo_id_search_reads_completed_archives(self):
        root = """# Memory Starmap TODO List

## Todo Items

| id | status | priority | title | node | updated | notes |
| --- | --- | --- | --- | --- | --- | --- |
| SG-0202 | planned | P1 | Restore archive search | [[notes/memory-starmap-todo-list/restore-archive-search]] | 2026-08-12 | Current row. |

## Completed Archives

| archive | sequence | first id | last id | count |
| --- | --- | --- | --- | --- |
| [[notes/memory-starmap-todo-list/completed-archive-0004]] | 4 | SG-0151 | SG-0201 | 2 |
"""
        archive = """# Memory Starmap Completed TODO Archive 0004

## Todo Items

| id | status | priority | title | node | updated | notes |
| --- | --- | --- | --- | --- | --- | --- |
| SG-0151 | completed | P1 | Earlier completed row | [[notes/memory-starmap-todo-list/earlier-completed-row]] | 2026-08-01 | Done. |
| SG-0201 | completed | P1 | Include persist identity metadata in SRE decision bundles | [[notes/memory-starmap-todo-list/include-persist-identity-metadata-in-sre-decision-bundles]] | 2026-08-11 | Done. |
"""

        def fake_run_gbrain(command, slug, timeout=0):
            self.assertEqual(command, "get")
            return {"notes/memory-starmap-todo-list": root, "notes/memory-starmap-todo-list/completed-archive-0004": archive}[slug]

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_index = Path(tmpdir) / "missing-archive-index.json"
            with mock.patch("server.COMPLETED_TODO_ARCHIVE_INDEX_PATH", missing_index), mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
                results, status = server.exact_todo_id_search_results("SG-0201")
        self.assertEqual(status, "complete")
        self.assertEqual(results[0]["slug"], "notes/memory-starmap-todo-list/include-persist-identity-metadata-in-sre-decision-bundles")
        self.assertIn("archived", results[0]["preview"].lower())

    def test_exact_todo_id_search_uses_durable_completed_archive_index_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_index = Path(tmpdir) / "completed-todo-archive-index.json"
            archive_index.write_text(json.dumps({
                "schema": "memory-stargraph-completed-todo-archive-index-v1",
                "archives": [{
                    "slug": "notes/memory-starmap-todo-list/completed-archive-0004",
                    "sequence": 4,
                    "first_id": "SG-0151",
                    "last_id": "SG-0201",
                    "count": 2,
                    "rows": [
                        {
                            "id": "SG-0151",
                            "status": "completed",
                            "priority": "P1",
                            "title": "Earlier completed row",
                            "slug": "notes/memory-starmap-todo-list/earlier-completed-row",
                            "updated": "2026-08-01",
                        },
                        {
                            "id": "SG-0201",
                            "status": "completed",
                            "priority": "P1",
                            "title": "Include persist identity metadata in SRE decision bundles",
                            "slug": "notes/memory-starmap-todo-list/include-persist-identity-metadata-in-sre-decision-bundles",
                            "updated": "2026-08-11",
                        },
                    ],
                }],
            }))

            with mock.patch("server.COMPLETED_TODO_ARCHIVE_INDEX_PATH", archive_index), mock.patch("server.run_gbrain") as run_gbrain:
                results, status = server.exact_todo_id_search_results("SG-0201")
        self.assertEqual(status, "complete")
        self.assertEqual(results[0]["slug"], "notes/memory-starmap-todo-list/include-persist-identity-metadata-in-sre-decision-bundles")
        run_gbrain.assert_not_called()

    def test_exact_todo_id_search_fails_closed_on_archive_mismatch(self):
        root = """# Memory Starmap TODO List

## Todo Items

| id | status | priority | title | node | updated | notes |
| --- | --- | --- | --- | --- | --- | --- |

## Completed Archives

| archive | sequence | first id | last id | count |
| --- | --- | --- | --- | --- |
| [[notes/memory-starmap-todo-list/completed-archive-0004]] | 4 | SG-0151 | SG-0201 | 50 |
"""
        archive = """# Archive

## Todo Items

| id | status | priority | title | node | updated | notes |
| --- | --- | --- | --- | --- | --- | --- |
| SG-0201 | completed | P1 | Incomplete archive | [[notes/incomplete]] | 2026-08-11 | Bad metadata. |
"""

        def fake_run_gbrain(command, slug, timeout=0):
            self.assertEqual(command, "get")
            return {"notes/memory-starmap-todo-list": root, "notes/memory-starmap-todo-list/completed-archive-0004": archive}[slug]

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_index = Path(tmpdir) / "missing-archive-index.json"
            with mock.patch("server.COMPLETED_TODO_ARCHIVE_INDEX_PATH", missing_index), mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
                results, status = server.exact_todo_id_search_results("SG-0201")
        self.assertEqual(results, [])
        self.assertEqual(status, "partial_timeout")

    def test_health_uses_cached_startup_graph_without_graph_request(self):
        fake_store = FakeStore()
        fake_store.graph = None
        cached = {
            "title": "Memory Stargraph",
            "source": {"mode": "cache", "status": "cached-startup"},
            "stats": {"nodes": 75, "edges": 120},
            "nodes": [],
            "edges": [],
        }

        def health_graph():
            fake_store.calls.append(("get_health_graph",))
            fake_store.graph = cached
            return cached

        fake_store.get_health_graph = health_graph
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.runtime_gbrain_version", return_value="V0.46.28.0"),
            mock.patch("server.gbrain_reranker_readiness", return_value=ready_reranker_readiness()),
        ):
            status, data = self.dispatch_get("/api/health")

        self.assertEqual(status, 200)
        self.assertTrue(data["loaded"])
        self.assertEqual(data["source"]["status"], "cached-startup")
        self.assertEqual(data["stats"]["nodes"], 75)
        self.assertEqual(data["gbrain_version"], "V0.46.28.0")
        self.assertEqual(data["gbrain_reranker"]["status"], "ready")
        self.assertEqual(fake_store.calls, [("get_health_graph",)])

    def test_retired_openclaw_profile_routes_are_not_served_even_with_legacy_token(self):
        headers = {"Authorization": "Bearer retired-token"}
        routes = (
            ("GET", "/api/internal/openclaw-profiles/active"),
            ("GET", "/api/internal/openclaw-profiles/operations/retired-operation"),
            ("POST", "/api/internal/openclaw-profiles/provision"),
            (
                "POST",
                "/api/internal/openclaw-profiles/operations/retired-operation/recover",
            ),
        )
        server_class = getattr(
            server, "MemoryStargraphHTTPServer", server.ThreadingHTTPServer
        )
        httpd = server_class(("127.0.0.1", 0), MemoryStargraphHandler)
        serve_thread = threading.Thread(target=httpd.serve_forever)
        serve_thread.start()
        try:
            with mock.patch.dict(
                "os.environ",
                {
                    "MEMORY_STARGRAPH_OC_PROVISION_ENABLED": "1",
                    "MEMORY_STARGRAPH_OC_PROVISION_TOKEN": "retired-token",
                },
                clear=False,
            ):
                for method, path in routes:
                    request = Request(
                        f"http://127.0.0.1:{httpd.server_address[1]}{path}",
                        data=b"{}" if method == "POST" else None,
                        headers={
                            **headers,
                            "Content-Type": "application/json",
                        },
                        method=method,
                    )
                    with self.subTest(method=method, path=path):
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(request, timeout=3)
                        self.assertEqual(raised.exception.code, HTTPStatus.NOT_FOUND)
        finally:
            httpd.shutdown()
            serve_thread.join(3)
            httpd.server_close()

        self.assertFalse(serve_thread.is_alive())
        for retired_symbol in (
            "openclaw_profile_activation_service",
            "openclaw_profile_activation_executor",
            "start_openclaw_profile_activation_runtime",
            "stop_openclaw_profile_activation_runtime",
            "openclaw_provisioning_authorized",
        ):
            self.assertFalse(hasattr(server, retired_symbol))
    def test_health_preserves_unloaded_state_when_cache_unavailable(self):
        fake_store = FakeStore()
        fake_store.graph = None

        def health_graph():
            fake_store.calls.append(("get_health_graph",))
            return None

        fake_store.get_health_graph = health_graph
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.gbrain_reranker_readiness", return_value=ready_reranker_readiness()),
        ):
            status, data = self.dispatch_get("/api/health")

        self.assertEqual(status, 200)
        self.assertFalse(data["loaded"])
        self.assertIsNone(data["source"])
        self.assertIsNone(data["stats"])
        self.assertEqual(fake_store.calls, [("get_health_graph",)])

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

    def test_worker_read_endpoints_return_tags_and_bounded_pages(self):
        fake_store = mock.Mock()
        fake_store.get_entity_tags.return_value = ["active", "capture-link"]
        fake_store.list_pages.return_value = [
            {"slug": "runs/a", "type": "run", "title": "Run A", "updated": "2026-08-25"}
        ]
        with mock.patch("server.STORE", fake_store):
            tag_status, tag_data = self.dispatch_get("/api/entity-tags/runs%2Fa")
            page_status, page_data = self.dispatch_get(
                "/api/pages?tag=active&type=run&limit=250"
            )

        self.assertEqual(tag_status, 200)
        self.assertEqual(tag_data["tags"], ["active", "capture-link"])
        fake_store.get_entity_tags.assert_called_once_with("runs/a")
        self.assertEqual(page_status, 200)
        self.assertEqual(page_data["pages"][0]["slug"], "runs/a")
        fake_store.list_pages.assert_called_once_with(
            tag="active", entity_type="run", limit="250"
        )

    def test_backlinks_endpoint_returns_compact_page_when_requested(self):
        fake_store = FakeStore()
        fake_store.backlink_page = mock.Mock(return_value=({
            "items": [{
                "from_slug": "people/two",
                "to_slug": "people/tony-guan",
                "link_type": "knows",
            }],
            "page": 1,
            "limit": 1,
            "total": 2,
        }, None))
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-backlinks/people%2Ftony-guan",
                {"compact": True, "page": 1, "limit": 1},
            )

        self.assertEqual(status, 200)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["items"], [{
            "from_slug": "people/two",
            "to_slug": "people/tony-guan",
            "link_type": "knows",
        }])
        self.assertNotIn("output", data)
        fake_store.backlink_page.assert_called_once_with("people/tony-guan", 1, 1)

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

    def test_gbrain_backend_config_infers_secondary_authority_from_secondary_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "local.json"
            config_path.write_text(json.dumps({"gbrain_path": "/Users/toddy/.gbrain-secondary-home/bin/gbrain-secondary"}))
            with mock.patch.dict("os.environ", {"MEMORY_STARGRAPH_CONFIG": str(config_path)}):
                status, data = self.dispatch_get("/api/gbrain-backend-config")

        self.assertEqual(status, 200)
        self.assertEqual(data["current_backend"]["label"], "Secondary/test")
        self.assertEqual(data["current_backend"]["role"], "secondary")
        self.assertEqual(data["current_backend"]["write_authority"], "non_primary")
        self.assertTrue(data["current_backend"]["requires_split_brain_ack"])

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

    def test_entity_save_uses_post_refresh_raw_cache_boundary(self):
        fake_store = FakeStore()
        content = "---\ntype: person\n---\n\n# Tony Guan\n"

        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post(
                "/api/entity-save/people%2Ftony-guan",
                {"content": content},
            )

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(
            fake_store.calls,
            [
                ("save_entity_raw", "people/tony-guan", content),
                ("refresh_after_entity_save",),
            ],
        )

    def test_entity_media_endpoint_returns_detected_media(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/entity-media/people%2Ftony-guan")

        self.assertEqual(status, 200)
        self.assertEqual(data["slug"], "people/tony-guan")
        self.assertEqual(data["media"][0]["kind"], "image")
        self.assertIn(("get_entity_media", "people/tony-guan"), fake_store.calls)

    def test_media_file_streams_original_bytes_in_bounded_chunks(self):
        class RecordingWriter:
            def __init__(self):
                self.parts = []

            def write(self, data):
                self.parts.append(bytes(data))
                return len(data)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media_path = root / "products" / "memory-stargraph" / "large.png"
            media_path.parent.mkdir(parents=True)
            expected = b"x" * (server.MEDIA_STREAM_CHUNK_BYTES * 2 + 37)
            media_path.write_bytes(expected)
            handler = object.__new__(MemoryStargraphHandler)
            handler.wfile = RecordingWriter()
            handler.headers = {}
            handler.send_response = mock.Mock()
            handler.send_header = mock.Mock()
            handler.end_headers = mock.Mock()

            with mock.patch("server.MEDIA_ROOTS", [root]):
                handler.serve_media_file("/media/products/memory-stargraph/large.png")

            self.assertEqual(b"".join(handler.wfile.parts), expected)
            self.assertEqual(len(handler.wfile.parts), 3)
            self.assertLessEqual(max(map(len, handler.wfile.parts)), server.MEDIA_STREAM_CHUNK_BYTES)

            handler.wfile.parts.clear()
            with mock.patch("server.MEDIA_ROOTS", [root]):
                handler.serve_media_file("/media/products/memory-stargraph/large.png", head_only=True)
            self.assertEqual(handler.wfile.parts, [])

            handler.headers = {"Range": f"bytes={server.MEDIA_STREAM_CHUNK_BYTES - 20}-{server.MEDIA_STREAM_CHUNK_BYTES + 20}"}
            handler.send_response.reset_mock()
            handler.send_header.reset_mock()
            with mock.patch("server.MEDIA_ROOTS", [root]):
                handler.serve_media_file("/media/products/memory-stargraph/large.png")
            self.assertEqual(b"".join(handler.wfile.parts), expected[server.MEDIA_STREAM_CHUNK_BYTES - 20 : server.MEDIA_STREAM_CHUNK_BYTES + 21])
            handler.send_response.assert_called_once_with(HTTPStatus.PARTIAL_CONTENT)
            self.assertIn(
                mock.call(
                    "Content-Range",
                    f"bytes {server.MEDIA_STREAM_CHUNK_BYTES - 20}-{server.MEDIA_STREAM_CHUNK_BYTES + 20}/{len(expected)}",
                ),
                handler.send_header.call_args_list,
            )

            handler.wfile.parts.clear()
            handler.headers = {"Range": "bytes=99999999-"}
            handler.send_response.reset_mock()
            handler.send_header.reset_mock()
            with mock.patch("server.MEDIA_ROOTS", [root]):
                handler.serve_media_file("/media/products/memory-stargraph/large.png")
            self.assertEqual(handler.wfile.parts, [])
            handler.send_response.assert_called_once_with(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.assertIn(mock.call("Content-Range", f"bytes */{len(expected)}"), handler.send_header.call_args_list)

        self.assertEqual(server.parse_media_byte_range("bytes=-50", 100), (50, 99))
        self.assertEqual(server.parse_media_byte_range("bytes=90-", 100), (90, 99))
        self.assertIs(server.parse_media_byte_range("bytes=0-1,4-5", 100), server.MEDIA_RANGE_INVALID)

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
                "broad_graph_status": "optional_timeout",
                "broad_graph_unavailable_reason": "broad_graph_timeout",
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
        self.assertEqual(safe["broad_graph_status"], "optional_timeout")
        self.assertEqual(safe["broad_graph_unavailable_reason"], "broad_graph_timeout")
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
                "| SG-0150 | completed | P1 | Restore unrelated resolver health | [[notes/memory-starmap-todo-list/restore-unrelated-resolver-health]] | 2026-07-18T02:10:00-07:00 | Completed: reliability monitoring is healthy. |",
                "| SG-0149 | planned | P1 | Reconcile Ask Yoda operational recommendations with resolved incident state | [[notes/memory-starmap-todo-list/reconcile-ask-yoda-operational-recommendations-with-resolved-incident-st]] | 2026-07-19T01:14:12-07:00 | Planned current gap. |",
            ]
        )
        children = {
            "notes/memory-starmap-todo-list/separate-synthetic-resolver-probe-telemetry": "Status: completed\nCompletion Evidence: live resolver dry run excluded synthetic probes; auto_applied=0.",
            "notes/memory-starmap-todo-list/add-broad-graph-timeout-telemetry": "Status: completed\nCompletion Evidence: /api/yoda-logs exposes context_degraded and broad_graph_timeout.",
        }

        def fake_page(slug, timeout=20):
            del timeout
            if slug == "notes/memory-starmap-todo-list":
                return {"content": root}
            return {"content": children.get(slug, "")}

        stable = {"selected_node": "", "graph": "", "backlinks": "", "timings": {}}
        with (
            mock.patch.object(store, "get_yoda_page", side_effect=fake_page),
            mock.patch.object(store, "get_yoda_search_results", return_value=[]),
        ):
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
        self.assertNotIn("SG-0150", prompt)

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
                        "node_path": "/opt/local/bin/node",
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
            self.assertEqual(saved["yoda_node_path"], "/opt/local/bin/node")

    def test_openclaw_node_runtime_version_gate_matches_launcher_contract(self):
        self.assertTrue(server.openclaw_supports_node_version("v22.22.3"))
        self.assertFalse(server.openclaw_supports_node_version("v22.22.2"))
        self.assertFalse(server.openclaw_supports_node_version("v24.14.0"))
        self.assertTrue(server.openclaw_supports_node_version("v24.15.0"))
        self.assertFalse(server.openclaw_supports_node_version("v25.8.1"))
        self.assertTrue(server.openclaw_supports_node_version("v25.9.0"))

    def test_openclaw_agent_returns_unavailable_when_node_runtime_is_not_supported(self):
        with (
            mock.patch(
                "server.select_openclaw_node_runtime",
                return_value={
                    "status": "unavailable",
                    "path": "",
                    "version": "",
                    "source": "",
                    "error": "OpenClaw requires Node.js >=24.15.0; found v24.14.0",
                    "candidates": [],
                },
            ),
            mock.patch("server.subprocess.run") as run,
        ):
            result = server.run_openclaw_agent("prompt", config={"timeout": 20, "model": ""}, return_details=True)

        self.assertIsNone(result["output"])
        self.assertEqual(result["openclaw_status"], "runtime_unavailable")
        self.assertEqual(result["model_status"], "unavailable")
        self.assertEqual(result["node_runtime_status"], "unavailable")
        run.assert_not_called()

    def test_openclaw_agent_places_selected_node_runtime_first_in_path(self):
        completed = subprocess.CompletedProcess(
            ["openclaw"],
            0,
            stdout=b'{"finalAssistantVisibleText":"model answer"}',
            stderr=b"",
        )
        node_path = "/Users/toddy/.local/node-v24.15.0/bin/node"
        with (
            mock.patch(
                "server.select_openclaw_node_runtime",
                return_value={
                    "status": "ok",
                    "path": node_path,
                    "version": "v24.15.0",
                    "source": "configured",
                    "error": "",
                    "candidates": [],
                },
            ),
            mock.patch("server.subprocess.run", return_value=completed) as run,
        ):
            result = server.run_openclaw_agent("prompt", config={"timeout": 20, "model": ""}, return_details=True)

        self.assertEqual(result["output"], "model answer")
        self.assertEqual(result["node_runtime_status"], "ok")
        self.assertEqual(result["node_runtime_path"], node_path)
        env_path = run.call_args.kwargs["env"]["PATH"]
        self.assertTrue(env_path.startswith("/Users/toddy/.local/node-v24.15.0/bin:"))

    def test_gbrain_think_yoda_uses_question_and_anchor_from_prompt(self):
        prompt = "\n".join(
            [
                "You are Ask Yoda inside Memory Stargraph.",
                "Selected node: products/memory-stargraph",
                "Question: What is Memory Stargraph?",
                "Retrieval depth: 4",
                "Selected node content:",
                "# Memory Stargraph",
            ]
        )
        with mock.patch(
            "server.yoda_gbrain_call_tool", return_value={"answer": "model-backed answer"}
        ) as call_tool:
            result = server.run_gbrain_think_yoda(
                prompt,
                {"model": "openai:gpt-5.2", "timeout": 60},
                return_details=True,
            )

        self.assertEqual(result["output"], "model-backed answer")
        self.assertEqual(result["model_status"], "answered")
        call_tool.assert_called_once_with(
            "think",
            {
                "question": "What is Memory Stargraph?",
                "anchor": "products/memory-stargraph",
                "model": "openai:gpt-5.2",
                "save": False,
                "take": False,
            },
            timeout=60,
        )

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
                "/api/autopilot-findings",
                "/api/autopilot-findings/<id>/acknowledge",
            }.issubset(endpoints)
        )

    def test_autopilot_findings_endpoint_proxies_authoritative_gbrain_state(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/autopilot-findings?state=blocked&limit=500&offset=3")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["findings"][0]["state"], "blocked")
        self.assertIn(
            ("list_autopilot_findings", {"state": "blocked", "limit": 200, "offset": 3}),
            fake_store.calls,
        )

    def test_hosting_autopilot_findings_alias_uses_same_proxy(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_get("/api/hosting/autopilot-findings?limit=10")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIn(
            ("list_autopilot_findings", {"state": "", "limit": 10, "offset": 0}),
            fake_store.calls,
        )

    def test_autopilot_findings_falls_back_to_empty_supported_state_when_tool_missing(self):
        store = server.GraphStore()
        missing_tool = RuntimeError(
            "GBrain backend does not expose autopilot_findings_list: Unknown tool: autopilot_findings_list"
        )
        with (
            mock.patch("server.gbrain_call_tool", side_effect=missing_tool) as fake_tool,
            mock.patch("server.run_gbrain", return_value="No pages found.\n") as fake_gbrain,
        ):
            data = store.list_autopilot_findings({"limit": 10, "offset": 0})
            cached = store.list_autopilot_findings({"limit": 10, "offset": 0})

        self.assertEqual(data["findings"], [])
        self.assertEqual(cached, data)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["backend_status"], "gbrain_tag_fallback")
        self.assertNotIn("Unknown tool", json.dumps(data))
        self.assertEqual(fake_tool.call_count, 1)
        self.assertEqual(fake_gbrain.call_count, 2)
        self.assertIn(mock.call("list", "--tag", "autopilot-finding", "-n", "20", timeout=8), fake_gbrain.mock_calls)

    def test_autopilot_findings_falls_back_when_remote_mcp_reports_unknown_operation(self):
        store = server.GraphStore()
        missing_operation = RuntimeError(
            "UPGRADE_AVAILABLE 0.42.59.0 0.46.24.0\n"
            "Remote tool autopilot_findings_list failed: "
            '{"error":"unknown_operation","message":"Unknown: autopilot_findings_list"}'
        )
        with (
            mock.patch("server.gbrain_call_tool", side_effect=missing_operation),
            mock.patch("server.run_gbrain", return_value="No pages found.\n") as fake_gbrain,
        ):
            data = store.list_autopilot_findings({"limit": 1, "offset": 0})

        self.assertEqual(data["findings"], [])
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["backend_status"], "gbrain_tag_fallback")
        self.assertNotIn("unknown_operation", json.dumps(data))
        self.assertIn(
            mock.call("list", "--tag", "autopilot-finding", "-n", "20", timeout=8),
            fake_gbrain.mock_calls,
        )

    def test_autopilot_findings_reuses_missing_tool_capability_and_fallback_snapshot(self):
        store = server.GraphStore()
        missing_tool = RuntimeError("Unknown tool: autopilot_findings_list")
        with (
            mock.patch("server.gbrain_call_tool", side_effect=missing_tool) as fake_tool,
            mock.patch("server.run_gbrain", return_value="No pages found.\n") as fake_gbrain,
        ):
            first = store.list_autopilot_findings({"limit": 1, "offset": 0})
            second = store.list_autopilot_findings({"limit": 20, "offset": 0})

        self.assertEqual(first["backend_status"], "gbrain_tag_fallback")
        self.assertEqual(second["backend_status"], "gbrain_tag_fallback")
        self.assertEqual(fake_tool.call_count, 1)
        self.assertEqual(fake_gbrain.call_count, 2)

    def test_autopilot_findings_keeps_capability_when_result_cache_clears(self):
        store = server.GraphStore()
        missing_tool = RuntimeError("Unknown tool: autopilot_findings_list")
        with (
            mock.patch("server.gbrain_call_tool", side_effect=missing_tool) as fake_tool,
            mock.patch("server.run_gbrain", return_value="No pages found.\n") as fake_gbrain,
        ):
            store.list_autopilot_findings({"limit": 1, "offset": 0})
            store.autopilot_findings_cache.clear()
            store.list_autopilot_findings({"limit": 1, "offset": 0})

        self.assertEqual(fake_tool.call_count, 1)
        self.assertEqual(fake_gbrain.call_count, 4)

    def test_autopilot_findings_tag_fallback_lists_tags_concurrently(self):
        barrier = threading.Barrier(len(server.AUTOPILOT_FINDING_FALLBACK_TAGS))

        def fake_gbrain(*args, **_kwargs):
            self.assertEqual(args[:2], ("list", "--tag"))
            barrier.wait(timeout=1)
            return "No pages found.\n"

        with mock.patch("server.run_gbrain", side_effect=fake_gbrain):
            data = server.list_autopilot_findings_from_gbrain_pages({"limit": 1})

        self.assertEqual(data["findings"], [])
        self.assertEqual(data["checked_tags"], list(server.AUTOPILOT_FINDING_FALLBACK_TAGS))

    def test_autopilot_findings_tag_fallback_lists_bounded_pages(self):
        store = server.GraphStore()
        missing_tool = RuntimeError("Unknown tool: autopilot_findings_list")

        def fake_gbrain(*args, **_kwargs):
            if args[:3] == ("list", "--tag", "autopilot-finding"):
                return "notes/autopilot/finding-one\tnote\t2026-08-15\tFinding One\n"
            if args[:3] == ("list", "--tag", "follow-up"):
                return "No pages found.\n"
            if args == ("get", "notes/autopilot/finding-one"):
                return (
                    "---\n"
                    "title: Finding One\n"
                    "state: blocked\n"
                    "severity: high\n"
                    "rationale: Needs operator review.\n"
                    "owner: sre\n"
                    "repair_attempts: 1\n"
                    "postcondition_failures: 2\n"
                    "recommended_action: Review run evidence.\n"
                    "---\n"
                    "# Finding One\n"
                )
            raise AssertionError(args)

        with (
            mock.patch("server.gbrain_call_tool", side_effect=missing_tool),
            mock.patch("server.run_gbrain", side_effect=fake_gbrain) as run_gbrain,
        ):
            data = store.list_autopilot_findings({"state": "blocked", "limit": 5, "offset": 0})
            resolved = store.list_autopilot_findings({"state": "resolved", "limit": 5, "offset": 0})

        self.assertEqual(data["total"], 1)
        self.assertEqual(data["findings"][0]["slug"], "notes/autopilot/finding-one")
        self.assertEqual(data["findings"][0]["state"], "blocked")
        self.assertEqual(data["findings"][0]["severity"], "high")
        self.assertEqual(data["findings"][0]["repair_attempts"], 1)
        self.assertEqual(data["findings"][0]["postcondition_failures"], 2)
        self.assertEqual(data["findings"][0]["backend_source"], "gbrain_tag_fallback")
        self.assertEqual(resolved["total"], 0)
        self.assertEqual(run_gbrain.call_count, 3)

    def test_autopilot_findings_preserves_non_tool_backend_errors(self):
        store = server.GraphStore()
        with mock.patch("server.gbrain_call_tool", side_effect=RuntimeError("network failed")):
            with self.assertRaisesRegex(RuntimeError, "network failed"):
                store.list_autopilot_findings({"limit": 10})

    def test_autopilot_finding_acknowledgement_does_not_claim_resolution(self):
        fake_store = FakeStore()
        with mock.patch("server.STORE", fake_store):
            status, data = self.dispatch_post("/api/autopilot-findings/7/acknowledge", {})

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["finding"]["state"], "blocked")
        self.assertEqual(data["finding"]["acknowledged_by"], "memory-stargraph-ui")
        self.assertIn(("acknowledge_autopilot_finding", 7), fake_store.calls)

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

    def test_activation_funnel_is_privacy_safe_and_reports_live_readiness(self):
        fake_store = FakeStore()
        fake_store.graph = {
            "source": {"mode": "gbrain", "status": "live", "warnings": []},
            "nodes": [{"slug": "index", "degree": 3}],
        }
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.GBRAIN") as gbrain_path,
            mock.patch("server.GBRAIN_FILE_STORE_ROOTS", [Path(tempfile.gettempdir())]),
            mock.patch("server.GBRAIN_FILE_BASE_URLS", []),
        ):
            gbrain_path.exists.return_value = True
            status, data = self.dispatch_get("/api/activation-funnel")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["read_only"])
        self.assertTrue(data["privacy_safe"])
        self.assertEqual(data["mode"], "live-ready")
        step_ids = {step["id"] for step in data["steps"]}
        self.assertTrue(
            {
                "sample_brain_opened",
                "sample_node_selected",
                "relationship_provenance_viewed",
                "sample_yoda_attempted",
                "setup_diagnostics_reviewed",
                "live_gbrain_readiness_checked",
            }.issubset(step_ids)
        )
        self.assertTrue(data["live_state"]["ready"])
        self.assertNotIn("api_key", json.dumps(data).lower())
        self.assertNotIn("prompt", json.dumps(data).lower())

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

    def test_weekly_memory_value_digest_reports_verified_outcomes(self):
        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.timezone.utc)
                return value if tz is None else value.astimezone(tz)

        fake_store = FakeStore()
        evidence = {
            "notes/memory-starmap-todo-list": (
                "| SG-0184 | completed | P1 | Benchmark | [[notes/benchmark]] | 2026-08-01T07:57:00-07:00 | Completed. |\n"
                "| SG-0185 | completed | P1 | Search parity | [[notes/search]] | 2026-08-01T21:09:00-07:00 | Completed. |\n"
                "| SG-0167 | completed | P1 | Ask Yoda model fix | [[notes/superseding]] | 2026-08-02T08:24:28-07:00 | Completed. |\n"
                "| SG-0166 | failed | P1 | Historical blocker | [[notes/failed]] | 2026-07-28T16:08:24-07:00 | Failed. |"
            ),
            "notes/failed": (
                "---\n"
                "type: todo\n"
                "status: failed\n"
                "todo_id: SG-0166\n"
                "superseded_by: notes/superseding\n"
                "superseded_by_todo_id: SG-0167\n"
                "supersession_evidence:\n"
                "  - runs/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df\n"
                "---\n"
                "# Failed historical audit\n"
            ),
            "notes/superseding": (
                "---\n"
                "type: todo\n"
                "status: completed\n"
                "todo_id: SG-0167\n"
                "---\n"
                "# Completed superseding TODO\n"
            ),
            "learnings/memory-stargraph-20260719-operational-state-reconciliation-and-source-sync-preflight": "# Learning\n\nSource-sync preflight.",
            "reports/memory-stargraph-wish-sg0184-20260801t074549-0700-63e45d0": "10/10 answer success, 10/10 recall success, expected source coverage, contradiction pruning verified.",
            "runs/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df": "model-backed non-fallback answers with fallback state observed as zero.",
            "runs/memory-stargraph-wish-sg0185-20260801t204507-0700-125d15f": "API top slug, UI top slug, focus slug, and first visible result all aligned.",
            "runs/memory-stargraph-capture-link-drain-capture-link-drain-20260802t000254-0700-scheduled-85": "completed_empty_snapshot_enrichment with terminal outcomes.",
            "learnings/memory-stargraph-discovery-20260802-package-proof-before-expanding-surface": "Learning: package proof before expanding surface.",
        }

        def fake_gbrain(command, slug, **_kwargs):
            self.assertEqual(command, "get")
            return evidence[slug]

        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.run_gbrain", side_effect=fake_gbrain),
            mock.patch(
                "server.resolver_feedback_health",
                return_value={"pending": 0, "events_24h": 2},
            ),
            mock.patch(
                "server.latest_sre_numeric_evidence",
                return_value={
                    "status": "pass",
                    "passed": True,
                    "freshness": "current",
                    "evidence": [{"slug": "reports/memory-stargraph-wish-sg0196-20260809t144900-0700-56c8c7d", "available": True, "status": "available"}],
                    "counts": {
                        "numeric_schema_present": 1,
                        "capacity_categories_present": 1,
                        "backup_evidence_present": 1,
                        "restore_evidence_present": 1,
                        "baseline_windows_present": 1,
                    },
                    "summary": "Numeric SRE capacity, backup freshness, restore rehearsal, and 7-day/30-day baseline evidence is present.",
                },
            ),
            mock.patch("server.read_deployment_attestation", return_value=ready_deployment_attestation()),
            mock.patch("server.datetime", FixedDateTime),
        ):
            status, data = self.dispatch_get("/api/memory-value-digest?window=week")

        self.assertEqual(status, 200)
        self.assertTrue(data["read_only"])
        outcomes = data["verified_memory_outcomes"]
        self.assertEqual(outcomes["schema_version"], 1)
        self.assertEqual(outcomes["window"], "week")
        self.assertIn("weekly_deltas", outcomes)
        self.assertEqual(outcomes["weekly_deltas"]["completed"], 3)
        self.assertEqual(outcomes["summary_counts"]["gates_total"], 9)
        self.assertEqual(outcomes["summary_counts"]["gates_passed"], 9)
        gates = {gate["key"]: gate for gate in outcomes["gates"]}
        self.assertEqual(gates["retrieval_quality_benchmark"]["status"], "pass")
        self.assertEqual(gates["natural_language_search_parity"]["status"], "pass")
        self.assertEqual(gates["contradiction_pruning"]["status"], "pass")
        self.assertEqual(gates["unresolved_blockers"]["status"], "pass")
        self.assertEqual(gates["sre_capacity_backup_restore"]["status"], "pass")
        self.assertEqual(gates["configured_target_deployment_attestation"]["status"], "pass")
        self.assertEqual(gates["configured_target_deployment_attestation"]["counts"]["configured_target_count"], 1)
        self.assertEqual(gates["unresolved_blockers"]["counts"]["current_unresolved"], 0)
        self.assertEqual(gates["unresolved_blockers"]["counts"]["historical_failed"], 1)
        self.assertEqual(gates["unresolved_blockers"]["counts"]["superseded_failed"], 1)
        self.assertEqual(outcomes["historical_failures"][0]["status"], "superseded")
        self.assertEqual(outcomes["historical_failures"][0]["superseded_by_todo_id"], "SG-0167")
        self.assertEqual(outcomes["current_unresolved_blockers"], [])
        self.assertIn("reports/memory-stargraph-wish-sg0184-20260801t074549-0700-63e45d0", gates["retrieval_quality_benchmark"]["evidence_slugs"])
        serialized = json.dumps(outcomes).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("sk-", serialized)
        self.assertNotIn("/users/", serialized)
        self.assertNotIn("raw prompt", serialized)
        self.assertFalse(outcomes["resolver_choice"]["auto_approval"])
        self.assertEqual(outcomes["deployment_attestation"]["configured_remote"]["verified_target_count"], 1)

    def test_weekly_memory_value_digest_overlaps_resolver_and_outcome_reads(self):
        barrier = threading.Barrier(2)

        def resolver_health():
            barrier.wait(timeout=1)
            return {"pending": 2}

        def weekly_outcomes(_window, _backlog, _resolver):
            barrier.wait(timeout=1)
            return {"resolver_choice": {"status": "unknown", "pending_proposals": 0, "auto_approval": False}}

        with (
            mock.patch("server.STORE", FakeStore()),
            mock.patch("server.safe_gbrain_get_text_bounded", return_value=""),
            mock.patch("server.resolver_feedback_health", side_effect=resolver_health),
            mock.patch("server.verified_memory_outcomes", side_effect=weekly_outcomes),
        ):
            data = server.memory_value_digest("week")

        self.assertEqual(data["resolver_health"]["pending"], 2)
        self.assertEqual(data["verified_memory_outcomes"]["resolver_choice"]["status"], "observed")
        self.assertEqual(data["verified_memory_outcomes"]["resolver_choice"]["pending_proposals"], 2)

    def test_weekly_memory_value_digest_marks_missing_evidence_partial(self):
        fake_store = FakeStore()

        def fake_gbrain(command, slug, **_kwargs):
            self.assertEqual(command, "get")
            if slug == "notes/memory-starmap-todo-list":
                return "| SG-0186 | planned | P1 | Planned | [[notes/planned]] | 2026-08-02 | Planned. |"
            if slug == "learnings/memory-stargraph-20260719-operational-state-reconciliation-and-source-sync-preflight":
                return "# Learning\n\nNo recent durable Learning was readable."
            raise RuntimeError(f"missing {slug}")

        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.run_gbrain", side_effect=fake_gbrain),
            mock.patch("server.resolver_feedback_health", return_value={"pending": 0}),
            mock.patch(
                "server.latest_sre_numeric_evidence",
                return_value={
                    "status": "missing",
                    "passed": False,
                    "freshness": "missing",
                    "evidence": [],
                    "counts": {},
                    "summary": "Numeric SRE evidence missing.",
                },
            ),
            mock.patch("server.read_deployment_attestation", return_value={
                **ready_deployment_attestation(),
                "status": "no_activity",
                "freshness": "no_activity",
                "summary": "No durable deployment attestation.",
                "evidence_slugs": [],
                "counts": {"configured_target_count": 0, "verified_target_count": 0, "stale_target_count": 0, "missing_target_count": 0, "source_mismatch_count": 0},
                "configured_remote": {"status": "no_activity", "configured_target_count": 0, "verified_target_count": 0},
            }),
        ):
            status, data = self.dispatch_get("/api/memory-value-digest?window=week")

        self.assertEqual(status, 200)
        outcomes = data["verified_memory_outcomes"]
        self.assertEqual(outcomes["status"], "partial")
        self.assertGreater(outcomes["summary_counts"]["gates_missing"], 0)
        gates = {gate["key"]: gate for gate in outcomes["gates"]}
        self.assertEqual(gates["retrieval_quality_benchmark"]["status"], "missing")
        self.assertEqual(gates["worker_learnings"]["status"], "missing")
        self.assertEqual(gates["sre_capacity_backup_restore"]["status"], "missing")
        self.assertEqual(gates["configured_target_deployment_attestation"]["status"], "no_activity")
        self.assertEqual(gates["unresolved_blockers"]["status"], "degraded")
        self.assertFalse(gates["retrieval_quality_benchmark"]["passed"])
        self.assertEqual(gates["retrieval_quality_benchmark"]["evidence_slugs"], [])

    def test_latest_sre_numeric_evidence_passes_with_current_backup_and_daily_weekly_evidence(self):
        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = dt.datetime(2026, 8, 17, 10, 0, tzinfo=dt.timezone.utc)
                return value if tz is None else value.astimezone(tz)

        def fake_evidence(slug, *_args, **_kwargs):
            if slug == "_backups/backup-latest":
                return "# Backup\n\n- Run timestamp UTC: 2026-08-17T09:00:00Z\n"
            return (
                "memory-stargraph-sre-numeric-evidence-v1 cpu memory disk open-file "
                "backup freshness restore rehearsal checksum 7-day 30-day "
                "daily observed_at 2026-08-17T09:30:00Z weekly observed_at 2026-08-17T08:30:00Z"
            )

        with (
            mock.patch("server.safe_gbrain_get_text_bounded", side_effect=fake_evidence),
            mock.patch("server.datetime", FixedDateTime),
        ):
            result = server.latest_sre_numeric_evidence()

        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["passed"])
        self.assertEqual(result["backup_freshness"]["status"], "current")
        self.assertEqual(result["counts"]["daily_evidence_current"], 1)
        self.assertEqual(result["counts"]["weekly_evidence_current"], 1)

    def test_terminal_sre_evidence_pairs_selects_newest_valid_terminal_run_per_mode(self):
        daily_new = "runs/memory-stargraph-sre-daily-reliability-20260826-new"
        daily_old = "runs/memory-stargraph-sre-daily-reliability-20260825-old"
        weekly_new = "runs/memory-stargraph-sre-weekly-resilience-20260826-new"
        pages = [{"slug": slug} for slug in (daily_new, daily_old, weekly_new)]
        texts = {
            daily_new: (
                "---\nstatus: completed\ncompleted_at: 2026-08-26T10:00:00Z\n"
                "mode: daily_reliability\nreport_slug: reports/daily-new\n"
                "product_owner_notification_status: acknowledged_by_product_owner\n"
                "product_owner_notification_pending: false\n---\n"
            ),
            "reports/daily-new": f"---\nstatus: completed\nrun_slug: {daily_new}\n---\n",
            daily_old: (
                "---\nstatus: completed\ncompleted_at: 2026-08-25T10:00:00Z\n"
                "mode: daily_reliability\nreport_slug: reports/daily-old\n---\n"
            ),
            "reports/daily-old": f"---\nstatus: completed\nrun_slug: {daily_old}\n---\n",
            weekly_new: (
                "---\nstatus: completed_with_skips\ncompleted_at: 2026-08-26T09:00:00Z\n"
                "mode: weekly_resilience\nreport_slug: reports/weekly-new\n---\n"
            ),
            "reports/weekly-new": f"---\nstatus: completed_with_skips\nrun_slug: {weekly_new}\n---\n",
        }
        store = mock.Mock()
        store.list_pages.return_value = pages

        with (
            mock.patch("server.STORE", store),
            mock.patch("server.safe_gbrain_get_text_bounded", side_effect=lambda slug, *_args, **_kwargs: texts.get(slug, "")),
        ):
            records = server.terminal_sre_evidence_pairs()

        self.assertEqual([item["run_slug"] for item in records], [daily_new, weekly_new])
        self.assertTrue(records[0]["acknowledged"])
        self.assertFalse(records[1]["acknowledged"])

    def test_terminal_sre_evidence_pairs_fail_closed_on_nonterminal_or_mismatched_evidence(self):
        planned = "runs/memory-stargraph-sre-daily-reliability-planned"
        mismatched = "runs/memory-stargraph-sre-weekly-resilience-mismatch"
        store = mock.Mock()
        store.list_pages.return_value = [{"slug": planned}, {"slug": mismatched}]
        texts = {
            planned: "---\nstatus: implementing\ncompleted_at: 2026-08-26T10:00:00Z\nreport_slug: reports/planned\n---\n",
            mismatched: "---\nstatus: completed\ncompleted_at: 2026-08-26T09:00:00Z\nreport_slug: reports/mismatch\n---\n",
            "reports/mismatch": "---\nstatus: completed\nrun_slug: runs/unrelated\n---\n",
        }

        with (
            mock.patch("server.STORE", store),
            mock.patch("server.safe_gbrain_get_text_bounded", side_effect=lambda slug, *_args, **_kwargs: texts.get(slug, "")),
        ):
            self.assertEqual(server.terminal_sre_evidence_pairs(), [])

    def test_runtime_gbrain_version_reuses_initialized_persistent_server_info(self):
        server.runtime_gbrain_version.cache_clear()
        original_version = server.PERSISTENT_GBRAIN_SEARCH.server_version
        try:
            server.PERSISTENT_GBRAIN_SEARCH.server_version = "V0.46.28.0"
            with mock.patch("server.subprocess.run") as run:
                self.assertEqual(server.runtime_gbrain_version(), "V0.46.28.0")
            run.assert_not_called()
        finally:
            server.PERSISTENT_GBRAIN_SEARCH.server_version = original_version
            server.runtime_gbrain_version.cache_clear()

    def test_runtime_gbrain_version_is_bounded_and_truthful(self):
        server.runtime_gbrain_version.cache_clear()
        try:
            completed = subprocess.CompletedProcess(["gbrain", "--version"], 0, stdout="gbrain 0.14.2\n", stderr="")
            with mock.patch("server.subprocess.run", return_value=completed) as run:
                self.assertEqual(server.runtime_gbrain_version(), "V0.14.2")
            run.assert_called_once()

            server.runtime_gbrain_version.cache_clear()
            failed = subprocess.CompletedProcess(["gbrain", "--version"], 1, stdout="", stderr="unavailable")
            with mock.patch("server.subprocess.run", return_value=failed):
                self.assertEqual(server.runtime_gbrain_version(), "")
        finally:
            server.runtime_gbrain_version.cache_clear()

    def test_runtime_gbrain_version_retries_transient_unavailable_probe(self):
        server.runtime_gbrain_version.cache_clear()
        try:
            failed = subprocess.CompletedProcess(["gbrain", "--version"], 1, stdout="", stderr="starting")
            completed = subprocess.CompletedProcess(["gbrain", "--version"], 0, stdout="gbrain 0.46.28.0\n", stderr="")
            with mock.patch("server.subprocess.run", side_effect=[failed, completed]) as run:
                self.assertEqual(server.runtime_gbrain_version(), "V0.46.28.0")
            self.assertEqual(run.call_count, 2)
        finally:
            server.runtime_gbrain_version.cache_clear()

    def test_reranker_readiness_parses_zeroentropy_warning_and_human_approved_action(self):
        result = server.parse_gbrain_reranker_readiness(
            "",
            "Config key not found: search.reranker.model",
            1,
            search_stderr=(
                "[gbrain] DEPRECATED: ZeroEntropy reranker stops working on 2026-09-04. "
                "Switch: `gbrain config set search.reranker.model voyage:rerank-2.5`"
            ),
            search_returncode=0,
            observed_at=dt.datetime(2026, 8, 30, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["state"], "deprecated_zeroentropy")
        self.assertTrue(result["sunset_detected"])
        self.assertEqual(result["sunset_date"], "2026-09-04")
        self.assertEqual(result["days_until_sunset"], 5)
        self.assertTrue(result["operator_action"]["approval_required"])
        self.assertFalse(result["operator_action"]["automatic_mutation"])
        self.assertIn("voyage:rerank-2.5", result["operator_action"]["apply_command"])
        self.assertNotIn("Config key not found", json.dumps(result))

    def test_reranker_readiness_accepts_supported_override_without_search_probe(self):
        result = server.parse_gbrain_reranker_readiness(
            "voyage:rerank-2.5\n",
            "",
            0,
            observed_at=dt.datetime(2026, 8, 30, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["state"], "supported_override")
        self.assertTrue(result["configured_override"])
        self.assertFalse(result["sunset_detected"])

    def test_reranker_readiness_is_partial_when_config_and_warning_are_unverified(self):
        result = server.parse_gbrain_reranker_readiness(
            "",
            "bounded config read failed",
            1,
            search_stderr="",
            search_returncode=None,
            observed_at=dt.datetime(2026, 8, 30, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["state"], "unverified")
        self.assertFalse(result["sunset_detected"])

    def test_reranker_readiness_is_missing_when_local_binary_probe_is_unavailable(self):
        result = server.parse_gbrain_reranker_readiness(
            "",
            "config probe unavailable",
            None,
            search_returncode=None,
            observed_at=dt.datetime(2026, 8, 30, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["state"], "gbrain_unavailable")

    def test_reranker_probe_skips_search_for_supported_override(self):
        supported = subprocess.CompletedProcess([], 0, stdout="voyage:rerank-2.5\n", stderr="")
        with (
            mock.patch("server.GBRAIN", Path("/configured/gbrain")),
            mock.patch("server.shutil.which", return_value="/managed/path/gbrain"),
            mock.patch("server.subprocess.run", return_value=supported) as run,
        ):
            result = server._probe_gbrain_reranker_readiness()

        self.assertEqual(result["status"], "ready")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], "/managed/path/gbrain")
        self.assertEqual(run.call_args.args[0][1:4], ["config", "get", "search.reranker.model"])

    def test_reranker_probe_degrades_when_default_config_is_unset(self):
        missing = subprocess.CompletedProcess(
            [],
            1,
            stdout="",
            stderr="Config key not found: search.reranker.model",
        )
        with mock.patch("server.subprocess.run", return_value=missing) as run:
            result = server._probe_gbrain_reranker_readiness()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["state"], "deprecated_default_unconfigured")
        self.assertEqual(run.call_count, 1)
        self.assertTrue(result["sunset_detected"])

    def test_latest_sre_numeric_evidence_reports_warning_and_critical_backup_freshness(self):
        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = dt.datetime(2026, 8, 17, 10, 0, tzinfo=dt.timezone.utc)
                return value if tz is None else value.astimezone(tz)

        base = (
            "memory-stargraph-sre-numeric-evidence-v1 cpu memory disk open-file "
            "backup freshness restore rehearsal checksum 7-day 30-day "
            "daily observed_at 2026-08-17T09:30:00Z weekly observed_at 2026-08-17T08:30:00Z"
        )

        def run_with_backup(backup_at):
            def fake_evidence(slug, *_args, **_kwargs):
                if slug == "_backups/backup-latest":
                    return f"# Backup\n\n- Run timestamp UTC: {backup_at}\n"
                return base
            with (
                mock.patch("server.safe_gbrain_get_text_bounded", side_effect=fake_evidence),
                mock.patch("server.datetime", FixedDateTime),
            ):
                return server.latest_sre_numeric_evidence()

        warning = run_with_backup("2026-08-15T18:00:00Z")
        critical = run_with_backup("2026-08-12T10:00:01Z")

        self.assertEqual(warning["status"], "warning")
        self.assertFalse(warning["passed"])
        self.assertEqual(warning["counts"]["backup_freshness_warning"], 1)
        self.assertEqual(critical["status"], "critical")
        self.assertFalse(critical["passed"])
        self.assertEqual(critical["counts"]["backup_freshness_critical"], 1)

    def test_backup_freshness_uses_explicit_run_timestamp_before_body_dates(self):
        result = server.backup_latest_freshness(
            "# Backup\n\n"
            "- Run timestamp UTC: 2026-08-12T10:00:01Z\n\n"
            "## Staged Changes\n\n"
            "- Added bahn-webinar-2026-08-27.md\n",
            observed_at=dt.datetime(2026, 8, 17, 10, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(result["latest_backup_at"], "2026-08-12T10:00:01Z")
        self.assertEqual(result["status"], "critical")

    def test_latest_sre_numeric_evidence_requires_current_daily_evidence_for_recovery(self):
        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = dt.datetime(2026, 8, 17, 10, 0, tzinfo=dt.timezone.utc)
                return value if tz is None else value.astimezone(tz)

        def fake_evidence(slug, *_args, **_kwargs):
            if slug == "_backups/backup-latest":
                return "# Backup\n\n- Run timestamp UTC: 2026-08-17T09:00:00Z\n"
            return (
                "memory-stargraph-sre-numeric-evidence-v1 cpu memory disk open-file "
                "backup freshness restore rehearsal checksum 7-day 30-day "
                "weekly observed_at 2026-08-17T08:30:00Z"
            )

        with (
            mock.patch("server.safe_gbrain_get_text_bounded", side_effect=fake_evidence),
            mock.patch("server.datetime", FixedDateTime),
        ):
            result = server.latest_sre_numeric_evidence()

        self.assertEqual(result["status"], "missing")
        self.assertFalse(result["passed"])
        self.assertEqual(result["daily_evidence"]["status"], "missing")
        self.assertEqual(result["counts"]["daily_evidence_current"], 0)

    def test_weekly_digest_and_customer_readiness_surface_critical_sre_evidence(self):
        fake_store = FakeStore()
        critical_sre = {
            "status": "critical",
            "passed": False,
            "freshness": "critical",
            "evidence": [{"slug": "_backups/backup-latest", "available": True, "status": "available"}],
            "evidence_slugs": ["_backups/backup-latest"],
            "counts": {"backup_freshness_critical": 1},
            "summary": "Latest backup evidence is older than the critical freshness threshold.",
        }

        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.safe_gbrain_get_text_bounded", return_value="unavailable: redacted"),
            mock.patch("server.resolver_feedback_health", return_value={"pending": 0}),
            mock.patch("server.latest_sre_numeric_evidence", return_value=critical_sre),
            mock.patch("server.read_deployment_attestation", return_value=ready_deployment_attestation()),
        ):
            status, digest = self.dispatch_get("/api/memory-value-digest?window=week")

        self.assertEqual(status, 200)
        outcomes = digest["verified_memory_outcomes"]
        self.assertEqual(outcomes["sre_numeric_evidence"]["status"], "critical")
        self.assertEqual(outcomes["sre_numeric_evidence"]["freshness"], "critical")
        self.assertEqual(outcomes["summary_counts"]["gates_degraded"], 1)
        gates = {gate["key"]: gate for gate in outcomes["gates"]}
        self.assertEqual(gates["sre_capacity_backup_restore"]["status"], "critical")

        weekly = {
            "verified_memory_outcomes": {
                "status": "degraded",
                "freshness": {"status": "critical"},
                "summary_counts": {"gates_passed": 8, "gates_total": 9},
                "sre_numeric_evidence": critical_sre,
            }
        }
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.first_run_activation_funnel", return_value={"mode": "live-ready"}),
            mock.patch("server.attachment_storage_status", return_value={"available": True}),
            mock.patch("server.public_yoda_model_config", return_value={"backend": "gbrain_think", "model": "openai:gpt-5.2"}),
            mock.patch("server.gbrain_reranker_readiness", return_value=ready_reranker_readiness()),
            mock.patch("server.memory_value_digest", return_value=weekly),
            mock.patch("server.resolver_feedback_health", return_value={"pending": 0, "proposal_counts": {"pending": 0}}),
            mock.patch("server.configured_target_readiness", return_value=("ready", {"evidence_slugs": []}, "Configured target evidence is available.")),
        ):
            status, readiness = self.dispatch_get("/api/customer-readiness")

        self.assertEqual(status, 200)
        checks = {check["id"]: check for check in readiness["checks"]}
        self.assertEqual(readiness["status"], "degraded")
        self.assertEqual(checks["sre_numeric_evidence"]["status"], "critical")
        self.assertEqual(checks["sre_numeric_evidence"]["freshness"], "critical")

    def test_weekly_memory_value_digest_keeps_broken_supersession_degraded(self):
        fake_store = FakeStore()
        base_evidence = {
            "learnings/memory-stargraph-20260719-operational-state-reconciliation-and-source-sync-preflight": "# Learning\n\nSource-sync preflight.",
            "reports/memory-stargraph-wish-sg0184-20260801t074549-0700-63e45d0": "10/10 answer success, 10/10 recall success, expected source coverage, contradiction pruning verified.",
            "runs/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df": "model-backed non-fallback answers with fallback state observed as zero.",
            "runs/memory-stargraph-wish-sg0185-20260801t204507-0700-125d15f": "API top slug, UI top slug, focus slug, and first visible result all aligned.",
            "runs/memory-stargraph-capture-link-drain-capture-link-drain-20260802t000254-0700-scheduled-85": "completed_empty_snapshot_enrichment with terminal outcomes.",
            "learnings/memory-stargraph-discovery-20260802-package-proof-before-expanding-surface": "Learning: package proof before expanding surface.",
        }

        cases = [
            (
                "missing target",
                {
                    "notes/memory-starmap-todo-list": "| SG-0166 | failed | P1 | Failed | [[notes/failed]] | 2026-07-28T16:08:24-07:00 | Failed. |",
                    "notes/failed": "---\nstatus: failed\ntodo_id: SG-0166\nsuperseded_by: notes/missing\nsuperseded_by_todo_id: SG-0167\nsupersession_evidence:\n  - runs/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df\n---\n# Failed\n",
                },
                "supersession target is unavailable",
            ),
            (
                "incomplete target",
                {
                    "notes/memory-starmap-todo-list": "| SG-0166 | failed | P1 | Failed | [[notes/failed]] | 2026-07-28T16:08:24-07:00 | Failed. |",
                    "notes/failed": "---\nstatus: failed\ntodo_id: SG-0166\nsuperseded_by: notes/superseding\nsuperseded_by_todo_id: SG-0167\nsupersession_evidence:\n  - runs/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df\n---\n# Failed\n",
                    "notes/superseding": "---\nstatus: implementing\ntodo_id: SG-0167\n---\n# Incomplete\n",
                },
                "supersession target is not completed",
            ),
            (
                "cyclic target",
                {
                    "notes/memory-starmap-todo-list": "| SG-0166 | failed | P1 | Failed | [[notes/failed]] | 2026-07-28T16:08:24-07:00 | Failed. |",
                    "notes/failed": "---\nstatus: failed\ntodo_id: SG-0166\nsuperseded_by: notes/superseding\nsuperseded_by_todo_id: SG-0167\nsupersession_evidence:\n  - runs/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df\n---\n# Failed\n",
                    "notes/superseding": "---\nstatus: completed\ntodo_id: SG-0167\nsuperseded_by: notes/failed\n---\n# Cyclic\n",
                },
                "cyclic supersession metadata",
            ),
            (
                "missing evidence",
                {
                    "notes/memory-starmap-todo-list": "| SG-0166 | failed | P1 | Failed | [[notes/failed]] | 2026-07-28T16:08:24-07:00 | Failed. |",
                    "notes/failed": "---\nstatus: failed\ntodo_id: SG-0166\nsuperseded_by: notes/superseding\nsuperseded_by_todo_id: SG-0167\n---\n# Failed\n",
                    "notes/superseding": "---\nstatus: completed\ntodo_id: SG-0167\n---\n# Completed\n",
                },
                "supersession evidence is absent",
            ),
        ]

        for _label, evidence, reason in cases:
            merged = {**base_evidence, **evidence}

            def fake_gbrain(command, slug, **_kwargs):
                self.assertEqual(command, "get")
                if slug not in merged:
                    raise RuntimeError(f"missing {slug}")
                return merged[slug]

            with (
                mock.patch("server.STORE", fake_store),
                mock.patch("server.run_gbrain", side_effect=fake_gbrain),
                mock.patch("server.resolver_feedback_health", return_value={"pending": 0}),
                mock.patch(
                    "server.latest_sre_numeric_evidence",
                    return_value={
                        "status": "pass",
                        "passed": True,
                        "freshness": "current",
                        "evidence": [{"slug": "reports/memory-stargraph-wish-sg0196-20260809t144900-0700-56c8c7d", "available": True, "status": "available"}],
                        "counts": {},
                        "summary": "Numeric SRE evidence present.",
                    },
                ),
                mock.patch("server.read_deployment_attestation", return_value=ready_deployment_attestation()),
            ):
                status, data = self.dispatch_get("/api/memory-value-digest?window=week")

            self.assertEqual(status, 200)
            outcomes = data["verified_memory_outcomes"]
            gate = {item["key"]: item for item in outcomes["gates"]}["unresolved_blockers"]
            self.assertEqual(gate["status"], "degraded")
            self.assertEqual(gate["counts"]["current_unresolved"], 1)
            self.assertEqual(gate["counts"]["invalid_supersession"], 1 if "supersession" in reason or "cyclic" in reason else 0)
            self.assertIn(reason, outcomes["historical_failures"][0]["reason"])

    def test_customer_readiness_is_read_only_and_exposes_one_safe_next_step(self):
        fake_store = FakeStore()
        weekly = {
            "verified_memory_outcomes": {
                "status": "pass",
                "freshness": {"status": "current"},
                "summary_counts": {"gates_passed": 7, "gates_total": 7},
            }
        }
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.setup_diagnostics", return_value={"status": "ready"}),
            mock.patch("server.first_run_activation_funnel", return_value={"mode": "live-ready"}),
            mock.patch("server.attachment_storage_status", return_value={"available": True}),
            mock.patch("server.public_yoda_model_config", return_value={"backend": "gbrain_think", "model": "openai:gpt-5.2"}),
            mock.patch("server.gbrain_reranker_readiness", return_value=ready_reranker_readiness()),
            mock.patch("server.memory_value_digest", return_value=weekly),
            mock.patch("server.latest_sre_numeric_evidence", return_value={"status": "pass", "freshness": "current", "evidence_slugs": ["reports/memory-stargraph-wish-sg0196-20260809t144900-0700-56c8c7d"]}),
            mock.patch("server.resolver_feedback_health", return_value={"pending": 0, "proposal_counts": {"pending": 0}}),
            mock.patch(
                "server.configured_target_readiness",
                return_value=("ready", {"configured_target_count": 1}, "Configured target evidence is available."),
            ),
        ):
            status, data = self.dispatch_get("/api/customer-readiness")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["read_only"])
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["summary_counts"]["checks_total"], 9)
        self.assertEqual(data["summary_counts"]["ready"], 9)
        self.assertIsInstance(data["safe_next_step"], dict)
        self.assertTrue(data["safe_next_step"]["safe"])
        self.assertFalse(data["safe_next_step"]["mutation"])
        self.assertFalse(data["safe_next_step"]["auto_repair"])
        self.assertEqual(data["prohibited_actions"], {
            "auto_repair": False,
            "resolver_auto_approval": False,
            "production_mutation": False,
        })
        self.assertEqual({check["id"] for check in data["checks"]}, {
            "service_health",
            "activation",
            "model_configuration",
            "gbrain_reranker",
            "durable_storage",
            "weekly_verified_outcomes",
            "resolver_pending",
            "sre_numeric_evidence",
            "configured_targets",
        })
        serialized = json.dumps(data).lower()
        self.assertIn("notes/memory-starmap-todo-list", serialized)
        self.assertNotIn("/users/", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("sk-", serialized)
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("raw prompt", serialized)

    def test_customer_readiness_degrades_for_reranker_sunset_without_auto_mutation(self):
        reranker = ready_reranker_readiness()
        reranker.update({
            "status": "degraded",
            "state": "deprecated_zeroentropy",
            "sunset_detected": True,
            "summary": "GBrain search still depends on the ZeroEntropy reranker, which stops working on 2026-09-04.",
        })
        weekly = {
            "verified_memory_outcomes": {
                "status": "pass",
                "freshness": {"status": "current"},
                "sre_numeric_evidence": {"status": "pass", "freshness": "current"},
            }
        }
        with (
            mock.patch("server.STORE", FakeStore()),
            mock.patch("server.first_run_activation_funnel", return_value={"mode": "live-ready"}),
            mock.patch("server.attachment_storage_status", return_value={"available": True}),
            mock.patch("server.public_yoda_model_config", return_value={"backend": "gbrain_think"}),
            mock.patch("server.gbrain_reranker_readiness", return_value=reranker),
            mock.patch("server.memory_value_digest", return_value=weekly),
            mock.patch("server.resolver_feedback_health", return_value={"pending": 0}),
            mock.patch(
                "server.configured_target_readiness",
                return_value=("ready", {"evidence_slugs": []}, "Configured target evidence is available."),
            ),
        ):
            status, data = self.dispatch_get("/api/customer-readiness")

        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "degraded")
        check = {item["id"]: item for item in data["checks"]}["gbrain_reranker"]
        self.assertEqual(check["status"], "degraded")
        self.assertEqual(data["safe_next_step"]["check_id"], "gbrain_reranker")
        self.assertTrue(data["gbrain_reranker"]["operator_action"]["approval_required"])
        self.assertFalse(data["gbrain_reranker"]["operator_action"]["automatic_mutation"])
        self.assertNotIn("/users/", json.dumps(data).lower())

    def test_customer_readiness_reuses_weekly_resolver_and_deployment_evidence(self):
        weekly = {
            "resolver_health": {"pending": 0, "proposal_counts": {"pending": 0}},
            "verified_memory_outcomes": {
                "status": "pass",
                "freshness": {"status": "current"},
                "sre_numeric_evidence": {
                    "status": "pass",
                    "freshness": "current",
                    "evidence_slugs": ["reports/sre"],
                },
                "deployment_attestation": {
                    "status": "ready",
                    "freshness": "current",
                    "summary": "Configured target evidence is current.",
                    "evidence_slugs": ["reports/deployment"],
                    "local": {"status": "current"},
                    "configured_remote": {
                        "status": "ready",
                        "configured_target_count": 1,
                        "verified_target_count": 1,
                    },
                },
            },
        }
        with (
            mock.patch("server.STORE", FakeStore()),
            mock.patch("server.first_run_activation_funnel", return_value={"mode": "live-ready"}),
            mock.patch("server.attachment_storage_status", return_value={"available": True}),
            mock.patch("server.public_yoda_model_config", return_value={"backend": "gbrain_think"}),
            mock.patch("server.gbrain_reranker_readiness", return_value=ready_reranker_readiness()),
            mock.patch("server.memory_value_digest", return_value=weekly),
            mock.patch("server.resolver_feedback_health", side_effect=AssertionError("duplicate resolver read")),
            mock.patch("server.configured_target_readiness", side_effect=AssertionError("duplicate deployment read")),
        ):
            data = server.customer_readiness()

        checks = {check["id"]: check for check in data["checks"]}
        self.assertEqual(checks["resolver_pending"]["status"], "ready")
        self.assertEqual(checks["configured_targets"]["status"], "ready")
        self.assertEqual(data["target_evidence"]["configured_remote"]["verified_target_count"], 1)

    def test_settings_evidence_builds_one_digest_for_both_cards(self):
        store = server.GraphStore()
        digest = {"ok": True, "verified_memory_outcomes": {"status": "pass"}}
        readiness = {"ok": True, "status": "ready"}
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.memory_value_digest", return_value=digest) as digest_read,
            mock.patch("server.customer_readiness", return_value=readiness) as readiness_read,
        ):
            status, data = self.dispatch_get("/api/settings-evidence")
            cached_status, cached = self.dispatch_get("/api/settings-evidence")
            refreshed_status, refreshed = self.dispatch_get("/api/settings-evidence?refresh=1")

        self.assertEqual(status, 200)
        self.assertEqual(cached_status, 200)
        self.assertEqual(refreshed_status, 200)
        self.assertTrue(data["read_only"])
        self.assertEqual(data["digest"], digest)
        self.assertEqual(data["readiness"], readiness)
        self.assertEqual(cached, data)
        self.assertEqual(refreshed, data)
        self.assertEqual(digest_read.call_count, 2)
        self.assertEqual(readiness_read.call_count, 2)
        digest_read.assert_has_calls([mock.call("week"), mock.call("week")])
        readiness_read.assert_has_calls([mock.call(digest), mock.call(digest)])

    def test_settings_detail_endpoints_reuse_recent_combined_snapshot(self):
        store = server.GraphStore()
        digest = {"ok": True, "window": "week", "marker": "cached-digest"}
        readiness = {"ok": True, "status": "ready", "marker": "cached-readiness"}
        store.settings_evidence_cache.put("week", {
            "ok": True,
            "digest": digest,
            "readiness": readiness,
        })

        with (
            mock.patch("server.STORE", store),
            mock.patch("server.memory_value_digest", side_effect=AssertionError("duplicate digest read")),
            mock.patch("server.customer_readiness", side_effect=AssertionError("duplicate readiness read")),
        ):
            digest_status, digest_data = self.dispatch_get("/api/memory-value-digest?window=week")
            readiness_status, readiness_data = self.dispatch_get("/api/customer-readiness")

        self.assertEqual(digest_status, 200)
        self.assertEqual(readiness_status, 200)
        self.assertEqual(digest_data, digest)
        self.assertEqual(readiness_data, readiness)

    def test_settings_evidence_coalesces_concurrent_cold_reads(self):
        store = server.GraphStore()
        digest_started = threading.Event()
        release_digest = threading.Event()
        results = []

        def load_digest(_window):
            digest_started.set()
            release_digest.wait(timeout=1)
            return {"ok": True, "verified_memory_outcomes": {"status": "pass"}}

        def read_settings():
            results.append(server.settings_evidence())

        with (
            mock.patch("server.STORE", store),
            mock.patch("server.memory_value_digest", side_effect=load_digest) as digest_read,
            mock.patch("server.customer_readiness", return_value={"ok": True}) as readiness_read,
        ):
            first = threading.Thread(target=read_settings)
            second = threading.Thread(target=read_settings)
            first.start()
            self.assertTrue(digest_started.wait(timeout=1))
            second.start()
            time.sleep(0.02)
            release_digest.set()
            first.join(timeout=1)
            second.join(timeout=1)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(digest_read.call_count, 1)
        self.assertEqual(readiness_read.call_count, 1)

    def test_customer_readiness_reports_degraded_missing_partial_and_no_activity(self):
        fake_store = FakeStore()
        weekly = {
            "verified_memory_outcomes": {
                "status": "partial",
                "freshness": {"status": "partial"},
                "summary_counts": {"gates_passed": 4, "gates_total": 7},
            }
        }
        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.setup_diagnostics", return_value={"status": "ready"}),
            mock.patch("server.first_run_activation_funnel", return_value={"mode": "sample-first"}),
            mock.patch("server.attachment_storage_status", return_value={"available": False}),
            mock.patch("server.public_yoda_model_config", side_effect=RuntimeError("redacted failure")),
            mock.patch("server.gbrain_reranker_readiness", return_value=ready_reranker_readiness()),
            mock.patch("server.memory_value_digest", return_value=weekly),
            mock.patch("server.latest_sre_numeric_evidence", return_value={"status": "partial", "freshness": "partial", "evidence_slugs": []}),
            mock.patch("server.resolver_feedback_health", return_value={"proposal_counts": {"pending": 2}}),
            mock.patch(
                "server.configured_target_readiness",
                return_value=("no_activity", {"configured_target_count": 0}, "No target evidence is available."),
            ),
        ):
            status, data = self.dispatch_get("/api/customer-readiness")

        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(data["summary_counts"]["blocked"], 1)
        self.assertEqual(data["summary_counts"]["missing"], 1)
        self.assertEqual(data["summary_counts"]["partial"], 2)
        self.assertEqual(data["summary_counts"]["no_activity"], 1)
        checks = {check["id"]: check for check in data["checks"]}
        self.assertEqual(checks["durable_storage"]["status"], "blocked")
        self.assertEqual(checks["model_configuration"]["status"], "missing")
        self.assertEqual(checks["weekly_verified_outcomes"]["status"], "partial")
        self.assertEqual(checks["sre_numeric_evidence"]["status"], "partial")
        self.assertEqual(checks["configured_targets"]["status"], "no_activity")
        self.assertEqual(data["safe_next_step"]["check_id"], "model_configuration")
        serialized = json.dumps(data).lower()
        self.assertNotIn("redacted failure", serialized)
        self.assertNotIn("/users/", serialized)

    def test_deployment_attestation_reports_current_stale_missing_and_source_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deployment_attestations.json"
            current_payload = {
                "schema_version": 1,
                "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "ui_version": server.UI_VERSION,
                "source_commit": "abc123",
                "evidence_slugs": [
                    "runs/memory-stargraph-wish-sg0199-test",
                    "https://private.example.invalid/should-not-leak",
                    "/Users/toddy/secret",
                ],
                "local": {"verified": True, "observed_at": "2026-08-10T10:00:00Z"},
                "configured_remote": {"configured_target_count": 2, "verified_target_count": 2},
            }
            with (
                mock.patch("server.DEPLOYMENT_ATTESTATIONS_PATH", path),
                mock.patch("server.current_source_commit", return_value="abc123"),
            ):
                path.write_text(json.dumps(current_payload), encoding="utf-8")
                current = server.read_deployment_attestation()
                self.assertEqual(current["status"], "ready")
                self.assertEqual(current["counts"]["configured_target_count"], 2)
                self.assertEqual(current["counts"]["verified_target_count"], 2)
                self.assertEqual(current["local"]["status"], "current")
                self.assertEqual(current["evidence_slugs"], ["runs/memory-stargraph-wish-sg0199-test"])

                stale_payload = dict(current_payload)
                stale_payload["generated_at"] = "2026-01-01T00:00:00Z"
                path.write_text(json.dumps(stale_payload), encoding="utf-8")
                stale = server.read_deployment_attestation()
                self.assertEqual(stale["status"], "stale")
                self.assertEqual(stale["counts"]["stale_target_count"], 2)

                mismatch_payload = dict(current_payload)
                mismatch_payload["source_commit"] = "def456"
                path.write_text(json.dumps(mismatch_payload), encoding="utf-8")
                mismatch = server.read_deployment_attestation()
                self.assertEqual(mismatch["status"], "source_mismatch")
                self.assertEqual(mismatch["counts"]["source_mismatch_count"], 2)

                partial_payload = dict(current_payload)
                partial_payload["configured_remote"] = {"configured_target_count": 2, "verified_target_count": 1}
                path.write_text(json.dumps(partial_payload), encoding="utf-8")
                partial = server.read_deployment_attestation()
                self.assertEqual(partial["status"], "partial")
                self.assertEqual(partial["counts"]["missing_target_count"], 1)
                serialized = json.dumps(partial).lower()
                self.assertNotIn("private.example", serialized)
                self.assertNotIn("/users/", serialized)

                path.write_text("{not-json", encoding="utf-8")
                malformed = server.read_deployment_attestation()
                self.assertEqual(malformed["status"], "missing")
                self.assertEqual(malformed["counts"]["missing_target_count"], 1)

                path.unlink()
                missing = server.read_deployment_attestation()
                self.assertEqual(missing["status"], "no_activity")
                self.assertEqual(missing["configured_remote"]["configured_target_count"], 0)

    def test_memory_value_digest_redacts_resolver_runtime_paths(self):
        fake_store = FakeStore()

        def fake_gbrain(command, slug, **_kwargs):
            self.assertEqual(command, "get")
            if slug == "notes/memory-starmap-todo-list":
                return "| SG-0199 | implementing | P1 | Current work | [[notes/current]] | 2026-08-10 | Implementing. |"
            if slug == "learnings/memory-stargraph-20260719-operational-state-reconciliation-and-source-sync-preflight":
                return "# Learning\n\nOperational source-sync preflight evidence."
            raise RuntimeError(f"missing {slug}")

        with (
            mock.patch("server.STORE", fake_store),
            mock.patch("server.run_gbrain", side_effect=fake_gbrain),
            mock.patch(
                "server.resolver_feedback_health",
                side_effect=TimeoutError("Command '['/Users/toddy/.bun/bin/gbrain', 'call', 'resolver_feedback_health', '{}']' timed out after 20 seconds"),
            ),
        ):
            status, data = self.dispatch_get("/api/memory-value-digest?window=day")

        self.assertEqual(status, 200)
        self.assertIn("error", data["resolver_health"])
        serialized = json.dumps(data).lower()
        self.assertIn("[redacted-path]", serialized)
        self.assertNotIn("/users/", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("authorization", serialized)

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

    def test_take_proposal_tool_payload_uses_numeric_id_when_available(self):
        payload = server.take_review_action_payload("42", "accept", {"idempotency_key": "abc-123"})

        self.assertEqual(payload["id"], 42)
        self.assertIsInstance(payload["id"], int)
        self.assertEqual(payload["proposal_id"], "42")

    def test_take_proposal_tool_payload_preserves_non_numeric_audit_id(self):
        payload = server.take_review_action_payload("tp-1", "accept", {"idempotency_key": "abc-123"})

        self.assertEqual(payload["id"], "tp-1")
        self.assertEqual(payload["proposal_id"], "tp-1")

    def test_bulk_take_review_payload_includes_remote_actions_with_numeric_ids(self):
        payload = server.take_review_bulk_payload({
            "action": "accept",
            "ids": ["42", "43"],
            "idempotency_key": "bulk-123",
        })

        self.assertEqual(payload["ids"], ["42", "43"])
        self.assertEqual(payload["actions"], [{"id": 42, "action": "accept"}, {"id": 43, "action": "accept"}])

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
        with (
            mock.patch("server.configured_remote_mcp_path", return_value=None),
            mock.patch("server.run_gbrain", side_effect=RuntimeError(noisy)),
        ):
            with self.assertRaisesRegex(RuntimeError, "GBrain backend does not expose take_proposals_list"):
                server.gbrain_call_tool("take_proposals_list", {"limit": 2})

    def test_gbrain_tool_proxy_preserves_array_responses(self):
        output = '[{"id": 1, "claim": "First"}, {"id": 2, "claim": "Second"}]'
        with (
            mock.patch("server.configured_remote_mcp_path", return_value=None),
            mock.patch("server.run_gbrain", return_value=output),
        ):
            result = server.gbrain_call_tool("takes_list", {"limit": 2})

        self.assertIsInstance(result, list)
        self.assertEqual([row["id"] for row in result], [1, 2])

    def test_gbrain_tool_proxy_rejects_manifest_absence_without_failed_call(self):
        manifest = json.dumps(
            [
                {"name": "get_page"},
                {"name": "search"},
                {"name": "takes_list"},
            ]
        )
        server.LOCAL_GBRAIN_TOOL_MANIFEST_CACHE.clear()
        with (
            mock.patch("server.configured_remote_mcp_path", return_value=None),
            mock.patch("server.local_gbrain_tool_manifest_key", return_value=("test-manifest",)),
            mock.patch("server.run_gbrain", return_value=manifest) as fake_gbrain,
        ):
            with self.assertRaisesRegex(RuntimeError, "does not expose take_proposals_list"):
                server.gbrain_call_tool("take_proposals_list", {"limit": 2})

        fake_gbrain.assert_called_once_with(
            "--tools-json",
            timeout=server.GBRAIN_TOOL_MANIFEST_TIMEOUT_SECONDS,
        )

    def test_gbrain_tool_proxy_reuses_manifest_for_optional_tools(self):
        manifest = json.dumps([{"name": "get_page"}, {"name": "search"}])
        server.LOCAL_GBRAIN_TOOL_MANIFEST_CACHE.clear()
        with (
            mock.patch("server.configured_remote_mcp_path", return_value=None),
            mock.patch("server.local_gbrain_tool_manifest_key", return_value=("test-manifest",)),
            mock.patch("server.run_gbrain", return_value=manifest) as fake_gbrain,
        ):
            for tool_name in (
                "take_proposals_list",
                "resolver_feedback_health",
                "resolver_proposals_list",
                "autopilot_findings_list",
            ):
                with self.assertRaisesRegex(RuntimeError, f"does not expose {tool_name}"):
                    server.gbrain_call_tool(tool_name, {})

        fake_gbrain.assert_called_once_with(
            "--tools-json",
            timeout=server.GBRAIN_TOOL_MANIFEST_TIMEOUT_SECONDS,
        )

    def test_gbrain_tool_proxy_falls_back_when_manifest_is_invalid(self):
        server.LOCAL_GBRAIN_TOOL_MANIFEST_CACHE.clear()
        with (
            mock.patch("server.configured_remote_mcp_path", return_value=None),
            mock.patch("server.local_gbrain_tool_manifest_key", return_value=("test-manifest",)),
            mock.patch(
                "server.run_gbrain",
                side_effect=["not-json", '{"proposals": []}'],
            ) as fake_gbrain,
        ):
            result = server.gbrain_call_tool("take_proposals_list", {"limit": 2})

        self.assertEqual(result, {"proposals": []})
        self.assertEqual(fake_gbrain.call_count, 2)

    def test_take_proposals_reuses_successful_result_cache(self):
        store = server.GraphStore()
        result = {"proposals": [{"id": 1}], "counts": {"pending": 1}}
        with mock.patch("server.gbrain_call_tool", return_value=result) as fake_tool:
            first = store.list_take_proposals({"status": "pending", "limit": 20})
            second = store.list_take_proposals({"status": "pending", "limit": 20})

        self.assertEqual(second, first)
        self.assertEqual(fake_tool.call_count, 1)

    def test_take_proposals_reuses_explicit_missing_tool_capability(self):
        store = server.GraphStore()
        missing_tool = RuntimeError(
            "GBrain backend does not expose take_proposals_list: Unknown tool: take_proposals_list"
        )
        with mock.patch("server.gbrain_call_tool", side_effect=missing_tool) as fake_tool:
            with self.assertRaisesRegex(RuntimeError, "take_proposals_list"):
                store.list_take_proposals({"status": "pending", "limit": 20})
            with self.assertRaisesRegex(RuntimeError, "take_proposals_list"):
                store.list_take_proposals({"status": "accepted", "limit": 20})

        self.assertEqual(fake_tool.call_count, 1)

    def test_take_proposals_does_not_cache_transient_failures(self):
        store = server.GraphStore()
        transient = RuntimeError("GBrain remote request timed out")
        with mock.patch("server.gbrain_call_tool", side_effect=transient) as fake_tool:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                store.list_take_proposals({"status": "pending", "limit": 20})
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                store.list_take_proposals({"status": "pending", "limit": 20})

        self.assertEqual(fake_tool.call_count, 2)

    def test_takes_reuses_successful_result_cache(self):
        store = server.GraphStore()
        result = {
            "takes": [
                {
                    "id": 1,
                    "claim": "Existing take",
                    "holder": "people/tony-guan",
                    "active": True,
                }
            ]
        }
        with mock.patch("server.gbrain_call_tool", return_value=result) as fake_tool:
            first = store.list_takes({"holder": "people/tony-guan", "limit": 500})
            second = store.list_takes({"holder": "people/tony-guan", "limit": 500})

        self.assertEqual(second, first)
        self.assertEqual(fake_tool.call_count, 1)

    def test_takes_reuses_complete_snapshot_across_holder_filters(self):
        store = server.GraphStore()
        result = {
            "takes": [
                {"id": 1, "holder": "people/tony-guan", "active": True},
                {"id": 2, "holder": "world", "active": True},
                {"id": 3, "holder": "people/tony-guan", "active": False},
            ]
        }
        with mock.patch("server.gbrain_call_tool", return_value=result) as fake_tool:
            tony = store.list_takes({"holder": "people/tony-guan", "active": True, "limit": 500})
            world = store.list_takes({"holder": "world", "limit": 500})

        self.assertEqual([row["id"] for row in tony["takes"]], [1])
        self.assertEqual([row["id"] for row in world["takes"]], [2])
        fake_tool.assert_called_once_with(
            "takes_list",
            {"limit": server.TAKES_VIEW_FETCH_LIMIT, "offset": 0},
            timeout=30,
        )

    def test_takes_falls_back_when_complete_snapshot_reaches_limit(self):
        store = server.GraphStore()
        full = [
            {"id": index, "holder": "world", "active": True}
            for index in range(server.TAKES_VIEW_FETCH_LIMIT)
        ]
        filtered = [{"id": "target", "holder": "people/tony-guan", "active": True}]
        with mock.patch(
            "server.gbrain_call_tool",
            side_effect=[full, filtered],
        ) as fake_tool:
            result = store.list_takes({"holder": "people/tony-guan", "limit": 500})

        self.assertEqual(result["takes"], filtered)
        self.assertEqual(fake_tool.call_count, 2)
        self.assertEqual(fake_tool.call_args_list[-1].args[:2], (
            "takes_list",
            {"holder": "people/tony-guan", "limit": 500},
        ))

    def test_takes_keeps_resolved_filter_on_direct_backend_path(self):
        store = server.GraphStore()
        payload = {"holder": "world", "resolved": False, "limit": 500}
        with mock.patch("server.gbrain_call_tool", return_value={"takes": []}) as fake_tool:
            store.list_takes(payload)

        fake_tool.assert_called_once_with("takes_list", payload, timeout=30)

    def test_take_review_writes_invalidate_cached_lists(self):
        store = server.GraphStore()
        store.take_review_cache.put("proposals:test", {"proposals": [{"id": 1}]})
        store.take_review_cache.put("takes:test", {"takes": [{"id": 2}]})
        with mock.patch("server.gbrain_call_tool", return_value={"status": "accepted"}):
            store.review_take_proposal("1", "accept", {})

        self.assertEqual(len(store.take_review_cache), 0)

        store.take_review_cache.put("proposals:test", {"proposals": [{"id": 1}]})
        with mock.patch("server.gbrain_call_tool", return_value={"results": []}):
            store.bulk_review_take_proposals({"action": "reject", "ids": ["1"]})

        self.assertEqual(len(store.take_review_cache), 0)

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
        self.assertEqual(logs["entries"][0]["environment"], "test")
        self.assertTrue(logs["entries"][0]["synthetic"])
        self.assertTrue(logs["entries"][0]["test_run"])
        self.assertEqual(logs["entries"][0]["pair_id"], "api-probe-1")
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
                {
                    "events": [
                        {
                            "event_id": "stargraph-1",
                            "producer": "stargraph",
                            "metadata": json.dumps(
                                {
                                    "environment": "test",
                                    "synthetic": True,
                                    "test_run": True,
                                    "pair_id": "resolver-probe-1",
                                }
                            ),
                        }
                    ],
                    "limit": 2,
                },
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
        self.assertEqual(data["events"][0]["environment"], "test")
        self.assertTrue(data["events"][0]["synthetic"])
        self.assertTrue(data["events"][0]["test_run"])
        self.assertEqual(data["events"][0]["pair_id"], "resolver-probe-1")
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
        with (
            mock.patch("server.configured_remote_mcp_path", return_value=None),
            mock.patch("server.run_gbrain", return_value=output),
        ):
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

    def test_resolver_health_uses_local_read_only_fallback_when_tool_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "resolver_proposals.json").write_text("[]", encoding="utf-8")
            (data_dir / "resolver_dispatch_events.json").write_text(
                json.dumps([
                    {"created_at": "2026-08-16T09:00:00Z", "result_status": "success"},
                    {"created_at": "2026-08-16T09:05:00Z", "result_status": "timeout"},
                ]),
                encoding="utf-8",
            )
            with (
                mock.patch("server.RESOLVER_PROPOSALS_PATH", data_dir / "resolver_proposals.json"),
                mock.patch("server.RESOLVER_EVENTS_PATH", data_dir / "resolver_dispatch_events.json"),
                mock.patch("server.gbrain_call_tool", side_effect=RuntimeError("Unknown tool: resolver_feedback_health")),
            ):
                status, data = self.dispatch_get("/api/resolver/health")

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["fallback_used"])
        self.assertTrue(data["read_only"])
        self.assertEqual(data["source"], "local_resolver_ledger_fallback")
        self.assertEqual(data["pending"], 0)
        self.assertEqual(data["proposal_counts"]["pending"], 0)
        self.assertEqual(data["event_counts"]["success"], 1)
        self.assertEqual(data["event_counts"]["timeout"], 1)
        self.assertFalse(data["auto_approval"])
        serialized = json.dumps(data)
        self.assertNotIn("resolver_feedback_health", serialized)
        self.assertNotIn("Unknown tool", serialized)

    def test_resolver_health_reuses_missing_tool_capability_and_fallback(self):
        store = server.GraphStore()
        missing_tool = RuntimeError(
            "GBrain backend does not expose resolver_feedback_health: Unknown tool: resolver_feedback_health"
        )
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.gbrain_call_tool", side_effect=missing_tool) as fake_tool,
            mock.patch("server.resolver_feedback_health_from_local_ledger", return_value={"pending": 0}) as fallback,
        ):
            first = server.resolver_feedback_health()
            second = server.resolver_feedback_health()

        self.assertEqual(second, first)
        self.assertEqual(fake_tool.call_count, 1)
        self.assertEqual(fallback.call_count, 1)

    def test_resolver_health_keeps_capability_when_result_cache_clears(self):
        store = server.GraphStore()
        missing_tool = RuntimeError("Unknown tool: resolver_feedback_health")
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.gbrain_call_tool", side_effect=missing_tool) as fake_tool,
            mock.patch("server.resolver_feedback_health_from_local_ledger", return_value={"pending": 0}) as fallback,
        ):
            server.resolver_feedback_health()
            store.resolver_read_cache.clear()
            server.resolver_feedback_health()

        self.assertEqual(fake_tool.call_count, 1)
        self.assertEqual(fallback.call_count, 2)

    def test_resolver_health_does_not_cache_transient_failures(self):
        store = server.GraphStore()
        transient = RuntimeError("GBrain remote request timed out")
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.gbrain_call_tool", side_effect=transient) as fake_tool,
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                server.resolver_feedback_health()
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                server.resolver_feedback_health()

        self.assertEqual(fake_tool.call_count, 2)

    def test_resolver_proposals_reuses_successful_result_cache(self):
        store = server.GraphStore()
        result = {"proposals": [{"id": "rp-1", "impact": "{}"}]}
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.gbrain_call_tool", return_value=result) as fake_tool,
        ):
            first = server.resolver_list_proposals("pending", 100)
            second = server.resolver_list_proposals("pending", 100)

        self.assertEqual(second, first)
        self.assertEqual(fake_tool.call_count, 1)

    def test_resolver_proposals_reuses_explicit_missing_tool_capability(self):
        store = server.GraphStore()
        missing_tool = RuntimeError(
            "GBrain backend does not expose resolver_proposals_list: Unknown tool: resolver_proposals_list"
        )
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.gbrain_call_tool", side_effect=missing_tool) as fake_tool,
        ):
            with self.assertRaisesRegex(RuntimeError, "resolver_proposals_list"):
                server.resolver_list_proposals("pending", 100)
            with self.assertRaisesRegex(RuntimeError, "resolver_proposals_list"):
                server.resolver_list_proposals("accepted", 100)

        self.assertEqual(fake_tool.call_count, 1)

    def test_resolver_proposals_does_not_cache_transient_failures(self):
        store = server.GraphStore()
        transient = RuntimeError("GBrain remote request timed out")
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.gbrain_call_tool", side_effect=transient) as fake_tool,
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                server.resolver_list_proposals("pending", 100)
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                server.resolver_list_proposals("pending", 100)

        self.assertEqual(fake_tool.call_count, 2)

    def test_resolver_write_invalidates_read_and_settings_caches(self):
        store = server.GraphStore()
        store.resolver_read_cache.put("health", {"pending": 0})
        store.settings_evidence_cache.put("week", {"digest": {}})
        with (
            mock.patch("server.STORE", store),
            mock.patch("server.gbrain_call_tool", return_value={"ok": True}),
        ):
            server.resolver_submit_event({"event_id": "event-1"})

        self.assertEqual(len(store.resolver_read_cache), 0)
        self.assertEqual(len(store.settings_evidence_cache), 0)

    def test_resolver_health_fallback_reports_pending_without_mutating(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "resolver_proposals.json").write_text(
                json.dumps([
                    {"id": "rp-1", "status": "pending"},
                    {"id": "rp-2", "status": "accepted"},
                ]),
                encoding="utf-8",
            )
            (data_dir / "resolver_dispatch_events.json").write_text("[]", encoding="utf-8")
            with (
                mock.patch("server.RESOLVER_PROPOSALS_PATH", data_dir / "resolver_proposals.json"),
                mock.patch("server.RESOLVER_EVENTS_PATH", data_dir / "resolver_dispatch_events.json"),
                mock.patch("server.gbrain_call_tool", side_effect=RuntimeError("GBrain backend does not expose resolver_feedback_health: Unknown tool: resolver_feedback_health")),
            ):
                status, data = self.dispatch_get("/api/resolver/health")

        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "degraded")
        self.assertEqual(data["pending"], 1)
        self.assertEqual(data["proposal_counts"]["accepted"], 1)
        self.assertFalse(data["auto_approval"])

    def test_customer_readiness_uses_resolver_fallback_as_ready_when_none_pending(self):
        fake_store = FakeStore()
        weekly = {
            "verified_memory_outcomes": {
                "status": "pass",
                "freshness": {"status": "current"},
                "summary_counts": {"gates_passed": 9, "gates_total": 9},
                "sre_numeric_evidence": {"status": "pass", "freshness": "current", "evidence_slugs": ["reports/sre"]},
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "resolver_proposals.json").write_text("[]", encoding="utf-8")
            (data_dir / "resolver_dispatch_events.json").write_text("[]", encoding="utf-8")
            with (
                mock.patch("server.STORE", fake_store),
                mock.patch("server.RESOLVER_PROPOSALS_PATH", data_dir / "resolver_proposals.json"),
                mock.patch("server.RESOLVER_EVENTS_PATH", data_dir / "resolver_dispatch_events.json"),
                mock.patch("server.gbrain_call_tool", side_effect=RuntimeError("Unknown tool: resolver_feedback_health")),
                mock.patch("server.first_run_activation_funnel", return_value={"mode": "live-ready"}),
                mock.patch("server.attachment_storage_status", return_value={"available": True}),
                mock.patch("server.public_yoda_model_config", return_value={"backend": "gbrain_think", "model": "openai:gpt-5.2"}),
                mock.patch("server.gbrain_reranker_readiness", return_value=ready_reranker_readiness()),
                mock.patch("server.memory_value_digest", return_value=weekly),
                mock.patch(
                    "server.configured_target_readiness",
                    return_value=("ready", {"configured_target_count": 1}, "Configured target evidence is available."),
                ),
            ):
                status, data = self.dispatch_get("/api/customer-readiness")

        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["summary_counts"]["ready"], 9)
        resolver_check = {check["id"]: check for check in data["checks"]}["resolver_pending"]
        self.assertEqual(resolver_check["status"], "ready")
        self.assertEqual(resolver_check["freshness"], "current")
        serialized = json.dumps(data)
        self.assertNotIn("resolver_feedback_health", serialized)
        self.assertNotIn("Unknown tool", serialized)

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
