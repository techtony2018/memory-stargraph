# Worker Invocation And Wish TODO Drain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all five Memory Stargraph workers correct when invoked at any time, and make each Wish to Reallity invocation drain its invocation-start planned queue to truthful terminal states.

**Architecture:** Keep recurrence rules solely in each `automation.toml`; operational prompts derive identity, windows, and cutoffs from the actual invocation. Enforce that separation with repository-level `unittest` contract tests, then sync only the embedded trigger text into the five live automation definitions while preserving schedules, statuses, and persistent destination task IDs.

**Tech Stack:** Markdown worker prompts, TOML automation definitions, Python 3 standard-library `unittest` and `tomllib`, GBrain CLI contracts.

## Global Constraints

- A scheduled heartbeat or explicit manual run request may invoke any worker at any time.
- Every invocation records its actual `started_at` timestamp and a unique invocation ID.
- Relative evidence windows are anchored to actual `started_at`, never an assumed schedule time.
- Fixed clock times remain only in recurrence configuration or schedule documentation.
- Wish snapshots every parent backlog row that is exactly `planned` on its first authoritative read.
- Every Wish snapshot item must become `completed` or `failed` in both parent and child representations before the drain Run completes.
- Wish may use as many sequential batches and same-task continuations as needed; it has no run-wide API, UI, feature, architecture, or repository-boundary cutoff.
- Risky, destructive, privacy-sensitive, credentialed, or approval-gated actions still require human approval.
- Runtime `status`, `rrule`, `target_thread_id`, local memory, deployment configuration, and private coordinates must be preserved.
- Do not trigger an extra production worker invocation merely to verify wording.

---

### Task 1: Enforce The Cross-Worker Invocation Contract

**Files:**
- Create: `tests/test_automation_contracts.py`
- Modify: `automations/gbrain-x-intelligence-capture/prompt.md`
- Modify: `automations/gbrain-x-intelligence-capture/heartbeat-prompt.md`
- Modify: `automations/gbrain-x-intelligence-capture/thread-bootstrap.md`
- Modify: `automations/memory-stargraph-daily-learning-intake/prompt.md`
- Modify: `automations/memory-stargraph-daily-learning-intake/heartbeat-prompt.md`
- Modify: `automations/memory-stargraph-daily-learning-intake/thread-bootstrap.md`
- Modify: `automations/memory-stargraph-wish-to-reallity/prompt.md`
- Modify: `automations/memory-stargraph-wish-to-reallity/heartbeat-prompt.md`
- Modify: `automations/memory-stargraph-wish-to-reallity/thread-bootstrap.md`
- Modify: `automations/memory-stargraph-divergent-product-discovery/prompt.md`
- Modify: `automations/memory-stargraph-divergent-product-discovery/heartbeat-prompt.md`
- Modify: `automations/memory-stargraph-divergent-product-discovery/thread-bootstrap.md`
- Modify: `automations/memory-stargraph-goal-steward-daily-review/prompt.md`
- Modify: `automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md`

**Interfaces:**
- Consumes: each worker's existing persistent-task and `automation.toml` recurrence contract.
- Produces: one exact invocation paragraph shared by all run prompts; schedule-independent trigger/bootstrap wording; `WorkerInvocationContractTests` guarding both.

- [ ] **Step 1: Write the failing cross-worker contract tests**

Create `tests/test_automation_contracts.py` with:

