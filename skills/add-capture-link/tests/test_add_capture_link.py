from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "add_capture_link.py"
SPEC = importlib.util.spec_from_file_location("add_capture_link", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)

NOW = dt.datetime(2026, 7, 15, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=-7)))


class FakeGBrain:
    def __init__(self, *, parent: str | None = None):
        self.nodes = {module.PARENT_SLUG: parent or module.empty_parent(NOW)}
        self.edges: set[tuple[str, str, str]] = set()
        self.events: list[tuple] = []

    @classmethod
    def empty_capture_root(cls):
        return cls()

    @property
    def first_upload_index(self):
        return next(index for index, event in enumerate(self.events) if event[0] == "upload")

    @property
    def parent_put_index(self):
        return next(
            index
            for index, event in enumerate(self.events)
            if event[:2] == ("put", module.PARENT_SLUG)
        )

    def __call__(self, *args: str, input_text: str | None = None) -> str:
        command = args[0]
        if command == "get":
            slug = args[1]
            if slug not in self.nodes:
                raise module.NotFoundError(f"not found: {slug}")
            return self.nodes[slug]
        if command == "put":
            slug = args[1]
            content = input_text
            if content is None:
                content = args[args.index("--content") + 1]
            self.nodes[slug] = content
            self.events.append(("put", slug, content))
            return "ok"
        if command == "link":
            source, target = args[1:3]
            relation = args[args.index("--link-type") + 1]
            self.edges.add((source, target, relation))
            self.events.append(("link", source, target, relation))
            return "ok"
        if command == "unlink":
            source, target = args[1:3]
            relation = args[args.index("--link-type") + 1]
            self.edges.discard((source, target, relation))
            self.events.append(("unlink", source, target, relation))
            return "ok"
        if command == "graph":
            source = args[1]
            relation = args[args.index("--link-type") + 1]
            return json.dumps(
                [
                    {"from_slug": a, "to_slug": b, "link_type": kind}
                    for a, b, kind in sorted(self.edges)
                    if a == source and kind == relation
                ]
            )
        raise AssertionError(f"unexpected gbrain command: {args}")


class AddCaptureLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeGBrain.empty_capture_root()

    def file(self, name: str, data: bytes = b"content") -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def upload_side_effect(self, backend, fail_upload_number=None):
        count = 0

        def upload(_base_url, slug, path, _description):
            nonlocal count
            count += 1
            backend.events.append(("upload", slug, path.name))
            if count == fail_upload_number:
                raise module.AttachmentRequestError(
                    "upload failed", {"owner": "Stargraph", "error": "upload failed"}, may_have_persisted=True
                )
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            reference = f"gbrain:files/{slug}/{path.name}"
            backend.nodes[slug] += f"\n- {reference}\n"
            return {
                "ok": True,
                "slug": slug,
                "local_media": {
                    "durable_storage_verified": True,
                    "size_bytes": len(data),
                    "sha256": digest,
                    "canonical_relative_path": f"{slug}/{path.name}",
                    "served_url": reference,
                },
            }

        return upload

    def invoke(self, backend=None, *, attachments=None, fail_upload_number=None, **kwargs):
        backend = backend or self.backend
        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(
                module,
                "upload_attachment",
                side_effect=self.upload_side_effect(backend, fail_upload_number),
            ),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
        ):
            return module.queue_capture(
                source="https://example.com/a",
                source_kind="url",
                instructions="Capture this page",
                attachments=[str(path) for path in (attachments or [])],
                stargraph_url="http://127.0.0.1:8788",
                now=NOW,
                **kwargs,
            )

    def test_text_only_request_is_planned_and_never_invokes_capture_skill(self):
        backend = FakeGBrain.empty_capture_root()
        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "invoke_capture_skill") as capture_skill,
        ):
            result = module.queue_capture(
                source="https://example.com/a",
                source_kind="url",
                instructions="Capture this page",
                now=NOW,
            )
        self.assertEqual(result["capture_id"], "CAP-0001")
        self.assertEqual(result["status"], "planned")
        self.assertTrue(result["ok"])
        capture_skill.assert_not_called()

    def test_attachment_upload_is_verified_before_parent_row_and_links(self):
        attachment = self.file("shot.png", b"exact-image")
        backend = FakeGBrain.empty_capture_root()
        result = self.invoke(backend, attachments=[attachment])
        child = backend.nodes[result["child_slug"]]
        receipt = result["attachments"][0]
        self.assertIn(receipt["reference"], child)
        self.assertEqual(receipt["sha256"], hashlib.sha256(b"exact-image").hexdigest())
        self.assertEqual(receipt["size_bytes"], len(b"exact-image"))
        self.assertTrue(result["durable_storage_verified"])
        self.assertLess(backend.first_upload_index, backend.parent_put_index)
        parent_put = backend.parent_put_index
        self.assertTrue(all(index > parent_put for index, event in enumerate(backend.events) if event[0] == "link"))

    def test_private_spool_happens_before_parent_is_read(self):
        attachment = self.file("ordered.bin", b"bytes")
        events = []
        backend = FakeGBrain.empty_capture_root()

        def tracked_backend(*args, **kwargs):
            if args[:2] == ("get", module.PARENT_SLUG):
                events.append("parent-get")
            return backend(*args, **kwargs)

        real_spool = module._spool

        def tracked_spool(*args, **kwargs):
            events.append("spool")
            return real_spool(*args, **kwargs)

        with (
            mock.patch.object(module, "run_gbrain", side_effect=tracked_backend),
            mock.patch.object(module, "_spool", side_effect=tracked_spool),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=self.upload_side_effect(backend)),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
        ):
            module.queue_capture(
                source="https://example.com/a", source_kind="url", instructions="Capture",
                attachments=[str(attachment)], now=NOW,
            )
        self.assertLess(events.index("spool"), events.index("parent-get"))

    def test_partial_upload_failure_creates_no_planned_row_and_preserves_recovery_manifest(self):
        paths = [self.file("a.png", b"first"), self.file("b.png", b"second")]
        with self.assertRaises(module.QueueFailure) as caught:
            self.invoke(self.backend, attachments=paths, fail_upload_number=2)
        result = caught.exception.result
        self.assertTrue(result["reminder_required"])
        manifest = Path(result["recovery_manifest"])
        self.assertTrue(manifest.is_file())
        self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o600)
        payload = json.loads(manifest.read_text())
        self.assertEqual([Path(value).read_bytes() for value in payload["attachments"]], [b"first", b"second"])
        self.assertNotIn("| CAP-", self.backend.nodes[module.PARENT_SLUG])
        self.assertIn("--recovery-manifest", result["retry_command"])
        self.assertRegex(result["remind_after"], r"^2026-07-16T09:30:00-07:00$")
        self.assertEqual(result["proposed_blocker"]["owner"], "Stargraph")

    def test_parent_readback_failure_rolls_back_planned_row(self):
        attachment = self.file("one.bin", b"one")
        backend = FakeGBrain.empty_capture_root()
        corrupt_next_parent_read = False

        def flaky_backend(*args, input_text=None):
            nonlocal corrupt_next_parent_read
            if args[:2] == ("put", module.PARENT_SLUG):
                corrupt_next_parent_read = True
                return backend(*args, input_text=input_text)
            if args[:2] == ("get", module.PARENT_SLUG) and corrupt_next_parent_read:
                corrupt_next_parent_read = False
                return module.empty_parent(NOW)
            return backend(*args, input_text=input_text)

        with (
            mock.patch.object(module, "run_gbrain", side_effect=flaky_backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=self.upload_side_effect(backend)),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            self.assertRaises(module.QueueFailure) as caught,
        ):
            module.queue_capture(
                source="https://example.com/a", source_kind="url", instructions="Capture",
                attachments=[str(attachment)], now=NOW,
            )
        self.assertTrue(caught.exception.result["parent_unchanged"])
        self.assertNotIn("| CAP-", backend.nodes[module.PARENT_SLUG])
        self.assertIn("status: capture-recovery", backend.nodes[caught.exception.result["child_slug"]])

    def test_durable_sha_mismatch_preserves_manifest_without_parent_row(self):
        attachment = self.file("bad.bin", b"trusted")
        backend = FakeGBrain.empty_capture_root()

        def mismatched_upload(_base_url, slug, path, _description):
            backend.events.append(("upload", slug, path.name))
            reference = f"gbrain:files/{slug}/{path.name}"
            backend.nodes[slug] += f"\n- {reference}\n"
            return {
                "ok": True,
                "slug": slug,
                "local_media": {
                    "durable_storage_verified": True,
                    "size_bytes": len(b"trusted"),
                    "sha256": "0" * 64,
                    "canonical_relative_path": f"{slug}/{path.name}",
                    "served_url": reference,
                },
            }

        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=mismatched_upload),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            self.assertRaises(module.QueueFailure) as caught,
        ):
            module.queue_capture(
                source="file", source_kind="file", instructions="Capture",
                attachments=[str(attachment)], now=NOW,
            )
        self.assertTrue(Path(caught.exception.result["recovery_manifest"]).is_file())
        self.assertNotIn("| CAP-", backend.nodes[module.PARENT_SLUG])

    def test_multipart_upload_posts_only_to_encoded_stargraph_entity_endpoint(self):
        attachment = self.file("raw.bin", b"\x00raw-bytes\xff")
        slug = "notes/memory-starmap-capture-list/cap-0001-a"
        relative = f"{slug}/{attachment.name}"
        payload = json.dumps({
            "ok": True,
            "slug": slug,
            "local_media": {
                "durable_storage_verified": True,
                "size_bytes": attachment.stat().st_size,
                "sha256": hashlib.sha256(attachment.read_bytes()).hexdigest(),
                "canonical_relative_path": relative,
                "served_url": f"gbrain:files/{relative}",
            },
        }).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return payload

        with mock.patch.object(module.request, "urlopen", return_value=Response()) as urlopen:
            module.upload_attachment("http://127.0.0.1:8788", slug, attachment, "attachment")
        req = urlopen.call_args.args[0]
        self.assertEqual(
            req.full_url,
            "http://127.0.0.1:8788/api/entity-attach-file/notes%2Fmemory-starmap-capture-list%2Fcap-0001-a",
        )
        self.assertIn(b"\x00raw-bytes\xff", req.data)
        self.assertTrue(req.headers["Content-type"].startswith("multipart/form-data; boundary="))

    def test_target_collection_and_relationship_instructions_are_preserved(self):
        backend = FakeGBrain.empty_capture_root()
        with mock.patch.object(module, "run_gbrain", side_effect=backend):
            result = module.queue_capture(
                source="people/tony-guan",
                source_kind="slug",
                instructions="Enrich this existing node",
                target="people/tony-guan",
                collection="collections/people",
                relationships=["people/tony-guan|member_of|collections/people"],
                now=NOW,
            )
        child = backend.nodes[result["child_slug"]]
        self.assertIn("Target: people/tony-guan", child)
        self.assertIn("Collection: collections/people", child)
        self.assertIn("people/tony-guan|member_of|collections/people", child)
        self.assertIn("| slug | people/tony-guan | people/tony-guan |", backend.nodes[module.PARENT_SLUG])

    def test_queue_reads_back_both_graph_edges(self):
        result = self.invoke()
        self.assertIn((module.PARENT_SLUG, result["child_slug"], "has_capture_request"), self.backend.edges)
        self.assertIn((result["child_slug"], module.PARENT_SLUG, "capture_request_for"), self.backend.edges)
        self.assertTrue(result["graph_verified"])

    def test_text_only_graph_verification_failure_rolls_back_parent_row(self):
        backend = FakeGBrain.empty_capture_root()

        def missing_graph(*args, input_text=None):
            if args[0] == "graph":
                return "[]"
            return backend(*args, input_text=input_text)

        with (
            mock.patch.object(module, "run_gbrain", side_effect=missing_graph),
            self.assertRaises(module.QueueFailure),
        ):
            module.queue_capture(
                source="https://example.com/a", source_kind="url", instructions="Capture", now=NOW,
            )
        self.assertNotIn("| CAP-", backend.nodes[module.PARENT_SLUG])
        self.assertFalse(backend.edges)

    def test_duplicate_source_allocates_unique_capture_id_and_child_slug(self):
        first = self.invoke()
        second = self.invoke()
        self.assertEqual(first["capture_id"], "CAP-0001")
        self.assertEqual(second["capture_id"], "CAP-0002")
        self.assertNotEqual(first["child_slug"], second["child_slug"])

    def test_invalid_input_fails_before_gbrain_or_upload(self):
        with (
            mock.patch.object(module, "run_gbrain") as gbrain,
            mock.patch.object(module, "upload_attachment") as upload,
            self.assertRaises(module.QueueFailure),
        ):
            module.queue_capture(source="x", source_kind="unsupported", instructions="", now=NOW)
        gbrain.assert_not_called()
        upload.assert_not_called()

    def test_recovery_manifest_retry_reuses_exact_spooled_bytes_and_original_fields(self):
        attachment = self.file("source.bin", b"\x00exact\xff")
        with self.assertRaises(module.QueueFailure) as caught:
            self.invoke(self.backend, attachments=[attachment], fail_upload_number=1, target="target/a")
        manifest = caught.exception.result["recovery_manifest"]
        attachment.unlink()
        backend = FakeGBrain.empty_capture_root()
        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=self.upload_side_effect(backend)),
        ):
            result = module.queue_capture(recovery_manifest=manifest, now=NOW)
        self.assertEqual(result["attachments"][0]["sha256"], hashlib.sha256(b"\x00exact\xff").hexdigest())
        self.assertIn("Target: target/a", backend.nodes[result["child_slug"]])
        self.assertFalse(Path(manifest).parent.exists())

    def test_cli_json_is_queue_only(self):
        completed = subprocess.run(
            ["python3", str(SCRIPT), "--help"], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("--source-kind", completed.stdout)
        self.assertIn("--relationship", completed.stdout)
        self.assertNotIn("capture-now", completed.stdout)


if __name__ == "__main__":
    unittest.main()
