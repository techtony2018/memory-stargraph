# Memory Stargraph UX Engineer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent daily Memory Stargraph UX Engineer that dogfoods the dashboard-managed app as a demanding human user and promotes at most three reproduced UX findings into planned TODOs.

**Architecture:** Add one 6:00 AM heartbeat automation and persistent task. It tests realistic browser journeys against `http://127.0.0.1:8788`, writes a Goal-linked Run and UX report, and feeds evidence to the existing Quality & Learning Analyst and Product Owner without implementing fixes.

**Tech Stack:** TOML, Markdown worker prompts, Python `unittest`, in-app browser, Chrome CDP, GBrain CLI.

## Global Constraints

- Exact automation ID: `memory-stargraph-ux-engineer-daily-dogfood`.
- Exact role: `Memory Stargraph UX Engineer`.
- Daily 6:00 AM in `America/Los_Angeles`; manual triggers have no fixed cutoff.
- Final evidence must use dashboard-managed `http://127.0.0.1:8788`.
- Reuse browser tabs; never close a reused user tab.
- Prefer read-only journeys or designated synthetic fixtures; never expose private data.
- Test probes use `environment=test`, `synthetic=true`, `test_run=true`, and `pair_id=ux-dogfood:{invocation_id}:{journey_slug}`.
- Create or update at most three planned TODOs per run after reproduction and deduplication.
- Never implement fixes, deploy, approve resolver proposals, or perform destructive operations.
- Remain separate from the weekly Memory Stargraph Product Strategist.
- Use timezone-aware ISO 8601 in `America/Los_Angeles`.

## Deployment Quiescence Amendment

- Use Goal-linked Runs as cooperative change and UX leases for scheduled and manual invocations; there is no fixed kickoff or cutoff time.
- Before editing code, restarting, or deploying, the Memory Stargraph Engineer writes an active-change marker with invocation id, start time, intended scope, and a deployment fingerprint containing `ui_version`, health source state and timestamp, served HTML/JS asset version or hash, and local process cwd when available.
- UX confirms there is no marker, records the fingerprint, creates an active UX Run/lease, and re-reads active Runs before journeys. Engineer priority wins a concurrent-start race.
- UX rechecks marker, health, and fingerprint before and after every journey. Instability discards the run's observations, creates or updates no TODOs, and terminalizes the lease as `deferred_due_to_active_change` with before/after evidence.
- Before restart or deployment, Engineer re-reads active UX leases, waits for UX acknowledgement and terminalization, and must not silently deploy through an active UX lease.
- Failed changes remain visible. A stale UX lease or stale Engineer marker requires Product Owner resolution rather than automatic bypass.

---

### Task 1: Add The Tracked UX Engineer Contract

**Files:**
- Create: `automations/memory-stargraph-ux-engineer-daily-dogfood/automation.toml`
- Create: `automations/memory-stargraph-ux-engineer-daily-dogfood/heartbeat-prompt.md`
- Create: `automations/memory-stargraph-ux-engineer-daily-dogfood/prompt.md`
- Create: `automations/memory-stargraph-ux-engineer-daily-dogfood/thread-bootstrap.md`
- Modify: `tests/test_automation_contracts.py`

**Interfaces:**
- Consumes: deployed service health/UI, browser surfaces, recent deployments, backlog, UX reports, and Goal Runs.
- Produces: one UX Run, one UX report, rolling journey coverage, and zero to three planned TODO decisions.

- [ ] **Step 1: Write failing definition tests**

Add this entry to the existing role-title `expected` mapping:

```python
"memory-stargraph-ux-engineer-daily-dogfood": {
    "title": "Memory Stargraph UX Engineer",
    "rrule": "FREQ=DAILY;BYHOUR=6;BYMINUTE=0;BYSECOND=0",
    "target_thread_id": "{{UX_ENGINEER_THREAD_ID}}",
    "role_files": ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md"),
},
```

Add:

```python
def test_ux_engineer_dogfoods_deployed_app_with_bounded_authority(self):
    directory = ROOT / "automations/memory-stargraph-ux-engineer-daily-dogfood"
    definition = tomllib.loads((directory / "automation.toml").read_text())
    contract = "\n".join(
        (directory / name).read_text()
        for name in ("prompt.md", "heartbeat-prompt.md", "thread-bootstrap.md")
    )
    self.assertEqual(definition["id"], "memory-stargraph-ux-engineer-daily-dogfood")
    self.assertEqual(definition["name"], "Memory Stargraph UX Engineer")
    self.assertEqual(definition["rrule"], "FREQ=DAILY;BYHOUR=6;BYMINUTE=0;BYSECOND=0")
    self.assertEqual(definition["timezone"], "America/Los_Angeles")
    self.assertEqual(definition["destination"], "thread")
    self.assertEqual(definition["target_thread_id"], "{{UX_ENGINEER_THREAD_ID}}")
    for phrase in (
        "http://127.0.0.1:8788/api/health",
        "dashboard-managed",
        "demanding human user",
        "rolling seven-day",
        "reuse a suitable Memory Stargraph tab",
        "Chrome CDP",
        "environment=test",
        "synthetic=true",
        "test_run=true",
        "pair_id=ux-dogfood:{invocation_id}:{journey_slug}",
        "at most three planned TODOs",
        "must not implement fixes",
        "Goal-linked Run",
        "dated UX report",
        "manual trigger",
        "no fixed cutoff",
    ):
        self.assertIn(phrase, contract)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_automation_contracts.AutomationContractTests.test_worker_role_titles_are_user_facing_only \
  tests.test_automation_contracts.AutomationContractTests.test_ux_engineer_dogfoods_deployed_app_with_bounded_authority
```

Expected: failure because the new automation directory is absent.

- [ ] **Step 3: Create `automation.toml`**

```toml
version = 1
id = "memory-stargraph-ux-engineer-daily-dogfood"
kind = "heartbeat"
name = "Memory Stargraph UX Engineer"
status = "ACTIVE"
rrule = "FREQ=DAILY;BYHOUR=6;BYMINUTE=0;BYSECOND=0"
timezone = "America/Los_Angeles"
destination = "thread"
target_thread_id = "{{UX_ENGINEER_THREAD_ID}}"
prompt_file = "heartbeat-prompt.md"
worker_prompt_file = "prompt.md"
thread_bootstrap_file = "thread-bootstrap.md"
```

- [ ] **Step 4: Create heartbeat and bootstrap prompts**

`heartbeat-prompt.md`:

```markdown
Act as the Memory Stargraph UX Engineer and run the scheduled deployed-app dogfood review now in this persistent task. Read and follow `automations/memory-stargraph-ux-engineer-daily-dogfood/prompt.md` completely. Verify the dashboard-managed health endpoint, reuse a suitable Memory Stargraph tab, test realistic journeys as a demanding human user, and report the UX Run, report, evidence, and bounded planned TODOs.
```

`thread-bootstrap.md`:

```markdown
You are the persistent Memory Stargraph UX Engineer. Read `automations/memory-stargraph-ux-engineer-daily-dogfood/prompt.md` completely on every heartbeat or manual trigger. Use the dashboard-managed app like a demanding human user, preserve private data and human control, and keep this task reusable. This initialization turn is setup-only: verify the definition, prompt, browser readiness, local health, and routing without running journeys, writing reports, or filing TODOs. Future heartbeats and manual triggers run the full contract; a manual trigger has no fixed cutoff.
```

- [ ] **Step 5: Create the complete worker prompt**

Create `prompt.md` with this operational contract:

