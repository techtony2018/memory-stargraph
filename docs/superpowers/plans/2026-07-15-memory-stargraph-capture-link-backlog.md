# Memory Stargraph Capture Link Backlog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable queue-only capture backlog, `/add-capture-link` and `/get-capture-link` skills, and a persistent midnight worker that drains each frozen batch through Tony's enhanced local GBrain capture skills.

**Architecture:** A small reusable Python backlog engine owns Markdown parsing, status transitions, failed-item mirroring, and 50-row completed archives. Thin capture-specific commands and skills use that engine, while a tracked heartbeat automation drives a persistent worker task and records Pacific-time evidence using `America/Los_Angeles`.

**Tech Stack:** Python 3 standard library, GBrain CLI, Memory Stargraph multipart attachment API, Markdown/YAML GBrain nodes, Codex skills, TOML heartbeat automation definitions, `unittest`.

## Global Constraints

- Root backlog slug is exactly `notes/memory-starmap-capture-list`.
- Request IDs are monotonically increasing `CAP-0001`, `CAP-0002`, and so on.
- Allowed request statuses are exactly `planned`, `capturing`, `completed`, and `failed`.
- `/add-capture-link` is queue-only and must never perform the eventual content capture.
- Attached media is uploaded exactly once to the request child and the final captured node reuses the verified durable reference; it must not duplicate the bytes.
- Each full batch of the fifty oldest unarchived completed rows moves into an immutable archive; the active root retains all non-completed rows and zero to forty-nine completed rows.
- A nightly schedule fires at midnight in `America/Los_Angeles`, but the worker can be triggered manually at any time and has no fixed cutoff.
- Worker-generated logs, Runs, reports, transition evidence, and timestamped filenames use timezone-aware `America/Los_Angeles`; PDT and PST must follow daylight-saving rules automatically.
- Browser work inspects and reuses suitable existing tabs, never closes reused user tabs, and closes only temporary tabs created by that invocation.
- User-facing GBrain slugs use exact-label Markdown links to `http://127.0.0.1:8788/?slug=<URL-encoded-slug>`.
- Do not auto-approve resolver proposals, bypass authentication controls, perform destructive cleanup, or make privacy-sensitive captures without explicit human authority.
- Existing worker prompts and their live runtime copies must receive the same Pacific-time contract in the same delivery.

---

## File Map

- `scripts/automation/backlog_compaction.py`: reusable Markdown table, archive planning, archive rendering, and failed-view primitives.
- `scripts/automation/compact_sg_todo_backlog.py`: existing TODO-specific adapter over the reusable compaction engine.
- `scripts/automation/manage_capture_backlog.py`: capture root initialization, snapshotting, verified status transitions, capture-specific compaction, and JSON CLI.
- `tests/test_backlog_compaction.py`: generic engine and TODO-regression coverage.
- `tests/test_capture_backlog.py`: capture initialization, snapshot, transition, failure collection, and archive behavior.
- `skills/add-capture-link/`: repository-canonical queue-only skill, helper, tests, and agent metadata.
- `skills/get-capture-link/`: repository-canonical read-only skill, helper, tests, and agent metadata.
- `scripts/automation/install_capture_skills.py`: byte-identical installation into Codex and OpenClaw skill homes.
- `automations/memory-stargraph-capture-link-drain/`: tracked schedule, heartbeat, worker prompt, and persistent-task bootstrap.
- Existing `automations/*/prompt.md`: common Pacific-time reporting contract.
- `tests/test_automation_contracts.py`: capture worker, browser hygiene, persistent destination, and timezone assertions.
- `automations/README.md` and `docs/automation-runbook.md`: pipeline, restore, manual trigger, queue, archive, and recovery documentation.

### Task 1: Extract a Reusable Backlog Compaction Engine

**Files:**
- Create: `scripts/automation/backlog_compaction.py`
- Create: `tests/test_backlog_compaction.py`
- Modify: `scripts/automation/compact_sg_todo_backlog.py`
- Modify: `tests/test_todo_backlog_compaction.py`

**Interfaces:**
- Produces: `BacklogSpec`, `CompactionPlan`, `parse_rows(markdown, spec)`, `render_table(rows, spec)`, `plan_compaction(rows, existing_archives, spec)`, `replace_root_table(markdown, rows, archive_index, spec)`, and `node_slug(row)`.
- Preserves: all public imports currently used by `tests/test_todo_backlog_compaction.py`, including `ARCHIVE_SIZE`, `parse_todo_rows`, `plan_compaction`, and `render_todo_table`.

- [ ] **Step 1: Write failing generic compaction tests**

```python
import unittest

from scripts.automation.backlog_compaction import BacklogSpec, parse_rows, plan_compaction, render_table

CAPTURE = BacklogSpec(
    root_slug="notes/memory-starmap-capture-list",
    section_heading="Capture Items",
    columns=("id", "status", "source kind", "source", "target", "node", "updated", "notes"),
    completed_status="completed",
    archive_size=50,
    archive_prefix="notes/memory-starmap-capture-list/completed-archive-",
)


def capture_row(number: int, status: str) -> dict[str, str]:
    item = f"CAP-{number:04d}"
    return {
        "id": item,
        "status": status,
        "source kind": "url",
        "source": f"https://example.com/{number}",
        "target": "",
        "node": f"[[notes/memory-starmap-capture-list/{item.lower()}]]",
        "updated": "2026-07-15T09:00:00-07:00",
        "notes": "queued",
    }


class GenericBacklogCompactionTests(unittest.TestCase):
    def test_generic_capture_compaction_archives_full_oldest_batches(self):
        rows = [capture_row(200, "planned"), capture_row(201, "failed")]
        rows += [capture_row(index, "completed") for index in range(1, 127)]
        plan = plan_compaction(rows, {}, CAPTURE)
        self.assertEqual([archive["slug"] for archive in plan.archives_to_create], [
            "notes/memory-starmap-capture-list/completed-archive-0001",
            "notes/memory-starmap-capture-list/completed-archive-0002",
        ])
        self.assertEqual([row["id"] for row in plan.active_rows[:2]], ["CAP-0200", "CAP-0201"])
        self.assertEqual([row["id"] for row in plan.active_rows[2:]], [f"CAP-{i:04d}" for i in range(101, 127)])

    def test_generic_table_round_trips_escaped_cells(self):
        row = capture_row(1, "planned")
        row["notes"] = "A | B"
        self.assertEqual(parse_rows(render_table([row], CAPTURE), CAPTURE)[0]["notes"], "A | B")
```