```python
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUN_PROMPTS = {
    "gbrain-x-intelligence-capture": ROOT / "automations/gbrain-x-intelligence-capture/prompt.md",
    "memory-stargraph-daily-learning-intake": ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md",
    "memory-stargraph-wish-to-reallity": ROOT / "automations/memory-stargraph-wish-to-reallity/prompt.md",
    "memory-stargraph-divergent-product-discovery": ROOT / "automations/memory-stargraph-divergent-product-discovery/prompt.md",
    "memory-stargraph-goal-steward-daily-review": ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md",
}

TRIGGER_PROMPTS = [
    ROOT / "automations/gbrain-x-intelligence-capture/heartbeat-prompt.md",
    ROOT / "automations/memory-stargraph-daily-learning-intake/heartbeat-prompt.md",
    ROOT / "automations/memory-stargraph-wish-to-reallity/heartbeat-prompt.md",
    ROOT / "automations/memory-stargraph-divergent-product-discovery/heartbeat-prompt.md",
]

BOOTSTRAPS = [
    ROOT / "automations/gbrain-x-intelligence-capture/thread-bootstrap.md",
    ROOT / "automations/memory-stargraph-daily-learning-intake/thread-bootstrap.md",
    ROOT / "automations/memory-stargraph-wish-to-reallity/thread-bootstrap.md",
    ROOT / "automations/memory-stargraph-divergent-product-discovery/thread-bootstrap.md",
    ROOT / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md",
]

OPERATIONAL_PROMPTS = list(RUN_PROMPTS.values()) + TRIGGER_PROMPTS + BOOTSTRAPS
FIXED_CLOCK = re.compile(r"\b(?:0?[1-9]|1[0-2]):[0-5]\d\s*(?:AM|PM)\b", re.IGNORECASE)


class WorkerInvocationContractTests(unittest.TestCase):
    def test_every_run_prompt_is_invocation_scoped(self):
        required = (
            "scheduled heartbeat or explicit manual invocation",
            "`started_at`",
            "unique invocation ID",
            "same-day Runs",
            "default trigger, not a correctness assumption",
        )
        for worker_id, path in RUN_PROMPTS.items():
            with self.subTest(worker=worker_id):
                text = path.read_text()
                for phrase in required:
                    self.assertIn(phrase, text)

    def test_heartbeat_prompts_allow_scheduled_or_manual_delivery(self):
        for path in TRIGGER_PROMPTS:
            with self.subTest(path=path):
                self.assertIn("This trigger may be scheduled or manual.", path.read_text())

    def test_bootstraps_allow_invocation_at_any_time(self):
        for path in BOOTSTRAPS:
            with self.subTest(path=path):
                text = path.read_text()
                self.assertIn("scheduled heartbeat or explicit manual invocation", text)
                self.assertIn("at any time", text)

    def test_operational_prompts_do_not_hard_code_clock_times(self):
        for path in OPERATIONAL_PROMPTS:
            with self.subTest(path=path):
                match = FIXED_CLOCK.search(path.read_text())
                self.assertIsNone(match, f"hard-coded clock time {match.group(0)!r} in {path}" if match else "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify the new contract fails**

Run:

```bash
python3 -m unittest tests.test_automation_contracts.WorkerInvocationContractTests -v
```

Expected: FAIL because the run prompts lack `started_at`/invocation-ID language, heartbeat prompts describe only scheduled delivery, and bootstraps describe only future heartbeats.

- [ ] **Step 3: Add the exact shared invocation paragraph to all five run prompts**

Insert this paragraph immediately after each worker's opening role sentence in every file in `RUN_PROMPTS`:

```markdown
Invocation contract: This worker may be invoked by a scheduled heartbeat or explicit manual invocation at any time. At the start of every invocation, record the actual `started_at` timestamp and a unique invocation ID. Anchor all relative evidence windows to `started_at`, and use the invocation ID in the Goal-linked Run slug and record so same-day Runs never collide. The recurrence in `automation.toml` is a default trigger, not a correctness assumption.
```

Change time-bound role wording without changing responsibility:

```markdown
You are the X intelligence collector for GBrain and Memory Stargraph.
```

```markdown
You are the evidence and learning-intake automation for Memory Stargraph.
```

```markdown
You are the autonomous implementation worker for Memory Stargraph.
```

In the learning-intake prompt, replace “daily Memory Stargraph Wish to Reallity implementation run” with “next Memory Stargraph Wish to Reallity implementation invocation.” In its evidence step and the steward prompt, retain “previous 24 hours” but explicitly say the window ends at the current invocation's `started_at`.

- [ ] **Step 4: Make heartbeat and bootstrap wording trigger-agnostic**

For the X intelligence, learning-intake, and divergent-discovery `heartbeat-prompt.md` files, retain the worker-specific output requirements and add this exact sentence after the opening run command:

```markdown
This trigger may be scheduled or manual.
```

Replace the Wish heartbeat completely with this ordering so the invocation cutoff cannot drift while repository sync runs:

```markdown
Run the Memory Stargraph Wish to Reallity implementation cycle now in this persistent worktree task. This trigger may be scheduled or manual. Record the actual `started_at` and immediately capture the first authoritative backlog snapshot before mutable work. Then sync remote HEAD while preserving unrelated changes, read and follow `automations/memory-stargraph-wish-to-reallity/prompt.md` as the current source of truth, and report implementation, tests, deployment, Run, and Learning evidence back in this task.
```

Replace each bootstrap's final future-trigger sentence with worker-appropriate wording containing this exact contract:

```markdown
Future messages containing a scheduled heartbeat or explicit manual invocation may trigger a run in this same persistent task at any time. Use the actual invocation time and current tracked prompt; never assume the configured recurrence time.
```

For Wish to Reallity, preserve its worktree/sync requirement. In `steward-thread-prompt.md`, add the same sentence after the authoritative-context section because that file is both the steward's persistent bootstrap and owner contract.

- [ ] **Step 5: Run the cross-worker tests and verify they pass**

Run:

```bash
python3 -m unittest tests.test_automation_contracts.WorkerInvocationContractTests -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Verify recurrence configuration did not change**

