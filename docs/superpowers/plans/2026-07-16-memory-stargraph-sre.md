# Memory Stargraph SRE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one persistent Memory Stargraph SRE with separate daily reliability and weekly resilience heartbeats that operate only during verified quiet time, apply bounded remediation, measure scaling headroom, and never pollute resolver learning.

**Architecture:** Two tracked heartbeat definitions target one shared persistent task and one shared SRE worker prompt. The daily 8:00 AM mode performs stack reliability and capacity review; the Sunday 11:00 AM mode adds safe load, isolated restore, failover, and rollback exercises. Goal-linked Runs act as the SRE lease and evidence record, while live task state plus other active Runs provide the quiet-time gate.

**Tech Stack:** TOML heartbeat definitions, Markdown worker contracts, Python `unittest`, Codex task/automation APIs, GBrain Goal-linked Runs, dashboard-managed Memory Stargraph health and deployment runbooks.

## Global Constraints

- Persistent task title: `Memory Stargraph SRE`.
- Daily automation ID: `memory-stargraph-sre-daily-reliability`.
- Weekly automation ID: `memory-stargraph-sre-weekly-resilience`.
- Daily recurrence: `FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0` in `America/Los_Angeles`.
- Weekly recurrence: `FREQ=WEEKLY;BYDAY=SU;BYHOUR=11;BYMINUTE=0;BYSECOND=0` in `America/Los_Angeles`.
- Both automations target the same persistent task and remain manually triggerable without a fixed cutoff.
- The SRE performs no probing, load testing, remediation, or GBrain writes while another Memory Stargraph worker or SRE mode is active.
- If another worker starts during an SRE run, stop, contain or roll back incomplete work, terminalize `deferred_due_to_worker_activity`, and retry later in the same task.
- Daily resolver checks are read-only and generate no resolver events.
- Weekly end-to-end resolver probes require `environment=test`, `synthetic=true`, `test_run=true`, and `pair_id=sre:{mode}:{invocation_id}:{probe_slug}`; unverified isolation produces `resolver_probe_skipped_isolation_unverified` and no probe.
- Weekly fault injection is limited to an explicitly designated synthetic, disposable, or redundant target, one fault at a time; otherwise record `chaos_skipped_no_safe_target`.
- No destructive production-data repair/restore, migration, credential change, privacy expansion, infrastructure purchase, undocumented topology change, broad architecture change, or resolver auto-approval.
- Every user-facing GBrain slug is an exact-label Markdown link to `http://127.0.0.1:8788/?slug=<URL-encoded-slug>`.
- All SRE timestamps use timezone-aware ISO 8601 in `America/Los_Angeles`: PDT in summer and PST in winter; never use a fixed UTC-8 offset.

---

### Task 1: Add The Shared SRE Contract And Two Tracked Heartbeats

**Files:**
- Create: `automations/memory-stargraph-sre/prompt.md`
- Create: `automations/memory-stargraph-sre/thread-bootstrap.md`
- Create: `automations/memory-stargraph-sre-daily-reliability/automation.toml`
- Create: `automations/memory-stargraph-sre-daily-reliability/heartbeat-prompt.md`
- Create: `automations/memory-stargraph-sre-weekly-resilience/automation.toml`
- Create: `automations/memory-stargraph-sre-weekly-resilience/heartbeat-prompt.md`
- Modify: `tests/test_automation_contracts.py`

**Interfaces:**
- Consumes: live Codex task states, active Goal-linked Runs/leases, configured deployment targets, health endpoints, worker evidence, backup/restore evidence, and existing runbooks.
- Produces: one shared worker contract, one setup-only bootstrap, and two portable heartbeat definitions using `{{SRE_THREAD_ID}}`.

- [ ] **Step 1: Write the failing SRE contract test**

Add this test to `AutomationContractTests`:

