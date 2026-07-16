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
import tempfile
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


def capture_idempotency_key(source: str, now: dt.datetime) -> str:
    seed = f"{pacific_iso(now)}\0{source}\0{secrets.token_hex(16)}".encode("utf-8")
    return f"add-capture-link.{hashlib.sha256(seed).hexdigest()}"


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


def queue_authority_request(base_url: str, action: str, payload: dict) -> dict:
    if action not in {"reserve", "finalize"}:
        raise QueueFailure(f"Unsupported queue authority action: {action}")
    endpoint = f"{base_url}/api/capture-queue/{action}"
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            result = _read_json_response(response)
    except error.HTTPError as exc:
        try:
            evidence = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, AttributeError):
            evidence = {"error": f"HTTP {exc.code}"}
        raise AttachmentRequestError(
            f"Capture queue {action} failed with HTTP {exc.code}.", evidence,
            may_have_persisted=True,
        ) from exc
    except (error.URLError, TimeoutError, AttachmentRequestError) as exc:
        if isinstance(exc, AttachmentRequestError):
            raise
        raise AttachmentRequestError(
            f"Capture queue {action} request failed: {exc}", {"error": str(exc)},
            may_have_persisted=True,
        ) from exc
    if result.get("ok") is not True or not result.get("capture_id") or not result.get("child_slug"):
        raise AttachmentRequestError(
            f"Capture queue {action} response was incomplete.", result,
            may_have_persisted=True,
        )
    return result


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
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    return codex_home / "recovery" / "add-capture-link"


def _reject_symlink(path: Path, label: str) -> None:
    try:
        if path.is_symlink():
            raise QueueFailure(f"{label} must not be a symlink: {path}")
    except OSError as exc:
        raise QueueFailure(f"Could not inspect {label}: {exc}") from exc


def _codex_home() -> Path:
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    home.mkdir(parents=True, mode=0o700, exist_ok=True)
    return home.resolve(strict=True)


def _ensure_recovery_root() -> Path:
    home = _codex_home()
    recovery = home / "recovery"
    _reject_symlink(recovery, "recovery directory")
    recovery.mkdir(mode=0o700, exist_ok=True)
    _reject_symlink(recovery, "recovery directory")
    root = recovery / "add-capture-link"
    _reject_symlink(root, "recovery root")
    root.mkdir(mode=0o700, exist_ok=True)
    _reject_symlink(root, "recovery root")
    resolved = root.resolve(strict=True)
    if resolved.parent.parent != home:
        raise QueueFailure("Recovery root must remain beneath CODEX_HOME.")
    os.chmod(root, 0o700)
    return resolved


