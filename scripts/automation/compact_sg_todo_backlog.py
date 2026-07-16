#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.automation.backlog_compaction import (
    BacklogSpec,
    CompactionPlan,
    archive_sequence as generic_archive_sequence,
    escape_cell,
    find_table_start,
    item_number,
    node_slug,
    parse_rows,
    plan_compaction as generic_plan_compaction,
    render_archive_index,
    render_table,
    replace_root_table,
    split_markdown_row,
    strip_section,
)


ROOT_SLUG = "notes/memory-starmap-todo-list"
FAILED_COLLECTION_SLUG = f"{ROOT_SLUG}/failed-items"
ARCHIVE_PREFIX = f"{ROOT_SLUG}/completed-archive-"
ARCHIVE_SIZE = 50
TODO_COLUMNS = ["id", "status", "priority", "title", "node", "updated", "notes"]
INCOMPLETE_STATUSES = {"planned", "implementing", "failed"}
TODO_SPEC = BacklogSpec(
    root_slug=ROOT_SLUG,
    section_heading="Todo Items",
    columns=tuple(TODO_COLUMNS),
    completed_status="completed",
    archive_size=ARCHIVE_SIZE,
    archive_prefix=ARCHIVE_PREFIX,
)


def render_todo_table(rows: Iterable[dict[str, str]]) -> str:
    return render_table(rows, TODO_SPEC)


def parse_todo_rows(markdown: str) -> list[dict[str, str]]:
    return parse_rows(markdown, TODO_SPEC)


def find_todo_table_start(lines: list[str]) -> int | None:
    return find_table_start(lines, TODO_SPEC)


def archive_sequence(slug: str) -> int | None:
    return generic_archive_sequence(slug, TODO_SPEC)


def plan_compaction(
    rows: list[dict[str, str]],
    existing_archives: dict[str, list[dict[str, str]]],
) -> CompactionPlan:
    return generic_plan_compaction(rows, existing_archives, TODO_SPEC)


def render_archive(slug: str, sequence: int, rows: list[dict[str, str]]) -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return f"""---
type: collection
title: Memory Starmap Completed TODO Archive {sequence:04d}
source_kind: memory-stargraph-automation
captured_at: '{now}'
tags:
  - automation
  - memory-stargraph
  - todo-archive
---

# Memory Starmap Completed TODO Archive {sequence:04d}

Root backlog: [[{ROOT_SLUG}]]

## Summary

- Archive slug: `{slug}`
- Completed TODO count: {len(rows)}
- First TODO: `{rows[0]["id"]}`
- Last TODO: `{rows[-1]["id"]}`

## Todo Items

{render_todo_table(rows)}
"""


def render_failed_collection(rows: list[dict[str, str]]) -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return f"""---
type: collection
title: Memory Starmap Failed Items
source_kind: memory-stargraph-automation
captured_at: '{now}'
tags:
  - automation
  - memory-stargraph
  - todo
  - failed
---

# Memory Starmap Failed Items

Root backlog: [[{ROOT_SLUG}]]

This collection is a synchronized current-state view. Failed rows remain in the active backlog until they are completed or replanned.

## Failed Items

{render_todo_table(rows)}
"""


def replace_root_todo_table(markdown: str, rows: list[dict[str, str]], archive_index: list[dict[str, object]]) -> str:
    return replace_root_table(markdown, rows, archive_index, TODO_SPEC)


