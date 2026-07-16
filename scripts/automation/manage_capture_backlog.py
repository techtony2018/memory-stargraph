#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import functools
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.automation.backlog_compaction import (
    BacklogSpec,
    CompactionPlan,
    item_number,
    node_slug,
    parse_rows,
    plan_compaction,
    render_table,
    replace_root_table,
)


ROOT_SLUG = "notes/memory-starmap-capture-list"
FAILED_COLLECTION_SLUG = f"{ROOT_SLUG}/failed-items"
ARCHIVE_PREFIX = f"{ROOT_SLUG}/completed-archive-"
ALLOWED_STATUSES = {"planned", "capturing", "completed", "failed"}
PACIFIC = ZoneInfo("America/Los_Angeles")
DEFAULT_STARGRAPH_URL = "http://127.0.0.1:8788"
CAPTURE_SPEC = BacklogSpec(
    root_slug=ROOT_SLUG,
    section_heading="Capture Items",
    columns=("id", "status", "source kind", "source", "target", "node", "updated", "notes"),
    completed_status="completed",
    archive_size=50,
    archive_prefix=ARCHIVE_PREFIX,
)


def pacific_iso(now: dt.datetime | None = None) -> str:
    value = now or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(PACIFIC).replace(microsecond=0).isoformat()


def _queue_authority_post(path: str, payload: dict[str, object]) -> dict[str, object]:
    base = os.environ.get("MEMORY_STARGRAPH_URL", DEFAULT_STARGRAPH_URL).rstrip("/")
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(base + path, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"capture queue authority HTTP {exc.code}: {detail}") from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"capture queue authority unavailable: {exc}") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("capture queue authority returned an invalid response")
    return result


@contextmanager
def queue_authority_lease(operation: str):
    owner = f"manage-capture-backlog:{os.getpid()}:{operation}:{uuid.uuid4()}"
    lease = None
    last_error = None
    for delay in (0.0, 0.1, 0.25):
        if delay:
            time.sleep(delay)
        try:
            lease = _queue_authority_post(
                "/api/capture-queue/lease/acquire",
                {"owner": owner, "ttl_seconds": 300},
            )
            break
        except RuntimeError as exc:
            last_error = exc
    if lease is None:
        raise RuntimeError(f"could not acquire capture queue authority lease: {last_error}")
    body_error = None
    try:
        yield lease
    except BaseException as exc:  # preserve the operation failure if release also fails
        body_error = exc
        raise
    finally:
        try:
            _queue_authority_post(
                "/api/capture-queue/lease/release",
                {"owner": owner, "token": lease["token"]},
            )
        except Exception:
            if body_error is None:
                raise


def _uses_queue_authority(operation: str):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            with queue_authority_lease(operation):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def build_root(now: dt.datetime | None = None) -> str:
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

{render_table([], CAPTURE_SPEC)}
"""


def build_failed_collection(rows: list[dict[str, str]], now: dt.datetime | None = None) -> str:
    stamp = pacific_iso(now)
    return f"""---
type: collection
title: Memory Starmap Failed Capture Items
status: active
timezone: America/Los_Angeles
updated_at: '{stamp}'
---

# Memory Starmap Failed Capture Items

Root backlog: [[{ROOT_SLUG}]]

This is a synchronized current-state view. Failed requests remain active until explicitly requeued or resolved.

## Capture Items

{render_table(rows, CAPTURE_SPEC)}
"""


def build_archive(
    slug: str,
    sequence: int,
    rows: list[dict[str, str]],
    now: dt.datetime | None = None,
) -> str:
    if not rows:
        raise ValueError("archive requires at least one row")
    stamp = pacific_iso(now)
    return f"""---
type: collection
title: Memory Starmap Completed Capture Archive {sequence:04d}
status: immutable
timezone: America/Los_Angeles
captured_at: '{stamp}'
---

# Memory Starmap Completed Capture Archive {sequence:04d}

Root backlog: [[{ROOT_SLUG}]]

## Summary

- Archive slug: `{slug}`
- Completed capture count: {len(rows)}
- First capture: `{rows[0]["id"]}`
- Last capture: `{rows[-1]["id"]}`

## Capture Items

