import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from server import (
    GraphStore,
    collapse_part_identity,
    expand_raw_graph,
    finalize_graph,
    friendly_label,
    make_label,
    parse_backlink_types,
    parse_backlinks,
    parse_frontmatter,
    parse_link_types,
    parse_media_references,
    parse_page_list,
    parse_search_results,
    resolve_media_file_path,
    serve_url_for_media_reference,
)


class GraphParsingTests(unittest.TestCase):
    def test_parse_page_list_reads_gbrain_tabular_output(self):
        output = "people/tony-guan\tperson\t2026-06-27\tTony Guan\nproducts/jtuner\tproduct\t2026-06-28\tJTuner\n"
        rows = parse_page_list(output)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["slug"], "people/tony-guan")
        self.assertEqual(rows[0]["type"], "person")
        self.assertEqual(rows[1]["title"], "JTuner")

    def test_parse_search_results_reads_scores_slugs_and_previews(self):
        output = "[0.7772] organizations/erfapac -- # Equal Rights For All PAC (ERFA PAC)\n[0.7384] products/jtuner/rfc/part-03 -- Binary preview\n"
        rows = parse_search_results(output)

        self.assertEqual(rows[0]["slug"], "organizations/erfapac")
        self.assertEqual(rows[0]["score"], 0.7772)
        self.assertEqual(rows[0]["label"], "Equal Rights For All PAC (ERFA PAC)")
        self.assertEqual(rows[1]["slug"], "products/jtuner/rfc/part-03")

    def test_friendly_labels_strip_category_prefixes(self):
        self.assertEqual(make_label("companies/uber"), "Uber")
        self.assertEqual(friendly_label("companies/uber", "Companies/uber"), "Uber")
        self.assertEqual(friendly_label("organizations/stopprop16", "Organizations/stopprop16"), "Stopprop16")
        self.assertEqual(friendly_label("categories/people", "Categories/people"), "People")
        self.assertEqual(friendly_label("people/tony-guan", "Tony Guan"), "Tony Guan")

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
        graph_output = """[
  {"slug": "organizations/cfer-foundation", "links": [{"to_slug": "bills/aca7", "link_type": "oppose"}]},
  {"slug": "bills/aca7", "links": []}
]"""
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

    def test_parse_media_references_reads_frontmatter_profile_image(self):
        markdown = """---
type: reporter
title: Witty Wang
date: '2026-06-28T00:00:00.000Z'
source: user-provided
profile_image: people/witty-wang/witty-wang-profile.jpg
profile_image_uploaded_at: '2026-06-29'
---


"""
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
            ],
        }
        graph = finalize_graph(raw_graph)
        labels = {node["slug"]: node["label"] for node in graph["nodes"]}

        self.assertEqual(labels["companies/uber"], "Uber")
        self.assertEqual(labels["organizations/stopprop16"], "Stopprop16")
        self.assertEqual(labels["categories/people"], "People")

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
        self.assertEqual(collapsed["label"], "Agent/reports/gbrain Usage")
        self.assertEqual(collapsed["report_count"], 2)
        self.assertEqual(collapsed["degree"], 2)
        self.assertEqual(graph["stats"]["collapsed_reports"], 2)

    def test_graph_store_node_operations_call_gbrain_commands(self):
        store = GraphStore()
        with mock.patch("server.run_gbrain") as run, mock.patch.object(store, "invalidate") as invalidate:
            store.add_relationship("people/tony-guan", "companies/azul-systems", "employed by", "past role")
            store.remove_relationship("people/tony-guan", "companies/azul-systems", "employed by")
            store.update_tags("people/tony-guan", ["founder", "java"], ["old"])
            store.add_timeline_event("people/tony-guan", "2026-06-29", "Updated graph operations", "Details", "memory-stargraph")
            store.ask_gbrain("people/tony-guan", "What should I know?")
            store.backlinks("people/tony-guan")
            store.graph_query("people/tony-guan", "employed by", "both", "2")
            store.attach_file("people/tony-guan", "/tmp/example.pdf")
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
                mock.call("query", "What should I know? Related node: people/tony-guan"),
                mock.call("backlinks", "people/tony-guan"),
                mock.call("graph-query", "people/tony-guan", "--type", "employed by", "--direction", "both", "--depth", "2"),
                mock.call("files", "upload", "/tmp/example.pdf", "--page", "people/tony-guan"),
                mock.call("history", "people/tony-guan"),
                mock.call("embed", "people/tony-guan"),
            ]
        )
        self.assertEqual(invalidate.call_count, 6)


if __name__ == "__main__":
    unittest.main()
