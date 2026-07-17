# Knowledge Curator Empty-Queue Entity Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Memory Stargraph Knowledge Curator enrich up to two evidence-backed entities when its first authoritative capture snapshot is empty, prioritizing people and then bounded secondary entity types.

**Architecture:** Keep the existing capture worker, schedule, persistent task, and queue-drain path unchanged. Add one explicit branch immediately after the frozen snapshot: non-empty snapshots follow the existing drain contract exclusively; empty snapshots immediately create an active Goal-linked Run, deterministically reserve up to two entities before mutation, and finalize that Run with truthful results.

**Tech Stack:** Markdown automation prompts, TOML heartbeat definitions, Python `unittest`, GBrain CLI, Agent Reach, in-app browser, Chrome CDP.

## Global Constraints

- The automation ID remains `memory-stargraph-capture-link-drain`.
- The user-facing role remains `Memory Stargraph Knowledge Curator`.
- The schedule remains daily 12:00 AM in `America/Los_Angeles`, with manual triggering allowed and no fixed cutoff.
- A non-empty first authoritative snapshot always takes priority; enrichment must not run before or after draining it.
- The total empty-queue enrichment cap is two attempted entities, with fewer allowed only when the eligible candidate set is exhausted.
- Candidate priority is people, organizations/companies, teams/projects, products/technologies, then other public entities.
- Every category uses the same deterministic ordering: deficiency first, never-reviewed first, oldest enrichment or review timestamp, then lexical slug.
- Skip entities enriched or reviewed successfully within the previous 30 days.
- Create the active empty-queue Run before candidate selection, persist and read back reservations before mutation, and resolve reservation collisions by timestamp then invocation id.
- Finalize the active Run on success, failure, or caught interruption; leave unexpected crashes visible as stale active Runs.
- Use public evidence, preserve user-confirmed facts, reuse browser tabs, prevent duplicate media and graph writes, and preserve human control.
- Do not create synthetic capture requests or automatically create product TODOs from individual enrichment failures.
- All user-facing GBrain slugs must be exact-label links to `http://127.0.0.1:8788/?slug=<URL-encoded-slug>`.

---

### Task 1: Add And Test The Empty-Snapshot Enrichment Contract

**Files:**
- Modify: `tests/test_automation_contracts.py`
- Modify: `automations/memory-stargraph-capture-link-drain/prompt.md`
- Modify: `automations/memory-stargraph-capture-link-drain/heartbeat-prompt.md`
- Modify: `automations/memory-stargraph-capture-link-drain/thread-bootstrap.md`
- Modify: `automations/README.md`

**Interfaces:**
- Consumes: the JSON result from `python3 scripts/automation/manage_capture_backlog.py snapshot --json`, existing GBrain pages and Goal-linked Runs, installed capture skills, Agent Reach, and the existing browser-reuse contract.
- Produces: one mutually exclusive `capture_drain` or `empty_queue_enrichment` invocation mode; an early active Run and verified reservations for enrichment mode; up to two per-entity results with values `enriched`, `already_sufficient`, or `failed`; or invocation result `no_eligible_candidates`.

- [ ] **Step 1: Write the failing automation contract test**

Add this method to `AutomationContractTests` in
`tests/test_automation_contracts.py`:

```python
def test_capture_worker_enriches_two_entities_only_when_snapshot_is_empty(self):
    directory = ROOT / "automations/memory-stargraph-capture-link-drain"
    prompt = (directory / "prompt.md").read_text()
    heartbeat = (directory / "heartbeat-prompt.md").read_text()
    bootstrap = (directory / "thread-bootstrap.md").read_text()
    readme = (ROOT / "automations/README.md").read_text()
    contract = "\n".join((prompt, heartbeat, bootstrap, readme))

    required = (
        "zero planned items",
        "do not run entity enrichment",
        "maximum of two enrichment slots",
        "effective type is `person` first",
        "organizations or companies",
        "teams or projects",
        "products or technologies",
        "other public entities",
        "previous 30 days",
        "no_eligible_candidates",
        "agent-reach",
        "already_sufficient",
        "must not create capture backlog requests",
        "do not automatically create product TODOs",
        "Memory Stargraph Quality & Learning Analyst",
    )
    for phrase in required:
        self.assertIn(phrase, contract)

    self.assertIn(
        "A non-empty first authoritative snapshot always takes priority",
        prompt,
    )
    self.assertIn(
        "The total cap remains two attempted entities per invocation",
        prompt,
    )
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_automation_contracts.AutomationContractTests.test_capture_worker_enriches_two_entities_only_when_snapshot_is_empty
```