```python
    def test_sre_automations_share_one_quiet_time_worker(self):
        daily_dir = ROOT / "automations/memory-stargraph-sre-daily-reliability"
        weekly_dir = ROOT / "automations/memory-stargraph-sre-weekly-resilience"
        shared_dir = ROOT / "automations/memory-stargraph-sre"
        daily = tomllib.loads((daily_dir / "automation.toml").read_text())
        weekly = tomllib.loads((weekly_dir / "automation.toml").read_text())
        prompt = (shared_dir / "prompt.md").read_text()
        bootstrap = (shared_dir / "thread-bootstrap.md").read_text()
        heartbeats = "\n".join(
            ((daily_dir / "heartbeat-prompt.md").read_text(),
             (weekly_dir / "heartbeat-prompt.md").read_text())
        )
        contract = "\n".join((prompt, bootstrap, heartbeats))

        self.assertEqual(daily["id"], "memory-stargraph-sre-daily-reliability")
        self.assertEqual(daily["name"], "Memory Stargraph SRE Daily Reliability")
        self.assertEqual(daily["rrule"], "FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0")
        self.assertEqual(weekly["id"], "memory-stargraph-sre-weekly-resilience")
        self.assertEqual(weekly["name"], "Memory Stargraph SRE Weekly Resilience")
        self.assertEqual(weekly["rrule"], "FREQ=WEEKLY;BYDAY=SU;BYHOUR=11;BYMINUTE=0;BYSECOND=0")
        for definition in (daily, weekly):
            self.assertEqual(definition["timezone"], "America/Los_Angeles")
            self.assertEqual(definition["destination"], "thread")
            self.assertEqual(definition["target_thread_id"], "{{SRE_THREAD_ID}}")
            self.assertEqual(definition["worker_prompt_file"], "../memory-stargraph-sre/prompt.md")
            self.assertEqual(definition["thread_bootstrap_file"], "../memory-stargraph-sre/thread-bootstrap.md")

        for phrase in (
            "Memory Stargraph SRE", "live Codex task state",
            "active Goal-linked Runs or leases", "performs no health probing",
            "task-local deferral", "deferred_due_to_worker_activity",
            "at most one completed daily review", "at most one completed weekly review",
            "7-day and 30-day baselines", "capacity headroom",
            "documented last-known-good", "chaos_skipped_no_safe_target",
            "resolver_probe_skipped_isolation_unverified",
            "pair_id=sre:{mode}:{invocation_id}:{probe_slug}",
            "must not implement product or GBrain code", "manual trigger",
            "no fixed cutoff",
        ):
            self.assertIn(phrase, contract)
        self.assertIn("mode=daily_reliability", heartbeats)
        self.assertIn("mode=weekly_resilience", heartbeats)
```

Extend `test_every_worker_uses_dst_aware_pacific_reporting` by adding
`"memory-stargraph-sre"` to its `workers` tuple.

- [ ] **Step 2: Run the focused tests to verify RED**

```bash
python3 -m unittest \
  tests.test_automation_contracts.AutomationContractTests.test_sre_automations_share_one_quiet_time_worker \
  tests.test_automation_contracts.AutomationContractTests.test_every_worker_uses_dst_aware_pacific_reporting
```

Expected: errors because the SRE directories and definitions do not exist.

- [ ] **Step 3: Create both portable automation definitions**

Create `automations/memory-stargraph-sre-daily-reliability/automation.toml`:

```toml
version = 1
id = "memory-stargraph-sre-daily-reliability"
kind = "heartbeat"
name = "Memory Stargraph SRE Daily Reliability"
status = "ACTIVE"
rrule = "FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0"
timezone = "America/Los_Angeles"
destination = "thread"
target_thread_id = "{{SRE_THREAD_ID}}"
prompt_file = "heartbeat-prompt.md"
worker_prompt_file = "../memory-stargraph-sre/prompt.md"
thread_bootstrap_file = "../memory-stargraph-sre/thread-bootstrap.md"
```

Create `automations/memory-stargraph-sre-weekly-resilience/automation.toml`:

```toml
version = 1
id = "memory-stargraph-sre-weekly-resilience"
kind = "heartbeat"
name = "Memory Stargraph SRE Weekly Resilience"
status = "ACTIVE"
rrule = "FREQ=WEEKLY;BYDAY=SU;BYHOUR=11;BYMINUTE=0;BYSECOND=0"
timezone = "America/Los_Angeles"
destination = "thread"
target_thread_id = "{{SRE_THREAD_ID}}"
prompt_file = "heartbeat-prompt.md"
worker_prompt_file = "../memory-stargraph-sre/prompt.md"
thread_bootstrap_file = "../memory-stargraph-sre/thread-bootstrap.md"
```

- [ ] **Step 4: Create mode-specific heartbeat prompts**

Daily `heartbeat-prompt.md`:

```markdown
Act as the Memory Stargraph SRE and run `mode=daily_reliability` in this persistent task. Read `automations/memory-stargraph-sre/prompt.md` completely. First enforce the quiet-time gate; if the stack is busy, perform only the task-local deferral. When quiet, inspect the configured deployed stack, apply only bounded documented remediation, and report the reliability Run, incidents, capacity headroom, verification, TODO decisions, and approvals.
```

Weekly `heartbeat-prompt.md`:

```markdown
Act as the Memory Stargraph SRE and run `mode=weekly_resilience` in this persistent task. Read `automations/memory-stargraph-sre/prompt.md` completely. First enforce the quiet-time gate; if the stack is busy, perform only the task-local deferral. When quiet, run the weekly safe-target resilience contract, including bounded synthetic load, isolated restore rehearsal, documented recovery/failover/rollback checks, capacity-envelope evidence, and strict resolver isolation.
```

- [ ] **Step 5: Create the setup-only shared task bootstrap**

Create `automations/memory-stargraph-sre/thread-bootstrap.md`:

```markdown
You are the persistent Memory Stargraph SRE. Read `automations/memory-stargraph-sre/prompt.md` completely for every daily, weekly, deferred, retry, or manual invocation. Keep this task reusable and preserve human control. This initialization turn is setup-only: verify the two tracked definitions, shared prompt, configured health routes, live-task visibility, GBrain readiness, and routing without performing health probes, load tests, remediation, browser navigation, GBrain writes, Runs, or TODO creation. Future triggers supply `mode=daily_reliability` or `mode=weekly_resilience`; manual triggers have no fixed cutoff.
```

- [ ] **Step 6: Create the complete shared SRE prompt**

Create `automations/memory-stargraph-sre/prompt.md` with the following exact
operational sections and obligations:

```markdown
You are the Memory Stargraph SRE. Keep the deployed Memory Stargraph and GBrain stack reliable, recover documented failures safely, and make scaling limits visible without implementing product code.

Persistent Goal: `goals/memory-stargraph-continuous-learning-local-knowledge-os`
Product: `products/memory-stargraph`
Backlog: `notes/memory-starmap-todo-list`

The invocation supplies `mode=daily_reliability` or `mode=weekly_resilience`. The daily default is 8:00 AM and the weekly default is Sunday 11:00 AM in `America/Los_Angeles`. Manual triggers may run at any time and have no fixed cutoff.

Quiet-time contract:
1. Before doing anything operational, inspect live Codex task state and active Goal-linked Runs or leases for every Memory Stargraph worker, deployment, and other SRE mode. The SRE performs no health probing, load testing, remediation, browser navigation, or GBrain writes while another worker is active. Stale or conflicting state is not quiet.
2. If busy, make only a concise task-local deferral, schedule a retry in this same persistent task, and stop. Do not create an SRE Run merely because the stack is busy. Allow at most one completed daily review and at most one completed weekly review per Pacific calendar date.
3. When quiet, create an active Goal-linked SRE Run/lease with invocation id, mode, Pacific start time, and initial worker-state evidence, then immediately repeat the live-task and active-Run checks. On a race, terminalize `deferred_due_to_worker_activity` and stop.
4. Recheck worker and lease state before every mutating operation and before every weekly load or fault phase. If another worker starts, stop; contain or roll back incomplete work; record before/after evidence; terminalize `deferred_due_to_worker_activity`; and retry later. Other workers always take priority.

Daily reliability contract:
5. Read private target configuration and established runbooks without exposing credentials or concrete deployment coordinates. Cover the All Things Codex Dashboard, dashboard-managed local Memory Stargraph, configured remote Memory Stargraph targets, GBrain thin-client/remote health, resolver health, attachment storage/media retrieval, expected process cwd, versions, served asset identity, and version drift.
6. Collect safe available evidence for health, errors, timeouts, restarts, health/search/node/relationship/backlink/file latency, CPU, memory, disk, cache, open files, node/edge/file/storage/queue/backlog growth, worker success/failure/defer rates, worker durations, backup freshness/completeness, and the last verified restore rehearsal. Missing telemetry is a finding; never invent a value.
7. Maintain 7-day and 30-day baselines. Report absolute failures, meaningful regressions, capacity headroom, current estimated safe scale, and the next likely bottleneck.

Bounded remediation contract:
8. Use this order only: read back and retry a transient check; use an existing documented dashboard-managed restart or service recovery; recover a documented cache/routing condition without deleting durable data; or roll back to a documented last-known-good release when the target, release identity, rollback procedure, and verification path are explicit.
9. Before mutation record target, before state, exact planned action, rollback path, and authority. Afterward verify health, version, served assets, process cwd, resolver isolation, attachment availability, and the originally failing path. A failed remediation remains visible and never reports recovery.
10. The SRE must not implement product or GBrain code. It must not perform destructive production-data repair/restore, migration, credential change, privacy expansion, infrastructure purchase, undocumented topology change, broad architecture change, or resolver auto-approval without explicit human authority.

Weekly resilience contract:
11. In `mode=weekly_resilience`, repeat the daily preflight and health evidence, then use gradual bounded synthetic load with explicit abort gates; rehearse restore only into isolated temporary storage; and exercise documented restart, failover, recovery, and rollback one fault at a time on an explicitly designated synthetic, disposable, or redundant target.
12. Abort on user impact, unexpected saturation, verification loss, rollback uncertainty, or worker activity. If no explicitly safe target exists, record `chaos_skipped_no_safe_target` and preserve a proposal for human review rather than injecting a fault.
13. Record load shape, target classification, abort gates, observed limits, restore/failover/rollback results, containment, capacity envelope, comparison with prior weekly evidence, first expected bottleneck, and smallest evidence-backed mitigation. Never automatically purchase infrastructure or make a broad architecture change.

Resolver isolation contract:
14. Daily resolver checks are read-only health/status operations and generate no resolver events. Weekly end-to-end resolver testing may use only `environment=test`, `synthetic=true`, `test_run=true`, and `pair_id=sre:{mode}:{invocation_id}:{probe_slug}`.
15. Before a weekly end-to-end probe, verify those isolation fields reach telemetry and are excluded from production metrics, proposal generation, learning intake, resolver decisions, and user-quality scoring. If isolation cannot be verified, record `resolver_probe_skipped_isolation_unverified` and do not send the probe. Raw or unclassified Ask Yoda/resolver requests are forbidden.

Incident and escalation contract:
16. Deduplicate incidents by affected target, symptom, deployment identity, and active time window. Record severity, user impact, detection, timeline, evidence, attempted remediation, outcome, recurrence, and pending authority.
17. For unresolved code or scaling defects, create or update one evidence-backed planned TODO with reproduction, targets, baseline/regression data, bounded scope, acceptance criteria, rollback considerations, and verification. Do not duplicate an existing TODO and never mark it implementing, completed, or failed.
18. For an unresolved critical outage, contain the incident and terminalize/release the SRE lease first. Then send the evidence-backed planned TODO to the persistent Memory Stargraph Engineer task for immediate handling under its normal safety and deployment contracts. Lower severity work remains for Product Owner prioritization.
19. Create one dated reliability or resilience report and terminalize the Goal-linked Run with targets, trends, incidents, remediation, verification, capacity assessment, TODO decisions, approvals, blockers, and next check. Create durable Learnings only for reusable operational behavior.

Browser, privacy, and reporting contract:
20. If browser verification is needed, inspect existing tabs first, reuse a suitable same-origin/source tab, never close a reused user tab, and close only a temporary tab created by this run. Use authenticated Chrome CDP only when a documented check needs the user's session.
21. Never expose secrets, credentials, private host coordinates, or raw private content. Every user-facing GBrain slug is an exact-label Markdown link to `http://127.0.0.1:8788/?slug=<URL-encoded-slug>`.
22. Logs, Runs, reports, screenshots, filenames, and messages use timezone-aware ISO 8601 in `America/Los_Angeles`: PDT in summer and PST in winter. Do not use a fixed UTC-8 offset or label UTC as Pacific time.
```

- [ ] **Step 7: Run focused and full tests**

```bash
python3 -m unittest \
  tests.test_automation_contracts.AutomationContractTests.test_sre_automations_share_one_quiet_time_worker \
  tests.test_automation_contracts.AutomationContractTests.test_every_worker_uses_dst_aware_pacific_reporting
