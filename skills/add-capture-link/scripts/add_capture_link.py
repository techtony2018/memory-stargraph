#!/usr/bin/env python3
"""Queue source material for the persistent Memory Stargraph Capture Link worker."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
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
        or not isinstance(media.get("size_bytes"), int)
        or int(media.get("size_bytes")) < 0
        or not re.fullmatch(r"[0-9a-f]{64}", str(media.get("sha256") or ""))
    ):
        return []
    relative = str(media.get("canonical_relative_path") or f"{child_slug}/{filename}").strip("/")
    if not relative.startswith(f"{child_slug.strip('/')}/"):
        return []
    forms = (relative, f"/media/{relative}", f"gbrain:files/{relative}")
    reported = str(media.get("served_url") or "").strip()
    if reported not in forms:
        return []
    return [reported, *[value for value in forms if value != reported]]


def _spool(paths: list[Path], slug_part: str, now: dt.datetime) -> tuple[Path, list[Path]]:
    stamp = now.astimezone(PACIFIC).strftime("%Y%m%dT%H%M%S%z")
    bundle = _recovery_root() / f"{stamp}-{slug_part}"
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


def _receipt(payload: dict, child_slug: str, path: Path) -> dict:
    candidates = durable_reference_candidates(payload, child_slug, path.name)
    media = payload.get("local_media") if isinstance(payload, dict) else None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not candidates or not isinstance(media, dict):
        raise AttachmentRequestError("Attachment response did not report supported durable storage.", {"error": "durable_storage_missing", "filenames": [path.name]}, may_have_persisted=True)
    if media.get("size_bytes") != path.stat().st_size or media.get("sha256") != digest:
        raise AttachmentRequestError("Durable attachment byte or SHA-256 verification failed.", {"error": "durable_integrity_mismatch", "filenames": [path.name]}, may_have_persisted=True)
    return {"filename": path.name, "reference": candidates[0], "size_bytes": path.stat().st_size, "sha256": digest}


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


def queue_capture(
    *, source: str = "", source_kind: str = "", instructions: str = "",
    attachments: list[str] | None = None, target: str = "", collection: str = "",
    relationships: list[str] | None = None, stargraph_url: str | None = None,
    recovery_manifest: str | None = None, now: dt.datetime | None = None,
) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    retry_bundle = None
    prior = None
    if recovery_manifest:
        manifest_path = Path(recovery_manifest).expanduser()
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise QueueFailure(f"Could not read recovery manifest: {exc}") from exc
        source = prior["source"]
        source_kind = prior["source_kind"]
        instructions = prior["instructions"]
        target = prior.get("target", "")
        collection = prior.get("collection", "")
        relationships = prior.get("relationships", [])
        attachments = prior.get("attachments", [])
        retry_bundle = manifest_path.parent
    relationships = list(relationships or [])
    paths = validate_inputs(source, source_kind, instructions, target, collection, relationships, list(attachments or []))
    stamp = pacific_iso(now)
    if retry_bundle:
        bundle, spooled = retry_bundle, paths
    elif paths:
        bundle, spooled = _spool(paths, slugify(source), now)
    else:
        bundle, spooled = None, []

    parent = run_gbrain("get", PARENT_SLUG)
    rows = parse_capture_rows(parent)
    capture_id = prior.get("capture_id") if prior else next_capture_id(rows)
    child_slug = prior.get("child_slug") if prior else unique_child_slug(PARENT_SLUG, capture_id, source, parent)
    if any(row["id"] == capture_id or row["node"] == f"[[{child_slug}]]" for row in rows):
        raise QueueFailure(f"Capture ID or child is already planned: {capture_id}")

    provisional = build_child(
        capture_id=capture_id, child_slug=child_slug, source=source, source_kind=source_kind,
        instructions=instructions, target=target, collection=collection, relationships=relationships,
        created_at=stamp, status="capture-recovery", attachments=[],
    )
    receipts: list[dict] = []
    parent_written = False
    evidence: dict = {}
    try:
        existing = _get_optional(child_slug)
        if existing is not None and not (prior and "status: capture-recovery" in existing):
            raise QueueFailure(f"Capture child slug is occupied: {child_slug}")
        if existing is None:
            _put_verified(child_slug, provisional, "status: capture-recovery")
        if spooled:
            base_url = validate_stargraph_url(stargraph_url or os.environ.get("MEMORY_STARGRAPH_UPLOAD_URL") or os.environ.get("MEMORY_STARGRAPH_URL") or DEFAULT_STARGRAPH_URL)
            check_stargraph_health(base_url)
            for path in spooled:
                try:
                    payload = upload_attachment(base_url, child_slug, path, f"Attachment for {capture_id}")
                except AttachmentRequestError as exc:
                    evidence = exc.evidence
                    raise
                receipts.append(_receipt(payload, child_slug, path))
            attached = run_gbrain("get", child_slug)
            missing = [receipt["filename"] for receipt in receipts if receipt["reference"] not in attached]
            if missing:
                raise AttachmentRequestError("Durable references were not found in the child readback.", {"error": "durable_reference_missing", "filenames": missing}, may_have_persisted=True)

        final_child = build_child(
            capture_id=capture_id, child_slug=child_slug, source=source, source_kind=source_kind,
            instructions=instructions, target=target, collection=collection, relationships=relationships,
            created_at=stamp, status="planned", attachments=receipts,
        )
        _put_verified(child_slug, final_child, "status: planned")
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
        if bundle:
            shutil.rmtree(bundle)
        return {
            "ok": True, "capture_id": capture_id, "child_slug": child_slug,
            "status": "planned", "attachments": receipts,
            "durable_storage_verified": all(receipts) if receipts else True,
            "graph_verified": True,
        }
    except (AttachmentRequestError, RuntimeError, QueueFailure) as exc:
        if isinstance(exc, AttachmentRequestError):
            evidence = evidence or exc.evidence
        else:
            evidence = {"owner": "gbrain", "error": str(exc)}
        if parent_written:
            try:
                _unlink_best_effort(PARENT_SLUG, child_slug, "has_capture_request")
                _unlink_best_effort(child_slug, PARENT_SLUG, "capture_request_for")
                run_gbrain("put", PARENT_SLUG, input_text=parent)
                run_gbrain("put", child_slug, input_text=provisional)
            except RuntimeError:
                evidence["cleanup_error"] = "Could not restore the provisional transaction state."
        if bundle is None:
            raise QueueFailure(str(exc)) from exc
        evidence = sanitize_evidence(evidence)
        remind_after = pacific_iso(now + dt.timedelta(days=1))
        manifest_data = {
            "version": 1, "source": source, "source_kind": source_kind,
            "instructions": instructions, "target": target, "collection": collection,
            "relationships": relationships, "capture_id": capture_id, "child_slug": child_slug,
            "attachments": [str(path) for path in spooled], "failure_evidence": evidence,
            "remind_after": remind_after,
        }
        manifest_path = bundle / "recovery.json"
        blocker = _blocker(_failure_owner(evidence), evidence, manifest_path)
        retry_command = f"python3 {Path(__file__).resolve()} --recovery-manifest {manifest_path} --json"
        manifest_data.update(proposed_blocker=blocker, retry_command=retry_command)
        _write_manifest(bundle, manifest_data)
        result = {
            "ok": False, "error": str(exc), "capture_id": capture_id,
            "child_slug": child_slug, "parent_unchanged": run_gbrain("get", PARENT_SLUG) == parent,
            "recovery_manifest": str(manifest_path), "proposed_blocker": blocker,
            "retry_command": retry_command, "reminder_required": True, "remind_after": remind_after,
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