```markdown
You are the Memory Stargraph UX Engineer. Use the deployed application as a demanding human user who is hard to please. Find reproducible friction and the smallest improvements that make Memory Stargraph more streamlined, intuitive, understandable, trustworthy, and efficient.

Persistent Goal: `goals/memory-stargraph-continuous-learning-local-knowledge-os`
Product: `products/memory-stargraph`
Backlog: `notes/memory-starmap-todo-list`

This worker runs daily at 6:00 AM in `America/Los_Angeles` and may run by manual trigger at any time; there is no fixed cutoff. It is separate from the weekly Product Strategist, which owns broad product direction.

1. Record invocation id and timezone-aware `started_at` in `America/Los_Angeles`.
2. Read recent Goal Runs, deployments, UX reports, Learnings, user corrections, Ask Yoda evidence, and backlog. Build rolling seven-day journey coverage.
3. Verify `http://127.0.0.1:8788/api/health`; record `ui_version`, source state, warnings, and attachments. Final evidence must use dashboard-managed `http://127.0.0.1:8788`, not a temporary service or source inspection.
4. Inspect in-app browser tabs and reuse a suitable Memory Stargraph tab. If unavailable or authenticated state is required, use Chrome CDP, inspect its tabs, and reuse a suitable tab. Never close a reused user tab; close only tabs created by this run. Record tab counts before and after.
5. Choose journeys from recent changes, unresolved findings, and coverage. Across seven days cover orientation; search and return; relationships/backlinks; graph selection/hidden state; Ask Yoda question/follow-up; media/files/provenance; capture status; settings/Autopilot/diagnostics; history/deep links/state restoration; empty/loading/offline/failure/recovery; keyboard/focus/zoom/viewport/accessibility.
6. Challenge unclear wording, labels, icons, hierarchy, excessive clicks, repeated input, hidden controls, weak feedback, latency, instability, inconsistent state, insider terminology, accessibility, risky actions, and poor recovery.
7. Prefer read-only journeys and use designated synthetic fixtures for mutation. Test probes use `environment=test`, `synthetic=true`, `test_run=true`, and `pair_id=ux-dogfood:{invocation_id}:{journey_slug}` and must not affect genuine user metrics.
8. For each observation record intended outcome, start state, exact steps, action count, latency, expected/observed behavior, screenshot when visual, severity, affected user, friction rationale, smallest improvement, estimated effort saved, reproducibility, and related evidence.
9. Classify as `bug`, `friction`, `opportunity`, or `observation`; deduplicate against backlog and UX reports.
10. Create or update at most three planned TODOs. Require deployed-app reproduction, impact, exact steps, bounded scope, acceptance criteria, verification, risk/rollback, smallest improvement, and no duplicate. Never change TODOs to implementing, completed, or failed.
11. Create one dated UX report and Goal-linked Run linked to Goal and product, including version, browser, journeys, coverage, friction, action/latency evidence, classifications, TODO decisions, effort-saving improvements, blockers, and next journey.
12. Create durable Learnings only for reusable behavior. Product Owner reviews at 7:00 AM; Quality & Learning Analyst may use repeated UX and data-quality patterns.

If health is bad, record it and stop without calling it a UI finding. If the in-app browser fails, use Chrome CDP. If both fail, create a failed Run and do not substitute source inspection. Skip unsafe/private journeys. If no friction appears, create a successful no-op report.

Human-control contract: this worker must not implement fixes, edit code, deploy, auto-approve resolver proposals, perform destructive actions, expose private data, or broaden access. Every user-facing GBrain slug is an exact-label Markdown link to `http://127.0.0.1:8788/?slug=<URL-encoded-slug>`.

Pacific-time contract: logs, Runs, reports, screenshots, filenames, and messages use timezone-aware ISO 8601 in `America/Los_Angeles`: PDT in summer and PST in winter. Do not use fixed UTC-8 or label UTC as Pacific time.
```

- [ ] **Step 6: Verify GREEN and commit**

```bash
python3 -m unittest tests.test_automation_contracts
git diff --check -- automations/memory-stargraph-ux-engineer-daily-dogfood tests/test_automation_contracts.py
git add automations/memory-stargraph-ux-engineer-daily-dogfood tests/test_automation_contracts.py
git commit -m "feat: add Memory Stargraph UX Engineer contract"
```

Expected: tests end in `OK`; diff check is silent.

---

### Task 2: Connect UX Evidence To The Learning Loop

**Files:**
- Modify: `automations/README.md`
- Modify: `automations/memory-stargraph-goal-steward-daily-review/prompt.md`
- Modify: `automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md`
- Modify: `automations/memory-stargraph-daily-learning-intake/prompt.md`
- Modify: `tests/test_automation_contracts.py`

**Interfaces:**
- Consumes: UX Run/report and TODO decisions.
- Produces: morning Product Owner monitoring and Quality & Learning Analyst reuse.

- [ ] **Step 1: Write and run the failing integration test**

```python
def test_ux_engineer_evidence_reaches_product_owner_and_learning_intake(self):
    paths = (
        ROOT / "automations/README.md",
        ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md",
        ROOT / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md",
        ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md",
    )
    contract = "\n".join(path.read_text() for path in paths)
    for phrase in (
        "memory-stargraph-ux-engineer-daily-dogfood",
        "Memory Stargraph UX Engineer",
        "Daily 6:00 AM",
        "UX reports",
        "journey coverage",
        "repeated UX",
        "data-quality patterns",
    ):
        self.assertIn(phrase, contract)