- [ ] **Step 2: Run the new tests and confirm the missing-module failure**

Run: `python3 -m unittest tests.test_backlog_compaction -v`

Expected: `ModuleNotFoundError: No module named 'scripts.automation.backlog_compaction'`.

- [ ] **Step 3: Implement the generic value objects and pure functions**

```python
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
    return str(value or "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def render_table(rows: Iterable[dict[str, str]], spec: BacklogSpec) -> str:
    header = "| " + " | ".join(spec.columns) + " |"
    divider = "| " + " | ".join("---" for _ in spec.columns) + " |"
    body = ["| " + " | ".join(escape_cell(row.get(column, "")) for column in spec.columns) + " |" for row in rows]
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
    return None


def parse_rows(markdown: str, spec: BacklogSpec) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    start = find_table_start(lines, spec)
    if start is None:
        return []
    parsed: list[dict[str, str]] = []
    for line in lines[start + 2:]:
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


def replace_root_table(markdown: str, rows: list[dict[str, str]], archive_index: list[dict[str, object]], spec: BacklogSpec) -> str:
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


def plan_compaction(rows: list[dict[str, str]], existing_archives: dict[str, list[dict[str, str]]], spec: BacklogSpec) -> CompactionPlan:
    archived_ids = {row["id"] for archive in existing_archives.values() for row in archive if row.get("id")}
    completed = sorted((row for row in rows if row.get("status") == spec.completed_status), key=item_number)
    incomplete = sorted((row for row in rows if row.get("status") != spec.completed_status), key=item_number)
    pending = [row for row in completed if row.get("id") not in archived_ids]
    sequence = max([archive_sequence(slug, spec) or 0 for slug in existing_archives] or [0]) + 1
    created: list[dict[str, object]] = []
    while len(pending) >= spec.archive_size:
        batch, pending = pending[: spec.archive_size], pending[spec.archive_size:]
        created.append({"slug": f"{spec.archive_prefix}{sequence:04d}", "sequence": sequence, "rows": batch})
        sequence += 1
    active = incomplete + pending
    index = [
        {"slug": slug, "sequence": archive_sequence(slug, spec) or 0, "first_id": values[0]["id"], "last_id": values[-1]["id"], "count": len(values)}
        for slug, values in existing_archives.items() if values
    ]
    index += [
        {"slug": archive["slug"], "sequence": archive["sequence"], "first_id": archive["rows"][0]["id"], "last_id": archive["rows"][-1]["id"], "count": len(archive["rows"])}
        for archive in created
    ]
    index.sort(key=lambda entry: int(entry["sequence"]))
    return CompactionPlan(active, created, index, [row for row in active if row.get("status") == "failed"])
```

Keep archive titles and relation labels in the adapters so the engine remains domain-neutral.

- [ ] **Step 4: Convert the TODO helper into a compatibility adapter**

```python
from scripts.automation.backlog_compaction import (
    BacklogSpec,
    CompactionPlan,
    node_slug,
    parse_rows,
    plan_compaction as generic_plan_compaction,
    render_table,
    replace_root_table,
)

TODO_COLUMNS = ("id", "status", "priority", "title", "node", "updated", "notes")
TODO_SPEC = BacklogSpec(
    root_slug=ROOT_SLUG,
    section_heading="Todo Items",
    columns=TODO_COLUMNS,
    completed_status="completed",
    archive_size=ARCHIVE_SIZE,
    archive_prefix=ARCHIVE_PREFIX,
)


def parse_todo_rows(markdown: str) -> list[dict[str, str]]:
    return parse_rows(markdown, TODO_SPEC)


def render_todo_table(rows: Iterable[dict[str, str]]) -> str:
    return render_table(rows, TODO_SPEC)


def plan_compaction(rows, existing_archives):
    return generic_plan_compaction(rows, existing_archives, TODO_SPEC)
```

Use the generic `replace_root_table` inside `replace_root_todo_table`. Leave GBrain I/O, TODO archive prose, relation names, and CLI output in the existing adapter.

- [ ] **Step 5: Run generic and existing regression tests**

Run: `python3 -m unittest tests.test_backlog_compaction tests.test_todo_backlog_compaction -v`

Expected: all tests pass, including the three pre-existing TODO compaction tests.

- [ ] **Step 6: Commit the reusable engine**

```bash
git add scripts/automation/backlog_compaction.py scripts/automation/compact_sg_todo_backlog.py tests/test_backlog_compaction.py tests/test_todo_backlog_compaction.py
git commit -m "refactor: share backlog compaction engine"
```

### Task 2: Add Capture Backlog State Management

**Files:**
- Create: `scripts/automation/manage_capture_backlog.py`
- Create: `tests/test_capture_backlog.py`