def run_gbrain(args: list[str], input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gbrain", *args],
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(args, 124, exc.stdout or "", exc.stderr or f"timed out after {timeout}s")


def gbrain_get(slug: str) -> str | None:
    result = run_gbrain(["get", slug], timeout=90)
    if result.returncode != 0:
        return None
    return result.stdout


def gbrain_put(slug: str, markdown: str) -> None:
    result = run_gbrain(["put", slug], input_text=markdown, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"gbrain put failed for {slug}: {(result.stderr or result.stdout).strip()}")


def gbrain_link(source: str, target: str, link_type: str) -> bool:
    result = run_gbrain(
        ["link", source, target, "--link-type", link_type, "--link-source", "memory-stargraph-todo-compaction"],
        timeout=120,
    )
    return result.returncode == 0


def discover_existing_archives(max_archives: int = 200) -> dict[str, list[dict[str, str]]]:
    archives: dict[str, list[dict[str, str]]] = {}
    misses = 0
    for sequence in range(1, max_archives + 1):
        slug = f"{ARCHIVE_PREFIX}{sequence:04d}"
        markdown = gbrain_get(slug)
        if markdown is None:
            misses += 1
            if misses >= 3:
                break
            continue
        misses = 0
        rows = parse_todo_rows(markdown)
        archives[slug] = rows
    return archives


def apply_plan(root_markdown: str, plan: CompactionPlan) -> dict[str, object]:
    created_archives: list[str] = []
    linked_children = 0
    for archive in plan.archives_to_create:
        slug = str(archive["slug"])
        rows = archive["rows"]  # type: ignore[assignment]
        sequence = int(archive["sequence"])
        gbrain_put(slug, render_archive(slug, sequence, rows))
        created_archives.append(slug)
        if gbrain_link(ROOT_SLUG, slug, "has_completed_archive"):
            linked_children += 1
        for row in rows:
            child = node_slug(row)
            if child and gbrain_link(slug, child, "contains_todo"):
                linked_children += 1
            if child:
                gbrain_link(ROOT_SLUG, child, "has_todo")

    gbrain_put(FAILED_COLLECTION_SLUG, render_failed_collection(plan.failed_rows))
    gbrain_link(ROOT_SLUG, FAILED_COLLECTION_SLUG, "has_failed_collection")
    for row in plan.failed_rows:
        child = node_slug(row)
        if child:
            gbrain_link(FAILED_COLLECTION_SLUG, child, "has_failed_todo")

    updated_root = replace_root_todo_table(root_markdown, plan.active_rows, plan.archive_index)
    gbrain_put(ROOT_SLUG, updated_root)
    readback = gbrain_get(ROOT_SLUG) or ""
    readback_rows = parse_todo_rows(readback)
    if len(readback_rows) != len(plan.active_rows):
        raise RuntimeError(
            f"root readback row count mismatch: expected {len(plan.active_rows)}, got {len(readback_rows)}"
        )
    return {
        "created_archives": created_archives,
        "active_rows": len(plan.active_rows),
        "failed_rows": len(plan.failed_rows),
        "relationships_attempted": linked_children,
    }


def build_summary(rows: list[dict[str, str]], plan: CompactionPlan) -> dict[str, object]:
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row.get("status", "")] = statuses.get(row.get("status", ""), 0) + 1
    return {
        "root_slug": ROOT_SLUG,
        "archive_size": ARCHIVE_SIZE,
        "input_rows": len(rows),
        "input_statuses": statuses,
        "archives_to_create": [
            {
                "slug": archive["slug"],
                "count": len(archive["rows"]),  # type: ignore[arg-type]
                "first_id": archive["rows"][0]["id"],  # type: ignore[index]
                "last_id": archive["rows"][-1]["id"],  # type: ignore[index]
            }
            for archive in plan.archives_to_create
        ],
        "active_rows_after": len(plan.active_rows),
        "active_completed_after": sum(1 for row in plan.active_rows if row.get("status") == "completed"),
        "failed_rows": len(plan.failed_rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compact Memory Stargraph completed TODO rows into 50-row archive nodes.")
    parser.add_argument("--apply", action="store_true", help="Write GBrain changes. Default is dry-run.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    root_markdown = gbrain_get(ROOT_SLUG)
    if root_markdown is None:
        raise RuntimeError(f"Could not read {ROOT_SLUG}")
    rows = parse_todo_rows(root_markdown)
    if not rows:
        raise RuntimeError(f"No TODO rows parsed from {ROOT_SLUG}")
    existing_archives = discover_existing_archives()
    plan = plan_compaction(rows, existing_archives)
    summary = build_summary(rows, plan)
    if args.apply:
        summary["apply"] = apply_plan(root_markdown, plan)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Input rows: {summary['input_rows']} {summary['input_statuses']}")
        print(f"Archives to create: {len(plan.archives_to_create)}")
        for archive in summary["archives_to_create"]:  # type: ignore[index]
            print(f"- {archive['slug']}: {archive['first_id']}..{archive['last_id']} ({archive['count']})")
        print(f"Active rows after: {summary['active_rows_after']}")
        print(f"Active completed after: {summary['active_completed_after']}")
        print(f"Failed rows mirrored: {summary['failed_rows']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