Expected: `FAIL` because the current Curator prompt does not contain the
empty-snapshot entity-enrichment contract.

- [ ] **Step 3: Add the mutually exclusive invocation branch**

In `automations/memory-stargraph-capture-link-drain/prompt.md`, replace the
current numbered steps 4 through 10 with this exact block:

```markdown
4. Branch on the first authoritative snapshot:
   - If it contains one or more planned requests, set invocation mode to `capture_drain`, follow steps 5 through 11, and do not run entity enrichment before or after the drain. A non-empty first authoritative snapshot always takes priority.
   - If it contains zero planned items, set invocation mode to `empty_queue_enrichment`, immediately create an active Goal-linked Run before candidate listing, selection, reservation, or enrichment, skip capture-request transitions, execute the empty-queue enrichment contract below, and then continue to step 11.
5. For `capture_drain`, group frozen requests into the smallest safe coherent batches by source type, login/session, selected skill, target collection, verification path, and rollback boundary.
6. Before capture, move each selected request from `planned` to `capturing` in both parent and child with `manage_capture_backlog.py transition`; verify both readbacks.
7. Drain every frozen item. For each source, read the most specific installed skill completely, preferring `~/.codex/skills/<skill>/SKILL.md`, then `~/.openclaw/skills/<skill>/SKILL.md`, then repository/bundled fallback.
8. Route general sources to `gbrain-capture-link`, PDFs to `gbrain-pdf-capture`, LinkedIn to `gb-capture-linkedin`, and WeChat/X/profile sources to the most specific installed enhanced skill.
9. Reuse request attachments by durable reference and verified SHA-256. The final node must not upload or copy the bytes again. Link request to final with `captured_as` and final to request with `captured_from`.
10. Mark each frozen request `completed` only after source-specific readback, title, search, provenance, memberships, typed relationships, and attachment reuse verification. Otherwise mark it `failed` with exact attempt, evidence, preserved inputs, retry action, and human authority needed.
11. Run compaction again. For `capture_drain`, create one terminal Goal-linked Run. For `empty_queue_enrichment`, finalize the active Goal-linked Run. Record invocation mode, selection and reservation evidence, every terminal item or entity result, failures, timestamps, and durable Learnings.
```

- [ ] **Step 4: Add the complete empty-queue enrichment contract**

Insert this section immediately after the numbered steps in
`automations/memory-stargraph-capture-link-drain/prompt.md`:

```markdown
Empty-queue enrichment contract:

1. This contract runs only when the first authoritative snapshot contains zero planned items. Its active Goal-linked Run must already contain invocation, mode, start-time, and empty-snapshot evidence. Fill a maximum of two enrichment slots; fewer are allowed only when the eligible candidate set is exhausted. The total cap remains two attempted entities per invocation.
2. Build the people-first candidate set with `gbrain list --type person --limit 5000 --sort slug`. Read each candidate page, direct graph, backlinks, files, provenance, and recent Goal-linked enrichment Runs before ranking it.
3. Exclude candidates reviewed within the previous 30 days, reserved by another active enrichment Run, outside current privacy authority, without reliable public evidence, or requiring bypass of authentication or access controls.
4. In every category, order eligible candidates by deficiency first, never-reviewed first, oldest enrichment or review timestamp, then lexical slug. Apply this independently to people; organizations or companies; teams or projects; products or technologies; and other public entities.
5. Select nodes whose effective type is `person` first. If fewer than two eligible people exist, fill remaining slots from the secondary categories in the stated order.
6. Select and reserve one candidate at a time. Persist and read back slug, effective type, reservation timestamp, and invocation id in the active Run before mutation, then re-read other active enrichment Runs. Resolve a collision by earlier reservation timestamp, then invocation id; the losing invocation records and removes its reservation and selects the next candidate.
7. Continue until two entities have verified winning reservations or the eligible set is exhausted. If none are eligible, record `no_eligible_candidates` and finish successfully without speculative changes.
8. For public-source discovery, read and use the installed `agent-reach` skill. Prefer the most specific installed local GBrain or capture skill for each source.
9. Before changing a selected entity, preserve its current page, relationships, backlinks, files, and provenance as before-state evidence. Add only evidence-backed biography, durable profile media, authoritative sources, roles, or meaningful typed relationships.
10. Preserve user-confirmed facts and never replace them with weaker inferred web evidence. Prevent duplicate pages, links, relationships, files, and repeated media storage.
11. Inspect existing browser tabs first and reuse a suitable same-origin or same-source tab. Use authenticated Chrome CDP only when the source requires the user's existing session. Never close a reused user tab.
12. Verify page readback, searchability, direct relationships, backlinks, provenance, and media references. Record truthful evidence and one result per attempted entity:
    - `enriched`: at least one material evidence-backed improvement passed verification;
    - `already_sufficient`: the review found no responsible material improvement; record this Run's review timestamp so later selection can enforce the 30-day cooldown;
    - `failed`: record exact sources, operations, evidence, retry action, and human authority required.
13. Terminalize the active Run on success, failure, or caught interruption and release unattempted reservations. Leave an unexpected hard crash visible as a stale active Run with its reservations and last completed step.
14. This fallback must not create capture backlog requests. Individual failures do not automatically create product TODOs. Report systemic capture-skill, Stargraph, GBrain, authentication, verification, or media defects in the Goal-linked Run for the Memory Stargraph Quality & Learning Analyst to judge.
```

- [ ] **Step 5: Update heartbeat, bootstrap, and pipeline documentation**

Replace the `<instructions>` value in
`automations/memory-stargraph-capture-link-drain/heartbeat-prompt.md` with:

```xml
<instructions>Act as the Memory Stargraph Knowledge Curator and run the complete Capture Link worker instructions now. Anchor all logging to the actual invocation time in America/Los_Angeles and freeze the first planned snapshot. Drain every frozen request to completed or failed; when that snapshot contains zero planned items, run the people-first two-slot entity-enrichment fallback.</instructions>
```

Append this sentence to
`automations/memory-stargraph-capture-link-drain/thread-bootstrap.md`:

```markdown
When the first authoritative snapshot contains zero planned items, execute the people-first two-slot entity-enrichment fallback from the worker prompt.
```

In `automations/README.md`, replace the Knowledge Curator purpose with:

```markdown
Freeze and drain every planned Capture Link request; when the first snapshot is empty, enrich up to two evidence-backed entities with people first.
```

- [ ] **Step 6: Run focused and full automation tests**

Run:

```bash
python3 -m unittest \
  tests.test_automation_contracts.AutomationContractTests.test_capture_worker_enriches_two_entities_only_when_snapshot_is_empty
python3 -m unittest tests.test_automation_contracts
git diff --check -- \
  automations/memory-stargraph-capture-link-drain \
  automations/README.md \
  tests/test_automation_contracts.py
```

Expected:

```text
OK
OK
```

The diff check must produce no output.

- [ ] **Step 7: Commit the tracked contract**

```bash
git add \
  automations/memory-stargraph-capture-link-drain \
  automations/README.md \
  tests/test_automation_contracts.py
git commit -m "feat: enrich entities when Curator queue is empty"
```

---

### Task 1A: Add Active-Run Reservations And Uniform Ranking

**Files:**
- Modify: `tests/test_automation_contracts.py`
- Modify: `automations/memory-stargraph-capture-link-drain/prompt.md`
- Modify: `docs/superpowers/specs/2026-07-16-knowledge-curator-empty-queue-person-enrichment-design.md`
- Modify: `docs/superpowers/plans/2026-07-16-knowledge-curator-empty-queue-entity-enrichment.md`