**Interfaces:**
- Consumes: generic engine from Task 1.
- Produces: `CAPTURE_SPEC`, `build_root()`, `build_failed_collection(rows, now)`, `build_archive(slug, sequence, rows, now)`, `freeze_snapshot(rows)`, `transition(markdown, capture_id, expected, target, updated, notes)`, and CLI subcommands `init`, `list`, `snapshot`, `transition`, and `compact`.

- [ ] **Step 1: Write failing state-management tests**

```python
import datetime as dt
import unittest

from scripts.automation import manage_capture_backlog as capture


class CaptureBacklogTests(unittest.TestCase):
    def test_root_has_exact_schema_and_pacific_timestamp(self):
        now = dt.datetime(2026, 7, 15, 12, 0, tzinfo=dt.timezone.utc)
        root = capture.build_root(now)
        self.assertIn("timezone: America/Los_Angeles", root)
        self.assertIn("| id | status | source kind | source | target | node | updated | notes |", root)
        self.assertIn("2026-07-15T05:00:00-07:00", root)

    def test_snapshot_is_oldest_first_and_only_planned(self):
        rows = [
            {"id": "CAP-0003", "status": "planned"},
            {"id": "CAP-0001", "status": "failed"},
            {"id": "CAP-0002", "status": "planned"},
        ]
        self.assertEqual([row["id"] for row in capture.freeze_snapshot(rows)], ["CAP-0002", "CAP-0003"])

    def test_transition_requires_expected_parent_state(self):
        root = capture.fixture_root("CAP-0001", "planned")
        updated = capture.transition(root, "CAP-0001", "planned", "capturing", "2026-07-15T05:01:00-07:00", "batch run-1")
        self.assertIn("| CAP-0001 | capturing |", updated)
        with self.assertRaisesRegex(ValueError, "expected planned, found capturing"):
            capture.transition(updated, "CAP-0001", "planned", "completed", "2026-07-15T05:02:00-07:00", "bad")

    def test_transition_rejects_unknown_status(self):
        with self.assertRaisesRegex(ValueError, "unsupported status"):
            capture.transition(capture.fixture_root("CAP-0001", "planned"), "CAP-0001", "planned", "implementing", "x", "x")
```

- [ ] **Step 2: Run the tests and confirm failure**

Run: `python3 -m unittest tests.test_capture_backlog -v`

Expected: import or missing-attribute failure for `manage_capture_backlog`.

- [ ] **Step 3: Implement Pacific time, root rendering, snapshot, and transitions**

```python
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from zoneinfo import ZoneInfo

from scripts.automation.backlog_compaction import BacklogSpec, item_number, parse_rows, render_table

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


def freeze_snapshot(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted((dict(row) for row in rows if row.get("status") == "planned"), key=item_number)


def transition(markdown: str, capture_id: str, expected: str, target: str, updated: str, notes: str) -> str:
    if expected not in ALLOWED_STATUSES or target not in ALLOWED_STATUSES:
        raise ValueError("unsupported status")
    rows = parse_rows(markdown, CAPTURE_SPEC)
    matches = [row for row in rows if row.get("id") == capture_id]
    if len(matches) != 1:
        raise ValueError(f"expected one row for {capture_id}, found {len(matches)}")
    row = matches[0]
    if row["status"] != expected:
        raise ValueError(f"expected {expected}, found {row['status']}")
    row.update(status=target, updated=updated, notes=notes)
    return replace_capture_table(markdown, rows)
```

Implement `replace_capture_table` with Task 1's generic root-table replacement and expose a test-only `fixture_root(capture_id, status)` that renders one row through the same production table path.

- [ ] **Step 4: Add verified GBrain CLI operations and compaction**

```python
def run_gbrain(args: list[str], input_text: str | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gbrain", *args], input=input_text, text=True, capture_output=True, timeout=timeout, check=False)


def get_required(slug: str) -> str:
    result = run_gbrain(["get", slug])
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout


def put_verified(slug: str, markdown: str, expected_marker: str) -> None:
    result = run_gbrain(["put", slug], input_text=markdown)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    if expected_marker not in get_required(slug):
        raise RuntimeError(f"readback marker missing for {slug}: {expected_marker}")


def link(source: str, target: str, relation: str) -> None:
    result = run_gbrain(["link", source, target, "--link-type", relation, "--link-source", "memory-stargraph-capture-backlog"])
    if result.returncode and "already" not in (result.stderr or result.stdout).lower():
        raise RuntimeError((result.stderr or result.stdout).strip())
```

The `init --apply --json` command must create and verify the root and failed collection, then create `has_failed_collection` and reverse `failed_collection_for` links. `snapshot --json` must emit `invocation_id`, `started_at`, and the frozen planned rows without mutation. `transition --id CAP-... --from ... --to ... --notes ... --apply --json` must update parent and child, read both back, and maintain failed-item links when entering or leaving `failed`. `compact --apply --json` must create immutable 50-row archives, preserve child nodes, create `has_completed_archive`/`completed_archive_for` and `contains_capture_request` links, and verify the rewritten root count.

- [ ] **Step 5: Add mocked GBrain integration tests**

```python
def test_transition_apply_updates_parent_and_child_and_failed_collection(self):
    backend = FakeGBrain.with_one_request("CAP-0001", "capturing")
    with mock.patch.object(capture, "run_gbrain", side_effect=backend):
        result = capture.apply_transition("CAP-0001", "capturing", "failed", "source login required", NOW)
    self.assertEqual(result["status"], "failed")
    self.assertIn("status: failed", backend.nodes[result["child_slug"]])
    self.assertIn("CAP-0001", backend.nodes[capture.FAILED_COLLECTION_SLUG])
    self.assertIn((capture.FAILED_COLLECTION_SLUG, result["child_slug"], "has_failed_capture"), backend.links)


def test_compaction_is_idempotent_at_fifty_completed_rows(self):
    backend = FakeGBrain.with_completed_requests(50)
    with mock.patch.object(capture, "run_gbrain", side_effect=backend):
        first = capture.apply_compaction()
        second = capture.apply_compaction()
    self.assertEqual(first["created_archives"], [f"{capture.ARCHIVE_PREFIX}0001"])
    self.assertEqual(second["created_archives"], [])
    self.assertEqual(len(capture.parse_capture_rows(backend.nodes[capture.ROOT_SLUG])), 0)
```