Run:

```bash
git diff --exit-code -- 'automations/*/automation.toml'
```

Expected: exit 0 with no output.

- [ ] **Step 7: Commit the cross-worker invocation contract**

```bash
git add tests/test_automation_contracts.py \
  automations/gbrain-x-intelligence-capture/{prompt,heartbeat-prompt,thread-bootstrap}.md \
  automations/memory-stargraph-daily-learning-intake/{prompt,heartbeat-prompt,thread-bootstrap}.md \
  automations/memory-stargraph-wish-to-reallity/{prompt,heartbeat-prompt,thread-bootstrap}.md \
  automations/memory-stargraph-divergent-product-discovery/{prompt,heartbeat-prompt,thread-bootstrap}.md \
  automations/memory-stargraph-goal-steward-daily-review/{prompt,steward-thread-prompt}.md
git commit -m "feat: make worker invocations schedule independent"
```

---

### Task 2: Replace Wish Single-Batch Selection With Invocation-Scoped Drainage

**Files:**
- Modify: `tests/test_automation_contracts.py`
- Modify: `automations/memory-stargraph-wish-to-reallity/prompt.md`

**Interfaces:**
- Consumes: the `started_at` and unique invocation ID contract from Task 1; authoritative backlog node `notes/memory-starmap-todo-list`; live destination in `~/.codex/automations/memory-stargraph-wish-to-reallity/automation.toml`.
- Produces: immutable `snapshot_ids`, sequential `batch_ids`, terminal parent/child status, parent drain Run, batch Runs, and enumerable failed-item membership.

- [ ] **Step 1: Write failing Wish drain contract tests**

Append this class above the `if __name__ == "__main__"` block in `tests/test_automation_contracts.py`:

```python
class WishDrainContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = RUN_PROMPTS["memory-stargraph-wish-to-reallity"].read_text()

    def test_first_backlog_read_creates_immutable_snapshot(self):
        required = (
            "first authoritative backlog read",
            "snapshot every parent row whose status is exactly `planned`",
            "no clock hour is special",
            "A non-empty snapshot cannot produce a no-op",
            "post-cutoff",
        )
        for phrase in required:
            self.assertIn(phrase, self.text)

    def test_every_snapshot_item_reaches_a_terminal_state(self):
        required = (
            "every snapshot item",
            "`completed` or `failed`",
            "parent row and child node",
            "No snapshot item may remain `planned` or `implementing`",
        )
        for phrase in required:
            self.assertIn(phrase, self.text)

    def test_drain_can_use_multiple_batches_and_same_task_continuations(self):
        required = (
            "as many sequential batches as needed",
            "same persistent task",
            "target_thread_id",
            "not limited by one API, UI, feature, architecture, repository boundary, or batch",
        )
        for phrase in required:
            self.assertIn(phrase, self.text)

    def test_failed_items_have_evidence_and_collection_membership(self):
        required = (
            "real implementation attempt",
            "human_approval_required",
            "has_failed_collection",
            "failed_items_for",
            "has_failed_item",
            "member_of",
        )
        for phrase in required:
            self.assertIn(phrase, self.text)

    def test_old_single_batch_early_exit_contract_is_removed(self):
        self.assertNotIn("Select a coherent, bounded batch", self.text)
        self.assertNotIn("report no-op and exit", self.text)

    def test_trigger_captures_snapshot_before_repository_sync(self):
        heartbeat = (ROOT / "automations/memory-stargraph-wish-to-reallity/heartbeat-prompt.md").read_text()
        snapshot_at = heartbeat.index("first authoritative backlog snapshot")
        sync_at = heartbeat.index("sync remote HEAD")
        self.assertLess(snapshot_at, sync_at)
```

- [ ] **Step 2: Run the Wish tests and verify the old prompt fails**

Run:

```bash
python3 -m unittest tests.test_automation_contracts.WishDrainContractTests -v
```

Expected: FAIL on the missing snapshot, terminal-state, continuation, and failed-collection requirements; the former single-batch selection text is still present.

- [ ] **Step 3: Replace the Wish execution loop with the exact drain phases**

Keep its role, Goal, human-control, workspace, test, deployment, version, retrospective, and evidence requirements. Replace the numbered single-batch loop with these sections and exact obligations:

```markdown
## Invocation And Cutoff Snapshot

1. Record the actual `started_at` and unique drain invocation ID before mutable work.
2. Make the first authoritative backlog read with `gbrain get notes/memory-starmap-todo-list`; this first authoritative backlog read must snapshot every parent row whose status is exactly `planned`. Record the ordered IDs, priorities, and initial child statuses. This is the immutable cutoff, and no clock hour is special.
3. TODOs created after that read are post-cutoff. List them in the final report and leave them for the next scheduled or manual invocation.
4. An empty snapshot produces a verified no-op Goal-linked Run. A non-empty snapshot cannot produce a no-op.
5. Run normal automation-memory, runbook, preflight, and remote-HEAD sync checks while preserving the established snapshot and unrelated user changes.

## Drain Queue And Batches

The drain is responsible for every snapshot item and is not limited by one API, UI, feature, architecture, repository boundary, or batch. Order by priority, age, and dependency, then use as many sequential batches as needed. Coherence constrains an individual batch only; it may never omit unrelated snapshot items from the drain.

For each batch:

1. Re-read its parent rows and child nodes, then write bounded acceptance criteria, tests, rollback, and showcase evidence.
2. Change each selected parent row and child node from `planned` to `implementing` and verify both reads.
3. Make a real implementation attempt using existing project patterns. Run the smallest relevant tests early, inspect failures, iterate, and avoid unrelated refactors.
4. Apply all scope-appropriate test, browser, version, commit, push, deployment, and target-verification rules below.
5. Create a Goal-linked batch Run connected to the parent drain Run with `part_of`.
6. Terminalize every batch item as `completed` or `failed` in both the parent row and child node, then verify both reads.

A failed batch must not prevent later independent batches from running.

## Continuations

Prefer sequential batches in this persistent task. If context or runtime limits require another turn, persist the drain ID, cutoff, remaining snapshot IDs, terminal results, repository state, and next batch in automation memory and the in-progress parent Run. Read `target_thread_id` from `~/.codex/automations/memory-stargraph-wish-to-reallity/automation.toml`, then send one immediate continuation message to the same persistent task. Do not create parallel implementation tasks for overlapping repository or deployment work. Batch count, elapsed time, or unrelated scopes are not valid reasons to stop.

## Completion And Failure

Mark an item `completed` only after its acceptance criteria and required target verification pass. Evidence must include changed artifacts, tests, iteration/correction, commit and push result when applicable, deployment and version state when applicable, showcase slug, and rollback information.

Mark an item `failed` only after a real implementation attempt proves a concrete blocker or failed acceptance criterion. Record attempted steps, exact error or missing authority, tests and service/deployment readback, rollback or containment state, smallest recovery action, and dependency impact. Difficulty, priority, elapsed time, or an unrelated scope are not failure reasons.

If destructive migration, privacy-sensitive capture, resolver action, broad architecture approval, credentials, or external authority is required, stop before that action and use `human_approval_required` or the precise authority blocker. Never infer approval, and do not push or deploy unsafe partial work.

Ensure `notes/memory-starmap-todo-list/failed-items` exists. Maintain these enumerable links for every failed item:

- parent backlog -> failed collection with `has_failed_collection`;
- failed collection -> parent backlog with `failed_items_for`;
- failed collection -> failed child with `has_failed_item`;
- failed child -> failed collection with `member_of`.

Backfill existing failed child nodes without changing their evidence. Failed items remain visible in the parent backlog with status `failed`.

## Run Evidence And Terminal Verification

Create one parent Goal-linked drain Run using a collision-safe slug such as `runs/memory-stargraph-wish-to-reallity-drain-YYYY-MM-DDTHHMMSSZ`. Start it as `in_progress`, record the immutable snapshot and batch queue, and update it after every batch.

Before completing the parent Run:

1. Re-read the parent backlog and every snapshot child node.
2. Prove every snapshot item is `completed` or `failed` in both the parent row and child node.
3. Prove every failed item has bidirectional failed-collection membership.
4. No snapshot item may remain `planned` or `implementing`.
5. List post-cutoff items separately without modifying them.
6. Verify the parent drain Run and every batch Run link to the persistent Goal.

Failed terminal verification requires correction or another continuation. Finish with `drained_all_completed` or `drained_with_item_failures`, never partial success.
```

