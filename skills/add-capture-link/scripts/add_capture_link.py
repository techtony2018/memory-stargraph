#!/usr/bin/env python3
"""Queue source material for the persistent Memory Stargraph Capture Link worker."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys
from urllib import error, parse, request
from zoneinfo import ZoneInfo


PARENT_SLUG = "notes/memory-starmap-capture-list"
ALLOWED_SOURCE_KINDS = {
    "url", "file", "pdf", "text", "slug", "linkedin", "wechat", "x", "profile", "mixed"
}
TABLE_HEADER = "| id | status | source kind | source | target | node | updated | notes |"
TABLE_SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- | --- |"
PACIFIC = ZoneInfo("America/Los_Angeles")
DEFAULT_STARGRAPH_URL = "http://127.0.0.1:8788"


class NotFoundError(RuntimeError):
    pass


class QueueFailure(RuntimeError):
    def __init__(self, message: str, result: dict | None = None):
        super().__init__(message)
        self.result = result or {"ok": False, "error": message, "reminder_required": False}


class AttachmentRequestError(RuntimeError):
    def __init__(self, message: str, evidence: dict | None = None, *, may_have_persisted: bool = False):
        super().__init__(message)
        self.evidence = evidence or {"error": message}
        self.may_have_persisted = may_have_persisted


def run_gbrain(*args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["gbrain", *args], input=input_text, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip() or "gbrain command failed"
        if args[:1] == ("get",) and re.search(r"not found|does not exist|no such", message, re.I):
            raise NotFoundError(message)
        raise RuntimeError(message)
    return completed.stdout


def pacific_iso(now: dt.datetime | None = None) -> str:
    value = now or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        raise QueueFailure("Timestamp must be timezone-aware.")
    return value.astimezone(PACIFIC).replace(microsecond=0).isoformat()


def empty_parent(now: dt.datetime | None = None) -> str:
    stamp = pacific_iso(now)
    return f"""---
type: collection
title: Memory Starmap Capture List
status: active
timezone: America/Los_Angeles
updated_at: '{stamp}'
---

# Memory Starmap Capture List

Queue-only capture backlog. The persistent Capture Link worker owns capture execution.

## Capture Items

{TABLE_HEADER}
{TABLE_SEPARATOR}
"""


def escape_cell(value: str) -> str:
    return " ".join(str(value or "").replace("|", "\\|").split())


def parse_capture_rows(markdown: str) -> list[dict[str, str]]:
    rows = []
    for line in markdown.splitlines():
        match = re.match(
            r"^\|\s*(CAP-\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*((?:\\\||[^|])*)\|\s*((?:\\\||[^|])*)\|\s*([^|]+)\|\s*([^|]+)\|\s*((?:\\\||[^|])*)\|$",
            line,
        )
        if match:
            values = [value.strip().replace("\\|", "|") for value in match.groups()]
            rows.append(dict(zip(("id", "status", "source kind", "source", "target", "node", "updated", "notes"), values)))
    return rows


def next_capture_id(rows: list[dict[str, str]]) -> str:
    highest = max(
        (int(match.group(1)) for row in rows if (match := re.fullmatch(r"CAP-(\d+)", row.get("id", "")))),
        default=0,
    )
    return f"CAP-{highest + 1:04d}"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:56] or "source"


def unique_child_slug(parent_slug: str, capture_id: str, source: str, parent: str) -> str:
    base = f"{parent_slug}/{capture_id.lower()}-{slugify(source)}"
    occupied = {row.get("node", "").strip("[]") for row in parse_capture_rows(parent)}
    if base not in occupied:
        return base
    suffix = 2
    while f"{base}-{suffix}" in occupied:
        suffix += 1
    return f"{base}-{suffix}"


def build_child(
    *, capture_id: str, child_slug: str, source: str, source_kind: str,
    instructions: str, target: str, collection: str, relationships: list[str],
    created_at: str, status: str, attachments: list[dict],
) -> str:
    attachment_lines = [
        f"- `{item['reference']}` | bytes={item['size_bytes']} | sha256={item['sha256']}"
        for item in attachments
    ] or ["- None"]
    relationship_lines = [f"- `{value}`" for value in relationships] or ["- None"]
    return f"""---
type: capture-request
title: Capture request {capture_id}
status: {status}
capture_id: {capture_id}
source_kind: {source_kind}
parent: {PARENT_SLUG}
created_at: '{created_at}'
updated_at: '{created_at}'
timezone: America/Los_Angeles
---