- [ ] **Step 6: Run capture and TODO regression tests**

Run: `python3 -m unittest tests.test_capture_backlog tests.test_backlog_compaction tests.test_todo_backlog_compaction -v`

Expected: all tests pass.

- [ ] **Step 7: Commit capture backlog state management**

```bash
git add scripts/automation/manage_capture_backlog.py tests/test_capture_backlog.py
git commit -m "feat: add capture backlog state manager"
```

### Task 3: Build the Queue-Only `/add-capture-link` Skill

**Files:**
- Create: `skills/add-capture-link/SKILL.md`
- Create: `skills/add-capture-link/agents/openai.yaml`
- Create: `skills/add-capture-link/scripts/add_capture_link.py`
- Create: `skills/add-capture-link/tests/test_add_capture_link.py`

**Interfaces:**
- Consumes: Memory Stargraph `POST /api/entity-attach-file/<encoded-request-slug>` and GBrain CLI.
- Produces: `queue_capture(...) -> dict`, CLI arguments `--source`, `--source-kind`, `--instructions`, repeated `--attachment`, optional `--target`, `--collection`, `--relationship`, `--stargraph-url`, `--recovery-manifest`, and `--json`.

- [ ] **Step 1: Write failing queue transaction tests**

```python
class AddCaptureLinkTests(unittest.TestCase):
    def test_text_only_request_is_planned_and_never_invokes_capture_skill(self):
        backend = FakeGBrain.empty_capture_root()
        with mock.patch.object(module, "run_gbrain", side_effect=backend), mock.patch.object(module, "invoke_capture_skill") as capture_skill:
            result = module.queue_capture(source="https://example.com/a", source_kind="url", instructions="Capture this page", now=NOW)
        self.assertEqual(result["capture_id"], "CAP-0001")
        self.assertEqual(result["status"], "planned")
        capture_skill.assert_not_called()

    def test_attachment_upload_is_verified_before_parent_row_and_links(self):
        attachment = self.write_file("shot.png", b"exact-image")
        backend = FakeGBrain.empty_capture_root()
        result = self.invoke(backend, attachments=[str(attachment)])
        child = backend.nodes[result["child_slug"]]
        self.assertIn(result["attachments"][0]["reference"], child)
        self.assertEqual(result["attachments"][0]["sha256"], hashlib.sha256(b"exact-image").hexdigest())
        self.assertTrue(result["durable_storage_verified"])
        self.assertLess(backend.first_upload_index, backend.parent_put_index)

    def test_partial_upload_failure_creates_no_planned_row_and_preserves_recovery_manifest(self):
        with self.assertRaises(module.QueueFailure) as caught:
            self.invoke(FakeGBrain.empty_capture_root(), attachments=[self.file("a.png"), self.file("b.png")], fail_upload_number=2)
        result = caught.exception.result
        self.assertTrue(result["reminder_required"])
        self.assertTrue(Path(result["recovery_manifest"]).is_file())
        self.assertNotIn("| CAP-", self.backend.nodes[module.PARENT_SLUG])

    def test_target_collection_and_relationship_instructions_are_preserved(self):
        backend = FakeGBrain.empty_capture_root()
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
        self.assertIn("Collection: collections/people", child)
        self.assertIn("people/tony-guan|member_of|collections/people", child)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest discover -s skills/add-capture-link/tests -v`

Expected: import or missing-file failure for `add_capture_link.py`.

- [ ] **Step 3: Implement parsing, ID allocation, request rendering, and queue-only guard**

```python
PARENT_SLUG = "notes/memory-starmap-capture-list"
ALLOWED_SOURCE_KINDS = {"url", "file", "pdf", "text", "slug", "linkedin", "wechat", "x", "profile", "mixed"}


def next_capture_id(rows: list[dict[str, str]]) -> str:
    highest = max((int(match.group(1)) for row in rows if (match := re.fullmatch(r"CAP-(\d+)", row.get("id", "")))), default=0)
    return f"CAP-{highest + 1:04d}"


def build_child(*, capture_id: str, child_slug: str, source: str, source_kind: str, instructions: str, target: str, collection: str, relationships: list[str], created_at: str, status: str, attachments: list[dict]) -> str:
    attachment_lines = [
        f"- `{item['reference']}` | bytes={item['size_bytes']} | sha256={item['sha256']}"
        for item in attachments
    ] or ["- None"]
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

{chr(10).join(f'- `{value}`' for value in relationships) if relationships else '- None'}

## Durable Attachments

{chr(10).join(attachment_lines)}

## Attempt History

- {created_at}: queued by `/add-capture-link`; capture execution has not started.
"""


def invoke_capture_skill(*args, **kwargs):
    raise AssertionError("/add-capture-link is queue-only and must not invoke capture skills")
```

- [ ] **Step 4: Implement upload-once transaction and recovery**

Reuse the already-tested multipart, private-spool, response-sanitization, durable-reference, byte-count, SHA-256, and recovery-manifest behavior from `~/.codex/skills/add-sg-todo/scripts/add_sg_todo.py`, changing only domain names and schema. The commit must contain the actual copied-and-adapted functions `validate_stargraph_url`, `check_stargraph_health`, `upload_attachment`, `durable_reference_candidates`, `_spool`, `_write_manifest`, and `sanitize_evidence`; do not import from a user-home path at runtime.