After these sections, retain the existing concrete verification commands, dashboard-managed browser verification, version synchronization, deployment-target verification, safe staging/commit/push rules, durable Learning limits, five-minute retrospective, and final-report fields. Change those fields from “selected TODO ids” to snapshot, completed, failed, and post-cutoff IDs plus batch/continuation counts.

- [ ] **Step 4: Run Wish and cross-worker contract tests**

Run:

```bash
python3 -m unittest tests.test_automation_contracts -v
```

Expected: 10 tests PASS.

- [ ] **Step 5: Review the full Wish prompt for contradictory early exits**

Run:

```bash
rg -n "Select a coherent|selected batch|report no-op and exit|single batch|sufficient evidence or value" automations/memory-stargraph-wish-to-reallity/prompt.md
```

Expected: no output.

- [ ] **Step 6: Commit the drain contract**

```bash
git add tests/test_automation_contracts.py automations/memory-stargraph-wish-to-reallity/prompt.md
git commit -m "feat: drain invocation-start TODO queue"
```

---

### Task 3: Document Default Schedules, Manual Runs, And Drain Recovery

**Files:**
- Modify: `tests/test_automation_contracts.py`
- Modify: `automations/README.md`
- Modify: `docs/automation-runbook.md`

**Interfaces:**
- Consumes: Task 1 invocation terminology and Task 2 drain/continuation/failure relations.
- Produces: operator-facing distinction between default trigger configuration and invocation semantics, plus a safe manual-run and recovery procedure.

- [ ] **Step 1: Write failing documentation contract tests**

Append this class above the main guard in `tests/test_automation_contracts.py`:

```python
class AutomationDocumentationContractTests(unittest.TestCase):
    def test_readme_labels_schedules_as_defaults(self):
        text = (ROOT / "automations/README.md").read_text()
        self.assertIn("Default trigger (local time)", text)
        self.assertIn("scheduled heartbeat or explicit manual invocation", text)
        self.assertIn("recurrence is trigger configuration, not worker business logic", text)

    def test_runbook_documents_invocation_and_wish_recovery(self):
        text = (ROOT / "docs/automation-runbook.md").read_text()
        required = (
            "## Invocation Contract",
            "actual `started_at`",
            "## Wish Drain Recovery",
            "same persistent task",
            "notes/memory-starmap-todo-list/failed-items",
        )
        for phrase in required:
            self.assertIn(phrase, text)
```

