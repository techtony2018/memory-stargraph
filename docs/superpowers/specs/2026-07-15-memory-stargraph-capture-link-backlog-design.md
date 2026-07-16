# Memory Stargraph Capture Link Backlog Design

Date: 2026-07-15
Status: Approved design pending written-spec review
Timezone: `America/Los_Angeles`

## Objective

Create a dedicated GBrain capture backlog at `notes/memory-starmap-capture-list`, two queue-management skills (`/add-capture-link` and `/get-capture-link`), and a persistent nightly worker that drains the backlog through Tony's enhanced local GBrain capture skills. The system must preserve inputs and attachments, produce auditable status transitions, avoid duplicate media storage, archive each full batch of 50 completed rows, and use Pacific local time for worker-generated logs and reports.

This backlog is separate from `notes/memory-starmap-todo-list`. Product implementation belongs to the Wish to Reallity worker; source ingestion and graph capture belong to the Capture Link worker.

## Selected Approach

Use a dedicated table-backed root node with one child node per capture request. This follows the proven Memory Stargraph TODO routing and archive pattern without mixing capture work into the product backlog.

Alternatives rejected:

- Reusing the TODO list would allow the wrong worker to consume capture requests and would mix product delivery with content ingestion.
- A graph-only queue would be harder to drain deterministically, summarize, compact, and inspect from a simple slash command.

## GBrain Data Model

### Root

The root slug is:

```text
notes/memory-starmap-capture-list
```

It is a collection-like note with a `## Capture Items` table:

```markdown
| id | status | source kind | source | target | node | updated | notes |
```

IDs are monotonically increasing `CAP-0001`, `CAP-0002`, and so on.

Allowed statuses are:

- `planned`: safely queued and ready for a worker snapshot.
- `capturing`: frozen into an active invocation and currently being processed.
- `completed`: capture and all required verification succeeded.
- `failed`: a real attempt proved a concrete blocker or unmet acceptance criterion.

The active root retains every `planned`, `capturing`, and `failed` row plus only the newest unarchived zero to forty-nine completed rows. Oldest active rows remain first so the queue drains fairly.

### Request Children

Each request has a child below:

```text
notes/memory-starmap-capture-list/<request-slug>
```

The child records:

- `capture_id`, status, source kind, original source, and created/updated timestamps;
- requested target slug/type when supplied;
- capture instructions and requested typed relationships;
- source-specific routing decisions and the exact skill used;
- durable attachment references, byte counts, SHA-256 hashes, and hosted readback receipts;
- attempt history, blocker evidence, retry instructions, and human-control requirements;
- final captured slug or slugs and verification evidence.

The root links to each active child with `has_capture_request`; the child links back with `capture_request_for`.

### Failed Collection

Failed items are enumerable through:

```text
notes/memory-starmap-capture-list/failed-items
```

Use idempotent forward and reverse links equivalent to the TODO failed-items pattern. A request stays failed until explicitly requeued or resolved; the worker must not silently retry it in every invocation.

### Completed Archives

Each full batch of the fifty oldest unarchived completed rows moves into an immutable archive collection:

```text
notes/memory-starmap-capture-list/completed-archive-0001
notes/memory-starmap-capture-list/completed-archive-0002
```

The root links to each archive with `has_completed_archive`; archives link back with `completed_archive_for`. Archive rows retain child links and completion evidence. Compaction never deletes child nodes, final captured nodes, attachments, or provenance links.

## Attachment Staging and Reuse

`/add-capture-link` uploads attached media exactly once to the provisional request child through the Memory Stargraph multipart attachment endpoint. Queue finalization requires durable-storage confirmation, matching byte count and SHA-256, and hosted readback. A ledger row or warm local cache is not proof of durability.

The durable attachment path remains owned by the request child. The eventually captured node references that same durable path and links to the request with `captured_from`; the request links to each final node with `captured_as`. The worker must not upload or copy the bytes again merely to create a final-node-specific path. The request child remains durable after its table row is archived, so the shared reference does not become dangling.

If a capture tool normally uploads attachments itself, the worker must detect already-staged request attachments and use the verified references rather than invoke another upload. Completion evidence compares the final reference's hosted byte count and SHA-256 with the staged receipt.

## `/add-capture-link` Skill

The skill is queue-only. It never performs the eventual content capture.

