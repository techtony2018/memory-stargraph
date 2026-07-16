#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from urllib.parse import quote


ROOT_SLUG = "notes/memory-starmap-capture-list"
ALLOWED_FILTERS = {None, "planned", "capturing", "completed", "failed"}
COLUMNS = ("id", "status", "source kind", "source", "target", "node", "updated", "notes")


def run_gbrain(*args: str) -> str:
    if args[:1] != ("get",):
        raise ValueError("get-capture-link only permits gbrain get")
    completed = subprocess.run(["gbrain", *args], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "gbrain get failed")
    return completed.stdout


def split_markdown_row(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.strip().removeprefix("|").removesuffix("|"):
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


def parse_capture_rows(markdown: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if tuple(cell.lower() for cell in split_markdown_row(line)) == COLUMNS),
        None,
    )
    if start is None:
        return []
    rows = []
    for line in lines[start + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_markdown_row(line)
        if len(cells) >= len(COLUMNS):
            rows.append(dict(zip(COLUMNS, cells)))
    return rows


def node_slug(row: dict[str, str]) -> str:
    match = re.search(r"\[\[([^\]]+)\]\]", row.get("node", ""))
    if not match:
        raise ValueError(f"capture row {row.get('id') or 'unknown'} has no node slug")
    return match.group(1).strip()


def slug_link(slug: str) -> str:
    return f"[{slug}](http://127.0.0.1:8788/?slug={quote(slug, safe='')})"


def read_capture_backlog(status: str | None = None, capture_id: str | None = None) -> dict:
    if status not in ALLOWED_FILTERS:
        raise ValueError("status must be planned, capturing, completed, or failed")
    rows = parse_capture_rows(run_gbrain("get", ROOT_SLUG))
    selected = [
        row
        for row in rows
        if (status is None or row["status"] == status)
        and (capture_id is None or row["id"] == capture_id)
    ]
    statuses = sorted(ALLOWED_FILTERS - {None})
    return {
        "ok": True,
        "root_slug": ROOT_SLUG,
        "root_link": slug_link(ROOT_SLUG),
        "counts": {name: sum(row["status"] == name for row in rows) for name in statuses},
        "items": [
            {**row, "slug": (slug := node_slug(row)), "link": slug_link(slug)}
            for row in selected
        ],
    }


def render_markdown(result: dict) -> str:
    counts = result["counts"]
    lines = [
        f"Capture backlog: {result['root_link']}",
        "Counts: " + ", ".join(f"{name}={counts[name]}" for name in sorted(counts)),
    ]
    lines.extend(f"- {item['id']} ({item['status']}): {item['link']}" for item in result["items"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the Memory Stargraph capture backlog")
    parser.add_argument("--status", choices=sorted(ALLOWED_FILTERS - {None}))
    parser.add_argument("--id", dest="capture_id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = read_capture_backlog(status=args.status, capture_id=args.capture_id)
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
