import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from unittest import mock

from server import (
    DEFAULT_CONFIG,
    GraphStore,
    append_attachment_reference,
    collapse_part_identity,
    collect_seed_graph,
    ensure_media_references_available,
    extract_openclaw_answer,
    effective_yoda_retrieval_question,
    expand_raw_graph,
    finalize_graph,
    friendly_label,
    make_label,
    parse_backlink_types,
    parse_backlinks,
    parse_frontmatter,
    extract_summary_from_markdown_body,
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
    serve_url_for_media_reference,
    gbrain_file_url_for_relative_path,
    materialize_gbrain_file_reference,
    copy_file_to_gbrain_store,
    gbrain_file_ledger_has_relative_path,
    parse_gbrain_durable_evidence,
    safe_upload_filename,
)


class GraphParsingTests(unittest.TestCase):
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
                mock.call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "4", timeout=30),
                mock.call("backlinks", "people/tony-guan"),
                mock.call("query", "What should I know? people/tony-guan", "--adaptive-return", "true", "--limit", "10", "--relational", "true"),
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
        with mock.patch("server.run_gbrain") as run, mock.patch("server.run_openclaw_agent", return_value=None):
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

    def test_ask_yoda_prompt_uses_broader_retrieval_at_requested_depth(self):
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
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
            mock.patch("server.run_openclaw_agent", return_value="agent answer"),
        ):
            result = store.ask_yoda("people/tony-guan", "What does White Swan connect to?", depth=5)

        self.assertEqual(result["source"], "openclaw-agent")
        self.assertEqual(result["output"], "agent answer")
        self.assertIn("timings", result)
        run.assert_has_calls(
            [
                mock.call("get", "people/tony-guan"),
                mock.call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "5", timeout=30),
                mock.call("backlinks", "people/tony-guan"),
                mock.call("query", "What does White Swan connect to? people/tony-guan", "--adaptive-return", "true", "--limit", "10", "--relational", "true"),
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
        run.assert_any_call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "1", timeout=30)

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
            mock.patch("server.run_gbrain", side_effect=gbrain_result) as run,
            mock.patch("server.run_openclaw_agent", return_value="agent answer"),
        ):
            cold = store.ask_yoda("people/tony-guan", "What should I know?", depth=4)
            warm = store.ask_yoda("people/tony-guan", "What changed recently?", depth=4)

        self.assertFalse(cold["diagnostics"]["context_cache_hit"])
        self.assertTrue(warm["diagnostics"]["context_cache_hit"])
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
        self.assertEqual(store.yoda_context_cache, {})

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

    def test_forced_graph_refresh_invalidates_stable_yoda_context(self):
        store = GraphStore()
        store.yoda_context_cache = {"stale": {"created_at": 1, "context": {}}}
        refreshed = {"nodes": [], "edges": [], "source": {"mode": "test"}}

        with (
            mock.patch("server.collect_seed_graph", return_value=refreshed),
            mock.patch("server.finalize_graph", side_effect=lambda payload: payload),
            mock.patch("server.write_cache"),
        ):
            store.get_seed_graph(force=True)

        self.assertEqual(store.yoda_context_cache, {})

    def test_extract_openclaw_answer_ignores_cli_warnings(self):
        output = 'warning before json\n{"payloads":[{"text":"payload answer"}],"finalAssistantVisibleText":"visible answer"}\n[agent] done'

        self.assertEqual(extract_openclaw_answer(output), "visible answer")

    def test_run_openclaw_agent_uses_current_cli_shape(self):
        completed = mock.Mock()
        completed.returncode = 0
        completed.stdout = b'noise\n{"finalAssistantVisibleText":"agent answer"}'
        completed.stderr = b"[agent] done"
        with mock.patch("server.subprocess.run", return_value=completed) as run:
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
