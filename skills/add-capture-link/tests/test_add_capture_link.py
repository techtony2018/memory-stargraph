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
import threading
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "add_capture_link.py"
SPEC = importlib.util.spec_from_file_location("add_capture_link", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)
ORIGINAL_QUEUE_AUTHORITY_REQUEST = module.queue_authority_request

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
        self.reservations = {}
        self.authority_receipts = {}
        authority = mock.patch.object(module, "queue_authority_request", side_effect=self.fake_queue_authority)
        health = mock.patch.object(module, "check_stargraph_health", return_value={"ok": True})
        authority.start()
        health.start()
        self.addCleanup(authority.stop)
        self.addCleanup(health.stop)

    def fake_queue_authority(self, _base_url, action, payload):
        key = payload["idempotency_key"]
        if action == "reserve":
            if key not in self.reservations:
                parent = module.run_gbrain("get", module.PARENT_SLUG)
                capture_id = module.next_capture_id(module.parse_capture_rows(parent))
                child_slug = f"{module.PARENT_SLUG}/{capture_id.lower()}-{module.slugify(payload['source'])}"
                reservation = {**payload, "capture_id": capture_id, "child_slug": child_slug, "created_at": module.pacific_iso(NOW)}
                self.reservations[key] = reservation
                provisional = module.build_child(
                    capture_id=capture_id, child_slug=child_slug, source=payload["source"],
                    source_kind=payload["source_kind"], instructions=payload["instructions"],
                    target=payload["target"], collection=payload["collection"],
                    relationships=payload["relationships"], created_at=module.pacific_iso(NOW),
                    status="capture-recovery", attachments=[],
                )
                module._put_verified(child_slug, provisional, "status: capture-recovery")
            reservation = self.reservations[key]
            return {"ok": True, **reservation, "status": "capture-recovery", "graph_verified": False}
        reservation = self.reservations[key]
        if action == "attachment/verify":
            token = f"receipt-{hashlib.sha256((key + payload['canonical_relative_path']).encode()).hexdigest()[:16]}"
            receipt = {
                "ok": True,
                "receipt": token,
                "filename": payload["filename"],
                "reference": f"/media/{payload['canonical_relative_path']}",
                "served_url": f"/media/{payload['canonical_relative_path']}",
                "canonical_relative_path": payload["canonical_relative_path"],
                "size_bytes": payload["size_bytes"],
                "sha256": payload["sha256"],
            }
            self.authority_receipts[token] = receipt
            return receipt
        receipt_fields = {"receipt", "filename", "reference", "served_url", "canonical_relative_path", "size_bytes", "sha256"}
        attachments = [{field: receipt[field] for field in receipt_fields} for receipt in self.authority_receipts.values()]
        original_child = module.run_gbrain("get", reservation["child_slug"])
        original_parent = module.run_gbrain("get", module.PARENT_SLUG)
        final_child = module.build_child(
            capture_id=reservation["capture_id"], child_slug=reservation["child_slug"],
            source=reservation["source"], source_kind=reservation["source_kind"],
            instructions=reservation["instructions"], target=reservation["target"],
            collection=reservation["collection"], relationships=reservation["relationships"],
            created_at=reservation["created_at"], status="planned", attachments=attachments,
        )
        try:
            module._put_verified(reservation["child_slug"], final_child, "status: planned")
            marker = f"| {reservation['capture_id']} | planned |"
            if marker not in original_parent:
                row = (
                    f"| {reservation['capture_id']} | planned | {reservation['source_kind']} | {reservation['source']} | "
                    f"{reservation['target']} | [[{reservation['child_slug']}]] | {module.pacific_iso(NOW)} | queued |"
                )
                module._put_verified(module.PARENT_SLUG, module._append_planned_row(original_parent, row, module.pacific_iso(NOW)), marker)
            module._link_verified(module.PARENT_SLUG, reservation["child_slug"], "has_capture_request")
            module._link_verified(reservation["child_slug"], module.PARENT_SLUG, "capture_request_for")
        except RuntimeError:
            module._unlink_best_effort(module.PARENT_SLUG, reservation["child_slug"], "has_capture_request")
            module._unlink_best_effort(reservation["child_slug"], module.PARENT_SLUG, "capture_request_for")
            module.run_gbrain("put", module.PARENT_SLUG, input_text=original_parent)
            module.run_gbrain("put", reservation["child_slug"], input_text=original_child)
            raise
        return {"ok": True, **reservation, "status": "planned", "graph_verified": True, "attachments": attachments}

    def file(self, name: str, data: bytes = b"content") -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def upload_side_effect(self, backend, fail_upload_number=None):
        count = 0

        def upload(_base_url, slug, path, _description, authority=None):
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
            authority = authority or {
                "idempotency_key": next(iter(self.reservations), "test-key"),
                "canonical_relative_path": f"{slug}/{path.name}",
                "filename": path.name,
                "size_bytes": len(data),
                "sha256": digest,
            }
            token = f"receipt-{hashlib.sha256((authority['idempotency_key'] + authority['canonical_relative_path']).encode()).hexdigest()[:16]}"
            receipt = {
                "receipt": token,
                "filename": path.name,
                "reference": f"/media/{slug}/{path.name}",
                "served_url": f"/media/{slug}/{path.name}",
                "canonical_relative_path": f"{slug}/{path.name}",
                "size_bytes": len(data),
                "sha256": digest,
            }
            self.authority_receipts[token] = receipt
            return {
                "ok": True,
                "slug": slug,
                "attachment_receipt": receipt,
            }

        return upload

    def invoke(self, backend=None, *, attachments=None, fail_upload_number=None, **kwargs):
        backend = backend or self.backend

        def fetch_spooled(_base_url, served_url):
            filename = served_url.rsplit("/", 1)[-1]
            return next(
                path for path in (self.root / "codex" / "recovery" / "add-capture-link").glob(f"*/{filename}")
            ).read_bytes()

        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(
                module,
                "upload_attachment",
                side_effect=self.upload_side_effect(backend, fail_upload_number),
            ),
            mock.patch.object(module, "fetch_served_attachment", side_effect=fetch_spooled),
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
            mock.patch.object(module, "fetch_served_attachment", return_value=b"bytes"),
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
            mock.patch.object(module, "fetch_served_attachment", return_value=b"one"),
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

        def mismatched_upload(_base_url, slug, path, _description, _authority=None):
            backend.events.append(("upload", slug, path.name))
            reference = f"gbrain:files/{slug}/{path.name}"
            backend.nodes[slug] += f"\n- {reference}\n"
            return {
                "ok": True,
                "slug": slug,
                "attachment_receipt": {
                    "receipt": "server-token",
                    "filename": path.name,
                    "reference": f"/media/{slug}/{path.name}",
                    "served_url": f"/media/{slug}/{path.name}",
                    "size_bytes": len(b"trusted"),
                    "sha256": "0" * 64,
                    "canonical_relative_path": f"{slug}/{path.name}",
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

    def test_attachment_verify_authority_response_requires_opaque_receipt_not_capture_identity(self):
        payload = json.dumps({
            "ok": True,
            "receipt": "opaque-token",
            "filename": "proof.bin",
            "canonical_relative_path": "child/proof.bin",
            "size_bytes": 1,
            "sha256": "0" * 64,
            "reference": "/media/child/proof.bin",
            "served_url": "/media/child/proof.bin",
        }).encode()

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return payload

        with mock.patch.object(module.request, "urlopen", return_value=Response()):
            result = ORIGINAL_QUEUE_AUTHORITY_REQUEST(
                "http://127.0.0.1:8788", "attachment/verify", {"idempotency_key": "request-key"}
            )
        self.assertEqual(result["receipt"], "opaque-token")

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
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            mock.patch.object(module, "run_gbrain") as gbrain,
            mock.patch.object(module, "upload_attachment") as upload,
            self.assertRaises(module.QueueFailure) as caught,
        ):
            module.queue_capture(source="x", source_kind="unsupported", instructions="", now=NOW)
        gbrain.assert_not_called()
        upload.assert_not_called()
        self.assertTrue(Path(caught.exception.result["recovery_manifest"]).is_file())
        self.assertTrue(caught.exception.result["reminder_required"])

    def test_recovery_manifest_retry_reuses_exact_spooled_bytes_and_original_fields(self):
        attachment = self.file("source.bin", b"\x00exact\xff")
        with self.assertRaises(module.QueueFailure) as caught:
            self.invoke(self.backend, attachments=[attachment], fail_upload_number=1, target="target/a")
        manifest = caught.exception.result["recovery_manifest"]
        attachment.unlink()
        backend = self.backend
        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=self.upload_side_effect(backend)),
            mock.patch.object(module, "fetch_served_attachment", return_value=b"\x00exact\xff"),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
        ):
            result = module.queue_capture(recovery_manifest=manifest, now=NOW)
        self.assertEqual(result["attachments"][0]["sha256"], hashlib.sha256(b"\x00exact\xff").hexdigest())
        self.assertIn("Target: target/a", backend.nodes[result["child_slug"]])
        self.assertFalse(Path(manifest).parent.exists())

    def test_recovery_manifest_must_be_canonical_direct_child_recovery_json(self):
        recovery_root = self.root / "codex" / "recovery" / "add-capture-link"
        outside = self.root / "outside"
        outside.mkdir()
        outside_manifest = outside / "recovery.json"
        outside_manifest.write_text("{}")
        bundle = recovery_root / "bundle"
        bundle.mkdir(parents=True)
        escaped = bundle / "recovery.json"
        escaped.symlink_to(outside_manifest)
        with (
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            mock.patch.object(module, "run_gbrain") as gbrain,
            self.assertRaises(module.QueueFailure),
        ):
            module.queue_capture(recovery_manifest=str(escaped), now=NOW)
        gbrain.assert_not_called()
        self.assertTrue(outside_manifest.is_file())

    def test_text_only_parent_read_failure_preserves_exact_inputs_and_retry(self):
        with (
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex with spaces")}),
            mock.patch.object(module, "run_gbrain", side_effect=RuntimeError("parent unavailable")),
            self.assertRaises(module.QueueFailure) as caught,
        ):
            module.queue_capture(
                source="literal source text",
                source_kind="text",
                instructions="Keep every word exactly",
                target="target/a",
                collection="collections/a",
                relationships=["target/a|member_of|collections/a"],
                now=NOW,
            )
        result = caught.exception.result
        payload = json.loads(Path(result["recovery_manifest"]).read_text())
        self.assertEqual(payload["source"], "literal source text")
        self.assertEqual(payload["instructions"], "Keep every word exactly")
        self.assertEqual(payload["target"], "target/a")
        self.assertTrue(result["reminder_required"])
        self.assertIn("'", result["retry_command"])
        self.assertIn("--recovery-manifest", result["retry_command"])

    def test_concurrent_enqueues_are_serialized_and_allocate_distinct_ids(self):
        backend = FakeGBrain.empty_capture_root()
        first_provisional = threading.Event()
        release_first = threading.Event()
        parent_reads = 0
        guard = threading.Lock()

        def blocking_backend(*args, input_text=None):
            nonlocal parent_reads
            if args[:2] == ("get", module.PARENT_SLUG):
                with guard:
                    parent_reads += 1
            result = backend(*args, input_text=input_text)
            if args[:2] == ("put", f"{module.PARENT_SLUG}/cap-0001-one"):
                first_provisional.set()
                release_first.wait(5)
            return result

        results, errors = [], []

        def enqueue(source):
            try:
                results.append(module.queue_capture(
                    source=source, source_kind="text", instructions="Capture", now=NOW,
                ))
            except Exception as exc:  # noqa: BLE001 - surfaced in the assertion
                errors.append(exc)

        with (
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            mock.patch.object(module, "run_gbrain", side_effect=blocking_backend),
        ):
            first = threading.Thread(target=enqueue, args=("one",))
            second = threading.Thread(target=enqueue, args=("two",))
            first.start()
            self.assertTrue(first_provisional.wait(2))
            second.start()
            time.sleep(0.15)
            self.assertEqual(parent_reads, 1)
            release_first.set()
            first.join(5)
            second.join(5)
        self.assertFalse(errors)
        self.assertEqual(sorted(item["capture_id"] for item in results), ["CAP-0001", "CAP-0002"])

    def test_attachment_receipt_must_be_server_opaque_and_match_spooled_bytes(self):
        attachment = self.file("served.bin", b"trusted bytes")
        digest = hashlib.sha256(attachment.read_bytes()).hexdigest()
        payload = {
            "attachment_receipt": {
                "receipt": "opaque-server-token",
                "filename": attachment.name,
                "reference": "/media/child/served.bin",
                "served_url": "/media/child/served.bin",
                "size_bytes": attachment.stat().st_size,
                "sha256": digest,
                "canonical_relative_path": "child/served.bin",
            }
        }
        self.assertEqual(module._receipt(payload, "child", attachment, "http://127.0.0.1:8788")["receipt"], "opaque-server-token")
        payload["attachment_receipt"].pop("receipt")
        with self.assertRaises(module.AttachmentRequestError):
            module._receipt(payload, "child", attachment, "http://127.0.0.1:8788")

    def test_partial_multi_attachment_retry_uploads_each_attachment_once(self):
        paths = [self.file("first.bin", b"first"), self.file("second.bin", b"second")]
        backend = FakeGBrain.empty_capture_root()
        upload_counts = {path.name: 0 for path in paths}
        fail_second_once = True

        def upload(base_url, slug, path, description, authority=None):
            nonlocal fail_second_once
            upload_counts[path.name] += 1
            if path.name == "second.bin" and fail_second_once:
                fail_second_once = False
                raise module.AttachmentRequestError("second failed", {"error": "second failed"})
            return self.upload_side_effect(backend)(base_url, slug, path, description, authority)

        def fetch(_base_url, served_url):
            return (b"first" if served_url.endswith("first.bin") else b"second")

        with (
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=upload),
            mock.patch.object(module, "fetch_served_attachment", side_effect=fetch),
            self.assertRaises(module.QueueFailure) as caught,
        ):
            module.queue_capture(
                source="files", source_kind="mixed", instructions="Capture",
                attachments=[str(path) for path in paths], now=NOW,
            )
        manifest = caught.exception.result["recovery_manifest"]
        progress = json.loads(Path(manifest).read_text())
        self.assertEqual([item["filename"] for item in progress["receipts"]], ["first.bin"])
        with (
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=upload),
            mock.patch.object(module, "fetch_served_attachment", side_effect=fetch),
        ):
            result = module.queue_capture(recovery_manifest=manifest, now=NOW)
        self.assertTrue(result["ok"])
        self.assertEqual(upload_counts, {"first.bin": 1, "second.bin": 1})

    def test_retry_fails_closed_when_any_manifest_attachment_input_has_no_spooled_file(self):
        attachment = self.file("only.bin", b"only")
        with self.assertRaises(module.QueueFailure) as caught:
            self.invoke(self.backend, attachments=[attachment], fail_upload_number=1)
        manifest = Path(caught.exception.result["recovery_manifest"])
        payload = json.loads(manifest.read_text())
        payload["attachment_inputs"].append("/chat-host/missing-second.bin")
        manifest.write_text(json.dumps(payload))
        with (
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            mock.patch.object(module, "run_gbrain") as gbrain,
            self.assertRaises(module.QueueFailure),
        ):
            module.queue_capture(recovery_manifest=str(manifest), now=NOW)
        gbrain.assert_not_called()

    def test_recovery_resolves_codex_home_and_rejects_symlinked_root_bundle_manifest_and_lock(self):
        real_home = self.root / "real-codex"
        real_home.mkdir()
        symlink_home = self.root / "codex-link"
        symlink_home.symlink_to(real_home, target_is_directory=True)
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(symlink_home)}):
            resolved_root = module._ensure_recovery_root()
        self.assertTrue(resolved_root.is_relative_to(real_home.resolve()))

        codex_home = self.root / "codex"
        recovery_parent = codex_home / "recovery"
        recovery_parent.mkdir(parents=True)
        real_root = self.root / "outside-root"
        real_root.mkdir()
        (recovery_parent / "add-capture-link").symlink_to(real_root, target_is_directory=True)
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), self.assertRaises(module.QueueFailure):
            module._ensure_recovery_root()

        recovery_parent.joinpath("add-capture-link").unlink()
        root = recovery_parent / "add-capture-link"
        root.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (root / "bundle").symlink_to(outside, target_is_directory=True)
        (outside / "recovery.json").write_text("{}")
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), self.assertRaises(module.QueueFailure):
            module._validated_recovery_manifest(root / "bundle" / "recovery.json")

        (root / ".queue.lock").symlink_to(self.root / "outside-lock")
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), self.assertRaises(module.QueueFailure):
            with module._queue_lock():
                pass

    def test_served_byte_fetch_rejects_cross_origin_redirect(self):
        class RedirectedResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def geturl(self):
                return "https://evil.example/stolen.bin"
            def read(self):
                return b"trusted"

        opener = mock.Mock()
        opener.open.return_value = RedirectedResponse()
        with mock.patch.object(module.request, "build_opener", return_value=opener):
            with self.assertRaises(module.AttachmentRequestError):
                module.fetch_served_attachment("http://127.0.0.1:8788", "/media/child/file.bin")

    def test_ambiguous_upload_retry_probes_expected_canonical_path_before_reupload(self):
        attachment = self.file("ambiguous.bin", b"exact")
        backend = FakeGBrain.empty_capture_root()
        calls = 0

        def ambiguous_upload(*_args):
            nonlocal calls
            calls += 1
            raise module.AttachmentRequestError("connection lost", {"error": "timeout"}, may_have_persisted=True)

        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=ambiguous_upload),
            mock.patch.object(module, "fetch_served_attachment", side_effect=module.AttachmentRequestError("not found")),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            self.assertRaises(module.QueueFailure) as caught,
        ):
            module.queue_capture(
                source="file", source_kind="file", instructions="Capture",
                attachments=[str(attachment)], now=NOW,
            )
        manifest = Path(caught.exception.result["recovery_manifest"])
        progress = json.loads(manifest.read_text())
        expected = progress["attachment_progress"][0]["expected_canonical_relative_path"]
        self.assertEqual(expected, f"{progress['child_slug']}/ambiguous.bin")

        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "check_stargraph_health", return_value={"ok": True}),
            mock.patch.object(module, "upload_attachment", side_effect=ambiguous_upload),
            mock.patch.object(module, "fetch_served_attachment", return_value=b"exact"),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
        ):
            result = module.queue_capture(recovery_manifest=str(manifest), now=NOW)
        self.assertTrue(result["ok"])
        self.assertEqual(calls, 1)

    def test_receipt_failure_after_upload_is_probe_before_repeat_ambiguous(self):
        attachment = self.file("receipt-ambiguous.bin", b"exact")
        backend = FakeGBrain.empty_capture_root()
        uploads = 0

        def upload(*args):
            nonlocal uploads
            uploads += 1
            return self.upload_side_effect(backend)(*args)

        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "upload_attachment", side_effect=upload),
            mock.patch.object(module, "_receipt", side_effect=module.AttachmentRequestError("receipt lost")),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
            self.assertRaises(module.QueueFailure) as caught,
        ):
            module.queue_capture(source="file", source_kind="file", instructions="Capture", attachments=[str(attachment)], now=NOW)
        manifest = Path(caught.exception.result["recovery_manifest"])
        progress = json.loads(manifest.read_text())["attachment_progress"][0]
        self.assertTrue(progress["upload_started"])

        with (
            mock.patch.object(module, "run_gbrain", side_effect=backend),
            mock.patch.object(module, "upload_attachment", side_effect=upload),
            mock.patch.object(module, "fetch_served_attachment", return_value=b"exact"),
            mock.patch.dict(os.environ, {"CODEX_HOME": str(self.root / "codex")}),
        ):
            result = module.queue_capture(recovery_manifest=str(manifest), now=NOW)
        self.assertTrue(result["ok"])
        self.assertEqual(uploads, 1)

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