# Capture request {capture_id}

Status: {status}
Parent: [[{PARENT_SLUG}]]
Source: {source}
Target: {target or 'worker-selected'}
Collection: {collection or 'worker-selected'}

## Capture Instructions

{instructions}

## Requested Relationships

{chr(10).join(relationship_lines)}

## Durable Attachments

{chr(10).join(attachment_lines)}

## Attempt History

- {created_at}: queued by `/add-capture-link`; capture execution has not started.
"""


def invoke_capture_skill(*_args, **_kwargs):
    raise AssertionError("/add-capture-link is queue-only and must not invoke capture skills")


def validate_stargraph_url(value: str) -> str:
    parsed = parse.urlsplit(value.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise QueueFailure("Stargraph URL must be an HTTP(S) URL.")
    if parsed.username or parsed.password:
        raise QueueFailure("Credentials embedded in the Stargraph URL are not allowed.")
    return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _read_json_response(response) -> dict:
    raw = response.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AttachmentRequestError("Stargraph returned a non-JSON response.", {"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise AttachmentRequestError("Stargraph returned an invalid JSON object.")
    return payload


def check_stargraph_health(base_url: str) -> dict:
    try:
        with request.urlopen(f"{base_url}/api/health", timeout=10) as response:
            payload = _read_json_response(response)
    except (error.URLError, TimeoutError, AttachmentRequestError) as exc:
        if isinstance(exc, AttachmentRequestError):
            raise
        raise AttachmentRequestError(f"Stargraph health check failed: {exc}", {"error": str(exc)}) from exc
    if payload.get("ok") is not True:
        raise AttachmentRequestError("Stargraph health check did not report ok: true.", payload)
    return payload


def upload_attachment(base_url: str, slug: str, file_path: Path, description: str) -> dict:
    boundary = f"add-capture-link-{secrets.token_hex(12)}"
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = bytearray()
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="description"\r\n\r\n{description}\r\n'.encode())
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode()
    )
    body.extend(file_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    endpoint = f"{base_url}/api/entity-attach-file/{parse.quote(slug, safe='')}"
    req = request.Request(endpoint, data=bytes(body), method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with request.urlopen(req, timeout=120) as response:
            payload = _read_json_response(response)
    except error.HTTPError as exc:
        try:
            evidence = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, AttributeError):
            evidence = {"error": f"HTTP {exc.code}"}
        raise AttachmentRequestError(f"Attachment request failed with HTTP {exc.code}.", evidence, may_have_persisted=True) from exc
    except (error.URLError, TimeoutError, AttachmentRequestError) as exc:
        if isinstance(exc, AttachmentRequestError):
            exc.may_have_persisted = True
            raise
        raise AttachmentRequestError(f"Attachment request failed: {exc}", {"error": str(exc)}, may_have_persisted=True) from exc
    if payload.get("ok") is not True or payload.get("slug") != slug:
        raise AttachmentRequestError("Attachment response did not confirm the expected child slug.", payload, may_have_persisted=True)
    return payload


def sanitize_evidence(evidence: dict) -> dict:
    allowed = {"owner", "component", "code", "error_code", "error", "filenames", "cleanup_error"}
    sanitized = {}
    for key, value in evidence.items():
        if key not in allowed:
            continue
        if isinstance(value, str):
            value = re.sub(r"https?://[^\s]+", "[redacted-url]", value)[:1000]
        elif isinstance(value, list):
            value = [str(item)[:255] for item in value[:20]]
        elif not isinstance(value, (int, float, bool)) and value is not None:
            value = str(value)[:1000]
        sanitized[key] = value
    return sanitized or {"error": "Attachment queueing failed; detailed endpoint evidence was omitted."}


def durable_reference_candidates(payload: dict, child_slug: str, filename: str) -> list[str]:
    media = payload.get("local_media")
    if (
        not isinstance(media, dict)
        or media.get("durable_storage_verified") is not True
        or media.get("served_available") is not True
        or not isinstance(media.get("size_bytes"), int)
        or int(media.get("size_bytes")) < 0
        or not re.fullmatch(r"[0-9a-f]{64}", str(media.get("sha256") or ""))
    ):
        return []
    relative = str(media.get("canonical_relative_path") or f"{child_slug}/{filename}").strip("/")
    if not relative.startswith(f"{child_slug.strip('/')}/"):
        return []
    reported = str(media.get("served_url") or "").strip()
    served_path = parse.unquote(parse.urlsplit(reported).path).rstrip("/")
    if not reported or served_path != f"/media/{relative}".rstrip("/"):
        return []
    return [reported]


def _spool(paths: list[Path], slug_part: str, now: dt.datetime) -> tuple[Path, list[Path]]:
    stamp = now.astimezone(PACIFIC).strftime("%Y%m%dT%H%M%S%z")
    bundle = _ensure_recovery_root() / f"{stamp}-{slug_part}"
    suffix = 1
    while bundle.exists():
        bundle = bundle.with_name(f"{stamp}-{slug_part}-{suffix}")
        suffix += 1
    bundle.mkdir(parents=True, mode=0o700)
    os.chmod(bundle, 0o700)
    saved, used = [], set()
    for source in paths:
        name, counter = source.name, 1
        while name in used:
            name = f"{source.stem}-{counter}{source.suffix}"
            counter += 1
        used.add(name)
        target = bundle / name
        shutil.copyfile(source, target)
        os.chmod(target, 0o600)
        if target.read_bytes() != source.read_bytes():
            raise QueueFailure(f"Private spool byte verification failed for {source}.")
        saved.append(target)
    return bundle, saved


def _recovery_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    return codex_home / "recovery" / "add-capture-link"


def _ensure_recovery_root() -> Path:
    root = _recovery_root().expanduser()
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    return root.resolve()


@contextmanager
def _queue_lock():
    root = _ensure_recovery_root()
    lock_path = root / ".queue.lock"
    with lock_path.open("a+b") as lock_file:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _validated_recovery_manifest(raw_path: str | Path) -> Path:
    supplied = Path(raw_path).expanduser()
    if supplied.name != "recovery.json":
        raise QueueFailure("Recovery manifest must be named recovery.json.")
    try:
        root = _ensure_recovery_root()
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise QueueFailure(f"Could not resolve recovery manifest: {exc}") from exc
    if resolved.name != "recovery.json" or resolved.parent.parent != root or not resolved.is_file():
        raise QueueFailure("Recovery manifest must be recovery.json in a direct recovery-root child.")
    return resolved


def _remove_recovery_bundle(manifest_path: str | Path) -> None:
    validated = _validated_recovery_manifest(manifest_path)
    shutil.rmtree(validated.parent)


def _write_manifest(bundle: Path, data: dict) -> Path:
    path = bundle / "recovery.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def validate_inputs(source: str, source_kind: str, instructions: str, target: str, collection: str, relationships: list[str], attachments: list[str]) -> list[Path]:
    if not source.strip() or not instructions.strip():
        raise QueueFailure("Source and instructions must not be empty.")
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise QueueFailure(f"Unsupported source kind: {source_kind}")
    values = [source, target, collection, *relationships]
    if any("\n" in value or "\r" in value for value in values):
        raise QueueFailure("Source, target, collection, and relationships must be single-line values.")
    paths = []
    for raw in attachments:
        path = Path(raw).expanduser()
        if not path.is_file() or not os.access(path, os.R_OK):
            raise QueueFailure(f"Attachment is missing or unreadable: {path}")
        paths.append(path)
    return paths


def _get_optional(slug: str) -> str | None:
    try:
        return run_gbrain("get", slug)
    except NotFoundError:
        return None


def _put_verified(slug: str, markdown: str, marker: str) -> str:
    run_gbrain("put", slug, input_text=markdown)
    readback = run_gbrain("get", slug)
    if marker not in readback:
        raise RuntimeError(f"GBrain readback for {slug} did not contain {marker!r}")
    return readback


def _append_planned_row(parent: str, row: str, stamp: str) -> str:
    if TABLE_HEADER not in parent or TABLE_SEPARATOR not in parent:
        raise QueueFailure(f"Required capture table is missing from {PARENT_SLUG}.")
    updated = re.sub(r"(?m)^updated_at: '.*'$", f"updated_at: '{stamp}'", parent, count=1)
    lines = updated.splitlines()
    separator_index = lines.index(TABLE_SEPARATOR)
    insert_at = separator_index + 1
    while insert_at < len(lines) and lines[insert_at].startswith("| CAP-"):
        insert_at += 1
    lines.insert(insert_at, row)
    return "\n".join(lines).rstrip() + "\n"


def _link_verified(source: str, target: str, relation: str) -> None:
    try:
        run_gbrain("link", source, target, "--link-type", relation, "--link-source", "add-capture-link")
    except RuntimeError as exc:
        if "already" not in str(exc).lower():
            raise
    raw = run_gbrain("graph", source, "--depth", "1", "--link-type", relation, "--direction", "out")
    try:
        edges = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid graph readback for {source}") from exc
    if not any(
        edge.get("from_slug") == source and edge.get("to_slug") == target and edge.get("link_type") == relation
        for edge in edges if isinstance(edge, dict)
    ):
        raise RuntimeError(f"Graph readback missing {source} -[{relation}]-> {target}")


def _unlink_best_effort(source: str, target: str, relation: str) -> None:
    try:
        run_gbrain("unlink", source, target, "--link-type", relation)
    except RuntimeError:
        pass


def _trusted_served_url(base_url: str, served_url: str) -> str:
    trusted = parse.urlsplit(validate_stargraph_url(base_url))
    absolute = parse.urlsplit(parse.urljoin(f"{base_url.rstrip('/')}/", served_url))
    if (absolute.scheme, absolute.netloc) != (trusted.scheme, trusted.netloc):
        raise AttachmentRequestError(
            "Attachment served URL did not use the trusted Stargraph origin.",
            {"error": "served_url_cross_origin"},
            may_have_persisted=True,
        )
    return parse.urlunsplit(absolute)


def fetch_served_attachment(base_url: str, served_url: str) -> bytes:
    trusted_url = _trusted_served_url(base_url, served_url)
    try:
        with request.urlopen(trusted_url, timeout=120) as response:
            return response.read()
    except (error.URLError, TimeoutError) as exc:
        raise AttachmentRequestError(
            f"Could not fetch the served attachment: {exc}",
            {"error": "served_reference_unavailable"},
            may_have_persisted=True,
        ) from exc


def _verify_saved_receipt(receipt: dict, path: Path, base_url: str) -> dict:
    required = {"filename", "reference", "served_url", "size_bytes", "sha256"}
    if not isinstance(receipt, dict) or not required.issubset(receipt):
        raise AttachmentRequestError(
            "Saved attachment receipt is incomplete.", {"error": "saved_receipt_invalid"},
            may_have_persisted=True,
        )
    local_bytes = path.read_bytes()
    digest = hashlib.sha256(local_bytes).hexdigest()
    if (
        receipt["filename"] != path.name
        or receipt["reference"] != receipt["served_url"]
        or receipt["size_bytes"] != len(local_bytes)
        or receipt["sha256"] != digest
    ):
        raise AttachmentRequestError(
            "Saved attachment receipt does not match the recovery bytes.",
            {"error": "saved_receipt_integrity_mismatch", "filenames": [path.name]},
            may_have_persisted=True,
        )
    served_bytes = fetch_served_attachment(base_url, str(receipt["served_url"]))
    if len(served_bytes) != len(local_bytes) or hashlib.sha256(served_bytes).hexdigest() != digest:
        raise AttachmentRequestError(
            "Served attachment does not match the recovery bytes.",
            {"error": "served_integrity_mismatch", "filenames": [path.name]},
            may_have_persisted=True,
        )
    return dict(receipt)


def _receipt(payload: dict, child_slug: str, path: Path, base_url: str) -> dict:
    candidates = durable_reference_candidates(payload, child_slug, path.name)
    media = payload.get("local_media") if isinstance(payload, dict) else None
    local_bytes = path.read_bytes()
    digest = hashlib.sha256(local_bytes).hexdigest()
    if not candidates or not isinstance(media, dict):
        raise AttachmentRequestError("Attachment response did not report supported durable storage.", {"error": "durable_storage_missing", "filenames": [path.name]}, may_have_persisted=True)
    if media.get("size_bytes") != path.stat().st_size or media.get("sha256") != digest:
        raise AttachmentRequestError("Durable attachment byte or SHA-256 verification failed.", {"error": "durable_integrity_mismatch", "filenames": [path.name]}, may_have_persisted=True)
    served_url = candidates[0]
    served_bytes = fetch_served_attachment(base_url, served_url)
    if len(served_bytes) != len(local_bytes) or hashlib.sha256(served_bytes).hexdigest() != digest:
        raise AttachmentRequestError(
            "Served attachment byte or SHA-256 verification failed.",
            {"error": "served_integrity_mismatch", "filenames": [path.name]},
            may_have_persisted=True,
        )
    return {
        "filename": path.name,
        "reference": served_url,
        "served_url": served_url,
        "size_bytes": len(local_bytes),
        "sha256": digest,
    }


def _blocker(owner: str, evidence: dict, manifest: Path) -> dict:
    subject = "Memory Stargraph attachment capture" if owner == "Stargraph" else "GBrain attachment storage"
    return {
        "title": f"Repair {subject.lower()} failure",
        "owner": owner,
        "evidence": evidence,
        "acceptance_criteria": "Retry preserves exact attachment bytes and verifies durable byte count, SHA-256, parent, child, and graph readback.",
        "recovery_verification": f"Retry from {manifest}",
    }


def _failure_owner(evidence: dict) -> str:
    owner = str(evidence.get("owner") or evidence.get("component") or "").lower()
    code = str(evidence.get("code") or evidence.get("error_code") or "").lower()
    return "GBrain" if owner == "gbrain" or code.startswith("gbrain_") else "Stargraph"


def _preserve_input_failure(
    *, exc: QueueFailure, source: str, source_kind: str, instructions: str,
    attachments: list[str], target: str, collection: str, relationships: list[str],
    stargraph_url: str | None, now: dt.datetime,
) -> QueueFailure:
    readable = []
    for raw in attachments:
        path = Path(raw).expanduser()
        if path.is_file() and os.access(path, os.R_OK):
            readable.append(path)
    bundle, spooled = _spool(readable, slugify(source), now)
    manifest_path = bundle / "recovery.json"
    evidence = sanitize_evidence({"owner": "Stargraph", "error": str(exc)})
    remind_after = pacific_iso(now + dt.timedelta(days=1))
    blocker = _blocker(_failure_owner(evidence), evidence, manifest_path)
    retry_command = " ".join(
        shlex.quote(value)
        for value in (
            "python3", str(Path(__file__).resolve()), "--recovery-manifest",
            str(manifest_path), "--json",
        )
    )
    manifest_data = {
        "version": 2,
        "source": source,
        "source_kind": source_kind,
        "instructions": instructions,
        "target": target,
        "collection": collection,
        "relationships": relationships,
        "attachment_inputs": attachments,
        "attachments": [str(path) for path in spooled],
        "stargraph_url": stargraph_url or "",
        "receipts": [],
        "failure_evidence": evidence,
        "remind_after": remind_after,
        "proposed_blocker": blocker,
        "retry_command": retry_command,
    }
    _write_manifest(bundle, manifest_data)
    return QueueFailure(
        str(exc),
        {
            "ok": False,
            "error": str(exc),
            "parent_unchanged": True,
            "recovery_manifest": str(manifest_path),
            "proposed_blocker": blocker,
            "retry_command": retry_command,
            "reminder_required": True,
            "remind_after": remind_after,
        },
    )


def queue_capture(
    *, source: str = "", source_kind: str = "", instructions: str = "",
    attachments: list[str] | None = None, target: str = "", collection: str = "",
    relationships: list[str] | None = None, stargraph_url: str | None = None,
    recovery_manifest: str | None = None, now: dt.datetime | None = None,
) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    attachment_values = list(attachments or [])
    relationship_values = list(relationships or [])
    with _queue_lock():
        try:
            return _queue_capture_locked(
                source=source, source_kind=source_kind, instructions=instructions,
                attachments=attachment_values, target=target, collection=collection,
                relationships=relationship_values, stargraph_url=stargraph_url,
                recovery_manifest=recovery_manifest, now=now,
            )
        except QueueFailure as exc:
            if recovery_manifest or exc.result.get("recovery_manifest"):
                raise
            raise _preserve_input_failure(
                exc=exc, source=source, source_kind=source_kind, instructions=instructions,
                attachments=attachment_values, target=target, collection=collection,
                relationships=relationship_values, stargraph_url=stargraph_url, now=now,
            ) from exc


def _queue_capture_locked(
    *, source: str, source_kind: str, instructions: str, attachments: list[str],
    target: str, collection: str, relationships: list[str], stargraph_url: str | None,
    recovery_manifest: str | None, now: dt.datetime,
) -> dict:
    prior: dict = {}
    manifest_path: Path | None = None
    if recovery_manifest:
        manifest_path = _validated_recovery_manifest(recovery_manifest)
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(prior, dict):
                raise TypeError("manifest is not an object")
            source = prior["source"]
            source_kind = prior["source_kind"]
            instructions = prior["instructions"]
            target = prior.get("target", "")
            collection = prior.get("collection", "")
            relationships = list(prior.get("relationships", []))
            attachments = list(prior.get("attachments", []))
            stargraph_url = prior.get("stargraph_url") or stargraph_url
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise QueueFailure(f"Could not read recovery manifest: {exc}") from exc

    paths = validate_inputs(
        source, source_kind, instructions, target, collection, relationships, attachments
    )
    stamp = pacific_iso(now)
    if manifest_path:
        bundle, spooled = manifest_path.parent, paths
    else:
        bundle, spooled = _spool(paths, slugify(source), now)
        manifest_path = bundle / "recovery.json"

    effective_base = stargraph_url or os.environ.get("MEMORY_STARGRAPH_UPLOAD_URL") or os.environ.get("MEMORY_STARGRAPH_URL") or DEFAULT_STARGRAPH_URL
    manifest_data = {
        "version": 2,
        "source": source,
        "source_kind": source_kind,
        "instructions": instructions,
        "target": target,
        "collection": collection,
        "relationships": relationships,
        "attachments": [str(path) for path in spooled],
        "stargraph_url": effective_base,
        "receipts": list(prior.get("receipts", [])),
    }
    for key in ("capture_id", "child_slug", "remind_after"):
        if prior.get(key):
            manifest_data[key] = prior[key]
    _write_manifest(bundle, manifest_data)

    parent: str | None = None
    capture_id = str(prior.get("capture_id") or "")
    child_slug = str(prior.get("child_slug") or "")
    provisional = ""
    receipts: list[dict] = []
    parent_written = False
    child_finalized = False
    evidence: dict = {}
    try:
        parent = run_gbrain("get", PARENT_SLUG)
        rows = parse_capture_rows(parent)
        capture_id = capture_id or next_capture_id(rows)
        child_slug = child_slug or unique_child_slug(PARENT_SLUG, capture_id, source, parent)
        manifest_data.update(capture_id=capture_id, child_slug=child_slug)
        _write_manifest(bundle, manifest_data)
        if any(row["id"] == capture_id or row["node"] == f"[[{child_slug}]]" for row in rows):
            raise QueueFailure(f"Capture ID or child is already planned: {capture_id}")

        provisional = build_child(
            capture_id=capture_id, child_slug=child_slug, source=source, source_kind=source_kind,
            instructions=instructions, target=target, collection=collection,
            relationships=relationships, created_at=stamp, status="capture-recovery",
            attachments=[],
        )
        existing = _get_optional(child_slug)
        if existing is not None and not (prior and "status: capture-recovery" in existing):
            raise QueueFailure(f"Capture child slug is occupied: {child_slug}")
        if existing is None:
            _put_verified(child_slug, provisional, "status: capture-recovery")

        if spooled:
            base_url = validate_stargraph_url(effective_base)
            check_stargraph_health(base_url)
            saved_by_name = {
                item.get("filename"): item
                for item in manifest_data.get("receipts", [])
                if isinstance(item, dict) and item.get("filename")
            }
            for path in spooled:
                saved = saved_by_name.get(path.name)
                if saved is not None:
                    receipt = _verify_saved_receipt(saved, path, base_url)
                else:
                    try:
                        payload = upload_attachment(
                            base_url, child_slug, path, f"Attachment for {capture_id}"
                        )
                    except AttachmentRequestError as exc:
                        evidence = exc.evidence
                        raise
                    receipt = _receipt(payload, child_slug, path, base_url)
                receipts.append(receipt)
                manifest_data["receipts"] = list(receipts)
                _write_manifest(bundle, manifest_data)

        final_child = build_child(
            capture_id=capture_id, child_slug=child_slug, source=source, source_kind=source_kind,
            instructions=instructions, target=target, collection=collection,
            relationships=relationships, created_at=stamp, status="planned",
            attachments=receipts,
        )
        _put_verified(child_slug, final_child, "status: planned")
        child_finalized = True
        note = f"{len(receipts)} durable attachment(s)" if receipts else "queued; capture not started"
        row = (
            f"| {capture_id} | planned | {escape_cell(source_kind)} | {escape_cell(source)} | "
            f"{escape_cell(target)} | [[{child_slug}]] | {stamp} | {escape_cell(note)} |"
        )
        final_parent = _append_planned_row(parent, row, stamp)
        parent_written = True
        _put_verified(PARENT_SLUG, final_parent, f"| {capture_id} | planned |")
        _link_verified(PARENT_SLUG, child_slug, "has_capture_request")
        _link_verified(child_slug, PARENT_SLUG, "capture_request_for")
        verified_child = run_gbrain("get", child_slug)
        if any(receipt["reference"] not in verified_child for receipt in receipts):
            raise RuntimeError("Final child receipt readback failed")
        _remove_recovery_bundle(manifest_path)
        return {
            "ok": True,
            "capture_id": capture_id,
            "child_slug": child_slug,
            "status": "planned",
            "attachments": receipts,
            "durable_storage_verified": True,
            "graph_verified": True,
        }
    except (AttachmentRequestError, RuntimeError, QueueFailure) as exc:
        if isinstance(exc, AttachmentRequestError):
            evidence = evidence or exc.evidence
        else:
            evidence = {"owner": "gbrain", "error": str(exc)}
        if parent is not None and (parent_written or child_finalized):
            try:
                _unlink_best_effort(PARENT_SLUG, child_slug, "has_capture_request")
                _unlink_best_effort(child_slug, PARENT_SLUG, "capture_request_for")
                if parent_written:
                    run_gbrain("put", PARENT_SLUG, input_text=parent)
                if provisional:
                    run_gbrain("put", child_slug, input_text=provisional)
            except RuntimeError:
                evidence["cleanup_error"] = "Could not restore the provisional transaction state."
        evidence = sanitize_evidence(evidence)
        remind_after = pacific_iso(now + dt.timedelta(days=1))
        blocker = _blocker(_failure_owner(evidence), evidence, manifest_path)
        retry_command = " ".join(
            shlex.quote(value)
            for value in (
                "python3", str(Path(__file__).resolve()), "--recovery-manifest",
                str(manifest_path), "--json",
            )
        )
        manifest_data.update(
            failure_evidence=evidence,
            remind_after=remind_after,
            proposed_blocker=blocker,
            retry_command=retry_command,
            receipts=list(receipts or manifest_data.get("receipts", [])),
        )
        if capture_id:
            manifest_data["capture_id"] = capture_id
        if child_slug:
            manifest_data["child_slug"] = child_slug
        _write_manifest(bundle, manifest_data)
        parent_unchanged = False
        if parent is not None:
            try:
                parent_unchanged = run_gbrain("get", PARENT_SLUG) == parent
            except RuntimeError:
                parent_unchanged = False
        result = {
            "ok": False,
            "error": str(exc),
            "capture_id": capture_id or None,
            "child_slug": child_slug or None,
            "parent_unchanged": parent_unchanged,
            "recovery_manifest": str(manifest_path),
            "proposed_blocker": blocker,
            "retry_command": retry_command,
            "reminder_required": True,
            "remind_after": remind_after,
        }
        raise QueueFailure(str(exc), result) from exc


def _print_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        for key in ("capture_id", "child_slug", "status"):
            if key in result:
                print(f"{key}={result[key]}")
        if not result.get("ok", True):
            print(f"error={result.get('error', 'queue failed')}", file=sys.stderr)
            print(f"recovery_manifest={result.get('recovery_manifest', '')}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source")
    parser.add_argument("--source-kind", choices=sorted(ALLOWED_SOURCE_KINDS))
    parser.add_argument("--instructions")
    parser.add_argument("--attachment", action="append", default=[])
    parser.add_argument("--target", default="")
    parser.add_argument("--collection", default="")
    parser.add_argument("--relationship", action="append", default=[])
    parser.add_argument("--stargraph-url")
    parser.add_argument("--recovery-manifest", help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.recovery_manifest and not all((args.source, args.source_kind, args.instructions)):
        parser.error("--source, --source-kind, and --instructions are required unless --recovery-manifest is used")
    try:
        result = queue_capture(
            source=args.source or "", source_kind=args.source_kind or "", instructions=args.instructions or "",
            attachments=args.attachment, target=args.target, collection=args.collection,
            relationships=args.relationship, stargraph_url=args.stargraph_url,
            recovery_manifest=args.recovery_manifest,
        )
        _print_result(result, args.json)
        return 0
    except QueueFailure as exc:
        _print_result(exc.result, args.json)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