python3 -m unittest tests.test_automation_contracts
git diff --check -- automations/memory-stargraph-sre automations/memory-stargraph-sre-daily-reliability automations/memory-stargraph-sre-weekly-resilience tests/test_automation_contracts.py
```

Expected: focused tests and full suite end in `OK`; diff check is silent.

- [ ] **Step 8: Commit Task 1**

```bash
git add automations/memory-stargraph-sre automations/memory-stargraph-sre-daily-reliability automations/memory-stargraph-sre-weekly-resilience tests/test_automation_contracts.py
git commit -m "feat: add Memory Stargraph SRE contracts"
```

---

### Task 2: Connect SRE Evidence And Critical Handoffs To The Worker Loop

**Files:**
- Modify: `automations/README.md`
- Modify: `docs/automation-runbook.md`
- Modify: `automations/memory-stargraph-goal-steward-daily-review/prompt.md`
- Modify: `automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md`
- Modify: `automations/memory-stargraph-daily-learning-intake/prompt.md`
- Modify: `automations/memory-stargraph-wish-to-reallity/prompt.md`
- Modify: `tests/test_automation_contracts.py`

**Interfaces:**
- Consumes: SRE Runs, reports, incidents, capacity headroom, TODO decisions, and released critical-incident handoffs from Task 1.
- Produces: Product Owner oversight, Quality & Learning Analyst reuse, Engineer critical handling, and restore/runbook documentation.

- [ ] **Step 1: Write the failing feedback-loop test**

Add:

```python
    def test_sre_evidence_reaches_owner_learning_and_engineer(self):
        paths = (
            ROOT / "automations/README.md",
            ROOT / "docs/automation-runbook.md",
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/prompt.md",
            ROOT / "automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md",
            ROOT / "automations/memory-stargraph-daily-learning-intake/prompt.md",
            ROOT / "automations/memory-stargraph-wish-to-reallity/prompt.md",
        )
        contract = "\n".join(path.read_text() for path in paths)
        for phrase in (
            "memory-stargraph-sre-daily-reliability",
            "memory-stargraph-sre-weekly-resilience",
            "Daily 8:00 AM",
            "Sunday 11:00 AM",
            "SRE Runs",
            "capacity headroom",
            "reliability incidents",
            "repeated reliability",
            "released its SRE lease",
            "critical SRE handoff",
            "resolver_probe_skipped_isolation_unverified",
            "chaos_skipped_no_safe_target",
        ):
            self.assertIn(phrase, contract)