- [ ] **Step 2: Run the documentation tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_automation_contracts.AutomationDocumentationContractTests -v
```

Expected: 2 FAIL because the README treats times as the pipeline identity and the runbook has no invocation/drain recovery sections.

- [ ] **Step 3: Update the automation README with exact schedule semantics**

Rename the first pipeline table column to `Default trigger (local time)` and change the Wish purpose to “Drain the invocation-start planned TODO snapshot through implementation, verification, deployment, and Learning.” Add this paragraph immediately after the table:

```markdown
Each recurrence is trigger configuration, not worker business logic. Any persistent worker task may receive a scheduled heartbeat or explicit manual invocation at any time. Both paths use the same current tracked worker prompt, actual invocation `started_at`, unique invocation ID, evidence contract, and Goal links. Multiple same-day invocations are valid and must create distinct Runs.
```

In the restore checklist, require verification of both scheduled and manual trigger wording without sending a live run message.

- [ ] **Step 4: Add the runbook invocation and recovery procedures**

Insert this section after “Tracked Automation Definitions”:

```markdown
## Invocation Contract

The `rrule` in each live or tracked `automation.toml` is its default heartbeat trigger. It is never an execution cutoff. A scheduled heartbeat or explicit manual invocation may start the persistent worker at any time. The worker must record actual `started_at`, create a unique invocation ID and collision-safe Run slug, anchor relative windows to that timestamp, and read the current tracked prompt. Do not create a second persistent destination task for a manual run.
```

Insert this section before “Five-Minute Retrospective Hook”:

```markdown
## Wish Drain Recovery

The first authoritative backlog read after invocation establishes the immutable planned-item snapshot. If the worker cannot finish safely in the current turn, keep the parent drain Run `in_progress`, save remaining IDs and repository/deployment state, read the live `target_thread_id`, and send one continuation to the same persistent task. Never parallelize overlapping repository or deployment mutation.

Each snapshot item must finish as `completed` or `failed` in both parent and child records. A failed item needs concrete attempt, blocker, readback, rollback/containment, and recovery evidence. Ensure it is enumerable through `notes/memory-starmap-todo-list/failed-items` using `has_failed_collection`, `failed_items_for`, `has_failed_item`, and `member_of`. Human approval blockers remain failures for that invocation; they are not permission to take the gated action.
```

- [ ] **Step 5: Run documentation and full repository tests**

Run:

```bash
python3 -m unittest tests.test_automation_contracts -v
python3 -m unittest discover -s tests
```

Expected: automation contract tests PASS; full repository unittest suite PASS.

- [ ] **Step 6: Commit documentation and tests**

```bash
git add tests/test_automation_contracts.py automations/README.md docs/automation-runbook.md
git commit -m "docs: explain manual worker invocation and drain recovery"
```

---

### Task 4: Sync Live Trigger Prompts Without Changing Automation Identity

**Files:**
- Modify outside Git: `~/.codex/automations/gbrain-x-intelligence-capture/automation.toml`
- Modify outside Git: `~/.codex/automations/memory-stargraph-daily-learning-intake/automation.toml`
- Modify outside Git: `~/.codex/automations/memory-stargraph-wish-to-reallity/automation.toml`
- Modify outside Git: `~/.codex/automations/memory-stargraph-divergent-product-discovery/automation.toml`
- Modify outside Git: `~/.codex/automations/memory-stargraph-goal-steward-daily-review/automation.toml`

**Interfaces:**
- Consumes: live `prompt`, `status`, `rrule`, and `target_thread_id`; tracked trigger wording from Tasks 1–3.
- Produces: live embedded trigger prompts that permit scheduled or manual delivery while retaining all five persistent destinations and schedules.

- [ ] **Step 1: Capture immutable live fields before editing**

Run this read-only validation and save its output in the implementation report, not in Git:

```bash
python3 - <<'PY'
from pathlib import Path
import tomllib