The transaction order in `queue_capture` must be exactly:

```python
paths = validate_inputs(source, source_kind, instructions, target, collection, relationships, attachments)
bundle, spooled = spool_if_needed(paths, slug_seed, now)
parent = get_required(PARENT_SLUG)
capture_id = next_capture_id(parse_capture_rows(parent))
child_slug = unique_child_slug(PARENT_SLUG, capture_id, source, parent)
put_provisional_child(child_slug, status="capture-recovery")
receipts = [upload_and_verify(base_url, child_slug, path) for path in spooled]
put_verified(child_slug, build_child(status="planned", target=target, collection=collection, relationships=relationships, attachments=receipts), "status: planned")
put_verified(PARENT_SLUG, append_planned_row(parent, capture_id, child_slug, receipts), f"| {capture_id} | planned |")
link_verified(PARENT_SLUG, child_slug, "has_capture_request")
link_verified(child_slug, PARENT_SLUG, "capture_request_for")
verify_parent_child_graph_and_receipts(capture_id, child_slug, receipts)
remove_recovery_bundle(bundle)
```

If any upload or verification fails, write a `0600` recovery manifest under `${CODEX_HOME:-~/.codex}/recovery/add-capture-link`, preserve the exact spooled bytes, do not append a planned parent row, and return `reminder_required`, `remind_after`, a proposed Stargraph/GBrain blocker, and the exact `--recovery-manifest` retry command.

- [ ] **Step 5: Write the skill contract and agent metadata**

```markdown
---
name: add-capture-link
description: Queue URLs, files, PDFs, text, GBrain slugs, profiles, or attached media for the Memory Stargraph Capture Link worker under notes/memory-starmap-capture-list. Use when the user invokes /add-capture-link or asks to add source material to the capture backlog.
---

# Add Capture Link

This skill is queue-only. It creates a `planned` capture request and never performs the final capture.

1. Pass every chat-host attachment as a repeated `--attachment` argument.
2. Use the most specific `--source-kind`; use `mixed` only when one request intentionally combines source types.
3. Run `python3 "$SKILL_DIR/scripts/add_capture_link.py" ... --json`.
4. Report success only after parent, child, graph, and durable attachment verification return `ok: true`.
5. On `ok: false`, preserve the manifest and create exactly one user-visible reminder when `reminder_required` is true; never file the original request as planned.
```

Set `agents/openai.yaml` to advertise `/add-capture-link` as queue-only and to pass attached file paths literally.

- [ ] **Step 6: Run the skill tests**

Run: `python3 -m unittest discover -s skills/add-capture-link/tests -v`

Expected: all queue, attachment, recovery, duplicate, and no-capture tests pass.

- [ ] **Step 7: Commit the add skill**

```bash
git add skills/add-capture-link
git commit -m "feat: add queue-only capture link skill"
```

### Task 4: Build `/get-capture-link` and Install Both Skills

**Files:**
- Create: `skills/get-capture-link/SKILL.md`
- Create: `skills/get-capture-link/agents/openai.yaml`
- Create: `skills/get-capture-link/scripts/get_capture_link.py`
- Create: `skills/get-capture-link/tests/test_get_capture_link.py`
- Create: `scripts/automation/install_capture_skills.py`
- Create: `tests/test_capture_skill_install.py`

**Interfaces:**
- Consumes: capture table contract from Tasks 1-3.
- Produces: `read_capture_backlog(status=None, capture_id=None) -> dict`, exact local slug-link rendering, and idempotent byte-identical installation to `~/.codex/skills` and `~/.openclaw/skills`.

- [ ] **Step 1: Write failing read-only and installation tests**

```python
def test_status_filter_and_exact_clickable_links(self):
    with mock.patch.object(module, "run_gbrain", side_effect=FakeReadOnlyGBrain(ROOT)) as backend:
        result = module.read_capture_backlog(status="failed")
    self.assertEqual([item["id"] for item in result["items"]], ["CAP-0002"])
    self.assertEqual(
        result["items"][0]["link"],
        "[notes/memory-starmap-capture-list/failure](http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-capture-list%2Ffailure)",
    )
    self.assertFalse(any(call[0] in {"put", "link", "delete"} for call in backend.calls))


def test_installer_mirrors_repository_sources_byte_for_byte(self):
    with tempfile.TemporaryDirectory() as td:
        result = installer.install(repo_root=ROOT, codex_home=Path(td) / "codex", openclaw_home=Path(td) / "openclaw")
        self.assertEqual(result["installed"], ["add-capture-link", "get-capture-link"])
        for skill in result["installed"]:
            self.assertEqual(tree_digest(ROOT / "skills" / skill), tree_digest(Path(td) / "codex" / "skills" / skill))
            self.assertEqual(tree_digest(ROOT / "skills" / skill), tree_digest(Path(td) / "openclaw" / "skills" / skill))
```

Define the digest helper in `tests/test_capture_skill_install.py` so the assertion ignores generated caches but compares every shipped byte:

```python
import hashlib


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
```

- [ ] **Step 2: Run the tests and confirm missing implementations**

Run: `python3 -m unittest discover -s skills/get-capture-link/tests -v && python3 -m unittest tests.test_capture_skill_install -v`

Expected: missing module/file failures.

- [ ] **Step 3: Implement read-only filtering and link rendering**