{render_table(rows, CAPTURE_SPEC)}
"""


def parse_capture_rows(markdown: str) -> list[dict[str, str]]:
    rows = parse_rows(markdown, CAPTURE_SPEC)
    validate_capture_rows(rows)
    return rows


def validate_capture_rows(rows: list[dict[str, str]]) -> None:
    for row in rows:
        status = row.get("status", "")
        if status not in ALLOWED_STATUSES:
            raise ValueError(
                f"unsupported stored status {status or 'missing'} for {row.get('id') or 'unknown capture'}"
            )


def parse_archive_index(markdown: str) -> list[dict[str, object]]:
    pattern = re.compile(
        rf"^\| \[\[({re.escape(ARCHIVE_PREFIX)}\d{{4}})\]\] \| (\d+) \| ([^|]+) \| ([^|]+) \| (\d+) \|$",
        re.MULTILINE,
    )
    return [
        {
            "slug": match.group(1),
            "sequence": int(match.group(2)),
            "first_id": match.group(3).strip(),
            "last_id": match.group(4).strip(),
            "count": int(match.group(5)),
        }
        for match in pattern.finditer(markdown)
    ]


def replace_capture_table(
    markdown: str,
    rows: list[dict[str, str]],
    archive_index: list[dict[str, object]] | None = None,
) -> str:
    preserved_index = parse_archive_index(markdown) if archive_index is None else archive_index
    return replace_root_table(markdown, rows, preserved_index, CAPTURE_SPEC)


def freeze_snapshot(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    validate_capture_rows(rows)
    return sorted((dict(row) for row in rows if row.get("status") == "planned"), key=item_number)


def transition(
    markdown: str,
    capture_id: str,
    expected: str,
    target: str,
    updated: str,
    notes: str,
) -> str:
    if expected not in ALLOWED_STATUSES or target not in ALLOWED_STATUSES:
        raise ValueError("unsupported status")
    rows = parse_capture_rows(markdown)
    matches = [row for row in rows if row.get("id") == capture_id]
    if len(matches) != 1:
        raise ValueError(f"expected one row for {capture_id}, found {len(matches)}")
    row = matches[0]
    if row["status"] != expected:
        raise ValueError(f"expected {expected}, found {row['status']}")
    row.update(status=target, updated=updated, notes=notes)
    return replace_capture_table(markdown, rows)


def fixture_root(capture_id: str, status: str) -> str:
    root = build_root(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
    row = {
        "id": capture_id,
        "status": status,
        "source kind": "url",
        "source": "https://example.com",
        "target": "",
        "node": f"[[{ROOT_SLUG}/{capture_id.lower()}]]",
        "updated": "2026-01-01T00:00:00-08:00",
        "notes": "",
    }
    return replace_capture_table(root, [row])


def run_gbrain(
    args: list[str],
    input_text: str | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gbrain", *args],
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def result_error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout).strip()


def get_required(slug: str) -> str:
    result = run_gbrain(["get", slug])
    if result.returncode:
        raise RuntimeError(result_error(result))
    return result.stdout


def get_optional(slug: str) -> str | None:
    result = run_gbrain(["get", slug])
    if result.returncode == 0:
        return result.stdout
    error = result_error(result)
    if "not found" in error.lower() or "page_not_found" in error.lower():
        return None
    raise RuntimeError(error)


def put_readback(slug: str, markdown: str) -> str:
    result = run_gbrain(["put", slug], input_text=markdown)
    if result.returncode:
        raise RuntimeError(result_error(result))
    return get_required(slug)


def graph_edges(source: str, relation: str) -> list[dict[str, object]]:
    result = run_gbrain(
        ["graph", source, "--depth", "1", "--link-type", relation, "--direction", "out"]
    )
    if result.returncode:
        raise RuntimeError(result_error(result))
    try:
        edges = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid graph readback for {source}: {exc}") from exc
    if not isinstance(edges, list):
        raise RuntimeError(f"invalid graph readback for {source}: expected a list")
    return [edge for edge in edges if isinstance(edge, dict)]


def verify_link(source: str, target: str, relation: str, present: bool) -> None:
    matches = [
        edge
        for edge in graph_edges(source, relation)
        if edge.get("from_slug") == source
        and edge.get("to_slug") == target
        and edge.get("link_type") == relation
    ]
    if bool(matches) != present:
        expectation = "present" if present else "absent"
        raise RuntimeError(
            f"link readback mismatch: expected {source} -[{relation}]-> {target} to be {expectation}"
        )


def link(source: str, target: str, relation: str) -> None:
    result = run_gbrain(
        [
            "link",
            source,
            target,
            "--link-type",
            relation,
            "--link-source",
            "memory-stargraph-capture-backlog",
        ]
    )
    if result.returncode and "already" not in result_error(result).lower():
        raise RuntimeError(result_error(result))
    verify_link(source, target, relation, True)


def unlink(source: str, target: str, relation: str) -> None:
    result = run_gbrain(
        [
            "unlink",
            source,
            target,
            "--link-type",
            relation,
            "--link-source",
            "memory-stargraph-capture-backlog",
        ]
    )
    if result.returncode and "not found" not in result_error(result).lower():
        raise RuntimeError(result_error(result))
    verify_link(source, target, relation, False)


@_uses_queue_authority("init")
def apply_init(now: dt.datetime | None = None) -> dict[str, object]:
    root = get_optional(ROOT_SLUG)
    failed = get_optional(FAILED_COLLECTION_SLUG)
    if root is None:
        expected_root = build_root(now)
        readback = put_readback(ROOT_SLUG, expected_root)
        if parse_capture_rows(readback) != [] or "# Memory Starmap Capture List" not in readback:
            raise RuntimeError(f"root readback mismatch: {ROOT_SLUG}")
    elif "# Memory Starmap Capture List" not in root:
        raise RuntimeError(f"existing node has unexpected content: {ROOT_SLUG}")
    else:
        parse_capture_rows(root)
    if failed is None:
        readback = put_readback(FAILED_COLLECTION_SLUG, build_failed_collection([], now))
        if parse_capture_rows(readback) != [] or "# Memory Starmap Failed Capture Items" not in readback:
            raise RuntimeError(f"failed mirror readback mismatch: {FAILED_COLLECTION_SLUG}")
    elif "# Memory Starmap Failed Capture Items" not in failed:
        raise RuntimeError(f"existing node has unexpected content: {FAILED_COLLECTION_SLUG}")
    else:
        parse_capture_rows(failed)
    link(ROOT_SLUG, FAILED_COLLECTION_SLUG, "has_failed_collection")
    link(FAILED_COLLECTION_SLUG, ROOT_SLUG, "failed_collection_for")
    return {
        "root_slug": ROOT_SLUG,
        "failed_collection_slug": FAILED_COLLECTION_SLUG,
        "applied": True,
    }


@_uses_queue_authority("snapshot")
def create_snapshot(
    now: dt.datetime | None = None,
    invocation_id: str | None = None,
) -> dict[str, object]:
    rows = parse_capture_rows(get_required(ROOT_SLUG))
    return {
        "invocation_id": invocation_id or str(uuid.uuid4()),
        "started_at": pacific_iso(now),
        "rows": freeze_snapshot(rows),
    }


def update_child_status(
    markdown: str,
    expected: str,
    target: str,
    updated: str,
    notes: str,
) -> str:
    found = child_status(markdown)
    if found != expected:
        raise ValueError(f"expected child {expected}, found {found or 'missing'}")
    frontmatter_end = markdown.find("\n---", 4)
    if frontmatter_end < 0:
        raise ValueError("child frontmatter is missing a closing delimiter")
    frontmatter = markdown[:frontmatter_end]
    result = (
        re.sub(r"(?m)^status:\s*\S+\s*$", f"status: {target}", frontmatter, count=1)
        + markdown[frontmatter_end:]
    )
    frontmatter_end = result.find("\n---", 4)
    frontmatter = result[:frontmatter_end]
    if re.search(r"(?m)^updated_at:", frontmatter):
        frontmatter = re.sub(r"(?m)^updated_at:.*$", f"updated_at: '{updated}'", frontmatter, count=1)
        result = frontmatter + result[frontmatter_end:]
    history = f"- {updated}: {expected} -> {target}; {notes}"
    section = re.search(r"(?m)^## Attempt History\s*$", result)
    if not section:
        raise ValueError("child is missing ## Attempt History")
    next_section = re.search(r"(?m)^## ", result[section.end() :])
    end = section.end() + next_section.start() if next_section else len(result)
    before = result[:end].rstrip()
    after = result[end:].lstrip("\n")
    combined = before + "\n\n" + history + "\n"
    if after:
        combined += "\n" + after
    return combined


def child_status(markdown: str) -> str:
    if not markdown.startswith("---\n"):
        raise ValueError("child frontmatter is missing")
    end = markdown.find("\n---", 4)
    if end < 0:
        raise ValueError("child frontmatter is missing a closing delimiter")
    match = re.search(r"(?m)^status:\s*([^\s#]+)\s*$", markdown[4:end])
    if not match:
        raise ValueError("child frontmatter status is missing")
    status = match.group(1)
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported stored status {status} for child")
    return status


def child_transition_metadata(markdown: str, expected: str, target: str) -> tuple[str, str]:
    fields = frontmatter_fields(markdown)
    updated = fields.get("updated_at", "")
    if not updated:
        raise RuntimeError("child transition updated_at is missing")
    section = re.search(r"(?m)^## Attempt History\s*$", markdown)
    if not section:
        raise RuntimeError("child transition history is missing")
    next_section = re.search(r"(?m)^## ", markdown[section.end() :])
    end = section.end() + next_section.start() if next_section else len(markdown)
    prefix = f"- {updated}: {expected} -> {target}; "
    matching = [
        line[len(prefix) :]
        for line in markdown[section.end() : end].splitlines()
        if line.startswith(prefix)
    ]
    if len(matching) != 1:
        raise RuntimeError("child transition history entry mismatch")
    return updated, matching[0]


def verify_parent_root(markdown: str, expected_markdown: str) -> None:
    if (
        parse_capture_rows(markdown) != parse_capture_rows(expected_markdown)
        or parse_archive_index(markdown) != parse_archive_index(expected_markdown)
    ):
        raise RuntimeError("parent row readback mismatch (full root/index)")


def verify_child_transition(
    markdown: str,
    expected: str,
    target: str,
    updated: str,
    notes: str,
    exact_markdown: str | None = None,
) -> None:
    if child_status(markdown) != target:
        raise RuntimeError(f"child status readback mismatch for {target}")
    try:
        metadata = child_transition_metadata(markdown, expected, target)
    except RuntimeError as exc:
        raise RuntimeError("child transition readback mismatch") from exc
    if metadata != (updated, notes):
        raise RuntimeError("child transition readback mismatch")
    if exact_markdown is not None and markdown != exact_markdown:
        raise RuntimeError("child transition readback mismatch")


def verify_failed_mirror(markdown: str, expected_rows: list[dict[str, str]]) -> None:
    if parse_capture_rows(markdown) != expected_rows:
        raise RuntimeError("failed mirror readback mismatch")


@_uses_queue_authority("transition")
def apply_transition(
    capture_id: str,
    expected: str,
    target: str,
    notes: str,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    if expected not in ALLOWED_STATUSES or target not in ALLOWED_STATUSES:
        raise ValueError("unsupported status")
    stamp = pacific_iso(now)
    root = get_required(ROOT_SLUG)
    rows = parse_capture_rows(root)
    matches = [row for row in rows if row.get("id") == capture_id]
    if len(matches) != 1:
        raise ValueError(f"expected one row for {capture_id}, found {len(matches)}")
    child_slug = node_slug(matches[0])
    if not child_slug:
        raise ValueError(f"missing child node for {capture_id}")
    parent_row = matches[0]
    if parent_row["status"] not in {expected, target}:
        raise ValueError(
            f"expected parent {expected} or reconciled {target}, found {parent_row['status']}"
        )

    child = get_required(child_slug)
    found_child_status = child_status(child)
    if found_child_status not in {expected, target}:
        raise ValueError(
            f"expected child {expected} or reconciled {target}, found {found_child_status}"
        )

    parent_at_target = parent_row["status"] == target
    child_at_target = found_child_status == target
    normalized_notes = " ".join(notes.splitlines()).strip()
    if parent_at_target:
        canonical_stamp = parent_row["updated"]
        canonical_notes = parent_row["notes"]
        if child_at_target and child_transition_metadata(child, expected, target) != (
            canonical_stamp,
            canonical_notes,
        ):
            raise RuntimeError(f"inconsistent reconciled transition metadata for {capture_id}")
    elif child_at_target:
        canonical_stamp, canonical_notes = child_transition_metadata(child, expected, target)
    else:
        canonical_stamp, canonical_notes = stamp, normalized_notes

    if parent_at_target:
        updated_root = root
    else:
        updated_root = transition(
            root, capture_id, expected, target, canonical_stamp, canonical_notes
        )
    if child_at_target:
        updated_child = child
    else:
        updated_child = update_child_status(
            child, expected, target, canonical_stamp, canonical_notes
        )

    # Validate the existing mirror before mutating it, even though it will be rebuilt from the root.
    parse_capture_rows(get_required(FAILED_COLLECTION_SLUG))

    if updated_child != child:
        child_readback = put_readback(child_slug, updated_child)
    else:
        child_readback = child
    verify_child_transition(
        child_readback,
        expected,
        target,
        canonical_stamp,
        canonical_notes,
        updated_child if updated_child != child else None,
    )

    if updated_root != root:
        root_readback = put_readback(ROOT_SLUG, updated_root)
    else:
        root_readback = root
    verify_parent_root(root_readback, updated_root)

    updated_rows = parse_capture_rows(root_readback)
    failed_rows = [row for row in updated_rows if row.get("status") == "failed"]
    failed_markdown = build_failed_collection(failed_rows, now)
    failed_readback = put_readback(FAILED_COLLECTION_SLUG, failed_markdown)
    verify_failed_mirror(failed_readback, failed_rows)
    if target == "failed":
        link(FAILED_COLLECTION_SLUG, child_slug, "has_failed_capture")
        link(child_slug, FAILED_COLLECTION_SLUG, "failed_capture_for")
    else:
        unlink(FAILED_COLLECTION_SLUG, child_slug, "has_failed_capture")
        unlink(child_slug, FAILED_COLLECTION_SLUG, "failed_capture_for")
    return {
        "capture_id": capture_id,
        "status": target,
        "child_slug": child_slug,
        "updated_at": canonical_stamp,
    }


def existing_archives(root_markdown: str) -> dict[str, list[dict[str, str]]]:
    archives: dict[str, list[dict[str, str]]] = {}
    for entry in parse_archive_index(root_markdown):
        slug = str(entry["slug"])
        markdown = get_required(slug)
        rows = parse_capture_rows(markdown)
        validate_archive(markdown, slug, int(entry["sequence"]), rows)
        expected_index = {
            "slug": slug,
            "sequence": int(entry["sequence"]),
            "first_id": rows[0]["id"] if rows else "",
            "last_id": rows[-1]["id"] if rows else "",
            "count": len(rows),
        }
        if entry != expected_index:
            raise RuntimeError(f"archive index readback mismatch for {slug}")
        archives[slug] = rows
    return archives


def frontmatter_fields(markdown: str) -> dict[str, str]:
    if not markdown.startswith("---\n"):
        raise ValueError("frontmatter is missing")
    end = markdown.find("\n---", 4)
    if end < 0:
        raise ValueError("frontmatter is missing a closing delimiter")
    fields: dict[str, str] = {}
    for line in markdown[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip("'\"")
    return fields


def validate_archive(
    markdown: str,
    slug: str,
    sequence: int,
    expected_rows: list[dict[str, str]],
) -> None:
    fields = frontmatter_fields(markdown)
    exact_fields = {
        "type": "collection",
        "title": f"Memory Starmap Completed Capture Archive {sequence:04d}",
        "status": "immutable",
        "timezone": "America/Los_Angeles",
    }
    if any(fields.get(key) != value for key, value in exact_fields.items()) or not fields.get("captured_at"):
        raise RuntimeError(f"immutable archive metadata mismatch for {slug}")
    try:
        captured_at = dt.datetime.fromisoformat(fields["captured_at"])
    except ValueError as exc:
        raise RuntimeError(f"immutable archive timestamp mismatch for {slug}") from exc
    if captured_at.tzinfo is None:
        raise RuntimeError(f"immutable archive timestamp mismatch for {slug}")
    expected_markdown = build_archive(slug, sequence, expected_rows, captured_at)
    if markdown != expected_markdown or parse_capture_rows(markdown) != expected_rows:
        raise RuntimeError(f"immutable archive content mismatch for {slug}")


def compaction_preview(
    root_markdown: str,
) -> tuple[CompactionPlan, dict[str, list[dict[str, str]]]]:
    archives = existing_archives(root_markdown)
    return plan_compaction(parse_capture_rows(root_markdown), archives, CAPTURE_SPEC), archives


@_uses_queue_authority("compact")
def apply_compaction(now: dt.datetime | None = None) -> dict[str, object]:
    root = get_required(ROOT_SLUG)
    plan, indexed_archives = compaction_preview(root)
    parse_capture_rows(get_required(FAILED_COLLECTION_SLUG))
    created: list[str] = []
    resumed: list[str] = []
    reconciled_archives = dict(indexed_archives)
    for archive in plan.archives_to_create:
        slug = str(archive["slug"])
        sequence = int(archive["sequence"])
        rows = archive["rows"]
        assert isinstance(rows, list)
        markdown = build_archive(slug, sequence, rows, now)
        existing = get_optional(slug)
        if existing is None:
            readback = put_readback(slug, markdown)
            validate_archive(readback, slug, sequence, rows)
            created.append(slug)
        else:
            try:
                validate_archive(existing, slug, sequence, rows)
            except (RuntimeError, ValueError) as exc:
                raise RuntimeError(
                    f"archive already exists but is missing from the root index and content mismatches: {slug}"
                ) from exc
            resumed.append(slug)
        reconciled_archives[slug] = rows

    for slug, rows in reconciled_archives.items():
        link(ROOT_SLUG, slug, "has_completed_archive")
        link(slug, ROOT_SLUG, "completed_archive_for")
        for row in rows:
            child_slug = node_slug(row)
            if child_slug:
                link(slug, child_slug, "contains_capture_request")

    failed_markdown = build_failed_collection(plan.failed_rows, now)
    failed_readback = put_readback(FAILED_COLLECTION_SLUG, failed_markdown)
    verify_failed_mirror(failed_readback, plan.failed_rows)
    updated_root = replace_capture_table(root, plan.active_rows, plan.archive_index)
    root_readback = put_readback(ROOT_SLUG, updated_root)
    readback_rows = parse_capture_rows(root_readback)
    readback_index = parse_archive_index(root_readback)
    if readback_rows != plan.active_rows or readback_index != plan.archive_index:
        raise RuntimeError("root compaction readback mismatch")
    return {
        "created_archives": created,
        "resumed_archives": resumed,
        "active_rows": len(readback_rows),
        "failed_rows": len(plan.failed_rows),
    }


@_uses_queue_authority("list")
def list_backlog(status: str | None = None) -> dict[str, object]:
    rows = parse_capture_rows(get_required(ROOT_SLUG))
    if status:
        if status not in ALLOWED_STATUSES:
            raise ValueError("unsupported status")
        rows = [row for row in rows if row.get("status") == status]
    return {"root_slug": ROOT_SLUG, "count": len(rows), "rows": rows}


@_uses_queue_authority("transition-preview")
def preview_transition(capture_id: str, expected: str, target: str, notes: str) -> dict[str, object]:
    root = get_required(ROOT_SLUG)
    transition(root, capture_id, expected, target, pacific_iso(), notes)
    return {"capture_id": capture_id, "status": target, "applied": False}


@_uses_queue_authority("compact-preview")
def preview_compaction() -> dict[str, object]:
    root = get_required(ROOT_SLUG)
    plan, _ = compaction_preview(root)
    return {
        "created_archives": [str(archive["slug"]) for archive in plan.archives_to_create],
        "active_rows": len(plan.active_rows),
        "failed_rows": len(plan.failed_rows),
        "applied": False,
    }


def emit(result: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the Memory Stargraph capture backlog.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize root and failed collections.")
    init_parser.add_argument("--apply", action="store_true")
    init_parser.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list", help="List active capture rows.")
    list_parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES))
    list_parser.add_argument("--json", action="store_true")

    snapshot_parser = subparsers.add_parser("snapshot", help="Freeze the current planned queue.")
    snapshot_parser.add_argument("--invocation-id")
    snapshot_parser.add_argument("--json", action="store_true")

    transition_parser = subparsers.add_parser("transition", help="Transition one parent and child state.")
    transition_parser.add_argument("--id", required=True, dest="capture_id")
    transition_parser.add_argument("--from", required=True, dest="expected", choices=sorted(ALLOWED_STATUSES))
    transition_parser.add_argument("--to", required=True, dest="target", choices=sorted(ALLOWED_STATUSES))
    transition_parser.add_argument("--notes", required=True)
    transition_parser.add_argument("--apply", action="store_true")
    transition_parser.add_argument("--json", action="store_true")

    compact_parser = subparsers.add_parser("compact", help="Archive each full batch of completed rows.")
    compact_parser.add_argument("--apply", action="store_true")
    compact_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "init":
        result = apply_init() if args.apply else {
            "root_slug": ROOT_SLUG,
            "failed_collection_slug": FAILED_COLLECTION_SLUG,
            "applied": False,
        }
    elif args.command == "list":
        result = list_backlog(args.status)
    elif args.command == "snapshot":
        result = create_snapshot(invocation_id=args.invocation_id)
    elif args.command == "transition":
        if args.apply:
            result = apply_transition(args.capture_id, args.expected, args.target, args.notes)
        else:
            result = preview_transition(args.capture_id, args.expected, args.target, args.notes)
    else:
        if args.apply:
            result = apply_compaction()
        else:
            result = preview_compaction()
    emit(result, args.json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
