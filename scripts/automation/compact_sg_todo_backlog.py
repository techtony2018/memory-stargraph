#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


ROOT_SLUG = "notes/memory-starmap-todo-list"
FAILED_COLLECTION_SLUG = f"{ROOT_SLUG}/failed-items"
ARCHIVE_PREFIX = f"{ROOT_SLUG}/completed-archive-"
ARCHIVE_SIZE = 50
TODO_COLUMNS = ["id", "status", "priority", "title", "node", "updated", "notes"]
INCOMPLETE_STATUSES = {"planned", "implementing", "failed"}


@dataclass
class CompactionPlan:
    active_rows: list[dict[str, str]]
    archives_to_create: list[dict[str, object]]
    archive_index: list[dict[str, object]]
    failed_rows: list[dict[str, str]]


def split_markdown_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def escape_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def render_todo_table(rows: Iterable[dict[str, str]]) -> str:
    lines = [
        "| id | status | priority | title | node | updated | notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(escape_cell(row.get(column, "")) for column in TODO_COLUMNS) + " |")
    return "\n".join(lines)


def parse_todo_rows(markdown: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    start = find_todo_table_start(lines)
    if start is None:
        return []
    rows: list[dict[str, str]] = []
    for line in lines[start + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_markdown_row(line)
        if len(cells) < len(TODO_COLUMNS):
            continue
        rows.append({column: cells[index] for index, column in enumerate(TODO_COLUMNS)})
    return rows


def find_todo_table_start(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.strip().lower() != "## todo items":
            continue
        for table_index in range(index + 1, len(lines)):
            stripped = lines[table_index].strip()
            if not stripped:
                continue
            cells = [cell.lower() for cell in split_markdown_row(stripped)]
            if cells[: len(TODO_COLUMNS)] == TODO_COLUMNS:
                return table_index
            return None
    for index, line in enumerate(lines):
        cells = [cell.lower() for cell in split_markdown_row(line.strip())]
        if cells[: len(TODO_COLUMNS)] == TODO_COLUMNS:
            return index
    return None


def item_number(row: dict[str, str]) -> int:
    match = re.search(r"(\d+)", row.get("id", ""))
    return int(match.group(1)) if match else 10**9


def archive_sequence(slug: str) -> int | None:
    match = re.fullmatch(re.escape(ARCHIVE_PREFIX) + r"(\d{4})", slug)
    return int(match.group(1)) if match else None


def node_slug(row: dict[str, str]) -> str | None:
    match = re.search(r"\[\[([^\]]+)\]\]", row.get("node", ""))
    return match.group(1).strip() if match else None


def plan_compaction(
    rows: list[dict[str, str]],
    existing_archives: dict[str, list[dict[str, str]]],
) -> CompactionPlan:
    existing_archive_items = {
        row["id"]
        for archive_rows in existing_archives.values()
        for row in archive_rows
        if row.get("id")
    }
    completed = sorted((row for row in rows if row.get("status") == "completed"), key=item_number)
    incomplete = sorted((row for row in rows if row.get("status") != "completed"), key=item_number)
    unarchived_completed = [row for row in completed if row.get("id") not in existing_archive_items]

    next_sequence = max([archive_sequence(slug) or 0 for slug in existing_archives] or [0]) + 1
    archives_to_create: list[dict[str, object]] = []
    while len(unarchived_completed) >= ARCHIVE_SIZE:
        batch = unarchived_completed[:ARCHIVE_SIZE]
        unarchived_completed = unarchived_completed[ARCHIVE_SIZE:]
        archives_to_create.append(
            {
                "slug": f"{ARCHIVE_PREFIX}{next_sequence:04d}",
                "sequence": next_sequence,
                "rows": batch,
            }
        )
        next_sequence += 1

    newly_archived_items = {
        row["id"]
        for archive in archives_to_create
        for row in archive["rows"]  # type: ignore[index]
    }
    active_completed = [
        row
        for row in completed
        if row.get("id") not in existing_archive_items and row.get("id") not in newly_archived_items
    ]
    active_rows = incomplete + active_completed

    archive_index: list[dict[str, object]] = []
    for slug, archive_rows in existing_archives.items():
        if not archive_rows:
            continue
        archive_index.append(
            {
                "slug": slug,
                "sequence": archive_sequence(slug) or 0,
                "first_id": archive_rows[0]["id"],
                "last_id": archive_rows[-1]["id"],
                "count": len(archive_rows),
            }
        )
    for archive in archives_to_create:
        archive_rows = archive["rows"]  # type: ignore[assignment]
        archive_index.append(
            {
                "slug": archive["slug"],
                "sequence": archive["sequence"],
                "first_id": archive_rows[0]["id"],
                "last_id": archive_rows[-1]["id"],
                "count": len(archive_rows),
            }
        )
    archive_index.sort(key=lambda item: int(item["sequence"]))

    return CompactionPlan(
        active_rows=active_rows,
        archives_to_create=archives_to_create,
        archive_index=archive_index,
        failed_rows=[row for row in active_rows if row.get("status") == "failed"],
    )


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


def render_archive_index(index_rows: list[dict[str, object]]) -> str:
    if not index_rows:
        return ""
    lines = [
        "## Completed Archives",
        "",
        "| archive | sequence | first id | last id | count |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in index_rows:
        lines.append(
            f"| [[{row['slug']}]] | {row['sequence']} | {row['first_id']} | {row['last_id']} | {row['count']} |"
        )
    return "\n".join(lines)


def strip_section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    return pattern.sub("", markdown).rstrip()


def replace_root_todo_table(markdown: str, rows: list[dict[str, str]], archive_index: list[dict[str, object]]) -> str:
    lines = markdown.splitlines()
    start = find_todo_table_start(lines)
    if start is None:
        raise ValueError("Could not find ## Todo Items table in root backlog")
    end = start + 2
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    prefix = "\n".join(lines[:start])
    suffix = "\n".join(lines[end:])
    suffix = strip_section(suffix, "Completed Archives")
    archive_section = render_archive_index(archive_index)
    parts = [prefix.rstrip(), render_todo_table(rows)]
    if archive_section:
        parts.extend(["", archive_section])
    if suffix.strip():
        parts.extend(["", suffix.strip()])
    return "\n".join(parts).rstrip() + "\n"


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