Accepted inputs include:

- ordinary URLs and social URLs;
- local files and PDFs;
- pasted text or user-provided facts;
- existing GBrain slugs that need refresh, enrichment, or linking;
- profile/bulk-capture instructions such as LinkedIn or WeChat requests;
- one or more media attachments supplied by the chat host;
- optional target slug/type, collection/container, and exact relationship instructions.

The skill:

1. Parses and validates the request without guessing privacy-sensitive or ambiguous relationships.
2. Creates a provisional, unlinked recovery child.
3. Privately spools every attachment and uploads it through Stargraph.
4. Verifies durable byte receipts and appends durable references to the provisional child.
5. Assigns the next `CAP-*` ID, finalizes the child as `planned`, appends the parent row, and creates graph links only after all inputs are durable.
6. Verifies parent row, child status, graph links, and attachment references before reporting success.

On queueing failure, it does not create a misleading planned row. It preserves exact input/attachment bytes in a private recovery bundle and returns the manifest, proposed blocker, and exact retry command. It never substitutes, regenerates, crops, or silently drops supplied media.

## `/get-capture-link` Skill

The skill is read-only. It reads the authoritative root and supports:

- all items;
- `planned`;
- `capturing`;
- `completed`;
- `failed`.

Markdown output includes summary counts and exact clickable local Memory Stargraph links for request children and final captured slugs. It never changes statuses or triggers capture work.

## Persistent Capture Worker

Automation ID:

```text
memory-stargraph-capture-link-drain
```

Name:

```text
Memory Stargraph Capture Link Worker
```

The automation is a heartbeat targeting one persistent, separate worker thread. Its daily schedule is midnight in `America/Los_Angeles`. Midnight is only a scheduled trigger; the same worker may be triggered manually at any time and must anchor the invocation to its actual start time.

Each invocation:

1. Runs capture-list compaction and verifies the active root.
2. Records an invocation ID and actual Pacific start time, then freezes the first authoritative snapshot of every row whose status is exactly `planned`.
3. Groups snapshot items into the smallest safe coherent batches based on source type, authentication/session needs, shared browser or fetch setup, target collection, capture skill, verification path, and rollback boundary.
4. Moves every selected parent row and child node from `planned` to `capturing` and verifies both transitions before capture.
5. Drains every frozen item; it does not stop after one batch and does not impose a fixed end time.
6. Marks every snapshot item `completed` or `failed` in both parent and child records.
7. Runs compaction again, records a Goal-linked parent Run plus batch evidence, and reports completed, failed, and post-cutoff IDs separately.

Items created after the frozen snapshot belong to the next invocation.

## Capture Skill Routing

For every source type, the worker prefers Tony's enhanced local skill in this order:

1. `~/.codex/skills/<skill>/SKILL.md`
2. `~/.openclaw/skills/<skill>/SKILL.md`
3. repository or bundled fallback

The most specific applicable skill wins. Expected routing includes:

- general URLs, text, existing slugs, facts, and explicit graph links: `gbrain-capture-link`;
- PDFs: `gbrain-pdf-capture`;
- LinkedIn profile/post capture: `gb-capture-linkedin`;
- WeChat capture/import: the applicable installed WeChat capture skill;
- X/Twitter and other live public sources: `gbrain-capture-link` plus its prescribed live-fetch backend.

The worker reads the selected `SKILL.md` completely before acting. It resolves existing entities before creating pages, derives human-readable titles from content, sanitizes frontmatter leaks, adds explicit typed and membership relationships, and never automatically links ordinary captures to global `index`.

## Browser and Human-Control Contract

Before browser work, inspect existing tabs and reuse a suitable same-origin or same-source tab. Never close a reused user tab; close only a temporary tab created by the current invocation.

Use an authenticated Chrome CDP session when a source requires the user's login. Do not bypass authwalls, CAPTCHA, checkpoints, privacy controls, or access restrictions. Authentication, privacy-sensitive capture, destructive cleanup, ambiguous relationship semantics, or irreversible operations require human authority. A blocked item becomes `failed` with exact recovery instructions rather than being falsely completed.

## Completion and Failure Evidence

A completed item requires, as applicable:

- readable final GBrain slug and human-readable title;
- distinctive search readback;
- requested typed links plus enumerable collection membership;
- source provenance and bidirectional request/result links (`captured_as` and `captured_from`);
- attachment reference with hosted byte count and SHA-256 matching the staged receipt;
- source-specific verification prescribed by the chosen skill.

A failed item records:

- attempted steps and exact error/evidence;
- preserved source and attachments;
- tests/readback completed before failure;
- rollback or containment;
- smallest retry/recovery action;
- required login, approval, or authority.

## Pacific-Time Contract for All Workers

All Memory Stargraph worker-generated logs, Run records, batch reports, status-transition evidence, filenames containing timestamps, and final reports must use the IANA timezone `America/Los_Angeles`.

- In summer, timestamps display PDT and the correct `-07:00` offset.
- In winter, timestamps display PST and the correct `-08:00` offset.
- Use timezone-aware ISO 8601 values and include `PDT` or `PST` in human-facing reports when useful.
- Do not label UTC timestamps as Pacific time and do not use a fixed UTC-8 offset year-round.
- Preserve an external source's original timestamp as provenance when needed, but add a Pacific-normalized value for worker logs and reports.

This contract must be added to the prompts for the new Capture Link worker and all existing tracked Memory Stargraph workers:

- `gbrain-x-intelligence-capture`;
- `memory-stargraph-daily-learning-intake`;
- `memory-stargraph-wish-to-reallity`;
- `memory-stargraph-divergent-product-discovery`;
- `memory-stargraph-goal-steward-daily-review`.

The corresponding live automation prompts must be updated in the same implementation so checked-in desired state and runtime behavior do not drift.

## Tracked Components

Implementation will add or update:

- the root, failed-items collection, and required GBrain links;
- `~/.codex/skills/add-capture-link` and `~/.codex/skills/get-capture-link`;
- matching OpenClaw skill mirrors when that environment is expected to invoke the commands;
- capture-list helper scripts and tests;
- a parameterized/generalized compaction engine reused by TODO and capture backlogs;
- `automations/memory-stargraph-capture-link-drain/{automation.toml,heartbeat-prompt.md,prompt.md,thread-bootstrap.md}`;
- `automations/README.md`, the automation runbook, and automation contract tests;
- Pacific-time language in every tracked and live Memory Stargraph worker prompt;
- one persistent worker thread and its active midnight heartbeat automation.

## Test and Acceptance Plan

Automated coverage must prove:

- `CAP-*` ID allocation and table parsing;
- transactional queue creation with and without attachments;
- no planned row on partial attachment failure and a valid recovery manifest;
- `planned -> capturing -> completed|failed` transitions in both parent and child;
- broad source-kind parsing and most-specific local-skill routing;
- attachment upload-once behavior and final-node reference/hash reuse;
- complete frozen-snapshot draining and post-cutoff separation;
- failed-items graph maintenance;
- exact 50-row archive boundaries, oldest-first order, idempotency, and active-root retention rules;
- read-only status filtering and clickable slug rendering;
- persistent-thread destination and midnight `America/Los_Angeles` schedule;
- Pacific-time contract presence in all six worker prompts;
- manual triggers not depending on a fixed start or cutoff time.

Live acceptance must:

1. Queue representative URL, PDF/file, pasted-text, and media-bearing requests.
2. Verify attachments are durable before rows become planned.
3. Manually trigger the persistent worker and confirm it drains the frozen snapshot through the correct enhanced local skills.
4. Verify captured slugs, search, relationships, provenance, and attachment SHA-256 readback.
5. Prove the final captured node did not create a second stored media copy.
6. Exercise one concrete failure and verify failed-items evidence without losing inputs.
7. Exercise a 50-item synthetic compaction fixture and verify immutable archive links.
8. Verify the live heartbeat points to the persistent Capture Link worker, is active, and schedules midnight in `America/Los_Angeles`.
9. Inspect worker-generated Run/report timestamps and confirm PDT/PST is correct for the date.

## Rollout and Rollback

Roll out in this order: data/compaction helpers and tests, queue skills, GBrain root, worker prompt/definition, persistent thread, live heartbeat, then representative live capture. Do not seed arbitrary captures during setup.

Rollback pauses the new heartbeat, preserves the root/children/attachments for audit, and reverts tracked automation/skill code. It must not delete captured nodes, durable attachments, archive collections, or user inputs.