root = Path.home() / ".codex/automations"
ids = (
    "gbrain-x-intelligence-capture",
    "memory-stargraph-daily-learning-intake",
    "memory-stargraph-wish-to-reallity",
    "memory-stargraph-divergent-product-discovery",
    "memory-stargraph-goal-steward-daily-review",
)
for automation_id in ids:
    data = tomllib.loads((root / automation_id / "automation.toml").read_text())
    assert data["status"] == "ACTIVE"
    assert data["target_thread_id"] and "{{" not in data["target_thread_id"]
    print(automation_id, data["status"], data["rrule"], data["target_thread_id"])
PY
```

Expected: five `ACTIVE` rows with concrete persistent task IDs and their current recurrence rules. Treat task IDs as operational evidence; do not commit them.

- [ ] **Step 2: Patch only the five live `prompt` values**

Use `apply_patch` so no other TOML keys move. The four worker heartbeat values must preserve their current worker-specific report clauses and include:

```text
Run ... now in this persistent worker task. This trigger may be scheduled or manual. Read and follow automations/.../prompt.md as the current source of truth.
```

Wish must establish its snapshot before repository sync by using this exact ordering:

```text
Record the actual started_at and immediately capture the first authoritative backlog snapshot before mutable work. Then sync remote HEAD while preserving unrelated changes and read the current tracked prompt.
```

The steward value must retain its full review checklist and add this exact prefix after its role sentence:

```text
This worker may be invoked by a scheduled heartbeat or explicit manual invocation at any time. Record the actual started_at and a unique invocation ID; anchor the previous-24-hours window to started_at.
```

Do not edit `status`, `rrule`, `target_thread_id`, `created_at`, `updated_at`, `memory.md`, or `deployment-targets.env`.

- [ ] **Step 3: Parse and verify the live definitions after editing**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import tomllib

expected = {
    "gbrain-x-intelligence-capture": "FREQ=DAILY;BYHOUR=0;BYMINUTE=15;BYSECOND=0",
    "memory-stargraph-daily-learning-intake": "FREQ=DAILY;BYHOUR=1;BYMINUTE=0;BYSECOND=0",
    "memory-stargraph-wish-to-reallity": "FREQ=DAILY;BYHOUR=2;BYMINUTE=0;BYSECOND=0",
    "memory-stargraph-divergent-product-discovery": "FREQ=WEEKLY;BYDAY=SU;BYHOUR=4;BYMINUTE=0;BYSECOND=0",
    "memory-stargraph-goal-steward-daily-review": "FREQ=DAILY;BYHOUR=7;BYMINUTE=0;BYSECOND=0",
}
root = Path.home() / ".codex/automations"
for automation_id, rrule in expected.items():
    data = tomllib.loads((root / automation_id / "automation.toml").read_text())
    assert data["status"] == "ACTIVE"
    assert data["rrule"] == rrule
    assert data["target_thread_id"] and "{{" not in data["target_thread_id"]
    assert "manual" in data["prompt"].lower()
print("verified 5 live schedule-independent prompts; identities and recurrences preserved")
PY
```

Expected: `verified 5 live schedule-independent prompts; identities and recurrences preserved`.

- [ ] **Step 4: Run final repository verification without invoking a worker**

Run:

```bash
python3 -m unittest tests.test_automation_contracts -v
python3 -m unittest discover -s tests
git diff --check
git status --short --branch
```

Expected: all tests PASS, `git diff --check` has no output, and the worktree contains no implementation changes beyond intentional commits plus pre-existing unrelated user files. Do not send a task message or manually run a heartbeat during this verification.

- [ ] **Step 5: Report the handoff evidence**

Report the three repository commit hashes, five live automation IDs and `ACTIVE` status, preserved recurrence rules and persistent destinations, test counts, and the fact that no worker was fired for verification. Do not expose private deployment configuration or automation memory.