```

Run the focused test; expect `FAIL` because integration copy is absent.

- [ ] **Step 2: Update pipeline documentation**

Add after the 2:00 AM row:

```markdown
| Daily 6:00 AM | Memory Stargraph UX Engineer | `memory-stargraph-ux-engineer-daily-dogfood` | Dogfood the dashboard-managed app, record journey evidence, and promote at most three reproduced UX findings into planned TODOs. |
```

Change `All six automations` to `All seven automations`, and state that UX runs
after Engineer and before Product Owner.

- [ ] **Step 3: Update Product Owner monitoring**

Add `memory-stargraph-ux-engineer-daily-dogfood` to the monitored list. Add
`UX reports, journey coverage, reproduced friction, action counts, and UX TODO decisions`
to the steward evidence contract and runtime Product Owner review prompt.

- [ ] **Step 4: Update learning intake**

Insert:

```markdown
Review the latest Memory Stargraph UX Engineer Runs and UX reports. Identify repeated UX friction, journey regressions, confusing terminology, excessive action counts, weak recovery, accessibility problems, and data-quality patterns. Deduplicate against TODOs already promoted by the UX Engineer. Create or update a TODO only when the combined evidence meets this worker's normal qualification threshold; otherwise preserve the pattern as report evidence or durable Learning.
```

- [ ] **Step 5: Verify and commit**

```bash
python3 -m unittest tests.test_automation_contracts
git diff --check -- automations tests/test_automation_contracts.py
git add automations tests/test_automation_contracts.py
git commit -m "feat: connect UX evidence to learning loop"
```

Expected: tests end in `OK`; diff check is silent.

---

### Task 3: Register The Live Persistent UX Engineer

**Files:**
- Read: `automations/memory-stargraph-ux-engineer-daily-dogfood/thread-bootstrap.md`
- Modify outside Git through Codex task and automation APIs.

**Interfaces:**
- Consumes: committed tracked contract.
- Produces: one persistent task and one active heartbeat targeting it.

- [ ] **Step 1: Create one project-local persistent task**

Use the complete tracked bootstrap prompt in
`/Users/tony/Documents/Collective Knowledge System`. Set the task title to
`Memory Stargraph UX Engineer` and record its returned ID as
`ux_engineer_thread_id`.

- [ ] **Step 2: Verify setup-only readiness**

Require acknowledgement of tracked files, `/api/health`, browser readiness,
setup-only behavior with no journeys/writes/TODOs, and reuse of this task for
future scheduled and manual triggers.

- [ ] **Step 3: Create the heartbeat**

Use the automation API with:

```text
mode = create
id = memory-stargraph-ux-engineer-daily-dogfood
kind = heartbeat
name = Memory Stargraph UX Engineer
prompt = complete tracked heartbeat-prompt.md
status = ACTIVE
rrule = FREQ=DAILY;BYHOUR=6;BYMINUTE=0;BYSECOND=0
destination = thread
targetThreadId = ux_engineer_thread_id
```

- [ ] **Step 4: Verify registration without running UX journeys**

Read the automation and task. Verify exact ID, role, active status, 6:00 AM
recurrence, and target ID. Verify no duplicate automation/task exists. Record
the readiness evidence, but leave the first UX run for the next heartbeat or
explicit user trigger.