```

- [ ] **Step 2: Run the focused test to verify RED**

```bash
python3 -m unittest tests.test_automation_contracts.AutomationContractTests.test_sre_evidence_reaches_owner_learning_and_engineer
```

Expected: failure because the SRE identifiers and evidence contracts are absent downstream.

- [ ] **Step 3: Document both schedules and shared-task behavior**

Add these rows to `automations/README.md`:

```markdown
| Daily 8:00 AM | Memory Stargraph SRE | `memory-stargraph-sre-daily-reliability` | During verified quiet time, inspect deployed-stack reliability, apply bounded documented remediation, and report capacity headroom. |
| Sunday 11:00 AM | Memory Stargraph SRE | `memory-stargraph-sre-weekly-resilience` | During verified quiet time, run safe-target load, isolated restore, failover, rollback, and capacity-envelope exercises. |
```

Change `All seven automations` to `All nine automations`. State that both SRE
automations target one persistent task, busy runs defer task-locally, and
Sunday receives both the daily review and the separate weekly exercise.

- [ ] **Step 4: Add the operational runbook section**

Add after deployment quiescence in `docs/automation-runbook.md`:

```markdown
## SRE reliability and resilience

`memory-stargraph-sre-daily-reliability` runs daily at 8:00 AM and
`memory-stargraph-sre-weekly-resilience` runs Sunday at 11:00 AM in
`America/Los_Angeles`. Both target one persistent Memory Stargraph SRE task.

The SRE operates only when live task state and Goal-linked Runs/leases show no
other Memory Stargraph work. Busy or racing invocations defer as
`deferred_due_to_worker_activity`; other workers take priority. Daily work
checks deployed health, version and served-asset identity, resources, storage,
backups, attachments, resolver health, worker trends, and capacity headroom.
Bounded remediation uses only documented retry, dashboard-managed restart,
cache/routing recovery, or documented last-known-good rollback with before and
after verification.

