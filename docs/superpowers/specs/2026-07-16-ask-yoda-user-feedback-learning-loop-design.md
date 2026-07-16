# Ask Yoda User Feedback and Daily Learning Loop Design

Date: 2026-07-16

## Purpose

Give users a lightweight way to rate every completed Ask Yoda answer, add
optional written feedback, and feed that evidence into the existing daily
Memory Stargraph learning loop.

The system must distinguish among:

- Ask Yoda product or code problems;
- graph data-quality problems such as missing relationships or backlinks;
- capture-quality patterns that should improve future captures;
- answer-specific preferences or inconclusive feedback that does not justify
  work.

User feedback is evidence, not an automatic command to change code or graph
data. The Memory Stargraph Daily Learning Intake worker remains responsible for
judging whether evidence warrants a TODO, a data-quality recommendation, a
durable Learning, capture guidance, or no action.

## Worker Role Titles

The persistent tasks receive clear user-facing role titles:

| Existing worker | User-facing role title |
| --- | --- |
| Memory Stargraph Goal Steward | Memory Stargraph Product Owner |
| Memory Stargraph Wish to Reality Worker | Memory Stargraph Engineer |
| Memory Stargraph Daily Learning Intake Worker | Memory Stargraph Quality & Learning Analyst |
| GBrain X Intelligence Worker | GBrain Intelligence Researcher |
| Memory Stargraph Divergent Product Discovery Worker | Memory Stargraph Product Strategist |
| Memory Stargraph Capture Link Worker | Memory Stargraph Knowledge Curator |

These are presentation changes only. Existing automation IDs, schedules,
persistent target task IDs, routing, and internal compatibility names such as
`memory-stargraph-wish-to-reallity` remain unchanged.

The Product Owner audits the complete loop and surfaces gaps. It does not
duplicate analysis, implementation, capture, or research owned by the other
roles.

## Current System Context

Ask Yoda already has:

- server-backed chat history in `data/yoda_chats.json`;
- privacy-safe diagnostic history in `data/yoda_logs.json`;
- stable response `request_id` values;
- node-scoped and global View Log surfaces;
- resolver event submission with production versus test provenance;
- a daily 1:00 AM Learning Intake worker that already reviews Ask Yoda logs,
  resolver evidence, Runs, Learnings, health, backups, and recent changes.

The feedback feature extends these surfaces instead of creating a second
analysis automation or overloading resolver telemetry with general product
feedback.

## Answer Feedback Experience

Every completed assistant answer displays three compact controls beneath the
answer bubble:

1. thumbs up;
2. thumbs down;
3. a comment icon.

Thumbs up and thumbs down are mutually exclusive. A user may:

- select either rating;
- replace one rating with the other;
- click the active rating again to clear it;
- submit a comment with a rating;
- submit a comment without selecting a rating;
- edit or clear a previously saved comment.

Clicking the comment icon opens a compact inline editor with:

- a text area;
- Save;
- Cancel;
- a 2,000-character limit;
- a visible saving state;
- a saved confirmation only after server acknowledgement;
- a truthful retryable error when persistence fails.

Feedback controls do not appear on system messages, user messages, pending
answers, or failed requests that produced no completed answer.

Controls must work with keyboard navigation and screen readers. Each icon has a
specific accessible label, pressed state where applicable, tooltip, focus
style, and live-region status feedback.

## Stable Answer Identity

Each completed assistant message has a stable `answer_id`.

- New answers use the Ask Yoda `request_id` as their `answer_id`.
- Restored legacy answers without a request ID receive a deterministic ID
  derived from the node slug, timestamp, and sanitized answer content.
- Chat persistence retains `answer_id` and optional `request_id`.
- Reopening Ask Yoda, refreshing the page, or restarting the service must not
  generate a different identity for the same stored answer.

This identity allows feedback to be joined with chat history and diagnostic
logs without copying full questions or answers into the feedback ledger.

## Durable Feedback Ledger

Feedback is stored separately in:

```text
data/yoda_feedback.json
```

The ledger is keyed by `answer_id`. Each record contains:

```text
answer_id
request_id
slug
rating
comment
created_at
updated_at
review_status
reviewed_at
review_run_slug
decision
related_todo_ids
related_learning_slugs
```

Field contracts:

- `rating` is `up`, `down`, or empty.
- `comment` is secret-redacted, sanitized plain text with a maximum of 2,000
  characters.
- `review_status` is `unreviewed` or `reviewed`.
- `decision` is one of `no_action`, `product_todo_created`,
  `product_todo_updated`, `data_quality_recommendation`,
  `capture_guidance`, or `learning_only`.
- related IDs and slugs are arrays so one daily review can associate an item
  with existing evidence without rewriting the original feedback.

The ledger does not duplicate full question or answer content. The Quality &
Learning Analyst joins feedback to `yoda_chats.json` and `yoda_logs.json` using
the stable answer and request IDs.