@contextmanager
def _queue_lock():
    root = _ensure_recovery_root()
    lock_path = root / ".queue.lock"
    _reject_symlink(lock_path, "queue lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise QueueFailure(f"Could not open queue lock safely: {exc}") from exc
    with os.fdopen(descriptor, "a+b") as lock_file:
        _reject_symlink(lock_path, "queue lock")
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
    _reject_symlink(supplied, "recovery manifest")
    _reject_symlink(supplied.parent, "recovery bundle")
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
    _reject_symlink(validated, "recovery manifest")
    _reject_symlink(validated.parent, "recovery bundle")
    shutil.rmtree(validated.parent)


def _write_manifest(bundle: Path, data: dict) -> Path:
    _reject_symlink(bundle, "recovery bundle")
    path = bundle / "recovery.json"
    _reject_symlink(path, "recovery manifest")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=bundle, prefix=".recovery.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(bundle, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
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


class _NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_served_attachment(base_url: str, served_url: str) -> bytes:
    current = _trusted_served_url(base_url, served_url)
    opener = request.build_opener(_NoRedirectHandler())
    for _hop in range(6):
        try:
            with opener.open(current, timeout=120) as response:
                final_url = response.geturl() if hasattr(response, "geturl") else current
                _trusted_served_url(base_url, final_url)
                return response.read()
        except error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise AttachmentRequestError(
                    f"Could not fetch the served attachment: HTTP {exc.code}",
                    {"error": "served_reference_unavailable"},
                    may_have_persisted=True,
                ) from exc
            location = exc.headers.get("Location") if exc.headers else None
            if not location:
                raise AttachmentRequestError(
                    "Served attachment redirect omitted Location.",
                    {"error": "served_redirect_invalid"},
                    may_have_persisted=True,
                ) from exc
            current = _trusted_served_url(base_url, parse.urljoin(current, location))
        except (error.URLError, TimeoutError) as exc:
            raise AttachmentRequestError(
                f"Could not fetch the served attachment: {exc}",
                {"error": "served_reference_unavailable"},
                may_have_persisted=True,
            ) from exc
    raise AttachmentRequestError(
        "Served attachment exceeded the redirect limit.",
        {"error": "served_redirect_limit"},
        may_have_persisted=True,
    )


def _verify_saved_receipt(receipt: dict, path: Path, base_url: str) -> dict:
    required = {"filename", "reference", "served_url", "canonical_relative_path", "size_bytes", "sha256"}
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
    reported_url = candidates[0]
    relative = str(media.get("canonical_relative_path") or "").strip("/")
    served_url = f"/media/{parse.quote(relative, safe='/')}"
    served_bytes = fetch_served_attachment(base_url, reported_url)
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
        "canonical_relative_path": relative,
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

    paths = validate_inputs(source, source_kind, instructions, target, collection, relationships, attachments)
    if prior:
        attachment_inputs = prior.get("attachment_inputs")
        if not isinstance(attachment_inputs, list) or len(attachment_inputs) != len(paths):
            raise QueueFailure("Recovery manifest does not preserve one readable spool file for every attachment input.")
    if manifest_path:
        bundle, spooled = manifest_path.parent, paths
    else:
        bundle, spooled = _spool(paths, slugify(source), now)
        manifest_path = bundle / "recovery.json"

    effective_base = stargraph_url or os.environ.get("MEMORY_STARGRAPH_UPLOAD_URL") or os.environ.get("MEMORY_STARGRAPH_URL") or DEFAULT_STARGRAPH_URL
    idempotency_key = str(prior.get("idempotency_key") or capture_idempotency_key(source, now))
    manifest_data = {
        "version": 3,
        "source": source,
        "source_kind": source_kind,
        "instructions": instructions,
        "target": target,
        "collection": collection,
        "relationships": relationships,
        "attachment_inputs": list(prior.get("attachment_inputs", attachments)),
        "attachments": [str(path) for path in spooled],
        "stargraph_url": effective_base,
        "idempotency_key": idempotency_key,
        "receipts": list(prior.get("receipts", [])),
        "attachment_progress": list(prior.get("attachment_progress", [])),
    }
    for key in ("capture_id", "child_slug", "remind_after"):
        if prior.get(key):
            manifest_data[key] = prior[key]
    _write_manifest(bundle, manifest_data)

    capture_id = str(prior.get("capture_id") or "")
    child_slug = str(prior.get("child_slug") or "")
    receipts: list[dict] = []
    evidence: dict = {}
    try:
        base_url = validate_stargraph_url(effective_base)
        check_stargraph_health(base_url)
        reservation = queue_authority_request(base_url, "reserve", {
            "idempotency_key": idempotency_key,
            "source": source,
            "source_kind": source_kind,
            "instructions": instructions,
            "target": target,
            "collection": collection,
            "relationships": relationships,
        })
        authoritative_id = str(reservation["capture_id"])
        authoritative_slug = str(reservation["child_slug"])
        if (capture_id and capture_id != authoritative_id) or (child_slug and child_slug != authoritative_slug):
            raise QueueFailure("Server reservation does not match the preserved recovery identity.")
        capture_id, child_slug = authoritative_id, authoritative_slug
        manifest_data.update(capture_id=capture_id, child_slug=child_slug)
        progress_by_name = {
            item.get("filename"): dict(item)
            for item in manifest_data.get("attachment_progress", [])
            if isinstance(item, dict) and item.get("filename")
        }
        for path in spooled:
            progress = progress_by_name.setdefault(path.name, {
                "filename": path.name,
                "expected_canonical_relative_path": f"{child_slug}/{path.name}",
                "ambiguous_persistence": False,
                "upload_started": False,
            })
        manifest_data["attachment_progress"] = list(progress_by_name.values())
        _write_manifest(bundle, manifest_data)

        saved_by_name = {
            item.get("filename"): item
            for item in manifest_data.get("receipts", [])
            if isinstance(item, dict) and item.get("filename")
        }
        for path in spooled:
            saved = saved_by_name.get(path.name)
            progress = progress_by_name[path.name]
            expected_relative = str(progress["expected_canonical_relative_path"])
            expected_url = f"/media/{parse.quote(expected_relative, safe='/')}"
            if saved is not None:
                receipt = _verify_saved_receipt(saved, path, base_url)
            else:
                hosted = None
                if prior:
                    try:
                        hosted = fetch_served_attachment(base_url, expected_url)
                    except AttachmentRequestError:
                        if progress.get("ambiguous_persistence") or progress.get("upload_started"):
                            raise AttachmentRequestError(
                                "Ambiguous upload could not be reconciled at its expected canonical path.",
                                {"error": "ambiguous_upload_unavailable", "filenames": [path.name]},
                                may_have_persisted=True,
                            )
                if hosted is not None:
                    local = path.read_bytes()
                    digest = hashlib.sha256(local).hexdigest()
                    if len(hosted) != len(local) or hashlib.sha256(hosted).hexdigest() != digest:
                        raise AttachmentRequestError(
                            "Hosted bytes at the expected canonical path do not match the recovery spool.",
                            {"error": "ambiguous_upload_integrity_mismatch", "filenames": [path.name]},
                            may_have_persisted=True,
                        )
                    receipt = {
                        "filename": path.name,
                        "reference": expected_url,
                        "served_url": expected_url,
                        "canonical_relative_path": expected_relative,
                        "size_bytes": len(local),
                        "sha256": digest,
                    }
                else:
                    progress["upload_started"] = True
                    manifest_data["attachment_progress"] = list(progress_by_name.values())
                    _write_manifest(bundle, manifest_data)
                    try:
                        payload = upload_attachment(base_url, child_slug, path, f"Attachment for {capture_id}")
                    except AttachmentRequestError as exc:
                        evidence = exc.evidence
                        if exc.may_have_persisted:
                            progress["ambiguous_persistence"] = True
                            manifest_data["attachment_progress"] = list(progress_by_name.values())
                            _write_manifest(bundle, manifest_data)
                        raise
                    receipt = _receipt(payload, child_slug, path, base_url)
            receipts.append(receipt)
            manifest_data["receipts"] = list(receipts)
            progress["ambiguous_persistence"] = False
            progress["upload_started"] = False
            manifest_data["attachment_progress"] = list(progress_by_name.values())
            _write_manifest(bundle, manifest_data)

        finalized = queue_authority_request(base_url, "finalize", {
            "idempotency_key": idempotency_key,
            "attachments": receipts,
        })
        if str(finalized["capture_id"]) != capture_id or str(finalized["child_slug"]) != child_slug or finalized.get("status") not in {"planned", "finalized"}:
            raise AttachmentRequestError(
                "Capture queue finalize response did not match the reservation.", finalized,
                may_have_persisted=True,
            )
        _remove_recovery_bundle(manifest_path)
        return {
            "ok": True,
            "capture_id": capture_id,
            "child_slug": child_slug,
            "status": "planned",
            "attachments": receipts,
            "durable_storage_verified": True,
            "graph_verified": finalized.get("graph_verified") is True,
        }
    except (AttachmentRequestError, RuntimeError, QueueFailure) as exc:
        if isinstance(exc, AttachmentRequestError):
            evidence = evidence or exc.evidence
        else:
            evidence = {"owner": "gbrain", "error": str(exc)}
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
        result = {
            "ok": False,
            "error": str(exc),
            "capture_id": capture_id or None,
            "child_slug": child_slug or None,
            "parent_unchanged": True,
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