- [ ] **Step 1: Add failing regression tests**

Assert that the active Goal-linked Run is created before selection, every
selected slug is persisted and read back before mutation, reservation
collisions have a deterministic winner, and every fallback category uses the
same deficiency / never-reviewed / oldest-review / lexical-slug ordering.

- [ ] **Step 2: Verify RED**

```bash
python3 -m unittest \
  tests.test_automation_contracts.AutomationContractTests.test_capture_worker_reserves_entities_before_enrichment_and_terminalizes_run \
  tests.test_automation_contracts.AutomationContractTests.test_capture_worker_ranks_every_fallback_category_deterministically
```

Expected: failure because the original prompt creates its Run after enrichment
and does not spell out the ordering for secondary categories.

- [ ] **Step 3: Implement the minimum contract correction**

Create the active Run on entry to `empty_queue_enrichment`. Reserve candidates
one at a time, persist and read back each reservation before mutation, resolve
collisions by timestamp then invocation id, and terminalize the Run on success,
failure, or caught interruption. Leave a hard crash visible as a stale active
Run. Apply the identical deterministic ordering to all five category groups.

- [ ] **Step 4: Verify GREEN and the full contract suite**

```bash
python3 -m unittest \
  tests.test_automation_contracts.AutomationContractTests.test_capture_worker_reserves_entities_before_enrichment_and_terminalizes_run \
  tests.test_automation_contracts.AutomationContractTests.test_capture_worker_ranks_every_fallback_category_deterministically
python3 -m unittest tests.test_automation_contracts
git diff --check -- \
  automations/memory-stargraph-capture-link-drain/prompt.md \
  docs/superpowers/specs/2026-07-16-knowledge-curator-empty-queue-person-enrichment-design.md \
  docs/superpowers/plans/2026-07-16-knowledge-curator-empty-queue-entity-enrichment.md \
  tests/test_automation_contracts.py
```

---

### Task 2: Update And Verify The Live Curator Automation

**Files:**
- Read: `~/.codex/automations/memory-stargraph-capture-link-drain/automation.toml`
- Modify outside Git through the Codex automation API: live `memory-stargraph-capture-link-drain`

**Interfaces:**
- Consumes: the current live automation record and the tracked
  `automations/memory-stargraph-capture-link-drain/heartbeat-prompt.md`.
- Produces: the same live automation ID, status, recurrence, and persistent
  target task with the updated empty-snapshot heartbeat instructions.

- [ ] **Step 1: Capture the current live routing contract**

Read the live automation and record:

```text
id
name
status
rrule
target_thread_id
created_at
```

Expected stable values:

```text
id = memory-stargraph-capture-link-drain
name = Memory Stargraph Knowledge Curator
status = ACTIVE
rrule = FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0
```

- [ ] **Step 2: Update only the live heartbeat prompt**

Use the Codex automation update API with:

```text
mode = update
id = memory-stargraph-capture-link-drain
kind = heartbeat
name = Memory Stargraph Knowledge Curator
status = ACTIVE
rrule = FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0
destination = thread
targetThreadId = the unchanged current target_thread_id
prompt = the complete tracked heartbeat-prompt.md content
```

Do not create a replacement automation or persistent task.

- [ ] **Step 3: Verify live parity**

Read the live automation again and verify:

- `id`, `status`, `rrule`, `target_thread_id`, and `created_at` are unchanged;
- the prompt mentions the empty first snapshot and people-first two-slot
  enrichment fallback;
- the destination task remains the existing persistent Memory Stargraph
  Knowledge Curator task.

- [ ] **Step 4: Send a setup-only contract refresh to the persistent task**

Send one message to the existing `target_thread_id`:

```text
Contract refresh only: read the updated automations/memory-stargraph-capture-link-drain/prompt.md completely and acknowledge the people-first two-slot entity-enrichment fallback for an empty first authoritative snapshot. Do not drain the capture queue or enrich any entity in this setup-only turn.
```

Expected: concise readiness acknowledgement with no queue or GBrain mutation.
