import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from unittest import mock

from server import (
    DEFAULT_CONFIG,
    EvidenceListCache,
    GraphStore,
    PersistentGBrainSearch,
    TimedValueCache,
    append_attachment_reference,
    cached_primary_search_results,
    collapse_part_identity,
    collect_seed_graph,
    ensure_media_references_available,
    extract_openclaw_answer,
    effective_yoda_retrieval_question,
    evidence_record_search_results,
    exact_loaded_label_search_results,
    expand_raw_graph,
    finalize_graph,
    friendly_label,
    make_label,
    parse_backlink_types,
    parse_backlinks,
    parse_frontmatter,
    extract_summary_from_markdown_body,
    parse_graph_query_link_types,
    parse_link_types,
    materialize_local_media_for_slug,
    parse_multipart_form,
    parse_media_references,
    parse_page_list,
    parse_neighbors,
    parse_search_results,
    remote_media_url_for_relative_path,
    relationship_matches_question,
    resolve_media_file_path,
    run_openclaw_agent,
    run_gbrain,
    search_raw_graph,
    serve_url_for_media_reference,
    gbrain_file_url_for_relative_path,
    materialize_gbrain_file_reference,
    copy_file_to_gbrain_store,
    gbrain_file_ledger_has_relative_path,
    parse_gbrain_durable_evidence,
    safe_upload_filename,
    merge_search_results,
    format_mcp_json,
    format_mcp_graph_query,
    format_mcp_page_list,
    format_mcp_search_results,
    parse_gbrain_graph_query_arguments,
    parse_gbrain_list_arguments,
    parse_gbrain_query_arguments,
    parse_gbrain_search_arguments,
)