Clearing Ask Yoda chat history does not erase feedback. Feedback is durable
learning evidence. If its associated chat was cleared before review, the
worker uses the remaining slug, request ID, diagnostics, rating, and comment
and records that conversational context was unavailable.

Writes use the existing atomic JSON persistence pattern. Updates are
idempotent and preserve the original `created_at`.

## Feedback APIs

### Create or update feedback

```text
PUT /api/yoda-feedback/<answer_id>
```

Request fields:

```text
request_id
slug
rating
comment
```

The server validates answer identity, rating values, comment length, and
sanitization before atomically upserting the record.

### Read feedback

```text
GET /api/yoda-feedback
```

Supported filters:

```text
slug
since
until
rating
review_status
limit
```

The UI uses answer and slug filters to restore saved control state. The Quality
& Learning Analyst uses the time-window and review-status filters.

### Record review decisions

```text
POST /api/yoda-feedback/review
```

Request fields:

```text
answer_ids
review_run_slug
decision
related_todo_ids
related_learning_slugs
reviewed_at
```

Review updates are idempotent. A failed daily run does not mark feedback
reviewed or advance its successful review watermark.

## Daily Quality and Learning Analysis

No new recurring automation is created. The existing Memory Stargraph Daily
Learning Intake automation remains the owner and runs at 1:00 AM in
`America/Los_Angeles`.

For each invocation, the Quality & Learning Analyst:

1. reads unreviewed feedback since the last successful review;
2. joins it to Ask Yoda history and diagnostic logs;
3. reads current relationships and backlinks for affected node slugs;
4. checks resolver events, recent captures, Runs, Learnings, and existing TODOs;
5. clusters repeated symptoms and suppresses synonymous work;
6. assigns each signal to a decision lane;
7. creates or updates evidence-qualified TODOs only when justified;
8. creates sanitized data-quality recommendations and durable capture guidance
   when appropriate;
9. writes the daily report and Goal-linked Run;
10. marks feedback reviewed only after all required writes verify successfully.

Manual Learning Intake triggers use the same logic and watermark. Multiple
same-day invocations are valid and must remain idempotent.

## Decision Lanes

### Product or code issue

Examples include:

- incorrect or poorly formatted answers;
- slow context retrieval;
- broken feedback controls;
- misleading fallback behavior;
- missing diagnostics or observability;
- incorrect answer-to-log association.

The worker may create or update a planned Memory Stargraph TODO under its
existing rules:

- search for duplicates first;
- require reproducible or repeated evidence;
- include bounded acceptance and rollback criteria;
- create at most three planned TODOs per Learning Intake run.

A single rating never creates a TODO automatically.

### Graph data-quality issue

Examples include:

- missing or incorrect relationships;
- weak or absent backlinks;
- duplicate or ambiguous entities;
- incomplete source provenance;
- stale node content;
- insufficient graph context for the question.

The worker records an actionable recommendation with:

- affected slug;
- feedback and request IDs;
- observed answer symptom;
- current relationship or backlink evidence;
- suggested correction or verification;
- confidence;
- whether a user or capture workflow is the appropriate owner.

The worker does not automatically add, delete, or rewrite graph relationships
or backlinks.

### Capture-quality pattern

Examples include repeated captures that omit:

- authorship;
- publication dates;
- provenance;
- reciprocal capture links;
- collection membership;
- expected about, mentions, or documents relationships;
- source-native versus Pacific timestamps.

Repeated, corroborated patterns are distilled into a stable guidance node:

```text
notes/memory-stargraph-capture-quality-guidance
```

Relevant local capture skills read this concise guidance before capture and
record which guidance rules they applied in their Run evidence.

One-off node defects remain daily recommendations. A repeated skill-level
problem may justify a planned TODO to improve the responsible capture skill.

### Answer-specific or inconclusive feedback

Personal preferences, ambiguous comments, and isolated low-confidence ratings
remain evidence. The worker records `no_action` or `learning_only` with a
reason rather than manufacturing backlog work.

## GBrain Reporting

Create a curated collection:

```text
collections/memory-stargraph-yoda-feedback
```

Each daily report uses:

```text
collections/memory-stargraph-yoda-feedback/reports/YYYY-MM-DD
```

The report contains only sanitized operational evidence:

- review window;
- ratings and comments reviewed;
- reviewed and unreviewed counts;
- affected slugs and request IDs;
- product findings;
- graph data-quality recommendations;
- capture-quality patterns;
- TODOs created or updated;
- durable Learnings created or reused;
- no-action decisions and reasons;
- failures and retry state;
- Goal-linked Run.

Raw private questions, full answers, comments, tokens, cookies, credentials,
and hidden browser data are not copied into GBrain reports. Comments are
summarized only to the minimum needed to support a decision.

## Schedule and Feedback Loop

The existing daily sequence is preserved:

```text
12:00 AM  Memory Stargraph Knowledge Curator
12:15 AM  GBrain Intelligence Researcher
1:00 AM   Memory Stargraph Quality & Learning Analyst
2:00 AM   Memory Stargraph Engineer
```