```python
from urllib.parse import quote

ROOT_SLUG = "notes/memory-starmap-capture-list"
ALLOWED_FILTERS = {None, "planned", "capturing", "completed", "failed"}


def slug_link(slug: str) -> str:
    return f"[{slug}](http://127.0.0.1:8788/?slug={quote(slug, safe='')})"


def read_capture_backlog(status: str | None = None, capture_id: str | None = None) -> dict:
    if status not in ALLOWED_FILTERS:
        raise ValueError("status must be planned, capturing, completed, or failed")
    markdown = run_gbrain("get", ROOT_SLUG)
    rows = parse_capture_rows(markdown)
    selected = [row for row in rows if (status is None or row["status"] == status) and (capture_id is None or row["id"] == capture_id)]
    counts = {name: sum(row["status"] == name for row in rows) for name in sorted(ALLOWED_FILTERS - {None})}
    return {
        "ok": True,
        "root_slug": ROOT_SLUG,
        "root_link": slug_link(ROOT_SLUG),
        "counts": counts,
        "items": [{**row, "slug": node_slug(row), "link": slug_link(node_slug(row))} for row in selected],
    }
```

The CLI accepts `--status`, `--id`, and `--json`. Non-JSON Markdown prints summary counts plus exact-link entries; it never invokes `put`, `link`, `delete`, capture tools, or the worker.

- [ ] **Step 4: Write the get skill contract**

```markdown
---
name: get-capture-link
description: Read and filter Memory Stargraph capture backlog status from notes/memory-starmap-capture-list. Use when the user invokes /get-capture-link or asks which capture requests are planned, capturing, completed, or failed.
---

# Get Capture Link

This skill is read-only. Run the helper with optional `--status` or `--id`, and present every returned slug using its exact local Memory Stargraph Markdown link. Never mutate status or trigger capture work.
```

- [ ] **Step 5: Implement the safe installer**

```python
SKILLS = ("add-capture-link", "get-capture-link")


def install(repo_root: Path, codex_home: Path, openclaw_home: Path) -> dict:
    installed = []
    for name in SKILLS:
        source = repo_root / "skills" / name
        if not (source / "SKILL.md").is_file():
            raise RuntimeError(f"missing canonical skill: {source}")
        for home in (codex_home, openclaw_home):
            destination = home / "skills" / name
            temporary = destination.with_name(destination.name + ".new")
            shutil.rmtree(temporary, ignore_errors=True)
            shutil.copytree(source, temporary, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if destination.exists():
                shutil.rmtree(destination)
            temporary.rename(destination)
        installed.append(name)
    return {"ok": True, "installed": installed}
```

- [ ] **Step 6: Run read-only and installation tests**

Run: `python3 -m unittest discover -s skills/get-capture-link/tests -v && python3 -m unittest tests.test_capture_skill_install -v`

Expected: all tests pass and repository, Codex, and OpenClaw trees have identical digests in the temporary fixture.

- [ ] **Step 7: Commit the get skill and installer**

```bash
git add skills/get-capture-link scripts/automation/install_capture_skills.py tests/test_capture_skill_install.py
git commit -m "feat: add capture backlog status skill"
```

### Task 5: Add the Persistent Capture Link Worker

**Files:**
- Create: `automations/memory-stargraph-capture-link-drain/automation.toml`
- Create: `automations/memory-stargraph-capture-link-drain/heartbeat-prompt.md`
- Create: `automations/memory-stargraph-capture-link-drain/prompt.md`
- Create: `automations/memory-stargraph-capture-link-drain/thread-bootstrap.md`
- Modify: `tests/test_automation_contracts.py`

**Interfaces:**
- Consumes: `/add-capture-link` queue, capture state CLI, installed enhanced source-specific skills.
- Produces: heartbeat automation `memory-stargraph-capture-link-drain` targeting one persistent worker task and one Goal-linked Run per invocation.

- [ ] **Step 1: Write failing worker-contract tests**

```python
import tomllib


def test_capture_worker_is_persistent_midnight_and_manually_triggerable(self):
    definition = tomllib.loads((ROOT / "automations/memory-stargraph-capture-link-drain/automation.toml").read_text())
    prompt = (ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md").read_text()
    self.assertEqual(definition["id"], "memory-stargraph-capture-link-drain")
    self.assertEqual(definition["rrule"], "FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0")
    self.assertEqual(definition["timezone"], "America/Los_Angeles")
    self.assertEqual(definition["destination"], "thread")
    self.assertIn("{{CAPTURE_LINK_THREAD_ID}}", definition["target_thread_id"])
    self.assertIn("manual", prompt.lower())
    self.assertNotIn("cutoff", prompt.lower())


def test_capture_worker_freezes_and_drains_every_selected_item(self):
    prompt = (ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md").read_text()
    self.assertIn("first authoritative snapshot", prompt)
    self.assertIn("planned` to `capturing", prompt)
    self.assertIn("every frozen item", prompt)
    self.assertIn("completed` or `failed", prompt)
    self.assertIn("created after the frozen snapshot", prompt)


def test_capture_worker_routes_to_most_specific_local_skill_and_reuses_media(self):
    prompt = (ROOT / "automations/memory-stargraph-capture-link-drain/prompt.md").read_text()
    self.assertIn("~/.codex/skills/<skill>/SKILL.md", prompt)
    self.assertIn("~/.openclaw/skills/<skill>/SKILL.md", prompt)
    self.assertIn("gbrain-capture-link", prompt)
    self.assertIn("gbrain-pdf-capture", prompt)
    self.assertIn("gb-capture-linkedin", prompt)
    self.assertIn("must not upload or copy the bytes again", prompt)
```

- [ ] **Step 2: Run the automation tests and confirm missing files**

Run: `python3 -m unittest tests.test_automation_contracts -v`

Expected: failures because `automations/memory-stargraph-capture-link-drain` does not exist.

- [ ] **Step 3: Create the tracked definition and heartbeat**

