#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
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
    return parse_rows(markdown, CAPTURE_SPEC)


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


def put_verified(slug: str, markdown: str, expected_marker: str) -> None:
    result = run_gbrain(["put", slug], input_text=markdown)
    if result.returncode:
        raise RuntimeError(result_error(result))
    if expected_marker not in get_required(slug):
        raise RuntimeError(f"readback marker missing for {slug}: {expected_marker}")


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


def apply_init(now: dt.datetime | None = None) -> dict[str, object]:
    root = get_optional(ROOT_SLUG)
    failed = get_optional(FAILED_COLLECTION_SLUG)
    if root is None:
        put_verified(ROOT_SLUG, build_root(now), "# Memory Starmap Capture List")
    elif "# Memory Starmap Capture List" not in root:
        raise RuntimeError(f"existing node has unexpected content: {ROOT_SLUG}")
    if failed is None:
        put_verified(
            FAILED_COLLECTION_SLUG,
            build_failed_collection([], now),
            "# Memory Starmap Failed Capture Items",
        )
    elif "# Memory Starmap Failed Capture Items" not in failed:
        raise RuntimeError(f"existing node has unexpected content: {FAILED_COLLECTION_SLUG}")
    link(ROOT_SLUG, FAILED_COLLECTION_SLUG, "has_failed_collection")
    link(FAILED_COLLECTION_SLUG, ROOT_SLUG, "failed_collection_for")
    return {
        "root_slug": ROOT_SLUG,
        "failed_collection_slug": FAILED_COLLECTION_SLUG,
        "applied": True,
    }


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
    status_match = re.search(r"(?m)^status:\s*(\S+)\s*$", markdown)
    found = status_match.group(1) if status_match else None
    if found != expected:
        raise ValueError(f"expected child {expected}, found {found or 'missing'}")
    result = re.sub(r"(?m)^status:\s*\S+\s*$", f"status: {target}", markdown, count=1)
    if re.search(r"(?m)^updated_at:", result):
        result = re.sub(r"(?m)^updated_at:.*$", f"updated_at: '{updated}'", result, count=1)
    history = f"- {updated}: {expected} -> {target}; {notes}"
    return result.rstrip() + "\n\n" + history + "\n"


def apply_transition(
    capture_id: str,
    expected: str,
    target: str,
    notes: str,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    stamp = pacific_iso(now)
    root = get_required(ROOT_SLUG)
    rows = parse_capture_rows(root)
    matches = [row for row in rows if row.get("id") == capture_id]
    if len(matches) != 1:
        raise ValueError(f"expected one row for {capture_id}, found {len(matches)}")
    child_slug = node_slug(matches[0])
    if not child_slug:
        raise ValueError(f"missing child node for {capture_id}")
    updated_root = transition(root, capture_id, expected, target, stamp, notes)
    updated_child = update_child_status(get_required(child_slug), expected, target, stamp, notes)

    put_verified(child_slug, updated_child, f"status: {target}")
    put_verified(ROOT_SLUG, updated_root, f"| {capture_id} | {target} |")

    updated_rows = parse_capture_rows(get_required(ROOT_SLUG))
    failed_rows = [row for row in updated_rows if row.get("status") == "failed"]
    failed_markdown = build_failed_collection(failed_rows, now)
    failed_marker = f"| {capture_id} | failed |" if target == "failed" else "# Memory Starmap Failed Capture Items"
    put_verified(FAILED_COLLECTION_SLUG, failed_markdown, failed_marker)
    if target == "failed":
        link(FAILED_COLLECTION_SLUG, child_slug, "has_failed_capture")
        link(child_slug, FAILED_COLLECTION_SLUG, "failed_capture_for")
    if expected == "failed" and target != "failed":
        unlink(FAILED_COLLECTION_SLUG, child_slug, "has_failed_capture")
        unlink(child_slug, FAILED_COLLECTION_SLUG, "failed_capture_for")
    return {
        "capture_id": capture_id,
        "status": target,
        "child_slug": child_slug,
        "updated_at": stamp,
    }


def existing_archives(root_markdown: str) -> dict[str, list[dict[str, str]]]:
    archives: dict[str, list[dict[str, str]]] = {}
    for entry in parse_archive_index(root_markdown):
        slug = str(entry["slug"])
        archives[slug] = parse_capture_rows(get_required(slug))
    return archives


def compaction_preview(
    root_markdown: str,
) -> tuple[CompactionPlan, dict[str, list[dict[str, str]]]]:
    archives = existing_archives(root_markdown)
    return plan_compaction(parse_capture_rows(root_markdown), archives, CAPTURE_SPEC), archives


def apply_compaction(now: dt.datetime | None = None) -> dict[str, object]:
    root = get_required(ROOT_SLUG)
    plan, _ = compaction_preview(root)
    created: list[str] = []
    for archive in plan.archives_to_create:
        slug = str(archive["slug"])
        sequence = int(archive["sequence"])
        rows = archive["rows"]
        assert isinstance(rows, list)
        if get_optional(slug) is not None:
            raise RuntimeError(f"archive already exists but is missing from the root index: {slug}")
        markdown = build_archive(slug, sequence, rows, now)
        put_verified(slug, markdown, f"Archive slug: `{slug}`")
        created.append(slug)
        link(ROOT_SLUG, slug, "has_completed_archive")
        link(slug, ROOT_SLUG, "completed_archive_for")
        for row in rows:
            child_slug = node_slug(row)
            if child_slug:
                link(slug, child_slug, "contains_capture_request")

    failed_markdown = build_failed_collection(plan.failed_rows, now)
    put_verified(FAILED_COLLECTION_SLUG, failed_markdown, "# Memory Starmap Failed Capture Items")
    updated_root = replace_capture_table(root, plan.active_rows, plan.archive_index)
    put_verified(ROOT_SLUG, updated_root, "# Memory Starmap Capture List")
    readback_count = len(parse_capture_rows(get_required(ROOT_SLUG)))
    if readback_count != len(plan.active_rows):
        raise RuntimeError(
            f"root readback row count mismatch: expected {len(plan.active_rows)}, got {readback_count}"
        )
    return {
        "created_archives": created,
        "active_rows": readback_count,
        "failed_rows": len(plan.failed_rows),
    }


def list_backlog(status: str | None = None) -> dict[str, object]:
    rows = parse_capture_rows(get_required(ROOT_SLUG))
    if status:
        if status not in ALLOWED_STATUSES:
            raise ValueError("unsupported status")
        rows = [row for row in rows if row.get("status") == status]
    return {"root_slug": ROOT_SLUG, "count": len(rows), "rows": rows}


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
            root = get_required(ROOT_SLUG)
            transition(root, args.capture_id, args.expected, args.target, pacific_iso(), args.notes)
            result = {"capture_id": args.capture_id, "status": args.target, "applied": False}
    else:
        if args.apply:
            result = apply_compaction()
        else:
            root = get_required(ROOT_SLUG)
            plan, _ = compaction_preview(root)
            result = {
                "created_archives": [str(archive["slug"]) for archive in plan.archives_to_create],
                "active_rows": len(plan.active_rows),
                "failed_rows": len(plan.failed_rows),
                "applied": False,
            }
    emit(result, args.json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