The complete feedback loop is:

```text
Ask Yoda answer
-> user rating or comment
-> durable feedback ledger
-> daily history, log, graph, and feedback analysis
-> product TODO, data recommendation, capture guidance, Learning, or no action
-> Engineer or future capture applies the bounded improvement
-> Run evidence verifies the result
-> Product Owner audits whether the Learning changed later behavior
```

The recurrence time is a default trigger, not a cutoff. Manual worker triggers
use the same current prompts, actual invocation time, and evidence contract.

## Human Control

The feedback loop must not:

- automatically modify relationships or backlinks;
- delete or rewrite historical telemetry;
- accept, reject, or apply resolver proposals;
- persist raw private conversations into GBrain;
- create a TODO from every thumbs-down;
- make destructive data corrections;
- change worker routing or schedules without explicit authority.

Resolver-related feedback may be linked to resolver evidence only after the
Quality & Learning Analyst determines that the problem is actually routing or
resolver behavior rather than model quality, missing graph data, or user
preference.

## Failure and Retry Behavior

- A failed feedback save remains visibly unsaved and retryable.
- The UI never reports success before server acknowledgement.
- A failed daily analysis leaves feedback `unreviewed`.
- The successful review watermark advances only after the report, Run, TODO or
  Learning writes, and feedback review updates verify.
- Stable answer IDs, review Run slugs, and TODO duplicate checks make retries
  idempotent.
- Missing cleared chat context is recorded, not guessed.
- A day with no new feedback produces a clean no-op feedback section in the
  normal Learning Intake Run.
- Partial failures are reported with enough evidence for the next invocation to
  resume safely.

## Metrics

Daily and rolling summaries include:

- answers eligible for feedback;
- thumbs-up and thumbs-down counts;
- comment count;
- feedback participation rate;
- reviewed and unreviewed counts;
- review age;
- product, graph-quality, capture-quality, and inconclusive classifications;
- TODO creation and update yield;
- data-quality recommendation count;
- capture-guidance reuse count;
- feedback-to-completed-improvement follow-through;
- answer latency, fallback, and grounding metrics when relevant.

Metrics must not expose raw private text.

## Verification

### Backend

- atomic feedback creation and updates;
- valid rating transitions and clearing;
- independent comment submission;
- 2,000-character enforcement and secret redaction;
- stable new and legacy answer IDs;
- feedback persistence across restart;
- feedback survival after chat clearing;
- read filters and bounded limits;
- idempotent daily review updates;
- failed review does not advance review state.

### Frontend

- controls appear after every completed assistant answer;
- controls do not appear on other message types;
- rating toggle and replacement behavior;
- independent inline comment flow;
- saved state restores after closing and reopening Ask Yoda;
- saved state survives page and service restart;
- keyboard and screen-reader behavior;
- mobile and desktop layout;
- truthful saving and failure states;
- existing Ask GBrain fallback reveal and chat formatting remain intact.

### Daily automation

- one rating creates no automatic TODO;
- repeated or reproducible evidence may create or update one deduplicated TODO;
- graph-quality evidence produces a recommendation without graph mutation;
- repeated capture-quality evidence updates durable guidance;
- a representative later capture reads and applies that guidance;
- raw comments and conversations do not leak into GBrain;
- resolver proposals remain unchanged;
- no-op days record a clean Run;
- retry after partial failure does not duplicate work.

### Release verification

- all Python and JavaScript checks pass;
- visible and runtime versions align;
- dashboard-managed local service is restarted and verified;
- configured `.85` and `.102` targets are deployed and verified;
- desktop and mobile behavior is inspected through a reused browser tab;
- persistent Chrome tab count does not increase;
- daily worker prompt and automation contract tests pass;
- the Product Owner can trace feedback to review decision, TODO or guidance,
  implementation Run, and later verification.

## Acceptance Criteria

- Every completed Ask Yoda answer supports thumbs up, thumbs down, and optional
  text feedback through one comment icon.
- Feedback is durable, editable, idempotent, and associated with a stable
  answer identity.
- The Quality & Learning Analyst reviews new feedback, history, logs,
  relationships, and backlinks at least once daily.
- The worker decides whether to create or update a TODO; feedback never creates
  implementation work directly.
- Data-quality and capture-quality findings are preserved without automatic
  graph mutation.
- Relevant capture skills can reuse durable guidance in later Runs.
- Daily reporting is sanitized, Goal-linked, deduplicated, and auditable.
- Worker role titles are visible without changing automation IDs, persistent
  task routing, or schedules.
- Human approval remains required for resolver proposals and risky or
  destructive data changes.

## Out of Scope

- Public multi-user accounts or authentication;
- replacing the existing Ask Yoda chat or diagnostic stores;
- automatically editing graph relationships from feedback;
- automatically applying resolver proposals;
- sending feedback to a hosted analytics vendor;
- adding a second daily feedback automation;
- treating every rating as a support ticket or TODO.
