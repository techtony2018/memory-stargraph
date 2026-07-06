import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from server import (
    DEFAULT_CONFIG,
    GraphStore,
    append_attachment_reference,
    collapse_part_identity,
    collect_seed_graph,
    ensure_media_references_available,
    extract_openclaw_answer,
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
    resolve_media_file_path,
    run_openclaw_agent,
    run_gbrain,
    serve_url_for_media_reference,
    gbrain_file_url_for_relative_path,
    materialize_gbrain_file_reference,
    copy_file_to_gbrain_store,
)


class GraphParsingTests(unittest.TestCase):
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
        self.assertEqual(files["file"]["filename"], "witty wang.jpg")
        self.assertEqual(files["file"]["content_type"], "image/jpeg")
        self.assertEqual(files["file"]["data"], b"fake jpg")

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
                run.side_effect = ["# Azul Systems\n\nCompany notes.", "", ""]
                result = store.attach_file("companies/azul-systems", str(source), "Azul company logo")

            self.assertEqual(result["served_url"], "/media/companies/azul-systems/Azul.jpg")
            self.assertTrue(result["markdown_updated"])
            run.assert_any_call("put", "companies/azul-systems", input_text=mock.ANY)
            put_content = next(call.kwargs["input_text"] for call in run.mock_calls if call.args[:2] == ("put", "companies/azul-systems"))
            self.assertIn("![Azul company logo](companies/azul-systems/Azul.jpg)", put_content)
            invalidate.assert_called_once()

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
        with (
            mock.patch("server.run_gbrain") as run,
            mock.patch("server.run_openclaw_agent", return_value="agent answer"),
            mock.patch.object(store, "invalidate") as invalidate,
        ):
            run.return_value = "ok"
            store.add_relationship("people/tony-guan", "companies/azul-systems", "employed by", "past role")
            store.remove_relationship("people/tony-guan", "companies/azul-systems", "employed by")
            store.update_tags("people/tony-guan", ["founder", "java"], ["old"])
            store.add_timeline_event("people/tony-guan", "2026-06-29", "Updated graph operations", "Details", "memory-stargraph")
            store.ask_gbrain("people/tony-guan", "What should I know?")
            store.ask_yoda("people/tony-guan", "What should I know?", [{"role": "user", "content": "Earlier"}])
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
                mock.call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "1"),
                mock.call("query", "What should I know? people/tony-guan", "--adaptive-return", "true", "--limit", "8", "--relational", "true"),
                mock.call("get", "people/tony-guan"),
                mock.call("graph-query", "people/tony-guan", "--direction", "both", "--depth", "4"),
                mock.call("backlinks", "people/tony-guan"),
                mock.call("graph-query", "people/tony-guan", "--type", "employed by", "--direction", "both", "--depth", "2"),
                mock.call("get", "people/tony-guan"),
                mock.call("files", "upload", "/tmp/example.pdf", "--page", "people/tony-guan"),
                mock.call("history", "people/tony-guan"),
                mock.call("embed", "people/tony-guan"),
            ]
        )
        self.assertEqual(invalidate.call_count, 6)

    def test_ask_yoda_returns_fallback_when_openclaw_unavailable(self):
        store = GraphStore()
        with mock.patch("server.run_gbrain") as run, mock.patch("server.run_openclaw_agent", return_value=None):
            run.side_effect = ["# Tony Guan\n\nEngineer", "direct graph", "fallback graph", "retrieved context"]
            result = store.ask_yoda("people/tony-guan", "What changed?", [{"role": "user", "content": "Earlier question"}])

        self.assertEqual(result["source"], "fallback")
        self.assertIn("Question: What changed?", result["output"])
        self.assertIn("Selected node: people/tony-guan", result["output"])
        self.assertNotIn("OpenClaw agent unavailable", result["output"])
        self.assertNotIn("retrieved context", result["output"])
        self.assertNotIn("prompt", result)

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
