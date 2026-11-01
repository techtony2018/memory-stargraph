---
type: report
title: Memory Stargraph Divergent Product Discovery 2026-11-01
run: runs/memory-stargraph-divergent-product-discovery-20261101t040222-0800-85
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
status: completed_one_new_todo_strategy_candidates
product: products/memory-stargraph
started_at: '2026-11-01T04:02:22-08:00'
completed_at: '2026-11-01T04:08:11-08:00'
automation_id: memory-stargraph-divergent-product-discovery
invocation_id: memory-stargraph-divergent-product-discovery-20261101t040222-0800-85
source_commit: b90078e29bccfc8522d631335a9fa3e66e002a80
ui_version: V1.0.231
gbrain_version: V0.46.28.0
created_todo_ids:
  - SG-0246
updated_todo_ids: []
learning_slug: null
product_owner_destination_task_id: 019faa62-6058-7643-b9cc-a2627083af07
product_owner_notification_status: acknowledged_by_product_owner
product_owner_notification_pending: false
product_owner_acknowledged_at: '2026-11-01T04:10:50-08:00'
tags:
  - completed
  - discovery
  - memory-stargraph
  - product-strategy
---

# Memory Stargraph Divergent Product Discovery 2026-11-01

## Decision

This bounded .85 Product Strategy review completed with one new planned P1 TODO, SG-0246, and four retained strategy candidates. No strategy-parent row, Learning, product code, deployment, service, resolver, reranker, browser, backup/restore, production prompt, or production/user data was mutated.

SG-0246 is justified by a current, reproducible product integrity defect. The authoritative canonical backlog reports planned=10, completed=33, failed=2 before promotion and contains SG-0237 through SG-0245. An explicit supported `/api/settings-evidence?refresh=1` instead reports planned=2, completed=32, failed=2 and names only SG-0234 through SG-0236 as blockers. Source inspection shows the weekly digest reads the canonical backlog with `local_first=true`; the selected local file was last modified on 2026-10-17 and has exactly the stale 2/32/2 counts. After SG-0246 creation, the authoritative planned count is 11 while the weekly surface remains stale.

The official allocator verified SG-0246's parent row, child, durable readback, and graph link. The child nevertheless retained `capture-recovery` alongside `planned`, a recurrence of the lifecycle cleanup contract completed in SG-0227. Strategy did not mutate tags or create another TODO. Product Owner reconciliation is required.

## Source-Sync Preflight

- `workspace_path`: `/Users/toddy/memory-stargraph`
- `branch`: `main`
- `local_head`: `b90078e29bccfc8522d631335a9fa3e66e002a80`
- `upstream_ref`: `origin/main`
- `upstream_head`: `b90078e29bccfc8522d631335a9fa3e66e002a80`
- `dirty_state`: clean, with no untracked paths before Strategy artifacts
- `divergent_state`: ahead 0, behind 0
- `deployed_service_version`: V1.0.231; GBrain V0.46.28.0
- `required_script_existence`: role prompt and `scripts/automation/gbrain_worker_api.py` present
- `selected_source_path`: `/Users/toddy/memory-stargraph`
- `selected_source_surface`: current checkout plus dashboard-managed TLS API at `https://127.0.0.1:8788`
- `action_taken`: fetched origin with prune and used the current workspace; no source sync, overwrite, or deployment required
- Preserved unrelated deployment artifacts, including `config/tailscale-certs/`.

## Evidence Reviewed