```toml
version = 1
id = "memory-stargraph-capture-link-drain"
kind = "heartbeat"
name = "Memory Stargraph Capture Link Worker"
status = "ACTIVE"
rrule = "FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0"
timezone = "America/Los_Angeles"
destination = "thread"
target_thread_id = "{{CAPTURE_LINK_THREAD_ID}}"
prompt_file = "heartbeat-prompt.md"
worker_prompt_file = "prompt.md"
thread_bootstrap_file = "thread-bootstrap.md"
```

```markdown
<heartbeat>
  <automation_id>memory-stargraph-capture-link-drain</automation_id>
  <instructions>Run the complete Capture Link worker instructions now. Anchor all logging to the actual invocation time in America/Los_Angeles, freeze the first planned snapshot, and drain every frozen item to completed or failed.</instructions>
</heartbeat>
```

- [ ] **Step 4: Write the complete worker prompt**

The prompt must contain these operational commands and gates verbatim:

```markdown
1. Record an invocation id and timezone-aware start time in `America/Los_Angeles`. This worker may be started by its midnight heartbeat or manually at any time; there is no fixed cutoff.
2. Run `python3 scripts/automation/manage_capture_backlog.py compact --apply --json`.
3. Run `python3 scripts/automation/manage_capture_backlog.py snapshot --json` exactly once. This is the first authoritative snapshot. Items created after it belong to the next invocation.
4. Group frozen requests into the smallest safe coherent batches by source type, login/session, selected skill, target collection, verification path, and rollback boundary.
5. Before capture, move each selected request from `planned` to `capturing` in both parent and child with `manage_capture_backlog.py transition`; verify both readbacks.
6. Drain every frozen item. For each source, read the most specific installed skill completely, preferring `~/.codex/skills/<skill>/SKILL.md`, then `~/.openclaw/skills/<skill>/SKILL.md`, then repository/bundled fallback.
7. Route general sources to `gbrain-capture-link`, PDFs to `gbrain-pdf-capture`, LinkedIn to `gb-capture-linkedin`, and WeChat/X/profile sources to the most specific installed enhanced skill.
8. Reuse request attachments by durable reference and verified SHA-256. The final node must not upload or copy the bytes again. Link request to final with `captured_as` and final to request with `captured_from`.
9. Mark each frozen request `completed` only after source-specific readback, title, search, provenance, memberships, typed relationships, and attachment reuse verification. Otherwise mark it `failed` with exact attempt, evidence, preserved inputs, retry action, and human authority needed.
10. Run compaction again. Create one Goal-linked Run with invocation, batch grouping, every terminal item, failures, post-snapshot ids, timestamps, and durable Learnings.
```

Also include the browser reuse contract, authenticated Chrome CDP fallback, source title sanitization, no automatic `index` links, privacy/auth/approval gates, and exact clickable local slug formatting.

- [ ] **Step 5: Write persistent-task bootstrap instructions**

```markdown
You are the persistent Memory Stargraph Capture Link Worker. Read `automations/memory-stargraph-capture-link-drain/prompt.md` completely on every heartbeat or manual trigger. Work only on the frozen `planned` snapshot from `notes/memory-starmap-capture-list`; do not implement product TODOs. Use America/Los_Angeles for all worker evidence, preserve human control, and keep this task reusable across invocations.
```

- [ ] **Step 6: Run automation contract tests**

Run: `python3 -m unittest tests.test_automation_contracts -v`

Expected: all existing and new automation contract tests pass.

- [ ] **Step 7: Commit the tracked capture worker**

```bash
git add automations/memory-stargraph-capture-link-drain tests/test_automation_contracts.py
git commit -m "feat: add persistent capture link worker"
```

### Task 6: Enforce `America/Los_Angeles` Across Every Worker

**Files:**
- Modify: `automations/gbrain-x-intelligence-capture/prompt.md`
- Modify: `automations/memory-stargraph-daily-learning-intake/prompt.md`
- Modify: `automations/memory-stargraph-wish-to-reallity/prompt.md`
- Modify: `automations/memory-stargraph-divergent-product-discovery/prompt.md`
- Modify: `automations/memory-stargraph-goal-steward-daily-review/prompt.md`
- Modify: `tests/test_automation_contracts.py`

**Interfaces:**
- Produces: one exact reporting contract shared by all six worker prompts.

- [ ] **Step 1: Add failing all-worker timezone tests**

```python
def test_every_worker_uses_dst_aware_pacific_reporting(self):
    workers = (
        "gbrain-x-intelligence-capture",
        "memory-stargraph-daily-learning-intake",
        "memory-stargraph-wish-to-reallity",
        "memory-stargraph-divergent-product-discovery",
        "memory-stargraph-goal-steward-daily-review",
        "memory-stargraph-capture-link-drain",
    )
    required = (
        "America/Los_Angeles",
        "timezone-aware ISO 8601",
        "PDT in summer",
        "PST in winter",
        "Do not use a fixed UTC-8 offset",
    )
    for worker in workers:
        prompt = (ROOT / "automations" / worker / "prompt.md").read_text()
        for phrase in required:
            self.assertIn(phrase, prompt, f"{worker} missing {phrase}")
```

- [ ] **Step 2: Run the test and confirm five existing prompts fail**

Run: `python3 -m unittest tests.test_automation_contracts.AutomationContractTests.test_every_worker_uses_dst_aware_pacific_reporting -v`

Expected: fail on the first existing prompt missing the reporting contract.

- [ ] **Step 3: Append the exact contract to all six prompts**

```markdown
Pacific-time reporting contract: worker-generated logs, Run records, batch reports, status-transition evidence, timestamped filenames, and final reports must use timezone-aware ISO 8601 values in `America/Los_Angeles`. This means PDT in summer (`-07:00`) and PST in winter (`-08:00`). Do not use a fixed UTC-8 offset or label UTC values as Pacific time. Preserve source-native timestamps as provenance when needed, but add a Pacific-normalized value for worker evidence.
```