class GraphParsingTests(unittest.TestCase):
    def openclaw_yoda_config(self):
        return {
            "backend": "openclaw",
            "model": "",
            "base_url": "",
            "api_key_env": "OPENAI_API_KEY",
            "agent": "",
            "timeout": 45,
            "graph_query_timeout": 30,
            "broad_graph_budget": 8,
            "node_path": "",
            "node_fallback_paths": [],
        }

    def test_parse_frontmatter_preserves_folded_and_literal_titles(self):
        folded, _ = parse_frontmatter("---\ntitle: >-\n  A long\n  folded title\n---\n# Body\n")
        literal, _ = parse_frontmatter("---\ntitle: |-\n  Line one\n  Line two\n---\n# Body\n")

        self.assertEqual(folded["title"], "A long folded title")
        self.assertEqual(literal["title"], "Line one\nLine two")

    def test_effective_yoda_retrieval_question_inherits_short_followup_intent(self):
        history = [
            {"role": "user", "content": "which of my X posts were reposted by Garry Tan?"},
            {"role": "assistant", "content": "The graph does not contain enough evidence."},
            {"role": "user", "content": "try again"},
        ]

        resolved, inherited = effective_yoda_retrieval_question("try again", history)

        self.assertTrue(inherited)
        self.assertIn("which of my X posts were reposted by Garry Tan?", resolved)
        self.assertIn("Follow-up: try again", resolved)

    def test_relationship_question_matching_ignores_structural_stopwords(self):
        question = "which of my X posts were reposted by Garry Tan?"

        self.assertTrue(relationship_matches_question("reposted_by", question))
        self.assertFalse(relationship_matches_question("authored_by", question))
        self.assertFalse(relationship_matches_question("ceo of", question))

    def test_default_media_discovery_roots_avoid_user_folders(self):
        roots = DEFAULT_CONFIG["media_discovery_roots"]

        self.assertIn("data/uploads", roots)
        self.assertFalse(any(root.startswith("~/") for root in roots))

    def test_parse_page_list_reads_gbrain_tabular_output(self):
        output = "people/tony-guan\tperson\t2026-06-27\tTony Guan\nproducts/jtuner\tproduct\t2026-06-28\tJTuner\n"
        rows = parse_page_list(output)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["slug"], "people/tony-guan")
        self.assertEqual(rows[0]["type"], "person")
        self.assertEqual(rows[1]["title"], "JTuner")

    def test_collect_seed_graph_keeps_index_when_root_expansion_times_out(self):
        def fake_run_gbrain(*args, **_kwargs):
            if args[:2] == ("list", "-n"):
                return "people/tony-guan\tperson\t2026-06-27\tTony Guan\n"
            raise TimeoutError("root graph timed out")

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = collect_seed_graph()

        slugs = {node["slug"] for node in graph["nodes"]}
        self.assertIn("index", slugs)
        self.assertIn("people/tony-guan", slugs)
        self.assertFalse(graph["source"]["coverage"]["root_index_loaded"])

    def test_parse_search_results_reads_scores_slugs_and_previews(self):
        output = "[0.7772] organizations/erfapac -- # Equal Rights For All PAC (ERFA PAC)\n[0.7384] products/jtuner/rfc/part-03 -- Binary preview\n"
        rows = parse_search_results(output)

        self.assertEqual(rows[0]["slug"], "organizations/erfapac")
        self.assertEqual(rows[0]["score"], 0.7772)
        self.assertEqual(rows[0]["label"], "Equal Rights For All PAC (ERFA PAC)")
        self.assertEqual(rows[1]["slug"], "products/jtuner/rfc/part-03")

    def test_parse_gbrain_search_arguments_maps_supported_cli_options(self):
        payload = parse_gbrain_search_arguments(
            (
                "search",
                "memory stargraph",
                "--limit",
                "5",
                "--offset",
                "2",
                "--mode",
                "balanced",
                "--types",
                "report,run",
                "--snippet-chars",
                "0",
            )
        )

        self.assertEqual(
            payload,
            {
                "query": "memory stargraph",
                "limit": 5,
                "offset": 2,
                "mode": "balanced",
                "types": ["report", "run"],
                "snippet_chars": 0,
            },
        )
        with self.assertRaisesRegex(ValueError, "unsupported persistent search option"):
            parse_gbrain_search_arguments(("search", "query", "--unknown", "value"))

    def test_format_mcp_search_results_matches_cli_preview_contract(self):
        long_unicode_preview = "a" * 99 + "\U0001f680" + "tail"
        output = format_mcp_search_results(
            [
                {
                    "slug": "products/memory-stargraph",
                    "score": 0.7772,
                    "chunk_text": "\n  # Memory Stargraph  \nBody",
                },
                {
                    "slug": "learnings/utf16-preview",
                    "score": 0.5,
                    "chunk_text": long_unicode_preview,
                },
            ]
        )

        self.assertEqual(
            output,
            "[0.7772] products/memory-stargraph -- # Memory Stargraph\n"
            f"[0.5000] learnings/utf16-preview -- {'a' * 99}\n",
        )
        parsed = parse_search_results(output)
        self.assertEqual(parsed[0]["label"], "Memory Stargraph")
        self.assertEqual(parsed[1]["preview"], "a" * 99)

    def test_parse_gbrain_query_arguments_maps_current_yoda_options(self):
        payload = parse_gbrain_query_arguments(
            (
                "query",
                "What should I inspect?",
                "--no-expand",
                "--adaptive-return",
                "true",
                "--limit",
                "10",
                "--relational",
                "true",
            )
        )

        self.assertEqual(
            payload,
            {
                "query": "What should I inspect?",
                "expand": False,
                "adaptive_return": True,
                "limit": 10,
                "relational": True,
            },
        )
        with self.assertRaisesRegex(ValueError, "invalid boolean option"):
            parse_gbrain_query_arguments(("query", "question", "--relational", "maybe"))
        with self.assertRaisesRegex(ValueError, "unsupported persistent query option"):
            parse_gbrain_query_arguments(("query", "question", "--unknown"))

    def test_format_mcp_json_matches_cli_json_contract(self):
        self.assertEqual(
            format_mcp_json([{"slug": "products/memory-stargraph", "context": "Memory"}]),
            '[\n  {\n    "slug": "products/memory-stargraph",\n    "context": "Memory"\n  }\n]\n',
        )

    def test_parse_and_format_persistent_list_matches_cli_contract(self):
        payload = parse_gbrain_list_arguments(
            ("list", "--type", "run", "-n", "40", "--sort", "updated_desc")
        )
        output = format_mcp_page_list(
            [
                {
                    "slug": "runs/example",
                    "type": "run",
                    "title": "Example Run",
                    "updated_at": "2026-08-23T12:34:56.000Z",
                }
            ]
        )

        self.assertEqual(
            payload,
            {"type": "run", "limit": 40, "sort": "updated_desc"},
        )
        self.assertEqual(
            output,
            "runs/example\trun\t2026-08-23\tExample Run\n",
        )
        self.assertEqual(parse_page_list(output)[0]["slug"], "runs/example")
        with self.assertRaisesRegex(ValueError, "unsupported persistent list option"):
            parse_gbrain_list_arguments(("list", "--unknown"))

    def test_parse_and_format_persistent_graph_query_matches_cli_tree(self):
        payload = parse_gbrain_graph_query_arguments(
            (
                "graph-query",
                "products/memory-stargraph",
                "--direction",
                "both",
                "--depth",
                "2",
                "--type",
                "documents",
            )
        )
        paths = [
            {
                "from_slug": "products/memory-stargraph",
                "to_slug": "docs/zeta",
                "link_type": "documents",
                "depth": 1,
            },
            {
                "from_slug": "products/memory-stargraph",
                "to_slug": "docs/alpha",
                "link_type": "documents",
                "depth": 1,
            },
            {
                "from_slug": "docs/alpha",
                "to_slug": "products/memory-stargraph",
                "link_type": "documented_by",
                "depth": 1,
            },
        ]

        self.assertEqual(
            payload,
            {
                "slug": "products/memory-stargraph",
                "depth": 2,
                "direction": "both",
                "link_type": "documents",
            },
        )
        self.assertEqual(
            format_mcp_graph_query(paths, payload),
            "[depth 0] products/memory-stargraph\n"
            "  --documents-> docs/alpha (depth 1)\n"
            "    --documented_by-> products/memory-stargraph (depth 1)\n"
            "  --documents-> docs/zeta (depth 1)\n",
        )
        self.assertEqual(
            format_mcp_graph_query([], payload),
            "No edges found from products/memory-stargraph (--type documents).\n",
        )
        with self.assertRaisesRegex(ValueError, "unsupported persistent graph-query option"):
            parse_gbrain_graph_query_arguments(
                ("graph-query", "products/memory-stargraph", "--include-foreign")
            )

    def test_run_gbrain_prefers_active_persistent_search(self):
        persistent = mock.Mock(active=True)
        persistent.read_cli_output.return_value = "[0.90] products/memory-stargraph -- # Memory Stargraph\n"
        with (
            mock.patch("server.PERSISTENT_GBRAIN_SEARCH", persistent),
            mock.patch("server.run_gbrain_subprocess") as fallback,
        ):
            output = run_gbrain("search", "memory stargraph", "--limit", "5", timeout=6)

        self.assertIn("products/memory-stargraph", output)
        persistent.read_cli_output.assert_called_once_with(
            ("search", "memory stargraph", "--limit", "5"),
            6,
        )
        fallback.assert_not_called()

    def test_run_gbrain_falls_back_when_persistent_search_fails(self):
        persistent = mock.Mock(active=True)
        persistent.read_cli_output.side_effect = RuntimeError("synthetic process exit")
        with (
            mock.patch("server.PERSISTENT_GBRAIN_SEARCH", persistent),
            mock.patch("server.run_gbrain_subprocess", return_value="fallback") as fallback,
        ):
            output = run_gbrain("search", "memory stargraph", timeout=6)

        self.assertEqual(output, "fallback")
        self.assertEqual(fallback.call_args.args, ("search", "memory stargraph"))
        self.assertGreater(fallback.call_args.kwargs["timeout"], 5.5)

    def test_run_gbrain_routes_supported_read_commands_to_persistent_session(self):
        persistent = mock.Mock(active=True)
        persistent.read_cli_output.side_effect = ["query", "page", "[]\n", "rows\n"]
        with (
            mock.patch("server.PERSISTENT_GBRAIN_SEARCH", persistent),
            mock.patch("server.run_gbrain_subprocess") as fallback,
        ):
            outputs = [
                run_gbrain("query", "question", timeout=6),
                run_gbrain("get", "products/memory-stargraph", timeout=6),
                run_gbrain("backlinks", "products/memory-stargraph", timeout=6),
                run_gbrain("list", "--type", "run", "-n", "40", timeout=6),
            ]

        self.assertEqual(outputs, ["query", "page", "[]\n", "rows\n"])
        self.assertEqual(persistent.read_cli_output.call_count, 4)
        fallback.assert_not_called()

    def test_persistent_read_session_formats_list_pages(self):
        session = PersistentGBrainSearch()
        with (
            mock.patch.object(session, "_start_locked"),
            mock.patch.object(
                session,
                "_call_tool_locked",
                return_value=[
                    {
                        "slug": "runs/example",
                        "type": "run",
                        "title": "Example Run",
                        "updated_at": "2026-08-23T12:34:56.000Z",
                    }
                ],
            ) as call_tool,
        ):
            output = session.read_cli_output(
                ("list", "--type", "run", "-n", "40"),
                5,
            )

        self.assertEqual(
            output,
            "runs/example\trun\t2026-08-23\tExample Run\n",
        )
        self.assertEqual(call_tool.call_args.args[0], "list_pages")
        self.assertEqual(
            call_tool.call_args.args[1],
            {"type": "run", "limit": 40},
        )

    def test_persistent_read_session_pages_explicit_large_list_limit(self):
        session = PersistentGBrainSearch()
        first_page = [
            {
                "slug": f"pages/item-{index:03d}",
                "type": "note",
                "title": f"Item {index}",
                "updated_at": "2026-08-23T12:34:56.000Z",
            }
            for index in range(100)
        ]
        second_page = [
            {
                "slug": f"pages/item-{index:03d}",
                "type": "note",
                "title": f"Item {index}",
                "updated_at": "2026-08-23T12:34:56.000Z",
            }
            for index in range(100, 140)
        ]
        with (
            mock.patch.object(session, "_start_locked"),
            mock.patch.object(
                session,
                "_call_tool_locked",
                side_effect=[first_page, second_page],
            ) as call_tool,
        ):
            output = session.read_cli_output(("list", "-n", "140"), 5)

        self.assertEqual(len(parse_page_list(output)), 140)
        self.assertEqual(call_tool.call_count, 2)
        self.assertEqual(
            call_tool.call_args_list[0].args,
            ("list_pages", {"limit": 100, "offset": 0}, mock.ANY),
        )
        self.assertEqual(
            call_tool.call_args_list[1].args,
            ("list_pages", {"limit": 40, "offset": 100}, mock.ANY),
        )

    def test_persistent_read_session_formats_query_get_and_backlinks(self):
        session = PersistentGBrainSearch()
        with (
            mock.patch.object(session, "_start_locked"),
            mock.patch.object(
                session,
                "_call_tool_locked",
                side_effect=[
                    [{"slug": "products/memory-stargraph", "score": 0.75, "chunk_text": "# Memory Stargraph"}],
                    {"content": "---\ntitle: Memory Stargraph\n---\n"},
                    [{"from_slug": "goals/example", "to_slug": "products/memory-stargraph"}],
                ],
            ) as call_tool,
        ):
            query_output = session.read_cli_output(
                ("query", "What matters?", "--no-expand", "--limit", "10"),
                5,
            )
            get_output = session.read_cli_output(("get", "products/memory-stargraph"), 5)
            backlinks_output = session.read_cli_output(
                ("backlinks", "products/memory-stargraph"),
                5,
            )

        self.assertEqual(
            query_output,
            "[0.7500] products/memory-stargraph -- # Memory Stargraph\n",
        )
        self.assertEqual(get_output, "---\ntitle: Memory Stargraph\n---\n")
        self.assertEqual(
            backlinks_output,
            '[\n  {\n    "from_slug": "goals/example",\n    "to_slug": "products/memory-stargraph"\n  }\n]\n',
        )
        self.assertEqual(
            [item.args[0] for item in call_tool.call_args_list],
            ["query", "get_page", "get_backlinks"],
        )

    def test_persistent_read_session_formats_graph_query(self):
        session = PersistentGBrainSearch()
        with (
            mock.patch.object(session, "_start_locked"),
            mock.patch.object(
                session,
                "_call_tool_locked",
                return_value=[
                    {
                        "from_slug": "products/memory-stargraph",
                        "to_slug": "goals/example",
                        "link_type": "supports",
                        "depth": 1,
                    }
                ],
            ) as call_tool,
        ):
            output = session.read_cli_output(
                (
                    "graph-query",
                    "products/memory-stargraph",
                    "--direction",
                    "both",
                    "--depth",
                    "1",
                ),
                5,
            )

        self.assertEqual(
            output,
            "[depth 0] products/memory-stargraph\n"
            "  --supports-> goals/example (depth 1)\n",
        )
        self.assertEqual(call_tool.call_args.args[0], "traverse_graph")

    def test_evidence_record_search_lists_types_concurrently(self):
        barrier = threading.Barrier(4)
        slugs = {
            "learning": "learnings/parallel-evidence-benchmark",
            "todo": "notes/memory-starmap-todo-list/parallel-evidence-benchmark",
            "report": "reports/parallel-evidence-benchmark",
            "run": "runs/parallel-evidence-benchmark",
        }

        def fake_run_gbrain(*args, **_kwargs):
            page_type = args[2]
            barrier.wait(timeout=2)
            return f"{slugs[page_type]}\t{page_type}\t2026-08-23\tParallel evidence benchmark\n"

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            results, status, cache_status = evidence_record_search_results("parallel evidence benchmark")

        self.assertEqual(status, "complete")
        self.assertEqual(cache_status, "disabled")
        self.assertEqual({result["slug"] for result in results}, set(slugs.values()))

    def test_evidence_record_search_reuses_short_lived_page_cache(self):
        calls = []
        cache = EvidenceListCache(ttl_seconds=60)

        def fake_run_gbrain(*args, **_kwargs):
            page_type = args[2]
            calls.append(page_type)
            return f"runs/{page_type}-cache-benchmark\trun\t2026-08-23\tCache benchmark\n"

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            first_results, first_status, first_cache_status = evidence_record_search_results(
                "cache benchmark", row_cache=cache
            )
            second_results, second_status, second_cache_status = evidence_record_search_results(
                "cache benchmark", row_cache=cache
            )

        self.assertEqual(first_status, "complete")
        self.assertEqual(second_status, "complete")
        self.assertEqual(first_cache_status, "miss")
        self.assertEqual(second_cache_status, "hit")
        self.assertEqual(first_results, second_results)
        self.assertEqual(len(calls), 4)

    def test_evidence_record_search_serves_stale_rows_while_refreshing(self):
        cache = EvidenceListCache(ttl_seconds=30, stale_seconds=300)
        prefixes = {
            "learning": "learnings",
            "todo": "notes/memory-starmap-todo-list",
            "report": "reports",
            "run": "runs",
        }
        with mock.patch("server.time.monotonic", return_value=0):
            for page_type, prefix in prefixes.items():
                cache.put(
                    page_type,
                    40,
                    [
                        {
                            "slug": f"{prefix}/cache-benchmark-{page_type}",
                            "type": page_type,
                            "date": "2026-08-23",
                            "title": "Cache benchmark evidence",
                        }
                    ],
                )

        with (
            mock.patch("server.time.monotonic", return_value=31),
            mock.patch.object(cache, "refresh_async", return_value=True) as refresh,
            mock.patch("server.run_gbrain") as run,
        ):
            results, status, cache_status = evidence_record_search_results(
                "cache benchmark",
                row_cache=cache,
            )

        self.assertEqual(status, "complete")
        self.assertEqual(cache_status, "stale_hit")
        self.assertEqual(len(results), 4)
        self.assertEqual(refresh.call_count, 4)
        run.assert_not_called()

    def test_evidence_cache_clear_supersedes_an_inflight_refresh(self):
        cache = EvidenceListCache(ttl_seconds=30, stale_seconds=300)
        started = threading.Event()
        release = threading.Event()

        def loader():
            started.set()
            release.wait(timeout=1)
            return [{"slug": "runs/stale-refresh"}]

        self.assertTrue(cache.refresh_async("run", 40, loader))
        self.assertTrue(started.wait(timeout=1))
        self.assertFalse(cache.refresh_async("run", 40, loader))
        cache.clear()
        release.set()
        deadline = time.monotonic() + 1
        while cache.refreshing and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertIsNone(cache.get_stale("run", 40))

    def test_search_evidence_prewarm_is_nonblocking_and_coalesces(self):
        store = GraphStore()
        release = threading.Event()
        calls = []

        def fake_run_gbrain(*args, **_kwargs):
            page_type = args[2]
            calls.append(page_type)
            release.wait(timeout=1)
            return f"{page_type}s/prewarmed\t{page_type}\t2026-08-23\tPrewarmed evidence\n"

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            started_at = time.perf_counter()
            started = store.prewarm_search_evidence()
            elapsed = time.perf_counter() - started_at
            duplicate_started = store.prewarm_search_evidence()
            release.set()
            deadline = time.monotonic() + 1
            while store.evidence_list_cache.refreshing and time.monotonic() < deadline:
                time.sleep(0.01)

        self.assertEqual(started, 4)
        self.assertEqual(duplicate_started, 0)
        self.assertLess(elapsed, 0.5)
        self.assertEqual(set(calls), set(("learning", "todo", "report", "run")))
        for page_type in ("learning", "todo", "report", "run"):
            self.assertIsNotNone(store.evidence_list_cache.get(page_type, 40))
            self.assertIsNotNone(store.evidence_list_cache.wait_for_refresh(page_type, 40, 0))

    def test_evidence_search_joins_an_inflight_prewarm(self):
        store = GraphStore()
        release = threading.Event()
        calls = []
        prefixes = {
            "learning": "learnings",
            "todo": "notes/memory-starmap-todo-list",
            "report": "reports",
            "run": "runs",
        }

        def fake_run_gbrain(*args, **_kwargs):
            page_type = args[2]
            calls.append(page_type)
            release.wait(timeout=1)
            return f"{prefixes[page_type]}/prewarm-benchmark-{page_type}\t{page_type}\t2026-08-23\tPrewarm benchmark evidence\n"

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            self.assertEqual(store.prewarm_search_evidence(), 4)
            timer = threading.Timer(0.05, release.set)
            timer.start()
            results, status, cache_status = evidence_record_search_results(
                "prewarm benchmark",
                deadline=time.monotonic() + 1,
                per_type_timeout=1,
                row_cache=store.evidence_list_cache,
            )
            timer.join(timeout=1)

        self.assertEqual(status, "complete")
        self.assertEqual(cache_status, "prewarm_hit")
        self.assertEqual(len(results), 4)
        self.assertEqual(len(calls), 4)

    def test_graph_store_invalidation_clears_search_caches(self):
        store = GraphStore()
        store.evidence_list_cache.put("run", 40, [{"slug": "runs/cached"}])
        store.primary_search_cache.put("query", (({"slug": "cached"},), "complete"))
        store.yoda_search_cache.put("question", "cached search")
        store.yoda_source_cache.put("source", "cached source")
        store.relationship_type_cache.put("people/tony-guan", (("edge",),))

        store.invalidate()

        self.assertIsNone(store.evidence_list_cache.get("run", 40))
        self.assertIsNone(store.primary_search_cache.get("query"))
        self.assertIsNone(store.yoda_search_cache.get("question"))
        self.assertIsNone(store.yoda_source_cache.get("source"))
        self.assertIsNone(store.relationship_type_cache.get("people/tony-guan"))
        self.assertEqual(store.yoda_context_cache.entries, {})

    def test_timed_value_cache_expires_and_bounds_entries(self):
        cache = TimedValueCache(ttl_seconds=10, max_entries=2)
        with mock.patch("server.time.monotonic", return_value=0):
            cache.put("oldest", "one")
        with mock.patch("server.time.monotonic", return_value=1):
            cache.put("middle", "two")
        with mock.patch("server.time.monotonic", return_value=2):
            cache.put("newest", "three")
        with mock.patch("server.time.monotonic", return_value=3):
            self.assertIsNone(cache.get("oldest"))
            self.assertEqual(cache.get("middle"), "two")
            self.assertEqual(cache.get("newest"), "three")
        with mock.patch("server.time.monotonic", return_value=11.5):
            self.assertIsNone(cache.get("middle"))
            self.assertEqual(cache.get("newest"), "three")

    def test_timed_value_cache_load_once_prunes_expired_and_bounds_entries(self):
        cache = TimedValueCache(ttl_seconds=10, max_entries=2)
        cache.entries = {
            "expired": {"stored_at": 0, "value": "old"},
            "fresh": {"stored_at": 20, "value": "kept"},
        }

        with mock.patch("server.time.monotonic", return_value=21):
            value, status = cache.load_once("new", lambda: "loaded", timeout=1)

        self.assertEqual((value, status), ("loaded", "loaded"))
        self.assertEqual(set(cache.entries), {"fresh", "new"})

    def test_timed_value_cache_returns_stale_values_within_stale_window(self):
        cache = TimedValueCache(ttl_seconds=10, stale_seconds=30, max_entries=2)
        with mock.patch("server.time.monotonic", return_value=0):
            cache.put("query", "cached")
        with mock.patch("server.time.monotonic", return_value=12):
            self.assertIsNone(cache.get("query"))
            self.assertEqual(cache.get_stale("query"), "cached")
        with mock.patch("server.time.monotonic", return_value=31):
            self.assertIsNone(cache.get_stale("query"))

    def test_primary_search_returns_stale_value_while_refreshing_once(self):
        cache = TimedValueCache(ttl_seconds=10, stale_seconds=30, max_entries=2)
        release = threading.Event()
        cached_value = (({"slug": "pages/cached"},), "complete")
        query = "stale query"
        cache_key = hashlib.sha256(query.encode("utf-8")).hexdigest()
        with mock.patch("server.time.monotonic", return_value=0):
            cache.put(cache_key, cached_value)

        def slow_search(_query, _timeout):
            release.wait(timeout=1)
            return [{"slug": "pages/fresh"}], "complete"

        with (
            mock.patch("server.time.monotonic", return_value=12),
            mock.patch("server.live_primary_search_results", side_effect=slow_search) as search,
        ):
            first = cached_primary_search_results(query, 1, cache)
            second = cached_primary_search_results(query, 1, cache)
            release.set()

        self.assertEqual(first[0], [{"slug": "pages/cached"}])
        self.assertEqual(first[2], "stale_refresh_started")
        self.assertEqual(second[2], "stale_refresh_joined")
        self.assertEqual(search.call_count, 1)

    def test_graph_store_reuses_whitespace_equivalent_primary_search_results(self):
        store = GraphStore()
        seed_graph = finalize_graph(
            {
                "title": "Search cache test",
                "source": {"coverage": {}},
                "nodes": [
                    {
                        "slug": "index",
                        "id": "index",
                        "label": "Index",
                        "type": "root",
                        "links": [],
                    }
                ],
                "edge_types": [],
            }
        )
        for page_type in ("learning", "todo", "report", "run"):
            store.evidence_list_cache.put(page_type, 40, [])

        with (
            mock.patch.object(store, "get_seed_graph", return_value=seed_graph),
            mock.patch(
                "server.run_gbrain",
                return_value="[0.99] products/memory-stargraph -- # Memory Stargraph",
            ) as run,
        ):
            first = store.search("memory stargraph")
            second = store.search("  MEMORY   STARGRAPH  ")

        search_calls = [call for call in run.call_args_list if call.args[0] == "search"]
        self.assertEqual(len(search_calls), 1)
        self.assertEqual(first["source"]["coverage"]["search_primary_cache_status"], "miss")
        self.assertEqual(second["source"]["coverage"]["search_primary_cache_status"], "hit")

    def test_primary_search_coalesces_concurrent_cold_loads(self):
        cache = TimedValueCache(ttl_seconds=30, stale_seconds=300, max_entries=2)
        started = threading.Event()
        release = threading.Event()
        rows = []

        def slow_search(_query, _timeout):
            started.set()
            release.wait(timeout=1)
            return [{"slug": "pages/fresh"}], "complete"

        def search():
            rows.append(cached_primary_search_results("cold query", 1, cache))

        with mock.patch("server.live_primary_search_results", side_effect=slow_search) as live_search:
            first = threading.Thread(target=search)
            second = threading.Thread(target=search)
            first.start()
            self.assertTrue(started.wait(timeout=1))
            second.start()
            time.sleep(0.01)
            release.set()
            first.join(timeout=1)
            second.join(timeout=1)

        self.assertEqual(live_search.call_count, 1)
        self.assertEqual({row[2] for row in rows}, {"miss", "coalesced_hit"})
        self.assertTrue(all(row[0] == [{"slug": "pages/fresh"}] for row in rows))

    def test_graph_store_reads_independent_entities_concurrently_in_input_order(self):
        store = GraphStore()
        barrier = threading.Barrier(3)

        def fake_get_entity_raw(slug):
            barrier.wait(timeout=2)
            return f"# {slug}"

        with mock.patch.object(store, "get_entity_raw", side_effect=fake_get_entity_raw):
            pages = store.get_entities_raw(["pages/one", "pages/two", "pages/three"])

        self.assertEqual(list(pages), ["pages/one", "pages/two", "pages/three"])
        self.assertEqual(pages["pages/two"], "# pages/two")

    def test_yoda_state_reconciliation_reuses_one_todo_root_read(self):
        store = GraphStore()
        todo_root = "notes/memory-starmap-todo-list"
        backlog = """| id | status | priority | title | node | updated | notes |
| --- | --- | --- | --- | --- | --- | --- |
| SG-1000 | planned | P1 | Current reliability gap | [[notes/memory-starmap-todo-list/current-gap]] | 2026-08-23 | Planned. |
| SG-0999 | completed | P1 | Resolved reliability gap | [[notes/memory-starmap-todo-list/resolved-gap]] | 2026-08-22 | Completed. |
"""
        pages = {
            todo_root: backlog,
            "notes/memory-starmap-todo-list/current-gap": "# Current gap",
            "notes/memory-starmap-todo-list/resolved-gap": "# Resolved gap",
        }
        calls = []

        def fake_get_entity_raw(slug):
            calls.append(slug)
            return pages.get(slug)

        stable_context = {
            "selected_node": "# Product",
            "graph": "",
            "backlinks": "",
            "timings": {},
        }
        with (
            mock.patch.object(store, "get_entity_raw", side_effect=fake_get_entity_raw),
            mock.patch.object(store, "build_yoda_targeted_context", return_value={"text": "", "counts": {}}),
            mock.patch("server.run_gbrain", return_value=""),
        ):
            prompt = store.build_yoda_prompt(
                "products/memory-stargraph",
                "What current reliability gaps remain?",
                stable_context=stable_context,
            )

        self.assertIn("Current reliability gap", prompt)
        self.assertIn("Resolved reliability gap", prompt)
        self.assertEqual(calls.count(todo_root), 1)

    def test_yoda_search_reuses_an_exact_query_but_not_a_different_question(self):
        store = GraphStore()
        stable_context = {
            "selected_node": "# Product",
            "graph": "",
            "backlinks": "",
            "timings": {},
        }
        search_output = "\n".join(
            (
                "[0.99] products/memory-stargraph -- # Memory Stargraph",
                "[0.90] sources/relevant -- # Relevant source",
            )
        )

        def gbrain_result(*args, **_kwargs):
            if args[0] == "query":
                return search_output
            if args[0] == "get":
                return "# Relevant source"
            raise AssertionError(args)

        with (
            mock.patch.object(store, "build_yoda_current_todo_context", return_value={"text": "", "counts": {}}),
            mock.patch.object(
                store,
                "build_yoda_operational_remediation_context",
                return_value={"text": "", "counts": {}},
            ),
            mock.patch.object(store, "build_yoda_targeted_context", return_value={"text": "", "counts": {}}),
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
        ):
            first_prompt = store.build_yoda_prompt(
                "products/memory-stargraph",
                "What changed?",
                stable_context=stable_context,
            )
            second_prompt = store.build_yoda_prompt(
                "products/memory-stargraph",
                "What changed?",
                stable_context=stable_context,
            )
            store.build_yoda_prompt(
                "products/memory-stargraph",
                "What is next?",
                stable_context=stable_context,
            )

        query_calls = [call for call in run.call_args_list if call.args[0] == "query"]
        get_calls = [call for call in run.call_args_list if call.args[0] == "get"]
        self.assertEqual(first_prompt, second_prompt)
        self.assertEqual(len(query_calls), 2)
        self.assertTrue(all("--no-expand" in call.args for call in query_calls))
        self.assertEqual(len(get_calls), 1)
        self.assertEqual(len(store.yoda_search_cache.entries), 2)
        self.assertEqual(len(store.yoda_source_cache.entries), 1)

    def test_yoda_search_reuses_whitespace_equivalent_query(self):
        store = GraphStore()
        output = "[0.99] products/memory-stargraph -- # Memory Stargraph"

        with mock.patch("server.run_gbrain", return_value=output) as run:
            first = store.get_yoda_search_output(
                "What changed? products/memory-stargraph"
            )
            second = store.get_yoda_search_output(
                "  What   changed?   products/memory-stargraph  "
            )

        self.assertEqual(first, output)
        self.assertEqual(second, output)
        run.assert_called_once_with(
            "query",
            "What changed? products/memory-stargraph",
            "--no-expand",
            "--adaptive-return",
            "true",
            "--limit",
            "10",
            "--relational",
            "true",
        )

    def test_yoda_search_coalesces_concurrent_cold_loads(self):
        store = GraphStore()
        started = threading.Event()
        release = threading.Event()
        rows = []

        def slow_query(*_args, **_kwargs):
            started.set()
            release.wait(timeout=1)
            return "[0.99] products/memory-stargraph -- # Memory Stargraph\n"

        def search():
            rows.append(store.get_yoda_search_output("What changed? products/memory-stargraph"))

        with mock.patch("server.run_gbrain", side_effect=slow_query) as run:
            first = threading.Thread(target=search)
            second = threading.Thread(target=search)
            first.start()
            self.assertTrue(started.wait(timeout=1))
            second.start()
            time.sleep(0.01)
            release.set()
            first.join(timeout=1)
            second.join(timeout=1)

        self.assertEqual(run.call_count, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], rows[1])

    def test_yoda_source_pages_coalesce_concurrent_cold_loads_per_slug(self):
        store = GraphStore()
        release = threading.Event()
        calls = []
        rows = []
        slugs = ["pages/one", "pages/two", "pages/three", "pages/four"]

        def slow_get(slug):
            calls.append(slug)
            release.wait(timeout=1)
            return f"# {slug}"

        def load():
            rows.append(store.get_yoda_source_pages(slugs))

        with mock.patch.object(store, "get_entity_raw", side_effect=slow_get):
            first = threading.Thread(target=load)
            second = threading.Thread(target=load)
            first.start()
            second.start()
            deadline = time.monotonic() + 1
            while len(calls) < len(slugs) and time.monotonic() < deadline:
                time.sleep(0.005)
            release.set()
            first.join(timeout=1)
            second.join(timeout=1)

        self.assertEqual(sorted(calls), sorted(slugs))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], rows[1])

    def test_search_runs_primary_and_evidence_calls_concurrently(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "type": "root", "links": []}],
            "edge_types": [],
        }
        barrier = threading.Barrier(5)

        def fake_run_gbrain(*args, **_kwargs):
            barrier.wait(timeout=2)
            if args[0] == "search":
                return "[0.90] learnings/concurrent-search -- Concurrent search\n"
            if args[0] == "list":
                return ""
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "concurrent search benchmark")

        coverage = graph["source"]["coverage"]
        self.assertEqual(coverage["search_status"], "complete")
        self.assertEqual(coverage["search_slugs"][0], "learnings/concurrent-search")

    def test_search_raw_graph_promotes_matching_evidence_records(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "type": "root", "links": []}],
            "edge_types": [],
        }

        def fake_run_gbrain(*args, **_kwargs):
            if args == ("search", "exact TODO search fast terminal state"):
                return "[0.75] categories/todo -- Todo hub\n[0.60] notes/memory-starmap-todo-list -- Todo list\n"
            if args == ("list", "--type", "run", "-n", "40"):
                return "runs/memory-stargraph-wish-sg0163-20260728t021507-0700-ab843b8b\trun\t2026-07-28\tMemory Stargraph Developer SG-0163 Run\n"
            if args == ("list", "--type", "report", "-n", "40"):
                return ""
            if args == ("list", "--type", "learning", "-n", "40"):
                return "learnings/memory-stargraph-20260728-exact-todo-search-fast-terminal-state\tlearning\t2026-07-28\tExact TODO-ID search needs a ready local index and terminal UI evidence\n"
            if args == ("list", "--type", "todo", "-n", "40"):
                return "notes/memory-starmap-todo-list/make-search-show-results-or-clear-terminal-state-for-exact-todo-ids\ttodo\t2026-07-28\tMake search show results or a clear terminal state for exact TODO IDs\n"
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "exact TODO search fast terminal state")

        coverage = graph["source"]["coverage"]
        self.assertEqual(coverage["search_status"], "complete")
        self.assertEqual(coverage["search_primary_status"], "complete")
        self.assertEqual(coverage["search_evidence_status"], "complete")
        self.assertEqual(
            coverage["search_slugs"][0],
            "learnings/memory-stargraph-20260728-exact-todo-search-fast-terminal-state",
        )
        self.assertIn(
            "notes/memory-starmap-todo-list/make-search-show-results-or-clear-terminal-state-for-exact-todo-ids",
            coverage["evidence_search_slugs"],
        )
        self.assertGreater(coverage["search_slugs"].index("categories/todo"), 0)
        node_map = {node["slug"]: node for node in graph["nodes"]}
        self.assertEqual(
            node_map["learnings/memory-stargraph-20260728-exact-todo-search-fast-terminal-state"]["tags"],
            ["lazy-search"],
        )

    def test_search_raw_graph_reports_partial_status_when_evidence_budget_expires(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "type": "root", "links": []}],
            "edge_types": [],
        }

        def fake_run_gbrain(*args, **_kwargs):
            if args == ("search", "optional timeout telemetry is not a todo"):
                return "[0.82] learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo -- Optional timeout telemetry is not a TODO\n"
            if args == ("list", "--type", "learning", "-n", "40"):
                return "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo\tlearning\t2026-07-28\tOptional timeout telemetry is not a todo\n"
            if args[0] == "list":
                raise TimeoutError(args)
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "optional timeout telemetry is not a todo")

        coverage = graph["source"]["coverage"]
        self.assertEqual(graph["source"]["status"], "lazy-search-partial")
        self.assertEqual(coverage["search_status"], "partial_timeout")
        self.assertEqual(coverage["search_primary_status"], "complete")
        self.assertEqual(coverage["search_evidence_status"], "partial_timeout")
        self.assertIn(
            "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
            coverage["search_slugs"],
        )

    def test_search_raw_graph_collects_evidence_when_primary_times_out(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [
                {
                    "slug": "notes/memory-starmap-todo-list/persist-global-active-tag-readback-in-capture-link-terminal-results",
                    "id": "sg0193",
                    "label": "Persist global active tag readback in Capture Link terminal results",
                    "type": "todo",
                    "summary": "Optional timeout telemetry is not a todo appeared in lifecycle evidence.",
                    "tags": ["todo"],
                    "links": [],
                }
            ],
            "edge_types": [],
        }
        primary_timeouts = []

        def fake_run_gbrain(*args, **kwargs):
            if args == ("search", "optional timeout telemetry is not a todo"):
                primary_timeouts.append(kwargs.get("timeout"))
                raise TimeoutError(args)
            if args == ("list", "--type", "learning", "-n", "40"):
                return "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo\tlearning\t2026-07-28\tOptional timeout telemetry is not a todo\n"
            if args[0] == "list":
                return ""
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "optional timeout telemetry is not a todo")

        coverage = graph["source"]["coverage"]
        self.assertLessEqual(primary_timeouts[0], 6)
        self.assertEqual(coverage["search_primary_status"], "timeout")
        self.assertEqual(coverage["search_evidence_status"], "complete")
        self.assertEqual(coverage["search_status"], "partial_timeout")
        self.assertEqual(
            coverage["search_slugs"][0],
            "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
        )

    def test_search_raw_graph_resolves_exact_todo_id_from_backlog_before_live_search(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "type": "root", "links": []}],
            "edge_types": [],
        }
        backlog = "\n".join(
            [
                "| id | status | priority | title | node | updated | notes |",
                "| --- | --- | --- | --- | --- | --- | --- |",
                "| SG-0162 | completed | P1 | Reduce recurring Ask Yoda broad-graph timeout regression | [[notes/memory-starmap-todo-list/reduce-recurring-ask-yoda-broad-graph-timeout-regression]] | 2026-07-24 | Completed. |",
            ]
        )

        def fake_run_gbrain(*args, **_kwargs):
            if args == ("get", "notes/memory-starmap-todo-list"):
                return backlog
            raise AssertionError(f"exact TODO ID search should not call live search: {args}")

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "SG-0162")

        coverage = graph["source"]["coverage"]
        self.assertEqual(coverage["search_status"], "complete")
        self.assertEqual(coverage["search_primary_status"], "complete")
        self.assertEqual(coverage["search_evidence_status"], "skipped_exact_todo_id")
        self.assertEqual(coverage["search_exact_todo_id_status"], "complete")
        self.assertEqual(
            coverage["search_slugs"],
            ["notes/memory-starmap-todo-list/reduce-recurring-ask-yoda-broad-graph-timeout-regression"],
        )

    def test_search_raw_graph_resolves_exact_loaded_slug_without_live_search(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [
                {
                    "slug": "products/memory-stargraph",
                    "id": "product",
                    "label": "Memory Stargraph",
                    "type": "product",
                    "summary": "Local-first knowledge operating system.",
                    "tags": [],
                    "links": [],
                }
            ],
            "edge_types": [],
        }

        with mock.patch("server.run_gbrain") as run:
            graph = search_raw_graph(raw_graph, "  PRODUCTS/MEMORY-STARGRAPH  ")

        coverage = graph["source"]["coverage"]
        run.assert_not_called()
        self.assertEqual(coverage["search_status"], "complete")
        self.assertEqual(coverage["search_primary_cache_status"], "skipped_exact_slug")
        self.assertEqual(coverage["search_evidence_status"], "skipped_exact_slug")
        self.assertTrue(coverage["search_exact_slug"])
        self.assertEqual(coverage["search_exact_slug_source"], "loaded_graph")
        self.assertEqual(coverage["search_slugs"], ["products/memory-stargraph"])
        self.assertEqual(coverage["search_results"], 1)

    def test_search_raw_graph_verifies_unloaded_exact_slug_with_direct_get(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "links": []}],
            "edge_types": [],
        }
        page = "---\ntitle: Attachment Runbook\ntype: document\n---\n\n# Attachment Runbook\n\nDurable storage checks."

        with mock.patch("server.run_gbrain", return_value=page) as run:
            graph = search_raw_graph(raw_graph, "docs/gbrain-attachment-runbook")

        coverage = graph["source"]["coverage"]
        run.assert_called_once_with("get", "docs/gbrain-attachment-runbook", timeout=3)
        self.assertTrue(coverage["search_exact_slug"])
        self.assertEqual(coverage["search_exact_slug_source"], "gbrain_get")
        self.assertEqual(coverage["search_primary_cache_status"], "skipped_exact_slug")
        self.assertEqual(coverage["search_slugs"], ["docs/gbrain-attachment-runbook"])

    def test_search_raw_graph_resolves_unique_exact_loaded_label_without_live_search(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [
                {
                    "slug": "products/memory-stargraph",
                    "id": "product",
                    "label": "Memory Stargraph",
                    "type": "product",
                    "summary": "Local-first knowledge operating system.",
                    "tags": [],
                    "links": [],
                },
                {
                    "slug": "runs/example",
                    "id": "run",
                    "label": "Memory Stargraph...",
                    "type": "run",
                    "summary": "Truncated label must not create ambiguity.",
                    "tags": [],
                    "links": [],
                },
            ],
            "edge_types": [],
        }

        with mock.patch("server.run_gbrain") as run:
            graph = search_raw_graph(raw_graph, "  MEMORY   STARGRAPH  ")

        coverage = graph["source"]["coverage"]
        run.assert_not_called()
        self.assertTrue(coverage["search_exact_loaded_label"])
        self.assertEqual(
            coverage["search_primary_cache_status"],
            "skipped_exact_loaded_label",
        )
        self.assertEqual(
            coverage["search_evidence_status"],
            "skipped_exact_loaded_label",
        )
        self.assertEqual(coverage["search_slugs"], ["products/memory-stargraph"])
        self.assertEqual(coverage["search_results"], 1)

    def test_exact_loaded_label_search_rejects_ambiguous_single_and_broader_queries(self):
        raw_graph = {
            "nodes": [
                {"slug": "people/tony-guan", "label": "Tony Guan"},
                {"slug": "profiles/tony-guan", "label": "Tony Guan"},
                {"slug": "products/gbrain", "label": "Gbrain"},
            ]
        }

        self.assertIsNone(exact_loaded_label_search_results(raw_graph, "Tony Guan"))
        self.assertIsNone(exact_loaded_label_search_results(raw_graph, "Gbrain"))
        self.assertIsNone(
            exact_loaded_label_search_results(raw_graph, "Tony Guan publications")
        )

    def test_search_raw_graph_does_not_use_loaded_slug_fast_path_for_broader_query(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [
                {
                    "slug": "products/memory-stargraph",
                    "id": "product",
                    "label": "Memory Stargraph",
                    "type": "product",
                    "summary": "Local-first knowledge operating system.",
                    "tags": [],
                    "links": [],
                }
            ],
            "edge_types": [],
        }
        primary_result = {
            "slug": "products/memory-stargraph",
            "score": 1.0,
            "label": "Memory Stargraph",
            "preview": "Live primary result.",
        }

        with (
            mock.patch(
                "server.cached_primary_search_results",
                return_value=([primary_result], "complete", "miss"),
            ) as primary,
            mock.patch(
                "server.evidence_record_search_results",
                return_value=([], "complete", "hit"),
            ),
        ):
            graph = search_raw_graph(raw_graph, "products/memory-stargraph roadmap")

        coverage = graph["source"]["coverage"]
        primary.assert_called_once()
        self.assertFalse(coverage["search_exact_slug"])
        self.assertEqual(coverage["search_exact_slug_source"], "")
        self.assertEqual(coverage["search_primary_cache_status"], "miss")

    def test_search_raw_graph_falls_back_when_exact_slug_cannot_be_verified(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "links": []}],
            "edge_types": [],
        }

        with (
            mock.patch("server.run_gbrain", side_effect=RuntimeError("not found")) as get_page,
            mock.patch(
                "server.cached_primary_search_results",
                return_value=([], "complete", "miss"),
            ) as primary,
            mock.patch(
                "server.evidence_record_search_results",
                return_value=([], "complete", "hit"),
            ),
        ):
            graph = search_raw_graph(raw_graph, "docs/does-not-exist")

        coverage = graph["source"]["coverage"]
        get_page.assert_called_once_with("get", "docs/does-not-exist", timeout=3)
        primary.assert_called_once()
        self.assertFalse(coverage["search_exact_slug"])
        self.assertEqual(coverage["search_exact_slug_source"], "")
        self.assertEqual(coverage["search_primary_cache_status"], "miss")
        self.assertEqual(coverage["search_results"], 0)

    def test_search_raw_graph_missing_exact_todo_id_does_not_return_false_positives(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "type": "root", "links": []}],
            "edge_types": [],
        }
        backlog = "\n".join(
            [
                "| id | status | priority | title | node | updated | notes |",
                "| --- | --- | --- | --- | --- | --- | --- |",
                "| SG-0162 | completed | P1 | Reduce recurring Ask Yoda broad-graph timeout regression | [[notes/memory-starmap-todo-list/reduce-recurring-ask-yoda-broad-graph-timeout-regression]] | 2026-07-24 | Completed. |",
            ]
        )

        def fake_run_gbrain(*args, **_kwargs):
            if args == ("get", "notes/memory-starmap-todo-list"):
                return backlog
            raise AssertionError(f"missing exact TODO ID search should not broaden: {args}")

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "SG-9999")

        coverage = graph["source"]["coverage"]
        self.assertEqual(coverage["search_status"], "complete")
        self.assertEqual(coverage["search_primary_status"], "complete")
        self.assertEqual(coverage["search_evidence_status"], "skipped_exact_todo_id")
        self.assertEqual(coverage["search_results"], 0)
        self.assertEqual(coverage["search_slugs"], [])

    def test_search_raw_graph_loaded_product_identity_survives_live_timeouts(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [
                {
                    "slug": "runs/memory-stargraph-sre-daily-reliability-2026-08-09-sg0179-7b329889",
                    "id": "run",
                    "label": "Memory Stargraph...",
                    "type": "run",
                    "summary": "Truncated loaded run label",
                    "tags": [],
                    "links": [],
                },
                {
                    "slug": "products/memory-stargraph",
                    "id": "product",
                    "label": "Memory Stargraph",
                    "type": "product",
                    "summary": "Product node",
                    "tags": [],
                    "links": [],
                },
            ],
            "edge_types": [],
        }

        def fake_run_gbrain(*args, **_kwargs):
            if args == ("search", "memory stargraph product"):
                raise TimeoutError(args)
            if args[0] == "list":
                raise TimeoutError(args)
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "memory stargraph product")

        coverage = graph["source"]["coverage"]
        self.assertEqual(coverage["search_status"], "partial_timeout")
        self.assertEqual(coverage["search_primary_status"], "timeout")
        self.assertEqual(coverage["search_slugs"][0], "products/memory-stargraph")

    def test_merge_search_results_keeps_exact_primary_above_partial_broad_evidence(self):
        results = merge_search_results(
            [
                {
                    "slug": "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
                    "score": 1.0,
                    "label": "Optional timeout telemetry is not a TODO",
                    "preview": "",
                }
            ],
            [
                {
                    "slug": "learnings/memory-stargraph-20260724-optional-broad-graph-timeouts-should-not-degrade-grounded-context",
                    "score": 4.0,
                    "label": "Optional broad graph timeouts",
                    "preview": "",
                }
            ],
            "optional timeout telemetry is not a todo",
        )

        self.assertEqual(
            results[0]["slug"],
            "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
        )

    def test_merge_search_results_prefers_query_identity_over_lifecycle_body_score(self):
        results = merge_search_results(
            [
                {
                    "slug": "notes/memory-starmap-todo-list/persist-global-active-tag-readback-in-capture-link-terminal-results",
                    "score": 12.0,
                    "label": "Persist global active tag readback in Capture Link terminal results",
                    "preview": "UX evidence query optional timeout telemetry is not a todo appeared in a terminal report.",
                },
                {
                    "slug": "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
                    "score": 1.0,
                    "label": "Optional timeout telemetry is not a todo",
                    "preview": "",
                },
            ],
            [
                {
                    "slug": "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
                    "score": 5.2,
                    "label": "Optional timeout telemetry is not a todo",
                    "preview": "Evidence record: 2026-07-28 Optional timeout telemetry is not a todo",
                }
            ],
            "optional timeout telemetry is not a todo",
        )

        self.assertEqual(
            results[0]["slug"],
            "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
        )
        self.assertIn(
            "notes/memory-starmap-todo-list/persist-global-active-tag-readback-in-capture-link-terminal-results",
            [result["slug"] for result in results],
        )

    def test_search_raw_graph_uses_sentinel_when_operational_growth_hijacks_loaded_results(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [
                {
                    "slug": "notes/memory-starmap-todo-list/add-numeric-sre-capacity-backup-and-restore-evidence",
                    "id": "sg0196",
                    "label": "Add numeric SRE capacity backup and restore evidence",
                    "type": "todo",
                    "summary": 'UX evidence query "optional timeout telemetry is not a todo" appeared in SRE evidence growth.',
                    "tags": ["todo"],
                    "links": [],
                }
            ],
            "edge_types": [],
        }

        def fake_run_gbrain(*args, **_kwargs):
            if args == ("search", "optional timeout telemetry is not a todo"):
                raise TimeoutError(args)
            if args[0] == "list":
                raise TimeoutError(args)
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "optional timeout telemetry is not a todo")

        coverage = graph["source"]["coverage"]
        self.assertEqual(coverage["search_status"], "partial_timeout")
        self.assertEqual(
            coverage["search_slugs"][0],
            "learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo",
        )
        self.assertEqual(
            coverage["search_sentinel_slugs"],
            ["learnings/memory-stargraph-intake-2026-07-28-optional-timeout-telemetry-is-not-a-todo"],
        )
        self.assertIn(
            "notes/memory-starmap-todo-list/add-numeric-sre-capacity-backup-and-restore-evidence",
            coverage["loaded_graph_search_slugs"],
        )

    def test_merge_search_results_prefers_exact_product_label_for_product_name_query(self):
        results = merge_search_results(
            [
                {
                    "slug": "runs/memory-stargraph-wish-sg0195-20260809t041140-0700-ed8b1a1",
                    "score": 12.0,
                    "label": "Memory Stargraph Developer SG-0195 loaded search discoverability",
                    "preview": "",
                }
            ],
            [
                {
                    "slug": "runs/memory-stargraph-sre-daily-reliability-2026-08-09-sg0179-7b329889",
                    "score": 18.1,
                    "label": "Memory Stargraph...",
                    "preview": "Truncated loaded-graph label",
                },
                {
                    "slug": "products/memory-stargraph",
                    "score": 4.0,
                    "label": "Memory Stargraph",
                    "preview": "Product node",
                }
            ],
            "memory stargraph",
        )

        self.assertEqual(results[0]["slug"], "products/memory-stargraph")

    def test_evidence_search_ignores_low_signal_page_list_matches(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {}},
            "nodes": [{"slug": "index", "id": "index", "label": "Index", "type": "root", "links": []}],
            "edge_types": [],
        }

        def fake_run_gbrain(*args, **_kwargs):
            if args == ("search", "Tony Guan"):
                return "[0.90] people/tony-guan -- Tony Guan\n"
            if args[0] == "list":
                return "runs/memory-stargraph-daily-learning-intake-2026-07-28\trun\t2026-07-28\tMemory Stargraph Daily Learning Intake Run 2026-07-28\n"
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run_gbrain):
            graph = search_raw_graph(raw_graph, "Tony Guan")

        self.assertEqual(graph["source"]["coverage"]["search_slugs"], ["people/tony-guan"])
        self.assertEqual(graph["source"]["coverage"]["evidence_search_slugs"], [])

    def test_friendly_labels_strip_category_prefixes(self):
        self.assertEqual(make_label("companies/uber"), "Uber")
        self.assertEqual(friendly_label("companies/uber", "Companies/uber"), "Uber")
        self.assertEqual(friendly_label("organizations/stopprop16", "Organizations/stopprop16"), "Stopprop16")
        self.assertEqual(friendly_label("categories/people", "Categories/people"), "People")
        self.assertEqual(friendly_label("people/tony-guan", "Tony Guan"), "Tony Guan")
        self.assertEqual(make_label("people/melonplanter-uhx51x2s12"), "Melonplanter")
        self.assertEqual(friendly_label("people/melonplanter-uhx51x2s12", "Melonplanter Uhx51x2s12"), "Melonplanter")
        self.assertEqual(make_label("wechat-groups/voter-id-26239915567"), "Voter Id")
        self.assertEqual(friendly_label("wechat-groups/voter-id-26239915567", "Voter Id 26239915567"), "Voter Id")
        self.assertEqual(make_label("wechat-group-members/melonplanter-uhx51x2s12"), "Melonplanter")
        self.assertEqual(friendly_label("wechat-group-members/melonplanter-uhx51x2s12", "Melonplanter Uhx51x2s12"), "Melonplanter")
        self.assertEqual(make_label("people/wechat-group-members/wechat-member-42lwbvt012"), "Wechat Member")
        self.assertEqual(
            friendly_label("people/wechat-group-members/wechat-member-42lwbvt012", "李伟平"),
            "李伟平",
        )
        self.assertEqual(friendly_label("groups/wechat/svca-vip-27108422220", "SVCA VIP 聊天室 27108422220"), "SVCA VIP 聊天室")
        self.assertEqual(friendly_label("groups/wechat/very-long-title", "X" * 120), "XXXXXXXXXXXXXXXXX...")
        self.assertLessEqual(len(friendly_label("notes/very-long-title", "X" * 120)), 20)

    def test_parse_backlinks_reads_inbound_edges(self):
        output = """[
  {"from_slug": "people/frank-xu", "to_slug": "organizations/cfer-foundation", "link_type": "president"},
  {"from_slug": "people/gail-heriot", "to_slug": "organizations/cfer-foundation", "link_type": "executive vice president"}
]"""
        edges = parse_backlinks(output, "organizations/cfer-foundation")

        self.assertIn(("organizations/cfer-foundation", "people/frank-xu"), edges)
        self.assertIn(("organizations/cfer-foundation", "people/gail-heriot"), edges)

    def test_parse_link_types_reads_graph_relationships(self):
        output = """[
  {"slug": "people/tony-guan", "links": [{"to_slug": "universities/changan-university", "link_type": "studied in"}]}
]"""
        edge_types = parse_link_types(output, "people/tony-guan")

        self.assertEqual(edge_types[("people/tony-guan", "universities/changan-university")], {"studied in"})

    def test_parse_graph_query_link_types_reads_depth_one_outbound_relationships(self):
        output = """[depth 0] people/tony-guan
  --member_of-> categories/people (depth 1)
  --authored-> collections/tony-guan-publications (depth 1)
    --has_member-> posts/example (depth 2)
"""
        edge_types = parse_graph_query_link_types(output, "people/tony-guan")

        self.assertEqual(
            edge_types[("categories/people", "people/tony-guan")],
            {"member_of"},
        )
        self.assertEqual(
            edge_types[("collections/tony-guan-publications", "people/tony-guan")],
            {"authored"},
        )
        self.assertNotIn(("people/tony-guan", "posts/example"), edge_types)

    def test_direct_relationship_types_uses_bounded_outbound_query_and_backlinks(self):
        store = GraphStore()

        def fake_run(*args, **_kwargs):
            if args == (
                "graph-query",
                "people/tony-guan",
                "--direction",
                "out",
                "--depth",
                "1",
            ):
                return "[depth 0] people/tony-guan\n  --member_of-> categories/people (depth 1)\n"
            if args == ("backlinks", "people/tony-guan"):
                return '[{"from_slug":"posts/example","to_slug":"people/tony-guan","link_type":"authored_by"}]'
            raise AssertionError(args)

        with mock.patch("server.run_gbrain", side_effect=fake_run) as run:
            edge_types = store.direct_relationship_types("people/tony-guan")
            cached_edge_types = store.direct_relationship_types("people/tony-guan")

        self.assertEqual(
            edge_types[("categories/people", "people/tony-guan")],
            {"member_of"},
        )
        self.assertEqual(
            edge_types[("people/tony-guan", "posts/example")],
            {"authored_by"},
        )
        self.assertEqual(run.call_count, 2)
        self.assertEqual(dict(cached_edge_types), dict(edge_types))

    def test_parse_neighbors_ignores_unrelated_neighbor_edges_in_depth_one_json(self):
        output = """  Schema version 1 → 119 (114 migration(s) pending)
[
  {"slug": "people/tony-guan", "links": [{"to_slug": "companies/linkedin", "link_type": "employed_by"}]},
  {"slug": "companies/linkedin", "links": [
    {"to_slug": "people/tony-guan", "link_type": "employs"},
    {"to_slug": "products/unrelated", "link_type": "owns"}
  ]}
]"""

        edges = parse_neighbors(output, "people/tony-guan")
        edge_types = parse_link_types(output, "people/tony-guan")

        self.assertEqual(edges, {("companies/linkedin", "people/tony-guan")})
        self.assertEqual(edge_types[("companies/linkedin", "people/tony-guan")], {"employed_by", "employs"})
        self.assertNotIn(("companies/linkedin", "products/unrelated"), edge_types)

    def test_parse_backlink_types_reads_inbound_relationships(self):
        output = """[
  {"from_slug": "people/frank-xu", "to_slug": "organizations/cfer-foundation", "link_type": "president"}
]"""
        edge_types = parse_backlink_types(output, "organizations/cfer-foundation")

        self.assertEqual(edge_types[("organizations/cfer-foundation", "people/frank-xu")], {"president"})

    def test_expand_raw_graph_merges_backlinks_as_direct_neighbors(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "source": {"coverage": {"expanded_slugs": []}},
            "nodes": [
                {
                    "slug": "organizations/cfer-foundation",
                    "label": "Californians for Equal Rights Foundation",
                    "type": "organization",
                    "links": [],
                }
            ],
        }
        graph_output = """[depth 0] organizations/cfer-foundation
  --oppose-> bills/aca7 (depth 1)
"""
        backlinks_output = """[
  {"from_slug": "people/frank-xu", "to_slug": "organizations/cfer-foundation", "link_type": "president"},
  {"from_slug": "people/gail-heriot", "to_slug": "organizations/cfer-foundation", "link_type": "executive vice president"}
]"""

        with mock.patch("server.run_gbrain", side_effect=[graph_output, backlinks_output]):
            expanded = finalize_graph(expand_raw_graph(raw_graph, "organizations/cfer-foundation"))

        cfer = next(node for node in expanded["nodes"] if node["slug"] == "organizations/cfer-foundation")
        self.assertIn("bills/aca7", cfer["links"])
        self.assertIn("people/frank-xu", cfer["links"])
        self.assertIn("people/gail-heriot", cfer["links"])
        self.assertEqual(cfer["degree"], 3)
        edge_types = {
            (edge["source"], edge["target"]): edge["types"]
            for edge in expanded["edges"]
        }
        self.assertEqual(edge_types[("bills/aca7", "organizations/cfer-foundation")], ["oppose"])
        self.assertEqual(edge_types[("organizations/cfer-foundation", "people/frank-xu")], ["president"])

    def test_parse_frontmatter_supports_scalar_and_list_values(self):
        markdown = "---\ntype: product\ntitle: JTuner\ntags:\n  - gc-tuning\n  - jtuner\n---\n# JTuner\n\nBody text"
        meta, body = parse_frontmatter(markdown)
        self.assertEqual(meta["type"], "product")
        self.assertEqual(meta["title"], "JTuner")
        self.assertEqual(meta["tags"], ["gc-tuning", "jtuner"])
        self.assertIn("Body text", body)

    def test_summary_extraction_prefers_article_content_over_metadata(self):
        body = """# Blog Post

## Metadata

- Author: Example
- Published: 2026-07-01

## Content

This is the actual article body that should appear in the selection summary.

## Comments

- Nice post.
"""
        summary = extract_summary_from_markdown_body(body, "Blog Post", "blog_post")

        self.assertIn("actual article body", summary)
        self.assertNotIn("Metadata", summary)
        self.assertNotIn("Author:", summary)

    def test_summary_extraction_prefers_profile_sections_for_people(self):
        body = """# Example Person

## Metadata

- Source: import

## Profile

An engineering leader focused on developer tools and knowledge systems.
"""
        summary = extract_summary_from_markdown_body(body, "Example Person", "person")

        self.assertEqual(summary, "An engineering leader focused on developer tools and knowledge systems.")

    def test_parse_media_references_reads_markdown_and_html_media(self):
        markdown = """# Media

![Cover](https://example.com/cover.jpg)
[Demo video](https://example.com/demo.mp4)
<audio src="https://example.com/audio.mp3"></audio>
[Not media](https://example.com/page)
"""
        media = parse_media_references(markdown)

        self.assertEqual([item["kind"] for item in media], ["image", "video", "audio"])
        self.assertEqual(media[0]["label"], "Cover")
        self.assertTrue(all(item["embeddable"] for item in media))

    def test_parse_media_references_reads_markdown_image_path_with_spaces(self):
        markdown = "![Profile](people/example-person/Profile Photo.jpeg)"

        media = parse_media_references(markdown)

        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]["kind"], "image")
        self.assertEqual(media[0]["url"], "people/example-person/Profile Photo.jpeg")
        self.assertEqual(media[0]["served_url"], "/media/people/example-person/Profile%20Photo.jpeg")

    def test_parse_media_references_supports_gbrain_files_scheme(self):
        markdown = "![MSN](gbrain:files/blogs/tony-guan/msn/post/photo.jpg)"

        media = parse_media_references(markdown)

        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]["kind"], "image")
        self.assertEqual(media[0]["url"], "gbrain:files/blogs/tony-guan/msn/post/photo.jpg")
        self.assertEqual(media[0]["served_url"], "/media/blogs/tony-guan/msn/post/photo.jpg")

    def test_parse_media_references_reads_frontmatter_profile_image(self):
        with TemporaryDirectory() as tmpdir:
            markdown = """---
type: reporter
title: Witty Wang
date: '2026-06-28T00:00:00.000Z'
source: user-provided
profile_image: people/witty-wang/witty-wang-profile.jpg
profile_image_uploaded_at: '2026-06-29'
---


"""
            with mock.patch("server.MEDIA_ROOTS", [Path(tmpdir) / "empty-media-root"]):
                media = parse_media_references(markdown)

            self.assertEqual(len(media), 1)
            self.assertEqual(media[0]["kind"], "image")
            self.assertEqual(media[0]["url"], "people/witty-wang/witty-wang-profile.jpg")
            self.assertEqual(media[0]["label"], "profile image")
            self.assertEqual(media[0]["source"], "frontmatter:profile_image")
            self.assertFalse(media[0]["embeddable"])
            self.assertEqual(media[0]["served_url"], "/media/people/witty-wang/witty-wang-profile.jpg")
            self.assertFalse(media[0]["served_available"])

    def test_media_reference_served_url_uses_readonly_media_route(self):
        self.assertEqual(
            serve_url_for_media_reference("people/witty-wang/witty-wang-profile.jpg"),
            "/media/people/witty-wang/witty-wang-profile.jpg",
        )
        self.assertEqual(
            serve_url_for_media_reference("people/example-person/Profile Photo.jpeg"),
            "/media/people/example-person/Profile%20Photo.jpeg",
        )
        self.assertEqual(
            serve_url_for_media_reference("/media/people/example-person/Profile Photo.jpeg"),
            "/media/people/example-person/Profile%20Photo.jpeg",
        )
        self.assertIsNone(serve_url_for_media_reference("https://example.com/image.jpg"))
        self.assertIsNone(serve_url_for_media_reference("../secret.jpg"))
        self.assertIsNone(serve_url_for_media_reference("notes/private.txt"))

    def test_resolve_media_file_path_blocks_traversal_and_non_media(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            media_file = root / "people" / "witty-wang" / "witty-wang-profile.jpg"
            media_file.parent.mkdir(parents=True)
            media_file.write_bytes(b"fake jpg")
            text_file = root / "people" / "witty-wang" / "notes.txt"
            text_file.write_text("private", encoding="utf-8")

            with mock.patch("server.MEDIA_ROOTS", [root]):
                self.assertEqual(
                    resolve_media_file_path("/media/people/witty-wang/witty-wang-profile.jpg"),
                    media_file.resolve(),
                )
                self.assertIsNone(resolve_media_file_path("/media/people/witty-wang/notes.txt"))
                self.assertIsNone(resolve_media_file_path("/media/../secret.jpg"))

    def test_materialize_local_media_uses_existing_frontmatter_reference(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "media-root"
            source = Path(tmpdir) / "witty-wang-profile.jpg"
            source.write_bytes(b"fake jpg")
            markdown = """---
title: Witty Wang
profile_image: people/witty-wang/witty-wang-profile.jpg
---
"""

            with mock.patch("server.MEDIA_ROOTS", [root]):
                result = materialize_local_media_for_slug("people/witty-wang", source, markdown)

                self.assertEqual(result["served_url"], "/media/people/witty-wang/witty-wang-profile.jpg")
                self.assertTrue(result["served_available"])
                self.assertEqual((root / "people/witty-wang/witty-wang-profile.jpg").read_bytes(), b"fake jpg")

    def test_materialize_local_media_does_not_overwrite_different_existing_media_reference(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "media-root"
            source = Path(tmpdir) / "IMG_1234.jpg"
            source.write_bytes(b"fake jpg")
            markdown = """---
title: Witty Wang
profile_image: people/witty-wang/witty-wang-profile.jpg
---
"""

            with mock.patch("server.MEDIA_ROOTS", [root]):
                result = materialize_local_media_for_slug("people/witty-wang", source, markdown)

                self.assertEqual(result["served_url"], "/media/people/witty-wang/IMG_1234.jpg")
                self.assertEqual((root / "people/witty-wang/IMG_1234.jpg").read_bytes(), b"fake jpg")
                self.assertFalse((root / "people/witty-wang/witty-wang-profile.jpg").exists())

    def test_append_attachment_reference_adds_image_to_markdown(self):
        updated = append_attachment_reference("# Azul Systems\n\nCompany notes.", "companies/azul-systems/Azul.jpg")

        self.assertIn("## Attachments", updated)
        self.assertIn("![Azul](companies/azul-systems/Azul.jpg)", updated)
        self.assertEqual(updated, append_attachment_reference(updated, "companies/azul-systems/Azul.jpg"))

    def test_ensure_media_references_copies_from_discovery_roots(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "served"
            discovery_root = Path(tmpdir) / "uploads"
            source = discovery_root / "people/witty-wang/witty-wang-profile.jpg"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"fake jpg")
            with mock.patch("server.MEDIA_ROOTS", [media_root]), mock.patch("server.MEDIA_DISCOVERY_ROOTS", [discovery_root]):
                media = parse_media_references("""---
profile_image: people/witty-wang/witty-wang-profile.jpg
---
""")
                enriched = ensure_media_references_available(media)

                self.assertTrue(enriched[0]["served_available"])
                self.assertEqual(enriched[0]["materialized_from"], str(source.resolve()))
                self.assertEqual((media_root / "people/witty-wang/witty-wang-profile.jpg").read_bytes(), b"fake jpg")

    def test_remote_media_url_for_relative_path_encodes_path_segments(self):
        self.assertEqual(
            remote_media_url_for_relative_path("https://example.test/media", "companies/azul systems/Azul Logo.jpg"),
            "https://example.test/media/companies/azul%20systems/Azul%20Logo.jpg",
        )
        self.assertIsNone(remote_media_url_for_relative_path("file:///tmp/media", "companies/example/logo.jpg"))
        self.assertIsNone(remote_media_url_for_relative_path("https://example.test/media", "../secret.jpg"))

    def test_gbrain_file_url_for_relative_path_encodes_path_segments(self):
        self.assertEqual(
            gbrain_file_url_for_relative_path("https://gbrain-host.example/gbrain-files", "blogs/example post/photo 1.jpg"),
            "https://gbrain-host.example/gbrain-files/blogs/example%20post/photo%201.jpg",
        )
        self.assertIsNone(gbrain_file_url_for_relative_path("file:///tmp/gbrain-files", "blogs/example/photo.jpg"))
        self.assertIsNone(gbrain_file_url_for_relative_path("https://gbrain-host.example/gbrain-files", "../secret.jpg"))

    def test_ensure_media_references_fetches_from_remote_media_base(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "served"
            media = parse_media_references("""---
cover_image: companies/example-inc/logo.jpg
---
""")

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, _exc_type, _exc, _traceback):
                    return False

                def read(self):
                    return b"remote jpg"

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.MEDIA_DISCOVERY_ROOTS", []),
                mock.patch("server.REMOTE_MEDIA_BASE_URLS", ["https://gbrain-host.example/media/"]),
                mock.patch("server.urlopen", return_value=FakeResponse()) as urlopen_mock,
            ):
                enriched = ensure_media_references_available(media)

            self.assertTrue(enriched[0]["served_available"])
            self.assertEqual(enriched[0]["materialized_from"], "https://gbrain-host.example/media/companies/example-inc/logo.jpg")
            self.assertEqual((media_root / "companies/example-inc/logo.jpg").read_bytes(), b"remote jpg")
            urlopen_mock.assert_called_once()

    def test_ensure_media_references_fetches_gbrain_files_from_file_base(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "served"
            media = parse_media_references("![MSN](gbrain:files/blogs/example-post/photo 1.jpg)")

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, _exc_type, _exc, _traceback):
                    return False

                def read(self):
                    return b"gbrain jpg"

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.MEDIA_DISCOVERY_ROOTS", []),
                mock.patch("server.GBRAIN_FILE_BASE_URLS", ["https://gbrain-host.example/gbrain-files/"]),
                mock.patch("server.REMOTE_MEDIA_BASE_URLS", []),
                mock.patch("server.urlopen", return_value=FakeResponse()) as urlopen_mock,
            ):
                enriched = ensure_media_references_available(media)

            self.assertTrue(enriched[0]["served_available"])
            self.assertEqual(enriched[0]["materialized_from"], "https://gbrain-host.example/gbrain-files/blogs/example-post/photo%201.jpg")
            self.assertEqual((media_root / "blogs/example-post/photo 1.jpg").read_bytes(), b"gbrain jpg")
            urlopen_mock.assert_called_once()

    def test_ensure_media_references_fetches_relative_paths_from_gbrain_file_base(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "served"

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, _exc_type, _exc, _traceback):
                    return False

                def read(self):
                    return b"stargraph png"

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.MEDIA_DISCOVERY_ROOTS", []),
                mock.patch("server.GBRAIN_FILE_BASE_URLS", ["https://gbrain-host.example/gbrain-files/"]),
                mock.patch("server.REMOTE_MEDIA_BASE_URLS", []),
                mock.patch("server.urlopen", return_value=FakeResponse()) as urlopen_mock,
            ):
                media = parse_media_references("![UI](products/memory-stargraph/stargraph.png)")
                enriched = ensure_media_references_available(media)

            self.assertTrue(enriched[0]["served_available"])
            self.assertEqual(enriched[0]["materialized_from"], "https://gbrain-host.example/gbrain-files/products/memory-stargraph/stargraph.png")
            self.assertEqual((media_root / "products/memory-stargraph/stargraph.png").read_bytes(), b"stargraph png")
            urlopen_mock.assert_called_once()

    def test_materialize_gbrain_file_reference_reads_gbrain_store_root(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "served"
            store_root = Path(tmpdir) / "brain"
            source = store_root / "blogs/example-post/photo.jpg"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"stored jpg")

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.GBRAIN_FILE_STORE_ROOTS", [store_root]),
            ):
                result = materialize_gbrain_file_reference("blogs/example-post/photo.jpg")

            self.assertTrue(result["served_available"])
            self.assertEqual(result["source"], str(source.resolve()))
            self.assertEqual((media_root / "blogs/example-post/photo.jpg").read_bytes(), b"stored jpg")

    def test_materialize_gbrain_file_reference_fetches_from_gbrain_file_base(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "served"

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, _exc_type, _exc, _traceback):
                    return False

                def read(self):
                    return b"stored from file base"

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.MEDIA_DISCOVERY_ROOTS", []),
                mock.patch("server.GBRAIN_FILE_STORE_ROOTS", []),
                mock.patch("server.REMOTE_MEDIA_BASE_URLS", []),
                mock.patch("server.GBRAIN_FILE_BASE_URLS", ["https://gbrain-host.example/gbrain-files/"]),
                mock.patch("server.urlopen", return_value=FakeResponse()) as urlopen_mock,
            ):
                result = materialize_gbrain_file_reference("products/memory-stargraph/stargraph.png")

            self.assertTrue(result["served_available"])
            self.assertEqual(result["source"], "https://gbrain-host.example/gbrain-files/products/memory-stargraph/stargraph.png")
            self.assertEqual((media_root / "products/memory-stargraph/stargraph.png").read_bytes(), b"stored from file base")
            urlopen_mock.assert_called_once()

    def test_copy_file_to_gbrain_store_writes_storage_path(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "upload.jpg"
            source.write_bytes(b"uploaded jpg")
            store_root = Path(tmpdir) / "brain"

            with mock.patch("server.GBRAIN_FILE_STORE_ROOTS", [store_root]):
                destination = copy_file_to_gbrain_store(source, "people/example/upload.jpg")

            self.assertEqual(destination, store_root / "people/example/upload.jpg")
            self.assertEqual(destination.read_bytes(), b"uploaded jpg")

    def test_parse_multipart_form_reads_browser_file_upload(self):
        boundary = "----memory-stargraph-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="witty wang.jpg"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode("utf-8") + b"fake jpg" + f"\r\n--{boundary}--\r\n".encode("utf-8")

        fields, files = parse_multipart_form(f"multipart/form-data; boundary={boundary}", body)

        self.assertEqual(fields, {})
        self.assertEqual(files["file"]["filename"], "witty-wang.jpg")
        self.assertEqual(files["file"]["content_type"], "image/jpeg")
        self.assertEqual(files["file"]["data"], b"fake jpg")

    def test_safe_upload_filename_canonicalizes_all_whitespace_and_preserves_unicode(self):
        self.assertEqual(
            safe_upload_filename("Screenshot 2026-07-15 at 11.26.53\u202fAM.png"),
            "Screenshot-2026-07-15-at-11.26.53-AM.png",
        )
        self.assertEqual(safe_upload_filename("普通 文件_name-1.png"), "普通-文件_name-1.png")
        self.assertEqual(safe_upload_filename("simple_ASCII-file.png"), "simple_ASCII-file.png")

    def test_parse_gbrain_durable_evidence_requires_exact_hash_size_and_path(self):
        source = b"exact attachment bytes"
        digest = __import__("hashlib").sha256(source).hexdigest()
        output = (
            'Uploaded: people/example/photo.png\n'
            'GBRAIN_FILE_EVIDENCE '
            f'{{"durable_storage_verified":true,"storage_path":"people/example/photo.png",'
            f'"filename":"photo.png","size_bytes":{len(source)},"sha256":"{digest}",'
            '"disposition":"uploaded"}\n'
        )

        evidence = parse_gbrain_durable_evidence(output, "people/example/photo.png", source)

        self.assertTrue(evidence["durable_storage_verified"])
        self.assertEqual(evidence["sha256"], digest)
        with self.assertRaisesRegex(RuntimeError, "durable storage evidence"):
            parse_gbrain_durable_evidence(output, "people/example/other.png", source)

    def test_run_gbrain_tolerates_non_utf8_output(self):
        completed = mock.Mock(returncode=0, stdout=b"uploaded \xff image", stderr=b"")
        with mock.patch("server.GBRAIN") as gbrain, mock.patch("server.subprocess.run", return_value=completed):
            gbrain.exists.return_value = True
            gbrain.__str__ = lambda _self: "/usr/local/bin/gbrain"

            output = run_gbrain("files", "upload", "/tmp/photo.jpg", "--page", "people/witty-wang")

        self.assertIn("uploaded", output)
        self.assertIn("\ufffd", output)

    def test_graph_store_attach_file_updates_markdown_reference(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "media"
            source = Path(tmpdir) / "Azul.jpg"
            source.write_bytes(b"fake jpg")
            store = GraphStore()

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.run_gbrain") as run,
                mock.patch.object(store, "invalidate") as invalidate,
            ):
                digest = __import__("hashlib").sha256(b"fake jpg").hexdigest()
                run.side_effect = [
                    "# Azul Systems\n\nCompany notes.",
                    f'GBRAIN_FILE_EVIDENCE {{"durable_storage_verified":true,"storage_path":"companies/azul-systems/Azul.jpg","filename":"Azul.jpg","size_bytes":8,"sha256":"{digest}","disposition":"uploaded"}}',
                    "1 file(s):\n  companies/azul-systems / Azul.jpg  [8KB, image/jpeg]",
                    "# Azul Systems\n\nCompany notes.",
                    "",
                ]
                result = store.attach_file("companies/azul-systems", str(source), "Azul company logo")

            self.assertEqual(result["served_url"], "/media/companies/azul-systems/Azul.jpg")
            self.assertTrue(result["markdown_updated"])
            run.assert_any_call("files", "list", "companies/azul-systems")
            run.assert_any_call("put", "companies/azul-systems", input_text=mock.ANY)
            put_content = next(call.kwargs["input_text"] for call in run.mock_calls if call.args[:2] == ("put", "companies/azul-systems"))
            self.assertIn("![Azul company logo](companies/azul-systems/Azul.jpg)", put_content)
            invalidate.assert_called_once()

    def test_graph_store_attach_file_reloads_latest_page_before_markdown_write(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "media"
            source = Path(tmpdir) / "tammy.jpg"
            source.write_bytes(b"fake jpg")
            store = GraphStore()
            initial = "\n".join(
                [
                    "---",
                    "type: concept",
                    "title: Agent Tammy",
                    "---",
                    "",
                    "# Agent Tammy",
                    "",
                    "Old profile.",
                ]
            )
            latest = initial.replace("type: concept", "type: agent").replace(
                "Old profile.", "Canonical agent profile."
            )

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.run_gbrain") as run,
                mock.patch.object(store, "invalidate"),
            ):
                digest = __import__("hashlib").sha256(b"fake jpg").hexdigest()
                run.side_effect = [
                    initial,
                    (
                        f'GBRAIN_FILE_EVIDENCE {{"durable_storage_verified":true,'
                        f'"storage_path":"agents/tammy/tammy.jpg","filename":"tammy.jpg",'
                        f'"size_bytes":8,"sha256":"{digest}","disposition":"uploaded"}}\n'
                        "1 file(s):\n  agents/tammy / tammy.jpg  [8B, image/jpeg]"
                    ),
                    latest,
                    "",
                ]

                store.attach_file("agents/tammy", str(source), "GTasks agent avatar")

            put_content = next(
                call.kwargs["input_text"]
                for call in run.mock_calls
                if call.args[:2] == ("put", "agents/tammy")
            )
            self.assertIn("type: agent", put_content)
            self.assertIn("Canonical agent profile.", put_content)
            self.assertNotIn("Old profile.", put_content)
            self.assertIn(
                "![GTasks agent avatar](agents/tammy/tammy.jpg)",
                put_content,
            )

    def test_graph_store_attach_file_preserves_custom_type_from_upload_side_effect(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "media"
            source = Path(tmpdir) / "toddy.jpg"
            source.write_bytes(b"fake jpg")
            store = GraphStore()
            initial = "\n".join(
                [
                    "---",
                    "type: agent",
                    "title: Agent Toddy",
                    "---",
                    "",
                    "# Agent Toddy",
                    "",
                    "Canonical agent profile.",
                ]
            )
            post_upload = initial.replace("type: agent", "type: concept")

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.run_gbrain") as run,
                mock.patch.object(store, "invalidate"),
            ):
                digest = __import__("hashlib").sha256(b"fake jpg").hexdigest()
                run.side_effect = [
                    initial,
                    (
                        f'GBRAIN_FILE_EVIDENCE {{"durable_storage_verified":true,'
                        f'"storage_path":"agents/toddy/toddy.jpg","filename":"toddy.jpg",'
                        f'"size_bytes":8,"sha256":"{digest}","disposition":"uploaded"}}\n'
                        "1 file(s):\n  agents/toddy / toddy.jpg  [8B, image/jpeg]"
                    ),
                    post_upload,
                    "",
                ]

                store.attach_file("agents/toddy", str(source), "GTasks agent avatar")

            put_content = next(
                call.kwargs["input_text"]
                for call in run.mock_calls
                if call.args[:2] == ("put", "agents/toddy")
            )
            self.assertIn("type: agent", put_content)
            self.assertNotIn("type: concept", put_content)

    def test_graph_store_attach_file_refuses_markdown_when_upload_fails(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "media"
            source = Path(tmpdir) / "Garry.jpg"
            source.write_bytes(b"fake jpg")
            store = GraphStore()

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.run_gbrain") as run,
                mock.patch.object(store, "invalidate") as invalidate,
            ):
                run.side_effect = ["# Garry Tan\n\nNotes.", RuntimeError("no storage backend")]
                with self.assertRaisesRegex(RuntimeError, "markdown was not updated"):
                    store.attach_file("people/garry-tan", str(source), "Garry")

            put_calls = [call for call in run.mock_calls if call.args[:1] == ("put",)]
            self.assertEqual(put_calls, [])
            invalidate.assert_not_called()

    def test_graph_store_attach_file_uses_remote_bridge_after_local_upload_failure(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "media"
            source = Path(tmpdir) / "Bridge.jpg"
            source.write_bytes(b"bridge jpg")
            store = GraphStore()

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.GBRAIN_FILES_BRIDGE_SSH", "toddy@example"),
                mock.patch("server.run_gbrain") as run,
                mock.patch("server.run_gbrain_files_bridge") as bridge,
                mock.patch.object(store, "invalidate") as invalidate,
            ):
                run.side_effect = [
                    "# Bridge\n\nNotes.",
                    RuntimeError("localOnly thin-client has no storage"),
                    "# Bridge\n\nNotes.",
                    "",
                ]
                digest = __import__("hashlib").sha256(b"bridge jpg").hexdigest()
                bridge.return_value = (
                    f'GBRAIN_FILE_EVIDENCE {{"durable_storage_verified":true,"storage_path":"people/bridge/Bridge.jpg","filename":"Bridge.jpg","size_bytes":10,"sha256":"{digest}","disposition":"uploaded"}}\n'
                    "1 file(s):\n  people/bridge / Bridge.jpg  [10B, image/jpeg]"
                )
                result = store.attach_file("people/bridge", str(source), "Bridge image")

            bridge.assert_called_once_with(str(source), "people/bridge")
            self.assertTrue(result["markdown_updated"])
            self.assertEqual(result["upload_transport"], "ssh-bridge")
            run.assert_any_call("put", "people/bridge", input_text=mock.ANY)
            invalidate.assert_called_once()

    def test_graph_store_attach_file_refuses_markdown_when_ledger_misses_upload(self):
        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "media"
            source = Path(tmpdir) / "Garry.jpg"
            source.write_bytes(b"fake jpg")
            store = GraphStore()

            with (
                mock.patch("server.MEDIA_ROOTS", [media_root]),
                mock.patch("server.run_gbrain") as run,
                mock.patch.object(store, "invalidate") as invalidate,
            ):
                digest = __import__("hashlib").sha256(b"fake jpg").hexdigest()
                run.side_effect = [
                    "# Garry Tan\n\nNotes.",
                    f'GBRAIN_FILE_EVIDENCE {{"durable_storage_verified":true,"storage_path":"people/garry-tan/Garry.jpg","filename":"Garry.jpg","size_bytes":8,"sha256":"{digest}","disposition":"uploaded"}}',
                    "No files for page: people/garry-tan",
                ]
                with self.assertRaisesRegex(RuntimeError, "not visible in GBrain files"):
                    store.attach_file("people/garry-tan", str(source), "Garry")

            put_calls = [call for call in run.mock_calls if call.args[:1] == ("put",)]
            self.assertEqual(put_calls, [])
            invalidate.assert_not_called()

    def test_gbrain_file_ledger_has_relative_path_checks_page_and_filename(self):
        output = "1 file(s):\n  people/garry-tan / Garry.jpg  [25KB, image/jpeg]\n"
        with mock.patch("server.run_gbrain", return_value=output):
            self.assertTrue(gbrain_file_ledger_has_relative_path("people/garry-tan", "people/garry-tan/Garry.jpg"))
            self.assertFalse(gbrain_file_ledger_has_relative_path("people/tony-guan", "people/garry-tan/Garry.jpg"))
            self.assertFalse(gbrain_file_ledger_has_relative_path("people/garry-tan", "people/garry-tan/not-Garry.jpg"))

    def test_gbrain_file_ledger_rejects_prefixed_remote_temp_filename(self):
        output = "1 file(s):\n  people/bridge / memory-stargraph-upload-123-Bridge.jpg  [10B, image/jpeg]\n"
        self.assertFalse(
            gbrain_file_ledger_has_relative_path(
                "people/bridge",
                "people/bridge/Bridge.jpg",
                ledger_output=output,
            )
        )

    def test_part_identity_collapses_slug_and_label(self):
        slug, label, collapsed = collapse_part_identity(
            "products/jtuner/rfc/part-09",
            "The RFC - JTuner - Part 09",
        )
        self.assertTrue(collapsed)
        self.assertEqual(slug, "products/jtuner/rfc")
        self.assertEqual(label, "The RFC - JTuner")

    def test_finalize_graph_collapses_part_nodes_before_degree_math(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "nodes": [
                {
                    "slug": "products/jtuner/rfc/part-01",
                    "label": "The RFC - JTuner - Part 01",
                    "type": "document",
                    "links": ["products/jtuner", "people/tony"],
                },
                {
                    "slug": "products/jtuner/rfc/part-02",
                    "label": "The RFC - JTuner - Part 02",
                    "type": "document",
                    "links": ["products/jtuner"],
                },
                {
                    "slug": "products/jtuner",
                    "label": "JTuner",
                    "type": "product",
                    "links": ["people/tony"],
                },
                {
                    "slug": "people/tony",
                    "label": "Tony",
                    "type": "person",
                    "links": [],
                },
            ],
        }
        graph = finalize_graph(raw_graph)
        slugs = {node["slug"] for node in graph["nodes"]}
        collapsed = next(node for node in graph["nodes"] if node["slug"] == "products/jtuner/rfc")

        self.assertNotIn("products/jtuner/rfc/part-01", slugs)
        self.assertNotIn("products/jtuner/rfc/part-02", slugs)
        self.assertEqual(collapsed["label"], "The RFC - JTuner")
        self.assertEqual(collapsed["parts_count"], 2)
        self.assertIn("The RFC - JTuner - Part 01", collapsed["collapsed_aliases"])
        self.assertEqual(collapsed["degree"], 2)
        self.assertEqual(graph["stats"]["collapsed_parts"], 2)

    def test_finalize_graph_uses_human_friendly_path_labels(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "nodes": [
                {"slug": "companies/uber", "label": "Companies/uber", "type": "company", "links": []},
                {"slug": "organizations/stopprop16", "label": "Organizations/stopprop16", "type": "organization", "links": []},
                {"slug": "categories/people", "label": "Categories/people", "type": "category", "links": []},
                {"slug": "people/melonplanter-uhx51x2s12", "label": "Melonplanter Uhx51x2s12", "type": "person", "links": []},
                {"slug": "wechat-groups/voter-id-26239915567", "label": "Voter Id 26239915567", "type": "wechat-group", "links": []},
                {"slug": "wechat-group-members/melonplanter-uhx51x2s12", "label": "Melonplanter Uhx51x2s12", "type": "person", "links": []},
                {"slug": "people/wechat-group-members/wechat-member-42lwbvt012", "label": "李伟平", "type": "person", "links": []},
                {"slug": "groups/wechat/svca-vip-27108422220", "label": "SVCA VIP 聊天室 27108422220", "type": "group", "links": []},
                {"slug": "notes/very-long-title", "label": "X" * 120, "type": "note", "links": []},
            ],
        }
        graph = finalize_graph(raw_graph)
        labels = {node["slug"]: node["label"] for node in graph["nodes"]}

        self.assertEqual(labels["companies/uber"], "Uber")
        self.assertEqual(labels["organizations/stopprop16"], "Stopprop16")
        self.assertEqual(labels["categories/people"], "People")
        self.assertEqual(labels["people/melonplanter-uhx51x2s12"], "Melonplanter")
        self.assertEqual(labels["wechat-groups/voter-id-26239915567"], "Voter Id")
        self.assertEqual(labels["wechat-group-members/melonplanter-uhx51x2s12"], "Melonplanter")
        self.assertEqual(labels["people/wechat-group-members/wechat-member-42lwbvt012"], "李伟平")
        self.assertEqual(labels["groups/wechat/svca-vip-27108422220"], "SVCA VIP 聊天室")
        self.assertEqual(labels["notes/very-long-title"], "XXXXXXXXXXXXXXXXX...")
        self.assertTrue(all(len(label) <= 20 for label in labels.values()))

    def test_finalize_graph_blocks_unwanted_tony_gu_entity(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "nodes": [
                {
                    "slug": "people/tony-gu",
                    "label": "People/Tony Gu",
                    "type": "person",
                    "links": ["index", "people/tony-guan"],
                },
                {
                    "slug": "index",
                    "label": "Brain Index",
                    "type": "note",
                    "links": ["people/tony-gu", "people/tony-guan"],
                },
                {
                    "slug": "people/tony-guan",
                    "label": "Tony Guan",
                    "type": "person",
                    "links": ["people/tony-gu"],
                },
            ],
        }
        graph = finalize_graph(raw_graph)
        slugs = {node["slug"] for node in graph["nodes"]}

        self.assertNotIn("people/tony-gu", slugs)
        self.assertFalse(any("people/tony-gu" in node["links"] for node in graph["nodes"]))
        self.assertFalse(any(edge["source"] == "people/tony-gu" or edge["target"] == "people/tony-gu" for edge in graph["edges"]))

    def test_finalize_graph_blocks_unwanted_darsha_entity_without_local_state(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "nodes": [
                {
                    "slug": "people/darsha-krana",
                    "label": "People/darsha Krana",
                    "type": "person",
                    "links": ["index"],
                },
                {
                    "slug": "index",
                    "label": "Brain Index",
                    "type": "note",
                    "links": ["people/darsha-krana"],
                },
            ],
        }
        graph = finalize_graph(raw_graph)
        slugs = {node["slug"] for node in graph["nodes"]}

        self.assertNotIn("people/darsha-krana", slugs)
        self.assertFalse(any("people/darsha-krana" in node["links"] for node in graph["nodes"]))
        self.assertFalse(any(edge["source"] == "people/darsha-krana" or edge["target"] == "people/darsha-krana" for edge in graph["edges"]))

    def test_finalize_graph_filters_deleted_entities_and_backlinks(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "nodes": [
                {
                    "slug": "people/darsha-krana",
                    "label": "People/darsha Krana",
                    "type": "person",
                    "links": ["index"],
                },
                {
                    "slug": "index",
                    "label": "Brain Index",
                    "type": "note",
                    "links": ["people/darsha-krana", "products/jtuner"],
                },
                {
                    "slug": "products/jtuner",
                    "label": "JTuner",
                    "type": "product",
                    "links": [],
                },
            ],
        }
        with mock.patch("server.read_deleted_slugs", return_value={"people/darsha-krana"}):
            graph = finalize_graph(raw_graph)
        slugs = {node["slug"] for node in graph["nodes"]}

        self.assertNotIn("people/darsha-krana", slugs)
        self.assertFalse(any("people/darsha-krana" in node["links"] for node in graph["nodes"]))
        self.assertFalse(any(edge["source"] == "people/darsha-krana" or edge["target"] == "people/darsha-krana" for edge in graph["edges"]))

    def test_finalize_graph_collapses_daily_gbrain_usage_reports(self):
        raw_graph = {
            "title": "Memory Stargraph",
            "nodes": [
                {
                    "slug": "agent/reports/gbrain-usage-2026-04-16",
                    "label": "Agent/reports/gbrain Usage 2026 04 16",
                    "type": "note",
                    "links": ["index"],
                },
                {
                    "slug": "agent/reports/gbrain-usage-2026-04-17",
                    "label": "Agent/reports/gbrain Usage 2026 04 17",
                    "type": "note",
                    "links": ["index", "projects/openclaw-gbrain-integration"],
                },
                {
                    "slug": "index",
                    "label": "Brain Index",
                    "type": "note",
                    "links": [],
                },
                {
                    "slug": "projects/openclaw-gbrain-integration",
                    "label": "OpenClaw gbrain Integration",
                    "type": "project",
                    "links": [],
                },
            ],
        }
        graph = finalize_graph(raw_graph)
        collapsed = next(node for node in graph["nodes"] if node["slug"] == "agent/reports/gbrain-usage")
        slugs = {node["slug"] for node in graph["nodes"]}

        self.assertNotIn("agent/reports/gbrain-usage-2026-04-16", slugs)
        self.assertEqual(collapsed["label"], "Gbrain Usage")
        self.assertLessEqual(len(collapsed["label"]), 20)
        self.assertEqual(collapsed["report_count"], 2)
        self.assertEqual(collapsed["degree"], 2)
        self.assertEqual(graph["stats"]["collapsed_reports"], 2)

    def test_graph_store_node_operations_call_gbrain_commands(self):
        store = GraphStore()
        tmpdir = TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        media_root = Path(tmpdir.name) / "media"
        source = Path(tmpdir.name) / "example.jpg"
        source.write_bytes(b"fake jpg")

        def fake_run(*args, **_kwargs):
            if args[:2] == ("files", "list"):
                return "1 file(s):\n  people/tony-guan / example.jpg  [8KB, image/jpeg]"
            if args[:2] == ("files", "upload"):
                digest = __import__("hashlib").sha256(b"fake jpg").hexdigest()
                return f'GBRAIN_FILE_EVIDENCE {{"durable_storage_verified":true,"storage_path":"people/tony-guan/example.jpg","filename":"example.jpg","size_bytes":8,"sha256":"{digest}","disposition":"uploaded"}}'
            return "ok"

        with (
            mock.patch("server.run_gbrain") as run,
            mock.patch("server.run_openclaw_agent", return_value="agent answer"),
            mock.patch("server.MEDIA_ROOTS", [media_root]),
            mock.patch.object(store, "invalidate") as invalidate,
        ):
            run.side_effect = fake_run
            store.add_relationship("people/tony-guan", "companies/azul-systems", "employed by", "past role")
            store.remove_relationship("people/tony-guan", "companies/azul-systems", "employed by")
            store.update_tags("people/tony-guan", ["founder", "java"], ["old"])
            store.add_timeline_event("people/tony-guan", "2026-06-29", "Updated graph operations", "Details", "memory-stargraph")
            store.ask_gbrain("people/tony-guan", "What should I know?")
            store.ask_yoda("people/tony-guan", "What should I know?", [{"role": "user", "content": "Earlier"}])
            store.backlinks("people/tony-guan")
            store.graph_query("people/tony-guan", "employed by", "both", "2")
            store.attach_file("people/tony-guan", str(source))
            store.history("people/tony-guan")
            store.refresh_embedding("people/tony-guan")

        run.assert_has_calls(
            [
                mock.call("link", "people/tony-guan", "companies/azul-systems", "--link-type", "employed by", "--context", "past role"),
                mock.call("unlink", "people/tony-guan", "companies/azul-systems", "--link-type", "employed by"),
                mock.call("tag", "people/tony-guan", "founder"),
                mock.call("tag", "people/tony-guan", "java"),
                mock.call("untag", "people/tony-guan", "old"),
                mock.call("timeline-add", "people/tony-guan", "2026-06-29", "Updated graph operations", "--detail", "Details", "--source", "memory-stargraph"),
                mock.call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "1", timeout=30),
                mock.call("query", "What should I know? people/tony-guan", "--adaptive-return", "true", "--limit", "8", "--relational", "true"),
                mock.call("get", "people/tony-guan"),
                mock.call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "2", timeout=8),
                mock.call("backlinks", "people/tony-guan"),
                mock.call("query", "What should I know? people/tony-guan", "--no-expand", "--adaptive-return", "true", "--limit", "10", "--relational", "true"),
                mock.call("backlinks", "people/tony-guan"),
                mock.call("graph-query", "people/tony-guan", "--type", "employed by", "--direction", "both", "--depth", "2"),
                mock.call("get", "people/tony-guan"),
                mock.call("files", "upload", str(source), "--page", "people/tony-guan"),
                mock.call("files", "list", "people/tony-guan"),
                mock.call("put", "people/tony-guan", input_text=mock.ANY),
                mock.call("history", "people/tony-guan"),
                mock.call("embed", "people/tony-guan"),
            ],
            any_order=True,
        )
        self.assertEqual(invalidate.call_count, 6)

    def test_ask_yoda_returns_fallback_when_openclaw_unavailable(self):
        store = GraphStore()
        with (
            mock.patch("server.yoda_runtime_config", return_value=self.openclaw_yoda_config()),
            mock.patch("server.run_gbrain") as run,
            mock.patch("server.run_openclaw_agent", return_value=None),
        ):
            run.side_effect = [
                "# Tony Guan\n\nEngineer",
                "direct graph",
                "backlink graph",
                "retrieved context",
                "fallback direct graph",
                "fallback retrieved context",
            ]
            result = store.ask_yoda("people/tony-guan", "What changed?", [{"role": "user", "content": "Earlier question"}])

        self.assertEqual(result["source"], "fallback")
        self.assertIn("Question: What changed?", result["output"])
        self.assertIn("Selected node: people/tony-guan", result["output"])
        self.assertIn("fallback_output", result)
        self.assertIn("Question-specific gbrain retrieval", result["fallback_output"])
        self.assertIn("fallback retrieved context", result["fallback_output"])
        self.assertIn("timings", result)
        self.assertNotIn("OpenClaw agent unavailable", result["output"])
        self.assertNotIn("retrieved context", result["output"])
        self.assertNotIn("prompt", result)

    def test_ask_yoda_prompt_caps_broad_graph_but_keeps_requested_retrieval_depth(self):
        store = GraphStore()
        search_output = "[0.92] notes/tai-chi/white-swan -- White Swan notes\n[0.73] people/tony-guan -- Tony"

        def gbrain_result(*args, **kwargs):
            del kwargs
            if args == ("get", "people/tony-guan"):
                return "# Tony Guan\n\nEngineer"
            if args[0] == "graph-query":
                return "expanded graph"
            if args[0] == "backlinks":
                return "backlinks"
            if args[0] == "query":
                return search_output
            if args == ("get", "notes/tai-chi/white-swan"):
                return "# White Swan\n\nTai Chi source note"
            raise AssertionError(args)

        with (
            mock.patch("server.yoda_runtime_config", return_value=self.openclaw_yoda_config()),
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
            mock.patch("server.run_openclaw_agent", return_value="agent answer"),
        ):
            result = store.ask_yoda("people/tony-guan", "What does White Swan connect to?", depth=5)

        self.assertEqual(result["source"], "openclaw-agent")
        self.assertEqual(result["output"], "agent answer")
        self.assertIn("timings", result)
        self.assertEqual(result["diagnostics"]["depth"], 5)
        self.assertEqual(result["diagnostics"]["context_counts"]["broad_graph_depth"], 2)
        run.assert_has_calls(
            [
                mock.call("get", "people/tony-guan"),
                mock.call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "2", timeout=8),
                mock.call("backlinks", "people/tony-guan"),
                mock.call("query", "What does White Swan connect to? people/tony-guan", "--no-expand", "--adaptive-return", "true", "--limit", "10", "--relational", "true"),
                mock.call("get", "notes/tai-chi/white-swan"),
            ],
            any_order=True,
        )

    def test_ask_yoda_uses_named_entity_backlinks_for_relationship_lookup(self):
        store = GraphStore()
        broad_search = "[1.19] platforms/tony-guan-x -- Tony Guan X Posts"
        entity_search = "[1.29] people/garry-tan -- Garry Tan"
        garry_backlinks = json.dumps(
            [
                {
                    "from_slug": "media/x-ecalifornians-status-2071774149987680569",
                    "to_slug": "people/garry-tan",
                    "link_type": "reposted_by",
                    "context": "",
                    "link_source": "manual",
                }
            ]
        )
        captured_prompt = {}

        def gbrain_result(*args, **kwargs):
            del kwargs
            if args == ("get", "people/tony-guan"):
                return "# Tony Guan"
            if args[0] == "graph-query":
                return "large broad graph"
            if args == ("backlinks", "people/tony-guan"):
                return "selected backlinks"
            if args[0] == "query":
                return broad_search
            if args == ("search", "Garry Tan", "--limit", "5"):
                return entity_search
            if args == ("get", "platforms/tony-guan-x"):
                return "# Tony Guan X Posts"
            if args == ("get", "people/garry-tan"):
                return "# Garry Tan"
            if args == ("backlinks", "people/garry-tan"):
                return garry_backlinks
            if args == ("get", "media/x-ecalifornians-status-2071774149987680569"):
                return "# Introducing Memory Stargraph\n\nTony's X post."
            raise AssertionError(args)

        def answer_from_prompt(prompt, return_details=False):
            captured_prompt["value"] = prompt
            result = {
                "output": "The Memory Stargraph post was reposted by Garry Tan.",
                "backend": "openclaw",
                "model_status": "answered",
                "openclaw_status": "ok",
            }
            return result if return_details else result["output"]

        with (
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
            mock.patch("server.run_yoda_model", side_effect=answer_from_prompt),
        ):
            result = store.ask_yoda(
                "people/tony-guan",
                "which of my X posts were reposted by Garry Tan?",
                depth=4,
            )

        self.assertEqual(result["source"], "openclaw")
        self.assertIn("Targeted entity relationship evidence", captured_prompt["value"])
        self.assertIn("people/garry-tan", captured_prompt["value"])
        self.assertIn("reposted_by", captured_prompt["value"])
        self.assertIn("media/x-ecalifornians-status-2071774149987680569", captured_prompt["value"])
        self.assertIn("Tony's X post", captured_prompt["value"])
        self.assertIn("possibly truncated", captured_prompt["value"])
        run.assert_has_calls(
            [
                mock.call("search", "Garry Tan", "--limit", "5"),
                mock.call("backlinks", "people/garry-tan"),
                mock.call("get", "media/x-ecalifornians-status-2071774149987680569"),
            ],
            any_order=True,
        )
        self.assertEqual(result["diagnostics"]["context_counts"]["targeted_entities"], 1)
        self.assertEqual(result["diagnostics"]["context_counts"]["relationship_source_reads"], 1)

    def test_ask_yoda_short_followup_reuses_prior_user_intent_and_constrains_broad_graph(self):
        store = GraphStore()
        history = [
            {"role": "user", "content": "which of my X posts were reposted by Garry Tan?"},
            {"role": "assistant", "content": "No Garry Tan node was found."},
            {"role": "user", "content": "try again"},
        ]
        captured_prompt = {}

        def gbrain_result(*args, **kwargs):
            del kwargs
            if args == ("get", "people/tony-guan"):
                return "# Tony Guan"
            if args == ("graph-query", "people/tony-guan", "--direction", "both", "--depth", "1"):
                return "constrained graph"
            if args == ("backlinks", "people/tony-guan"):
                return "selected backlinks"
            if args[0] == "query":
                self.assertIn("which of my X posts were reposted by Garry Tan?", args[1])
                return "[1.19] platforms/tony-guan-x -- Tony Guan X Posts"
            if args == ("get", "platforms/tony-guan-x"):
                return "# Tony Guan X Posts"
            if args == ("search", "Garry Tan", "--limit", "5"):
                return "[1.29] people/garry-tan -- Garry Tan"
            if args == ("get", "people/garry-tan"):
                return "# Garry Tan"
            if args == ("backlinks", "people/garry-tan"):
                return json.dumps(
                    [
                        {
                            "from_slug": "media/x-ecalifornians-status-2071774149987680569",
                            "to_slug": "people/garry-tan",
                            "link_type": "reposted_by",
                        }
                    ]
                )
            if args == ("get", "media/x-ecalifornians-status-2071774149987680569"):
                return "# Introducing Memory Stargraph"
            raise AssertionError(args)

        def answer_from_prompt(prompt, return_details=False):
            captured_prompt["value"] = prompt
            result = {
                "output": "The Memory Stargraph post was reposted by Garry Tan.",
                "backend": "openai",
                "model_status": "answered",
                "openclaw_status": "not_used",
            }
            return result if return_details else result["output"]

        with (
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
            mock.patch("server.run_yoda_model", side_effect=answer_from_prompt),
        ):
            result = store.ask_yoda("people/tony-guan", "try again", history, depth=4)

        self.assertIn("Resolved retrieval intent:", captured_prompt["value"])
        self.assertIn("which of my X posts were reposted by Garry Tan?", captured_prompt["value"])
        self.assertIn("Prior assistant answers are conversation context, not evidence", captured_prompt["value"])
        self.assertEqual(result["diagnostics"]["context_counts"]["broad_graph_depth"], 1)
        self.assertTrue(result["diagnostics"]["context_counts"]["retrieval_history_used"])
        self.assertEqual(result["diagnostics"]["context_counts"]["targeted_entities"], 1)
        self.assertEqual(result["diagnostics"]["context_counts"]["relationship_source_reads"], 1)
        run.assert_any_call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "1", timeout=8)

    def test_ask_yoda_current_todo_questions_include_authoritative_status_context(self):
        store = GraphStore()
        backlog = """# Memory Starmap Todo List

## Todo Items

| id | status | priority | title | node | updated | notes |
| --- | --- | --- | --- | --- | --- | --- |
| SG-0123 | completed | P1 | Already fixed regression | [[notes/memory-starmap-todo-list/already-fixed-regression]] | 2026-07-17 | Completed with verification. |
| SG-0146 | planned | P1 | Reconcile Ask Yoda recommendations with authoritative current state | [[notes/memory-starmap-todo-list/reconcile-ask-yoda-recommendations-with-authoritative-current-state]] | 2026-07-18 | Planned. |
"""

        def raw_entity(slug):
            return {
                "notes/memory-starmap-todo-list": backlog,
                "notes/memory-starmap-todo-list/already-fixed-regression": "# Already fixed\n\nStatus: completed",
                "notes/memory-starmap-todo-list/reconcile-ask-yoda-recommendations-with-authoritative-current-state": "# Reconcile\n\nStatus: planned",
            }.get(slug)

        with (
            mock.patch.object(store, "get_entity_raw", side_effect=raw_entity),
            mock.patch.object(store, "build_yoda_targeted_context", return_value={"text": "", "counts": {}}),
            mock.patch("server.run_gbrain", return_value=""),
        ):
            prompt = store.build_yoda_prompt(
                "notes/memory-starmap-todo-list",
                "Which current planned TODOs should we prioritize next, and is SG-0123 still open?",
                depth=4,
                stable_context={
                    "selected_node": "# Root",
                    "graph": "",
                    "backlinks": "",
                    "timings": {},
                },
                counts={},
            )

        self.assertIn("Authoritative current TODO state", prompt)
        self.assertIn("SG-0123 | completed | P1 | Already fixed regression", prompt)
        self.assertIn("SG-0146 | planned | P1 | Reconcile Ask Yoda recommendations with authoritative current state", prompt)
        self.assertIn("Do not recommend completed TODOs as current work", prompt)
        self.assertIn("## SG-0123 child node", prompt)
        self.assertIn("Status: completed", prompt)

    def test_yoda_prompt_builds_todo_and_operational_context_concurrently_in_order(self):
        store = GraphStore()
        barrier = threading.Barrier(2, timeout=1)

        def build_current(*_args, **_kwargs):
            barrier.wait()
            return {"text": "CURRENT TODO CONTEXT", "counts": {"current_todo_rows": 1}}

        def build_operational(*_args, **_kwargs):
            barrier.wait()
            return {"text": "OPERATIONAL CONTEXT", "counts": {"operational_state_rows": 1}}

        with (
            mock.patch.object(store, "build_yoda_current_todo_context", side_effect=build_current),
            mock.patch.object(store, "build_yoda_operational_remediation_context", side_effect=build_operational),
            mock.patch.object(store, "get_yoda_search_output", return_value=""),
            mock.patch.object(store, "build_yoda_targeted_context", return_value={"text": "", "counts": {}}),
        ):
            trace = {}
            counts = {}
            prompt = store.build_yoda_prompt(
                "products/memory-stargraph",
                "What is current?",
                stable_context={
                    "selected_node": "# Memory Stargraph",
                    "graph": "",
                    "backlinks": "",
                    "timings": {},
                },
                trace=trace,
                counts=counts,
            )

        self.assertLess(prompt.index("CURRENT TODO CONTEXT"), prompt.index("OPERATIONAL CONTEXT"))
        self.assertIn("current_todo_state", trace)
        self.assertIn("operational_state", trace)
        self.assertEqual(counts["current_todo_rows"], 1)
        self.assertEqual(counts["operational_state_rows"], 1)

    def test_ask_yoda_reuses_stable_node_context_across_different_questions(self):
        store = GraphStore()

        def gbrain_result(*args, **kwargs):
            del kwargs
            if args[0] == "get":
                return "# Tony\n\nEngineer"
            if args[0] == "graph-query":
                return "graph"
            if args[0] == "backlinks":
                return "backlinks"
            if args[0] == "query":
                return "search"
            raise AssertionError(args)

        with (
            mock.patch("server.yoda_runtime_config", return_value=self.openclaw_yoda_config()),
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
            mock.patch("server.run_openclaw_agent", return_value="agent answer"),
        ):
            cold = store.ask_yoda("people/tony-guan", "What should I know?", depth=4)
            warm = store.ask_yoda("people/tony-guan", "What changed recently?", depth=4)

        self.assertFalse(cold["diagnostics"]["context_cache_hit"])
        self.assertTrue(warm["diagnostics"]["context_cache_hit"])
        self.assertEqual(cold["diagnostics"]["context_counts"]["broad_graph_depth"], 2)
        self.assertEqual(run.call_count, 5)
        self.assertIn("context_subphases_ms", cold["diagnostics"])
        self.assertEqual(
            set(cold["diagnostics"]["context_subphases_ms"]),
            {"selected_node", "graph", "backlinks", "search", "direct_reads", "targeted_relationships", "assembly"},
        )
        self.assertEqual(
            set(cold["diagnostics"]["context_counts"]),
            {
                "prompt_chars",
                "history_messages",
                "search_results",
                "direct_reads",
                "targeted_entities",
                "targeted_backlink_reads",
                "relationship_source_reads",
                "retrieval_history_used",
                "broad_graph_depth",
            },
        )
        self.assertNotIn("prompt", cold["diagnostics"])
        store.invalidate()
        self.assertEqual(store.yoda_context_cache.entries, {})

    def test_yoda_stable_context_fetches_independent_sources_concurrently(self):
        store = GraphStore()
        barrier = threading.Barrier(3, timeout=1)

        def gbrain_result(*args, **kwargs):
            del kwargs
            barrier.wait()
            return {
                "get": "# Tony\n\nEngineer",
                "graph-query": "graph",
                "backlinks": "backlinks",
            }[args[0]]

        with mock.patch("server.run_gbrain", side_effect=gbrain_result):
            context = store.build_yoda_stable_context("people/tony-guan", depth=4)

        self.assertEqual(context["selected_node"], "# Tony\n\nEngineer")
        self.assertEqual(context["graph"], "graph")
        self.assertEqual(context["backlinks"], "backlinks")
        self.assertEqual(
            set(context["timings"]),
            {"selected_node", "graph", "backlinks"},
        )

    def test_yoda_stable_context_bounds_slow_broad_graph_as_optional_timeout(self):
        store = GraphStore()

        def gbrain_result(*args, **kwargs):
            if args[0] == "get":
                return "# Tony\n\nEngineer"
            if args[0] == "backlinks":
                return "selected backlinks"
            if args[0] == "graph-query":
                raise TimeoutError("forced slow graph traversal")
            raise AssertionError(args)

        with (
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
            mock.patch(
                "server.yoda_runtime_config",
                return_value={"graph_query_timeout": 60, "broad_graph_budget": 8},
            ),
        ):
            context = store.build_yoda_stable_context("people/tony-guan", depth=4)

        graph_call = next(call for call in run.call_args_list if call.args[0] == "graph-query")
        self.assertEqual(graph_call.kwargs["timeout"], 8)
        self.assertFalse(context["degraded"])
        self.assertEqual(context["degraded_reason"], "")
        self.assertEqual(context["broad_graph_status"], "optional_timeout")
        self.assertEqual(context["broad_graph_unavailable_reason"], "broad_graph_timeout")
        self.assertEqual(context["broad_graph_budget_ms"], 8000)
        self.assertIn("Broad graph context unavailable within retrieval budget", context["graph"])
        self.assertNotIn("forced slow graph traversal", context["graph"])

    def test_yoda_stable_context_coalesces_concurrent_cold_loads(self):
        store = GraphStore()
        started = threading.Event()
        release = threading.Event()
        contexts = []
        stable_context = {
            "selected_node": "# Node",
            "graph": "graph",
            "backlinks": "backlinks",
            "timings": {"selected_node": 1, "graph": 2, "backlinks": 3},
        }

        def load_context(_slug, _depth):
            started.set()
            release.wait(timeout=1)
            return stable_context

        def get_context():
            contexts.append(store.get_yoda_stable_context("products/memory-stargraph", 2))

        with mock.patch.object(store, "build_yoda_stable_context", side_effect=load_context) as load:
            first = threading.Thread(target=get_context)
            second = threading.Thread(target=get_context)
            first.start()
            self.assertTrue(started.wait(timeout=1))
            second.start()
            time.sleep(0.01)
            release.set()
            first.join(timeout=1)
            second.join(timeout=1)

        self.assertEqual(load.call_count, 1)
        self.assertEqual({status for _, status in contexts}, {"miss", "coalesced_hit"})
        self.assertEqual(contexts[0][0]["selected_node"], "# Node")
        coalesced_context = next(context for context, status in contexts if status == "coalesced_hit")
        self.assertEqual(coalesced_context["timings"], {"selected_node": 0, "graph": 0, "backlinks": 0})

    def test_yoda_context_cache_preserves_fresh_multi_key_entries_and_prunes_expired(self):
        store = GraphStore()
        store.yoda_context_cache.entries = {
            "stale": {"stored_at": 600, "value": {}},
            "fresh": {"stored_at": 900, "value": {}},
        }
        stable_context = {
            "selected_node": "# Node",
            "graph": "graph",
            "backlinks": "backlinks",
            "timings": {"selected_node": 1, "graph": 1, "backlinks": 1},
            "degraded": False,
            "degraded_reason": "",
            "broad_graph_status": "available",
            "broad_graph_unavailable_reason": "",
            "broad_graph_budget_ms": 8000,
        }
        model_result = {
            "output": "answer",
            "backend": "openclaw",
            "model_status": "answered",
            "openclaw_status": "ok",
            "node_runtime_status": "ok",
            "node_runtime_path": "/opt/local/bin/node",
            "node_runtime_version": "v24.15.0",
            "node_runtime_source": "configured",
        }

        with (
            mock.patch("server.time.time", return_value=1000),
            mock.patch("server.time.monotonic", return_value=1000),
            mock.patch.object(store, "build_yoda_stable_context", return_value=stable_context),
            mock.patch.object(store, "build_yoda_prompt", return_value="prompt"),
            mock.patch("server.run_yoda_model", return_value=model_result),
        ):
            result = store.ask_yoda("products/memory-stargraph", "What changed?", depth=3)

        self.assertFalse(result["diagnostics"]["context_cache_hit"])
        self.assertEqual(result["diagnostics"]["node_runtime_status"], "ok")
        self.assertEqual(result["diagnostics"]["node_runtime_path"], "/opt/local/bin/node")
        self.assertEqual(len(store.yoda_context_cache.entries), 2)
        self.assertIn("fresh", store.yoda_context_cache.entries)
        self.assertTrue(all(entry["stored_at"] >= 700 for entry in store.yoda_context_cache.entries.values()))

    def test_forced_graph_refresh_invalidates_stable_yoda_context(self):
        store = GraphStore()
        store.yoda_context_cache.put("stale", {})
        refreshed = {"nodes": [], "edges": [], "source": {"mode": "test"}}

        with (
            mock.patch("server.collect_seed_graph", return_value=refreshed),
            mock.patch("server.finalize_graph", side_effect=lambda payload: payload),
            mock.patch("server.write_cache"),
        ):
            store.get_seed_graph(force=True)

        self.assertEqual(store.yoda_context_cache.entries, {})

    def test_extract_openclaw_answer_ignores_cli_warnings(self):
        output = 'warning before json\n{"payloads":[{"text":"payload answer"}],"finalAssistantVisibleText":"visible answer"}\n[agent] done'

        self.assertEqual(extract_openclaw_answer(output), "visible answer")

    def test_run_openclaw_agent_uses_current_cli_shape(self):
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = b'noise\n{"finalAssistantVisibleText":"agent answer"}'
        completed.stderr = b"[agent] done"
        with (
            mock.patch(
                "server.select_openclaw_node_runtime",
                return_value={
                    "status": "ok",
                    "path": "/opt/local/bin/node",
                    "version": "v24.15.0",
                    "source": "configured",
                    "error": "",
                    "candidates": [],
                },
            ),
            mock.patch("server.subprocess.run", return_value=completed) as run,
        ):
            answer = run_openclaw_agent("answer this", timeout=30)

        self.assertEqual(answer, "agent answer")
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["openclaw", "agent", "--local", "--json"])
        self.assertIn("--message", command)
        self.assertIn("answer this", command)
        self.assertNotIn("run", command)
        self.assertNotIn("--stdin", command)

    def test_graph_store_uses_cache_for_fast_startup(self):
        store = GraphStore()
        cached = {
            "title": "Memory Stargraph",
            "source": {"mode": "cache", "status": "cached-startup"},
            "nodes": [{"slug": "index", "label": "Index", "links": [], "degree": 0}],
            "edges": [],
        }
        with mock.patch("server.cached_startup_graph", return_value=cached), mock.patch("server.collect_seed_graph") as collect:
            graph = store.get_seed_graph()

        self.assertIs(graph, cached)
        collect.assert_not_called()

    def test_graph_store_health_uses_cache_for_cold_startup(self):
        store = GraphStore()
        cached = {
            "title": "Memory Stargraph",
            "source": {"mode": "cache", "status": "cached-startup"},
            "stats": {"nodes": 75, "edges": 120},
            "nodes": [{"slug": "index", "label": "Index", "links": [], "degree": 0}],
            "edges": [],
        }
        with mock.patch("server.cached_startup_graph", return_value=cached), mock.patch("server.collect_seed_graph") as collect:
            graph = store.get_health_graph()

        self.assertIs(graph, cached)
        self.assertIs(store.graph, cached)
        collect.assert_not_called()

    def test_graph_store_health_stays_unloaded_when_cache_unavailable(self):
        store = GraphStore()
        with mock.patch("server.cached_startup_graph", return_value=None), mock.patch("server.collect_seed_graph") as collect:
            graph = store.get_health_graph()

        self.assertIsNone(graph)
        self.assertIsNone(store.graph)
        collect.assert_not_called()

    def test_get_entity_returns_all_direct_relationships_discovered_after_expand(self):
        store = GraphStore()
        graph = {
            "title": "Memory Stargraph",
            "source": {"mode": "test", "status": "ok"},
            "nodes": [
                {
                    "slug": "people/tony-guan",
                    "label": "Tony Guan",
                    "type": "person",
                    "category": "people",
                    "summary": "Person",
                    "links": ["companies/azul-systems"],
                    "degree": 1,
                    "expanded": True,
                },
                {
                    "slug": "companies/azul-systems",
                    "label": "Azul Systems",
                    "type": "company",
                    "category": "companies",
                    "summary": "Company",
                    "links": ["people/tony-guan"],
                    "degree": 1,
                },
                {
                    "slug": "projects/jtuner",
                    "label": "JTuner",
                    "type": "project",
                    "category": "projects",
                    "summary": "Project",
                    "links": ["people/tony-guan"],
                    "degree": 1,
                },
                {
                    "slug": "organizations/erfa",
                    "label": "ERFA",
                    "type": "organization",
                    "category": "organizations",
                    "summary": "Organization",
                    "links": ["people/tony-guan"],
                    "degree": 1,
                },
            ],
            "edges": [
                {"source": "people/tony-guan", "target": "companies/azul-systems", "types": ["employed by"]},
                {"source": "people/tony-guan", "target": "projects/jtuner", "types": ["built"]},
                {"source": "organizations/erfa", "target": "people/tony-guan", "types": ["led by"]},
            ],
            "stats": {"max_degree": 3},
        }
        with mock.patch.object(store, "get_seed_graph", return_value=graph):
            payload = store.get_entity("people/tony-guan")

        neighbor_slugs = {item["slug"] for item in payload["neighbors"]}
        self.assertEqual(
            neighbor_slugs,
            {"companies/azul-systems", "projects/jtuner", "organizations/erfa"},
        )
        self.assertEqual(payload["entity"]["degree"], 3)

    def test_graph_query_falls_back_to_loaded_graph_when_database_url_is_missing(self):
        store = GraphStore()
        graph = {
            "title": "Memory Stargraph",
            "source": {"mode": "test", "status": "ok"},
            "nodes": [
                {
                    "slug": "people/tony-guan",
                    "label": "Tony Guan",
                    "type": "person",
                    "category": "people",
                    "summary": "Person",
                    "links": ["companies/azul-systems"],
                    "degree": 1,
                },
                {
                    "slug": "companies/azul-systems",
                    "label": "Azul Systems",
                    "type": "company",
                    "category": "companies",
                    "summary": "Company",
                    "links": ["people/tony-guan"],
                    "degree": 1,
                },
            ],
            "edges": [
                {
                    "source": "people/tony-guan",
                    "target": "companies/azul-systems",
                    "types": ["employed by"],
                }
            ],
        }
        with mock.patch("server.run_gbrain", side_effect=RuntimeError("No database URL: database_url is missing from config")), mock.patch.object(
            store,
            "expand_entity",
            return_value=graph,
        ):
            output = store.graph_query("people/tony-guan", "employed by", "both", "1")

        self.assertIn("Remote-safe fallback", output)
        self.assertIn("people/tony-guan --employed by-> companies/azul-systems", output)
        self.assertIn("Azul Systems", output)

    def test_entity_media_reads_slug_even_when_not_loaded_in_seed_graph(self):
        store = GraphStore()
        markdown = "![MSN](gbrain:files/blogs/tony-guan/msn/post/photo.jpg)"

        with mock.patch("server.run_gbrain", return_value=markdown):
            media = store.get_entity_media("blogs/tony-guan/msn/post")

        self.assertEqual(media[0]["url"], "gbrain:files/blogs/tony-guan/msn/post/photo.jpg")
        self.assertEqual(media[0]["served_url"], "/media/blogs/tony-guan/msn/post/photo.jpg")


if __name__ == "__main__":
    unittest.main()