- Canonical product, project, [goals/memory-stargraph-continuous-learning-local-knowledge-os](http://127.0.0.1:8788/?slug=goals%2Fmemory-stargraph-continuous-learning-local-knowledge-os), canonical SG backlog, [notes/memory-stargraph-product-strategy-todo-list](http://127.0.0.1:8788/?slug=notes%2Fmemory-stargraph-product-strategy-todo-list), prior Strategy report, recent SRE/UX/Capture/X Runs and reports, recent Learnings, resolver state, health, setup and automation runbook, git history, activation, readiness, Ask Yoda configuration/logs, backup, and active-tag surfaces.
- Source began clean/current on `main == origin/main == b90078e2`. The only product-source change since the prior Strategy run is completed SG-0242's TODO paragraph preservation. The deployed service remains healthy and loaded at V1.0.231.
- Canonical backlog before promotion was planned=10, implementing=0, failed=2, completed=33. SG-0234 through SG-0245 already own restore, Escape, Capture scope history, large Run View, Ask Yoda runtime, pair IDs, disk, sample activation, .102 health, browser entity-cache revalidation, and View entity-link behavior. SG-0246 increases planned to 11.
- A forced Settings evidence refresh reports planned=2, completed=32, failed=2 and omits SG-0237 through SG-0245. `/Users/toddy/brain/notes/memory-starmap-todo-list.md` was last modified 2026-10-17 and has the same stale counts. The authoritative raw API has the current rows. This creates false blocker, readiness, and prioritization evidence.
- Customer readiness remains 5/9 ready: Ask Yoda model degraded, weekly outcomes degraded, reranker Critical and approval-gated, and configured-target attestation source-mismatched. SRE numeric evidence is marked ready/current.
- Ask Yoda remains backend `codex`, model `gpt-5.6-sol`, runtime unavailable. Among 30 sampled logs, 29 are test/synthetic and one is production. The production attempt at source timestamp `2026-10-28T02:18:05Z` fell back after 7.551 seconds with `Codex runtime is unavailable`. SG-0238 remains the current owner; no duplicate was created.
- Persistent Search is ready and idle, but its operating contract is missing and write safety is not attested. Cumulative metrics are 13,428 calls, 13,121 successes, 307 errors, 270 timeouts, and 171 CLI fallbacks. The latest error was a tool timeout at source timestamp `2026-11-01T11:00:52Z`. This is a trend requiring measurement, not a new distinct user-facing defect from this run.
- Retrieval remains 10/10 answers, 10/10 recall, and 9/9 expected sources in the latest SRE evidence. Backup is current. Restore rehearsal remains critically stale under SG-0234. Disk is 87.560%, 2.560 percentage points above warning, under SG-0240; SRE also recorded that emitted disk status remains `ok`, an interpretation gap.
- Activation remains privacy-safe at 1/6 complete. The sample demo details and action-receipt defect is already SG-0241.
- Resolver is ready through the read-only local ledger fallback, pending=0, auto-approval=false. Active-tag count was zero before SG-0246 creation.
- The newest Learnings sharpen two product hypotheses: explicit access paths/shared-write semantics and an observable sandboxed operations shell. They are strategy input only, not implementation authority.
- No external research or browser run was needed. Recent primary-source-backed Learnings and deployed local evidence were sufficient.

## Perspective Review

- First-time customer: sample-to-live activation remains the clearest first-value gap, but SG-0241 owns the broken sample detail path and false receipts. The new access-path contract should be tested as copy before implementation.
- Daily user: one production Ask Yoda attempt now proves real impact from the known runtime outage. SG-0238 must restore pre-send truth and managed runtime availability before recurring-value telemetry is meaningful.
- Power user and agent builder: a shared memory product needs explicit client access path, active identity, authority, provenance, conflict behavior, retention, indexing ownership, and recovery semantics. A read-only contract test is the smallest next step.
- Operator: restore evidence is critically stale, disk exceeds warning, .102 is unavailable, and weekly/readiness blocker evidence is sourced from a stale local mirror. Existing owners cover the first three; SG-0246 covers the last.
- Product Owner: the product has eleven planned rows after this promotion. The priority is truthful evidence and owner routing, not another broad feature surface.

## Discovery Exercises

- New-user walkthrough: activation API remains privacy-safe but only 1/6 complete; SG-0241 blocks a trustworthy sample details and receipt path.
- Failure-mode review: one production Ask Yoda attempt used deterministic retrieval but fell back because Codex runtime was unavailable; SG-0238 owns recovery.
- Evidence-parity audit: compared forced Settings evidence, authoritative raw backlog, and the selected local backlog mirror. This isolated the SG-0246 source-freshness defect without production mutation.
- Capacity review: disk warning and critically stale restore remain under SG-0240 and SG-0234; Persistent Search cumulative failures increased but no distinct bounded repro was established.

## Ranked Opportunities

Scores combine user impact, evidence strength, differentiation, effort, risk, reversibility, and measurability on a 100-point scale.

| Rank | Opportunity | Score | Decision |
| ---: | --- | ---: | --- |
| 1 | Align weekly outcomes with the authoritative backlog | 97 | Promoted as SG-0246 P1 |
| 2 | Complete a trustworthy sample-to-live first-value session | 92 | Deduped to ST-0001 and SG-0241 |
| 3 | Restore Ask Yoda, then measure recurring value | 91 | Deduped to SG-0238; diary remains approval-gated |
| 4 | Publish an access-path and shared-write contract | 87 | Strategy candidate under ST-0009/ST-0010 |
| 5 | Prototype an observable memory operations shell | 82 | Strategy candidate; no TODO |

## Opportunity Proposals

### 1. Align Weekly Outcomes With The Authoritative Backlog

- Target user: Product Owner, operator, and recurring workers.
- Job to be done: trust that weekly outcomes, blocker counts, and readiness reflect the canonical current backlog.
- Evidence: supported refresh returns 2/32/2 from an October 17 local mirror while authoritative raw state returns 10/33/2 before promotion and contains eight omitted planned rows.
- Capability or experiment: select authoritative backlog evidence or require a revision/currentness match before a local fallback can be labeled current.
- Expected value: prevents false prioritization, hidden ownership, and misleading readiness.
- Success metric: refreshed aggregate counts and blocker identities match authoritative raw state; unavailable/divergent evidence fails explicitly stale or source-mismatched.
- Smallest validation: focused fresh/stale/unavailable/divergent API fixtures plus one deployed read-only parity check.
- Risks/privacy: backend latency and transient availability. Keep bounded, privacy-safe aggregate output and only use fallback when attested current.
- Dedupe: SG-0244 is browser localStorage revalidation; SG-0246 is server-side operational evidence-source selection. Promoted as [notes/memory-starmap-todo-list/keep-weekly-outcomes-aligned-with-the-authoritative-todo-backlog](http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-todo-list%2Fkeep-weekly-outcomes-aligned-with-the-authoritative-todo-backlog).

### 2. Complete A Trustworthy Sample-To-Live First-Value Session

- Target user: first-time customer.
- Job to be done: inspect one synthetic memory, relationship, provenance trail, and truthful activation receipt before connecting private data.
- Evidence: activation remains 1/6; deployed dogfood found sample View falling through to live lookup and false completion receipts.
- Capability or experiment: after SG-0241, run one sample-only moderated session and measure time, comprehension, and privacy-boundary accuracy.
- Expected value: converts healthy setup into a credible first successful outcome.
- Success metric: 5/6 steps in under ten minutes, no live/private read, and correct sample-versus-live explanation.
- Smallest validation: one synthetic desktop/mobile walkthrough after SG-0241 acceptance.
- Risks/privacy: demo/live identity mixing and accidental private prompts. Keep the session synthetic and client-local.
- Dedupe: ST-0001 is the strategy parent and SG-0241 owns the current product defect.

### 3. Restore Ask Yoda, Then Measure Recurring Value

- Target user: daily user and Product Owner.
- Job to be done: receive evidence-backed answers reliably enough to judge usefulness, latency, and habit.
- Evidence: one production attempt now fell back on unavailable Codex runtime; 29/30 sampled rows are test/synthetic.
- Capability or experiment: complete SG-0238, then seek explicit consent for the bounded ten-workflow aggregate-only diary already proposed.
- Expected value: separates runtime reliability from answer value and produces real retention evidence.
- Success metric: managed runtime ready after restart, one synthetic non-fallback acceptance, then at least 8/10 workflow completion and 7/10 usefulness under approved privacy/cost gates.
- Smallest validation: SG-0238 acceptance first; do not start production telemetry in this run.
- Risks/privacy: prompt content, private graph context, retention, and model cost. Require consent, aggregate-only collection, isolation, and cost cap.
- Dedupe: runtime is SG-0238; the diary is an existing approval-packet candidate.

### 4. Publish An Access-Path And Shared-Write Contract

- Target user: prospective multi-agent customer and operator.
- Job to be done: choose CLI, MCP, or hosted access and understand identity, permission, provenance, conflicts, retention, indexing, residency, and rebuildability before granting access.
- Evidence: [learnings/gbrain-x-intelligence-20261030-agent-memory-onboarding-needs-explicit-access-paths-and-shared-write-semantics](http://127.0.0.1:8788/?slug=learnings%2Fgbrain-x-intelligence-20261030-agent-memory-onboarding-needs-explicit-access-paths-and-shared-write-semantics) plus existing pricing/identity Learnings.
- Capability or experiment: a static read-only contract card and tabletop comprehension test for one worker/client pair.
- Expected value: lowers setup ambiguity and makes local/shared-memory trust legible.
- Success metric: 8/10 reviewers correctly identify access path, active identity, write authority, conflict behavior, retention, and recovery source.
- Smallest validation: copy prototype; no account connection or production data.
- Risks/privacy: overpromising unsupported paths or regions. Label current, planned, and unknown boundaries explicitly.
- Dedupe: ST-0009/ST-0010 and prior personal-memory contract candidates; not an implementation-ready SG TODO.

### 5. Prototype An Observable Memory Operations Shell

- Target user: power user, agent builder, and operator.
- Job to be done: resume recurring work with memory context, run state, sandbox limits, tools, and pending human decisions visible in one place.
- Evidence: [learnings/gbrain-x-intelligence-20261028-agent-memory-needs-a-native-operations-shell-with-observable-sandboxed-compute](http://127.0.0.1:8788/?slug=learnings%2Fgbrain-x-intelligence-20261028-agent-memory-needs-a-native-operations-shell-with-observable-sandboxed-compute) and the current fragmented evidence surfaces.
- Capability or experiment: a read-only prototype for one recurring worker, with tool-schema token, resumption time, latency, and routing-miss instrumentation.
- Expected value: makes Memory Stargraph an operational habit rather than another graph or chat tab.
- Success metric: faster task resumption, correct sandbox/authority comprehension, and no increase in routing failures or exposed private data.
- Smallest validation: static/read-only prototype using existing Run and diagnostics evidence.
- Risks/privacy: accidental execution authority, sensitive host metadata, and scope creep into a desktop platform. Keep the first experiment non-executing and redacted.
- Dedupe: current Learning and ST-0005 overlap; no current evidence justifies product implementation.

## Duplicates Suppressed And Ideas Deferred

- SG-0234 owns critically stale restore rehearsal; SG-0240 owns disk growth/headroom and no cleanup is authorized.
- SG-0238 owns managed Codex runtime recovery and pre-send unavailable-state truth. The production fallback is new impact evidence, not a new defect.
- SG-0241 owns sample details and activation receipts; ST-0001 remains the strategy parent.
- SG-0243 owns .102 health; no remote service mutation is authorized.
- SG-0244 owns browser-side entity cache revalidation; it does not cover the server-side weekly evidence source selected by SG-0246.
- SG-0245 owns View markdown entity-link activation.
- Persistent Search cumulative timeout/fallback growth and disk-status interpretation need trend or owner review, but this run did not establish a separate reproducible product gap.
- SG-0246 retained `capture-recovery` after successful allocation. This recurs against completed SG-0227 acceptance and requires Product Owner reconciliation, not tag mutation or a duplicate TODO from Strategy.
- Reranker configuration remains explicitly approval-gated. Configured-target source mismatch remains evidence drift, not deployment authority.
- No new Learning was created because the access-path and operations-shell insights already exist as durable Learnings.

## Productization Insight

Memory Stargraph's differentiation depends on inspectable truth, not just more agent features. A shared-memory product cannot become trustworthy if its own readiness surface silently reads an older source than its canonical backlog. The same product principle applies to onboarding, runtime availability, identity, permissions, and execution: every operational claim needs a visible source and freshness contract.

## Required Opportunities

- Make it easier for a new customer: complete SG-0241, then test the sample-to-live first-value session and the static access-path/shared-write contract.
- Maximize recurring user value: complete SG-0238, then request explicit approval for the aggregate-only Ask Yoda workflow diary; do not measure retention through fallback behavior.

## Missing Evidence And Boundaries

- No direct first-time-customer completion session exists.
- Only one sampled production Ask Yoda attempt exists, and it failed over to deterministic fallback.
- No consent, retention, cost cap, or production telemetry authorization exists for the recurring-value diary.
- No comprehension evidence exists for access-path/shared-write or operations-shell hypotheses.
- Detailed resolver events remain unavailable although aggregate health is ready.
- No distinct bounded reproduction yet separates Persistent Search cumulative failures from test/restart churn.
- SG-0246's stale `capture-recovery` tag needs Product Owner reconciliation against SG-0227; Strategy made no tag mutation.
- No product code, deployment, service restart, resolver approval, reranker configuration, browser mutation, backup/restore action, production prompt, or production/user-data mutation occurred.

## Product Owner Delivery

- Destination task: `019faa62-6058-7643-b9cc-a2627083af07`.
- Status: `acknowledged_by_product_owner` at `2026-11-01T04:10:50-08:00`.
- Readback: accepted `completed_one_new_todo_strategy_candidates` and the single new P1 SG-0246 exactly once. The authoritative backlog mismatch and stale lifecycle tag are accepted as reported. No deployment, reranker, resolver, telemetry, or production mutation is authorized.
- Compact payload: Product Strategy 2026-11-01 completed_one_new_todo_strategy_candidates on clean/current `b90078e2`, V1.0.231 / GBrain V0.46.28.0. Promoted SG-0246 P1 because forced Settings refresh reads a 2026-10-17 local backlog mirror and reports 2 planned/32 completed/2 failed while authoritative raw state was 10/33/2 before promotion and includes SG-0237 through SG-0245; SG-0246 raises planned to 11. Parent/child/link readback passed, but the planned child retained stale `capture-recovery`, requiring SG-0227 lifecycle reconciliation without manual tag mutation. One production Ask Yoda attempt fell back after 7.551s because Codex runtime was unavailable; deduped to SG-0238. Activation remains 1/6 under SG-0241; restore Critical under SG-0234; disk 87.560% under SG-0240; retrieval remains 10/10, 10/10, 9/9; active tags were clear before allocation. Retain four candidates only: first-value session, Ask Yoda diary after SG-0238, access-path/shared-write contract, and observable operations-shell prototype. Requested follow-up: acknowledge SG-0246, reconcile its stale lifecycle tag, route once to Developer when prioritized, and do not authorize deployment, reranker change, production telemetry, or other product mutation from this report.

## Artifacts

- Run: [runs/memory-stargraph-divergent-product-discovery-20261101t040222-0800-85](http://127.0.0.1:8788/?slug=runs%2Fmemory-stargraph-divergent-product-discovery-20261101t040222-0800-85)
- Report: [reports/memory-stargraph-divergent-product-discovery-20261101t040222-0800-85](http://127.0.0.1:8788/?slug=reports%2Fmemory-stargraph-divergent-product-discovery-20261101t040222-0800-85)
- Promoted TODO: [notes/memory-starmap-todo-list/keep-weekly-outcomes-aligned-with-the-authoritative-todo-backlog](http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-todo-list%2Fkeep-weekly-outcomes-aligned-with-the-authoritative-todo-backlog)
- Learning: none; current insights were deduplicated to existing durable Learnings.