- [ ] **Step 4: Run the all-worker and full automation tests**

Run: `python3 -m unittest tests.test_automation_contracts -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the prompt contract**

```bash
git add automations/*/prompt.md tests/test_automation_contracts.py
git commit -m "chore: standardize worker Pacific timestamps"
```

### Task 7: Document, Install, Initialize, and Synchronize the Live Runtime

**Files:**
- Modify: `automations/README.md`
- Modify: `docs/automation-runbook.md`
- Modify: live skill trees under `~/.codex/skills` and `~/.openclaw/skills` by running the committed installer
- Modify: live automation definitions/prompts through the Codex automation API
- Create in GBrain: `notes/memory-starmap-capture-list` and `notes/memory-starmap-capture-list/failed-items`

**Interfaces:**
- Consumes: all committed components from Tasks 1-6.
- Produces: active local skills, initialized GBrain queue, persistent worker task, active midnight heartbeat, live prompt parity, and verification evidence.

- [ ] **Step 1: Update pipeline and operator documentation**

Add a midnight Capture Link row to `automations/README.md`, shifting X intelligence to its existing 12:15 AM row rather than implying ordering dependency. Document that manual trigger time is unrestricted. In `docs/automation-runbook.md`, add exact commands:

```bash
python3 scripts/automation/manage_capture_backlog.py init --apply --json
python3 scripts/automation/manage_capture_backlog.py list --json
python3 scripts/automation/manage_capture_backlog.py snapshot --json
python3 scripts/automation/manage_capture_backlog.py compact --apply --json
python3 scripts/automation/install_capture_skills.py --json
```

Document statuses, frozen-snapshot behavior, upload-once attachment ownership, `captured_as`/`captured_from`, failed-items collection, 50-row archives, manual worker triggers, and `America/Los_Angeles` timestamps.

- [ ] **Step 2: Run the full repository test suite before live mutation**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests pass.

Run: `python3 -m unittest discover -s skills/add-capture-link/tests -v && python3 -m unittest discover -s skills/get-capture-link/tests -v`

Expected: all skill tests pass.

- [ ] **Step 3: Commit documentation**

```bash
git add automations/README.md docs/automation-runbook.md
git commit -m "docs: add capture backlog operations"
```

- [ ] **Step 4: Install and verify both local skill copies**

Run: `python3 scripts/automation/install_capture_skills.py --json`

Expected JSON: `ok: true` and installed names `add-capture-link`, `get-capture-link`.

Run: `diff -qr skills/add-capture-link ~/.codex/skills/add-capture-link && diff -qr skills/add-capture-link ~/.openclaw/skills/add-capture-link && diff -qr skills/get-capture-link ~/.codex/skills/get-capture-link && diff -qr skills/get-capture-link ~/.openclaw/skills/get-capture-link`

Expected: no output and exit code 0.

- [ ] **Step 5: Initialize and verify the live GBrain backlog**

Run: `python3 scripts/automation/manage_capture_backlog.py init --apply --json`

Expected JSON: `ok: true`, exact root and failed collection slugs, and verified forward/reverse links.

Run: `gbrain get notes/memory-starmap-capture-list && gbrain get notes/memory-starmap-capture-list/failed-items && gbrain graph notes/memory-starmap-capture-list --depth 1`

Expected: root contains the exact Capture Items header, failed collection exists, and graph output contains the failed collection link.

- [ ] **Step 6: Create the persistent worker task and live heartbeat**

Use the Codex task-management tool to create one dedicated task from `automations/memory-stargraph-capture-link-drain/thread-bootstrap.md`; record its real task id. Use the Codex automation update tool to create or update `memory-stargraph-capture-link-drain` with:

```text
status=ACTIVE
rrule=FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0
timezone=America/Los_Angeles
destination=thread
target_thread_id=<the real persistent Capture Link task id>
prompt=<heartbeat-prompt.md content>
```

Do not trigger the worker as part of setup unless Tony separately requests a run; verify the destination and schedule read-only after creation.

- [ ] **Step 7: Synchronize Pacific-time language to all existing live workers**

For each live automation id below, use the automation update tool to preserve its current schedule, status, and destination while replacing its worker/heartbeat prompt with the checked-in prompt contract:

```text
gbrain-x-intelligence-capture
memory-stargraph-daily-learning-intake
memory-stargraph-wish-to-reallity
memory-stargraph-divergent-product-discovery
memory-stargraph-goal-steward-daily-review
```

Read each automation back and verify `America/Los_Angeles`, timezone-aware ISO 8601, PDT/PST language, existing target task id, and unchanged schedule/status.

- [ ] **Step 8: Run a non-mutating live skill smoke test**

Run:

```bash
python3 ~/.codex/skills/add-capture-link/scripts/add_capture_link.py --help
python3 ~/.codex/skills/get-capture-link/scripts/get_capture_link.py --json
```

Expected: the add helper exposes the documented queue-only arguments, and the get helper reads the live initialized root with `ok: true` without mutation. Attachment and parent/child transaction behavior remains covered by the endpoint-mocked tests; do not create an artificial live request that a later worker could mistake for user-authorized capture work.

- [ ] **Step 9: Final verification and handoff**

Run: `git status --short && git log --oneline --decorate -8`

Expected: clean tracked worktree and the plan's focused commits.

Report: installed skill paths, initialized root and failed slugs, persistent task id, automation id/status/schedule/destination, live parity for all six worker prompts, non-mutating smoke results, tests, and any authority-gated follow-up. Present every GBrain slug as an exact clickable local Memory Stargraph link.