Weekly work adds gradual synthetic load, isolated temporary restore rehearsal,
and one safe fault at a time on an explicitly synthetic, disposable, or
redundant target. Without a safe target it records
`chaos_skipped_no_safe_target`. Resolver health checks are read-only. An
end-to-end resolver probe requires `environment=test`, `synthetic=true`,
`test_run=true`, and `pair_id=sre:{mode}:{invocation_id}:{probe_slug}`; when
isolation cannot be verified, record
`resolver_probe_skipped_isolation_unverified` and skip the probe.
```

- [ ] **Step 5: Wire Product Owner monitoring**

In both Product Owner prompts, add both SRE automation IDs and:

```markdown
Review SRE Runs, daily reliability reports, weekly resilience reports, reliability incidents, capacity headroom, scaling bottlenecks, remediation and rollback evidence, deferred quiet-time runs, stale SRE leases, failed recovery, resolver isolation, and pending human approvals.
```

- [ ] **Step 6: Wire Quality & Learning Analyst reuse**

Add:

```markdown
Review recent SRE Runs and reports for repeated reliability failures, scaling regressions, missing telemetry, backup/restore gaps, attachment or resolver isolation defects, worker-duration growth, and recurring remediation. Deduplicate against TODOs already promoted by the SRE. Create or update a planned TODO only when the normal qualification threshold is met; otherwise preserve the pattern as report evidence or a durable Learning.
```

- [ ] **Step 7: Wire critical Engineer handoff**

Add before Engineer work selection:

```markdown
If manually triggered with a critical SRE handoff, verify the originating incident is contained and has released its SRE lease, read the evidence-backed planned TODO and Run, and treat it as the highest-priority eligible item under this Engineer's normal planning, human-control, testing, deployment-quiescence, and verification contracts. A critical SRE handoff never authorizes bypassing safety gates or implementing directly from an untracked chat claim.
```

- [ ] **Step 8: Run focused and full tests**

```bash
python3 -m unittest tests.test_automation_contracts.AutomationContractTests.test_sre_evidence_reaches_owner_learning_and_engineer
python3 -m unittest tests.test_automation_contracts
git diff --check -- automations docs/automation-runbook.md tests/test_automation_contracts.py
```

Expected: focused test and full suite end in `OK`; diff check is silent.

- [ ] **Step 9: Commit Task 2**

```bash
git add automations/README.md docs/automation-runbook.md automations/memory-stargraph-goal-steward-daily-review/prompt.md automations/memory-stargraph-goal-steward-daily-review/steward-thread-prompt.md automations/memory-stargraph-daily-learning-intake/prompt.md automations/memory-stargraph-wish-to-reallity/prompt.md tests/test_automation_contracts.py
git commit -m "feat: connect SRE evidence to worker loop"
```

---

### Task 3: Register The Shared Persistent SRE Task And Both Live Heartbeats

**Files:**
- Read: `automations/memory-stargraph-sre/thread-bootstrap.md`
- Read: `automations/memory-stargraph-sre-daily-reliability/heartbeat-prompt.md`
- Read: `automations/memory-stargraph-sre-weekly-resilience/heartbeat-prompt.md`
- Modify outside Git: Codex persistent task and automation registrations.

**Interfaces:**
- Consumes: committed tracked SRE contract and heartbeat prompts.
- Produces: one persistent project-local SRE task and two active heartbeat automations targeting it.

- [ ] **Step 1: Verify no duplicate live identity exists**

Search Codex tasks for the exact title `Memory Stargraph SRE`. Inspect:

```text
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-sre-daily-reliability/automation.toml
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-sre-weekly-resilience/automation.toml
```

Expected: no matching task or automation. If one exists, reuse/update it.

- [ ] **Step 2: Create one project-local persistent task**

Create a project-local task in
`/Users/tony/Documents/Collective Knowledge System` with the complete tracked
bootstrap prompt. Set its title to `Memory Stargraph SRE` and record the id as
`sre_thread_id`.

Expected setup-only acknowledgement:

```text
Both tracked definitions and the shared prompt are present. Live-task and GBrain routing are ready. No health probe, load test, remediation, browser navigation, Run, GBrain write, or TODO creation occurred. This task will be reused for daily, weekly, deferred, retry, and manual invocations.
```

- [ ] **Step 3: Create the daily heartbeat through the automation API**

```text
mode = create
kind = heartbeat
name = Memory Stargraph SRE Daily Reliability
prompt = complete tracked daily heartbeat-prompt.md
status = ACTIVE
rrule = FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0
destination = thread
targetThreadId = sre_thread_id
```

The generated ID must be `memory-stargraph-sre-daily-reliability`.

- [ ] **Step 4: Create the weekly heartbeat through the automation API**

```text
mode = create
kind = heartbeat
name = Memory Stargraph SRE Weekly Resilience
prompt = complete tracked weekly heartbeat-prompt.md
status = ACTIVE
rrule = FREQ=WEEKLY;BYDAY=SU;BYHOUR=11;BYMINUTE=0;BYSECOND=0
destination = thread
targetThreadId = sre_thread_id
```

The generated ID must be `memory-stargraph-sre-weekly-resilience`.

- [ ] **Step 5: Verify live registration without running SRE operations**

Read both live definitions and the task. Verify:

```text
memory-stargraph-sre-daily-reliability | ACTIVE | daily 8:00 AM | sre_thread_id
memory-stargraph-sre-weekly-resilience | ACTIVE | Sunday 11:00 AM | sre_thread_id
```

Verify the task is idle after setup-only acknowledgement, both automations
target the same task, no duplicates exist, and no operational SRE run or GBrain
mutation occurred.

- [ ] **Step 6: Run final tracked verification**

```bash
python3 -m unittest tests.test_automation_contracts
git diff --check -- automations docs tests/test_automation_contracts.py
git status --short
```

Expected: tests end in `OK`; diff check is silent; only unrelated pre-existing
workspace changes remain.
