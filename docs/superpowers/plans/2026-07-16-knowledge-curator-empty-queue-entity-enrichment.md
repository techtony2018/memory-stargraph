# Knowledge Curator Empty-Queue Entity Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Memory Stargraph Knowledge Curator enrich up to two evidence-backed entities when its first authoritative capture snapshot is empty, prioritizing people and then bounded secondary entity types.

**Architecture:** Keep the existing capture worker, schedule, persistent task, and queue-drain path unchanged. Add one explicit branch immediately after the frozen snapshot: non-empty snapshots follow the existing drain contract exclusively; empty snapshots use a deterministic two-slot enrichment contract and record results in the same Goal-linked Run.

**Tech Stack:** Markdown automation prompts, TOML heartbeat definitions, Python `unittest`, GBrain CLI, Agent Reach, in-app browser, Chrome CDP.

## Global Constraints

- The automation ID remains `memory-stargraph-capture-link-drain`.
- The user-facing role remains `Memory Stargraph Knowledge Curator`.
- The schedule remains daily 12:00 AM in `America/Los_Angeles`, with manual triggering allowed and no fixed cutoff.
- A non-empty first authoritative snapshot always takes priority; enrichment must not run before or after draining it.
- The total empty-queue enrichment cap is two attempted entities, with fewer allowed only when the eligible candidate set is exhausted.
- Candidate priority is people, organizations/companies, teams/projects, products/technologies, then other public entities.
- Skip entities enriched or reviewed successfully within the previous 30 days.
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
- Produces: one mutually exclusive `capture_drain` or `empty_queue_enrichment` invocation mode; up to two per-entity results with values `enriched`, `already_sufficient`, or `failed`; or invocation result `no_eligible_candidates`.

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
   - If it contains zero planned items, set invocation mode to `empty_queue_enrichment`, skip capture-request transitions, execute the empty-queue enrichment contract below, and then continue to step 11.
5. For `capture_drain`, group frozen requests into the smallest safe coherent batches by source type, login/session, selected skill, target collection, verification path, and rollback boundary.
6. Before capture, move each selected request from `planned` to `capturing` in both parent and child with `manage_capture_backlog.py transition`; verify both readbacks.
7. Drain every frozen item. For each source, read the most specific installed skill completely, preferring `~/.codex/skills/<skill>/SKILL.md`, then `~/.openclaw/skills/<skill>/SKILL.md`, then repository/bundled fallback.
8. Route general sources to `gbrain-capture-link`, PDFs to `gbrain-pdf-capture`, LinkedIn to `gb-capture-linkedin`, and WeChat/X/profile sources to the most specific installed enhanced skill.
9. Reuse request attachments by durable reference and verified SHA-256. The final node must not upload or copy the bytes again. Link request to final with `captured_as` and final to request with `captured_from`.
10. Mark each frozen request `completed` only after source-specific readback, title, search, provenance, memberships, typed relationships, and attachment reuse verification. Otherwise mark it `failed` with exact attempt, evidence, preserved inputs, retry action, and human authority needed.
11. Run compaction again. Create one Goal-linked Run with invocation mode, batch grouping or enrichment selection, every terminal item or entity result, failures, post-snapshot ids, timestamps, and durable Learnings.
```

- [ ] **Step 4: Add the complete empty-queue enrichment contract**

Insert this section immediately after the numbered steps in
`automations/memory-stargraph-capture-link-drain/prompt.md`:

```markdown
Empty-queue enrichment contract:

1. This contract runs only when the first authoritative snapshot contains zero planned items. Fill a maximum of two enrichment slots; fewer are allowed only when the eligible candidate set is exhausted. The total cap remains two attempted entities per invocation.
2. Build the people-first candidate set with `gbrain list --type person --limit 5000 --sort slug`. Read each candidate page, direct graph, backlinks, files, provenance, and recent Goal-linked enrichment Runs before ranking it.
3. Rank eligible people deterministically by: missing or weak biography; missing durable profile image; missing authoritative public sources; missing current or historically important roles; sparse meaningful typed relationships or backlinks; oldest successful enrichment or review evidence with never-reviewed first; then slug.
4. Skip an entity that was successfully enriched or reviewed within the previous 30 days, is already selected by another active enrichment Run, is private or sensitive beyond current authority, lacks reliable public evidence, or would require bypassing authentication or access controls.
5. Select nodes whose effective type is `person` first. If fewer than two eligible people exist, fill remaining slots by listing and ranking these types in order: organizations or companies; teams or projects; products or technologies; then other public entities with a clear evidence-backed enrichment opportunity.
6. Continue through the ranked candidates until two entities have been attempted or the eligible candidate set is exhausted. If none are eligible, record `no_eligible_candidates` in the Goal-linked Run and finish successfully without speculative changes.
7. For public-source discovery, read and use the installed `agent-reach` skill. Prefer the most specific installed local GBrain or capture skill for each source.
8. Before changing a selected entity, preserve its current page, relationships, backlinks, files, and provenance as before-state evidence. Add only evidence-backed biography, durable profile media, authoritative sources, roles, or meaningful typed relationships.
9. Preserve user-confirmed facts and never replace them with weaker inferred web evidence. Prevent duplicate pages, links, relationships, files, and repeated media storage.
10. Inspect existing browser tabs first and reuse a suitable same-origin or same-source tab. Use authenticated Chrome CDP only when the source requires the user's existing session. Never close a reused user tab.
11. Verify page readback, searchability, direct relationships, backlinks, provenance, and media references. Record one result per attempted entity:
    - `enriched`: at least one material evidence-backed improvement passed verification;
    - `already_sufficient`: the review found no responsible material improvement; record this Run's review timestamp so later selection can enforce the 30-day cooldown;
    - `failed`: record exact sources, operations, evidence, retry action, and human authority required.
12. This fallback must not create capture backlog requests. Individual failures do not automatically create product TODOs. Report systemic capture-skill, Stargraph, GBrain, authentication, verification, or media defects in the Goal-linked Run for the Memory Stargraph Quality & Learning Analyst to judge.
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
