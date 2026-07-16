from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class BacklogSpec:
    root_slug: str
    section_heading: str
    columns: tuple[str, ...]
    completed_status: str
    archive_size: int
    archive_prefix: str


@dataclass
class CompactionPlan:
    active_rows: list[dict[str, str]]
    archives_to_create: list[dict[str, object]]
    archive_index: list[dict[str, object]]
    failed_rows: list[dict[str, str]]


def split_markdown_row(line: str) -> list[str]:
    text = line.strip().removeprefix("|").removesuffix("|")
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


def render_table(rows: Iterable[dict[str, str]], spec: BacklogSpec) -> str:
    header = "| " + " | ".join(spec.columns) + " |"
    divider = "| " + " | ".join("---" for _ in spec.columns) + " |"
    body = [
        "| " + " | ".join(escape_cell(row.get(column, "")) for column in spec.columns) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body])


def find_table_start(lines: list[str], spec: BacklogSpec) -> int | None:
    heading = f"## {spec.section_heading}".lower()
    for index, line in enumerate(lines):
        if line.strip().lower() != heading:
            continue
        for table_index in range(index + 1, len(lines)):
            if not lines[table_index].strip():
                continue
            cells = tuple(cell.lower() for cell in split_markdown_row(lines[table_index]))
            return table_index if cells[: len(spec.columns)] == spec.columns else None
    for index, line in enumerate(lines):
        cells = tuple(cell.lower() for cell in split_markdown_row(line))
        if cells[: len(spec.columns)] == spec.columns:
            return index
    return None


def parse_rows(markdown: str, spec: BacklogSpec) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    start = find_table_start(lines, spec)
    if start is None:
        return []
    parsed: list[dict[str, str]] = []
    for line in lines[start + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_markdown_row(line)
        if len(cells) >= len(spec.columns):
            parsed.append({column: cells[index] for index, column in enumerate(spec.columns)})
    return parsed


def item_number(row: dict[str, str]) -> int:
    match = re.search(r"(\d+)", row.get("id", ""))
    return int(match.group(1)) if match else 10**9


def archive_sequence(slug: str, spec: BacklogSpec) -> int | None:
    match = re.fullmatch(re.escape(spec.archive_prefix) + r"(\d{4})", slug)
    return int(match.group(1)) if match else None


def node_slug(row: dict[str, str]) -> str | None:
    match = re.search(r"\[\[([^\]]+)\]\]", row.get("node", ""))
    return match.group(1).strip() if match else None


def strip_section(markdown: str, heading: str) -> str:
    return re.sub(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)", "", markdown).rstrip()


def render_archive_index(index_rows: list[dict[str, object]]) -> str:
    if not index_rows:
        return ""
    lines = [
        "## Completed Archives",
        "",
        "| archive | sequence | first id | last id | count |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| [[{row['slug']}]] | {row['sequence']} | {row['first_id']} | {row['last_id']} | {row['count']} |"
        for row in index_rows
    )
    return "\n".join(lines)


def replace_root_table(
    markdown: str,
    rows: list[dict[str, str]],
    archive_index: list[dict[str, object]],
    spec: BacklogSpec,
) -> str:
    lines = markdown.splitlines()
    start = find_table_start(lines, spec)
    if start is None:
        raise ValueError(f"Could not find ## {spec.section_heading} table in {spec.root_slug}")
    end = start + 2
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    prefix = "\n".join(lines[:start]).rstrip()
    suffix = strip_section("\n".join(lines[end:]), "Completed Archives")
    parts = [prefix, render_table(rows, spec)]
    archive_section = render_archive_index(archive_index)
    if archive_section:
        parts.extend(["", archive_section])
    if suffix.strip():
        parts.extend(["", suffix.strip()])
    return "\n".join(parts).rstrip() + "\n"


def plan_compaction(
    rows: list[dict[str, str]],
    existing_archives: dict[str, list[dict[str, str]]],
    spec: BacklogSpec,
) -> CompactionPlan:
    archived_ids = {
        row["id"]
        for archive in existing_archives.values()
        for row in archive
        if row.get("id")
    }
    completed = sorted(
        (row for row in rows if row.get("status") == spec.completed_status),
        key=item_number,
    )
    incomplete = sorted(
        (row for row in rows if row.get("status") != spec.completed_status),
        key=item_number,
    )
    pending = [row for row in completed if row.get("id") not in archived_ids]
    sequence = max([archive_sequence(slug, spec) or 0 for slug in existing_archives] or [0]) + 1
    created: list[dict[str, object]] = []
    while len(pending) >= spec.archive_size:
        batch, pending = pending[: spec.archive_size], pending[spec.archive_size :]
        created.append(
            {
                "slug": f"{spec.archive_prefix}{sequence:04d}",
                "sequence": sequence,
                "rows": batch,
            }
        )
        sequence += 1
    active = incomplete + pending
    index = [
        {
            "slug": slug,
            "sequence": archive_sequence(slug, spec) or 0,
            "first_id": values[0]["id"],
            "last_id": values[-1]["id"],
            "count": len(values),
        }
        for slug, values in existing_archives.items()
        if values
    ]
    index += [
        {
            "slug": archive["slug"],
            "sequence": archive["sequence"],
            "first_id": archive["rows"][0]["id"],  # type: ignore[index]
            "last_id": archive["rows"][-1]["id"],  # type: ignore[index]
            "count": len(archive["rows"]),  # type: ignore[arg-type]
        }
        for archive in created
    ]
    index.sort(key=lambda entry: int(entry["sequence"]))
    return CompactionPlan(
        active,
        created,
        index,
        [row for row in active if row.get("status") == "failed"],
    )
