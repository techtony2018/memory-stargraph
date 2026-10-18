---
type: report
title: Memory Stargraph Divergent Product Discovery 2026-10-18
run: runs/memory-stargraph-divergent-product-discovery-20261018t040148-0700-85
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
status: completed_no_new_todo_strategy_candidates
product: products/memory-stargraph
started_at: '2026-10-18T04:01:48-07:00'
completed_at: '2026-10-18T04:06:00-07:00'
automation_id: memory-stargraph-divergent-product-discovery
invocation_id: memory-stargraph-divergent-product-discovery-20261018t040148-0700-85
source_commit: e6287731ee381b2e87c72bd3599fd162afd006a0
ui_version: V1.0.231
gbrain_version: V0.46.28.0
created_todo_ids: []
updated_todo_ids: []
learning_slug: null
product_owner_destination_task_id: 019faa62-6058-7643-b9cc-a2627083af07
product_owner_notification_status: acknowledged_by_product_owner
product_owner_notification_pending: false
product_owner_acknowledged_at: '2026-10-18T04:08:08-07:00'
tags:
  - completed
  - discovery
  - memory-stargraph
  - product-strategy
---

# Memory Stargraph Divergent Product Discovery 2026-10-18

## Decision

The bounded .85 Product Strategy review completed with no new SG TODO, no strategy-parent mutation, and no new Learning. Current product defects already have explicit canonical owners: SG-0234 for restore-rehearsal recency, SG-0235 for Escape dismissal of the node actions menu, and failed SG-0236 for Capture Link scope completeness plus configured-target deployment recovery.

The meaningful product shift is that Ask Yoda now has a ready local Codex backend and several successful synthetic answers. This converts the old provider/runtime failure into a proof-of-value question: can a consented daily user obtain recurring value at acceptable latency and cost without exposing private prompts? Existing logs remain synthetic/test only, so this is strategy evidence, not permission to instrument production or dispatch Developer work.

## Source-Sync Preflight

- Workspace: `/Users/toddy/memory-stargraph`.
- Branch and source: `main == origin/main == e6287731ee381b2e87c72bd3599fd162afd006a0`; ahead 0, behind 0.
- Worktree before artifact creation: clean, with no untracked paths.
- Action: fetched origin with prune and used the current workspace; no fast-forward, overwrite, or deployment was required.
- Required role prompt and `scripts/automation/gbrain_worker_api.py` were present.
- Preserved local deployment artifacts, including `config/tailscale-certs/`.
- Service: dashboard-managed TLS at `https://127.0.0.1:8788`, healthy and loaded at V1.0.231 / GBrain V0.46.28.0.

## Evidence Reviewed

- Canonical product, project, [goals/memory-stargraph-continuous-learning-local-knowledge-os](http://127.0.0.1:8788/?slug=goals%2Fmemory-stargraph-continuous-learning-local-knowledge-os), canonical SG backlog, [notes/memory-stargraph-product-strategy-todo-list](http://127.0.0.1:8788/?slug=notes%2Fmemory-stargraph-product-strategy-todo-list), recent Product Strategy reports, recent SRE/UX/Developer Runs and reports, current Learnings, source history, health, readiness, resolver, activation, Ask Yoda, backup, active-tag, and search surfaces.
- Backlog: planned=2, implementing=0, failed=2, completed=32. The current planned work is SG-0234 and SG-0235. SG-0236 is failed after source implementation and .85 reload succeeded but the required .102 deployment and disabled-runner verification could not be completed because SSH and HTTPS were unreachable.
- Exact search now resolves SG-0234, SG-0235, and SG-0236 to their canonical children. The September orphan/index inconsistency is no longer current.
- Health: reranker remains Critical and approval-gated 44 days after the known sunset. No configuration change is authorized. Persistent Search is ready/idle but its MCP operating contract remains missing; cumulative metrics include 1,994 calls, 71 errors, 51 timeouts, and 42 CLI fallbacks.
- Customer readiness: 6/9 ready, one degraded, one Critical, and one source mismatch. Weekly outcomes are degraded, reranker is Critical, and configured-target attestation does not match current source/UI. The last condition is expected evidence drift until an authorized deployment verification, not a new product defect.
- SRE: retrieval remains 10/10 answers, 10/10 recall, and 9/9 expected sources. Backup is current. Restore-rehearsal evidence is about 52.8 days old and beyond the critical threshold; the October 15 SG-0234 weekly attempt correctly aborted before mutation because host load was above the capacity gate. The October 18 CPU sample was critical without correlated service impact.
- Activation: live-ready and privacy-safe, still 1/6 complete with `sample_brain_opened` next.
- Ask Yoda: backend `codex`, model `gpt-5.6-sol`, five ready sessions, structured read-only execution, and successful synthetic responses observed around 13 to 27 seconds. The sampled recent logs are all test/synthetic; no production-use or satisfaction evidence was observed.
- Resolver: ready through the local read-only ledger fallback, pending=0, auto-approval=false.
- UX: the October 17 bounded journey passed Search, View, relationships, backlinks, history, Follow-ups, readiness, Ask Yoda diagnostics, graph controls, and 390x844 mobile coverage. SG-0236 stayed failed and untouched; no new UX TODO was justified.
- Active tags were clear. No browser run or external research was needed because current local evidence was sufficient.

## Perspective Review

- First-time customer: setup is healthy, but activation remains 1/6 and readiness requires expert interpretation. The smallest adoption proof is one sample-only guided workflow, not more setup diagnostics.
- Daily user: local Codex can answer synthetic prompts, but the product has no consented recurring-use proof, satisfaction signal, or latency/cost expectation for real work.
- Power user and agent builder: local read-only Codex execution is a differentiated capability. It needs a clear boundary among local processing, retained telemetry, model cost, and evidence citations before it can be packaged as a trustworthy workflow.
- Operator: search and backup are available, but restore-rehearsal recency is Critical, the reranker is approval-gated, and configured-target attestation is stale. Each already has an owner or approval lane.
- Product Owner: the backlog contains two planned and two failed rows. Product Strategy should clarify experiments and approvals, not create duplicates while SG-0234 through SG-0236 remain unresolved.

## Ranked Opportunities

| Rank | Opportunity | Score | Decision |
| ---: | --- | ---: | --- |
| 1 | Prove recurring value for local Codex Ask Yoda | 92 | Strategy candidate; no TODO |
| 2 | Complete the capacity-safe recovery trust loop | 90 | Deduplicated to SG-0234 |
| 3 | Guided first-value activation beyond 1/6 | 88 | Existing ST-0001 candidate |
| 4 | Make bounded evidence claims visibly scoped | 86 | Deduplicated to SG-0236 and existing receipt Learnings |
| 5 | Explain the managed/local adoption and attestation boundary | 81 | Existing ST-0010 candidate |

## Opportunity Proposals

### 1. Prove Recurring Value For Local Codex Ask Yoda

- Target user: daily user and Product Owner.
- Job to be done: use private local knowledge to answer a real recurring question, with source evidence, predictable wait time, and no hidden prompt retention.
- Evidence: Codex-backed synthetic answers now succeed; recent production-use evidence remains absent.
- Capability or experiment: a consented, isolated ten-workflow diary using aggregate-only outcomes: completed/fallback, latency band, citation usefulness, explicit helpfulness, and bounded cost. Store no prompt, answer, private slug, or user identifier by default.
- Expected value: validates whether the fixed backend creates a habit and informs packaging, latency targets, and support investment.
- Success gate: at least 8/10 workflows complete, at least 7/10 are rated useful, source evidence is accepted in at least 8/10, median wait is at most 20 seconds, and the approved cost cap is not exceeded.
- Failure gate: any unconsented content retention, two privacy-boundary violations, cost-cap breach, or fewer than 6/10 completed/useful workflows stops the experiment.
- Smallest validation: Product Owner approves the event schema, consent text, namespace, retention, and cost cap; then run one synthetic rehearsal before any production collection.
- Risk and dedupe: this refines the existing privacy-safe Ask Yoda telemetry candidate and completed backend work. It is not a new implementation gap until the consented experiment is approved.

### 2. Complete The Capacity-Safe Recovery Trust Loop

- Target user: operator and customer relying on recoverability claims.
- Job to be done: know that a recent backup can actually be restored and cleaned up without endangering the live service.
- Evidence: backup is current, but accepted restore evidence is beyond Critical age; the latest rehearsal aborted safely because load was too high.
- Capability or experiment: retry the already-defined isolated weekly rehearsal only when quiet-time and normalized-load gates pass, preserving checksum and cleanup receipts.
- Expected value: turns backup availability into credible recovery proof.
- Success gate: fresh durable Run/report, checksum match, cleanup verification, no production mutation, and restored readiness recency.
- Failure gate: capacity gate breach, namespace collision, checksum mismatch, cleanup failure, or any need to touch production data.
- Smallest validation: the canonical weekly lane retries SG-0234 during an approved low-load window.
- Risk and dedupe: fully owned by SG-0234. Strategy creates no duplicate or deployment authorization.

### 3. Guided First-Value Activation Beyond 1/6

- Target user: first-time customer.
- Job to be done: reach one useful, privacy-safe answer and understand its provenance in a single session.
- Evidence: all setup checks pass and the product is live-ready, but activation is still 1/6.
- Capability or experiment: a sample-only walkthrough that opens a sample brain, selects a node, inspects provenance, asks one synthetic question, and shows readiness boundaries.
- Expected value: converts a healthy installation into visible customer value and exposes where onboarding stalls.
- Success gate: 5/6 steps in under ten minutes, one evidence-backed answer, zero private content persisted, and the user can state whether the session was sample or live.
- Failure gate: sample/live ambiguity, private content capture, more than two operator interventions, or failure to reach an answer.
- Smallest validation: one fresh first-time-user dogfood session against sample data.
- Risk and dedupe: existing ST-0001 plus completed activation instrumentation; retain as strategy candidate until a user session is approved.

### 4. Make Bounded Evidence Claims Visibly Scoped

- Target user: operator, Product Owner, and agent builder.
- Job to be done: distinguish “no candidate in the inspected window” from “no candidate exists.”
- Evidence: SG-0236 was created because a 500-row cap incorrectly supported a global no-candidate claim. Source implementation is complete, but configured-target deployment verification failed closed.
- Capability or experiment: show inspected count, cap reached, continuation/completeness state, and claim scope in durable receipts.
- Expected value: prevents false certainty across Capture Link and other bounded-list workflows.
- Success gate: capped fixtures cannot emit a global complete/no-candidate claim; exhausted fixtures can; receipts remain privacy-safe.
- Failure gate: any capped path still claims completeness or exposes private coordinates/content.
- Smallest validation: finish the already-authorized SG-0236 configured-target deployment and verification after remote services return.
- Risk and dedupe: SG-0236 already owns the implementation. The broader pattern is covered by existing source/index-scope and receipt Learnings.

### 5. Explain The Managed/Local Adoption And Attestation Boundary

- Target user: new customer, power user, and Product Owner.
- Job to be done: understand which components are local, which require configured targets, what is currently attested, and what remains approval-gated.
- Evidence: local V1.0.231 is healthy; configured-target proof is stale; the newest Learning recommends a hosted and CLI adoption ladder with explicit open-source trust signals.
- Capability or experiment: a read-only adoption matrix covering local UI, CLI, optional configured targets, data custody, export, revocation, source/license boundary, and last attested source.
- Expected value: makes degraded readiness understandable and lets customers choose convenience without losing control.
- Success gate: a new user can correctly identify where data resides, which path is verified, how to export/revoke, and why source mismatch is not automatically a local failure.
- Failure gate: private target coordinates are exposed, managed status is overstated, or attestation freshness is hidden.
- Smallest validation: a static Product Owner-reviewed matrix using current evidence; no target mutation.
- Risk and dedupe: existing ST-0010 and the 2026-10-18 adoption Learning. Keep as strategy input only.

## Dedupe And Deferrals

- SG-0234 already owns the Critical restore-rehearsal recency and bounded low-load retry.
- SG-0235 already owns the reproducible keyboard dismissal defect.
- SG-0236 already owns truthful capped-list scope and its failed configured-target deployment recovery.
- Completed Ask Yoda backend work owns runtime/provider recovery. This run only identifies the unproven recurring-value experiment.
- ST-0001 owns sample-to-live activation; ST-0010 owns managed/local packaging. Their `strategy_candidate` state is not implementation authority.
- Automatic reranker configuration is rejected for this role; explicit approval remains required.
- A configured-target source mismatch is expected evidence drift after source advancement and is not a distinct product defect.
- No new Learning was created because scoped-evidence receipts, consented telemetry, and managed/local trust boundaries already exist in durable Learnings.

## Required Opportunities

- Easier for a new customer: validate the guided sample-only first-value workflow and the managed/local attestation explanation.
- Maximize recurring user value: run a consented, privacy-safe local Codex Ask Yoda diary only after Product Owner approval of schema, retention, namespace, and cost cap.

## Boundaries And Approvals

- No product code, deployment, TODO mutation, strategy-parent mutation, resolver approval, reranker configuration, browser mutation, backup/restore action, production prompt, or production/user-data mutation occurred.
- Product Owner approval is required before any production Ask Yoda telemetry or diary experiment.
- Reranker mutation remains explicitly approval-gated.
- SG-0234 needs an approved low-load weekly retry; SG-0236 needs remote service recovery and authorized deployment verification.
- Configured-target details remain private and are not included.

## Product Owner Delivery

- Destination task: `019faa62-6058-7643-b9cc-a2627083af07`.
- Status: `acknowledged_by_product_owner` at `2026-10-18T04:08:08-07:00`.
- Readback: accepted `completed_no_new_todo_strategy_candidates`; preserve all five opportunities as approval-packet inputs only, with no TODO promotion or Developer dispatch. SG-0234, SG-0235, and failed SG-0236 retain their current ownership and status. Any real-user Ask Yoda diary requires explicit consent, isolated scope, retention/privacy boundaries, and a cost cap.
- Compact payload: Product Strategy 2026-10-18 completed on clean/current `e6287731` with healthy V1.0.231 / GBrain V0.46.28.0. No TODO, Learning, code, deployment, configuration, resolver, browser, or production-data mutation. Backlog is planned=2, failed=2, completed=32; SG-0234 owns Critical restore-rehearsal recency, SG-0235 owns Escape dismissal, and failed SG-0236 owns capped-scope truth plus remote deployment recovery. Retrieval remains 10/10 answers, 10/10 recall, 9/9 sources; activation remains 1/6; reranker is Critical/approval-gated; configured-target attestation is source-mismatched; active tags and resolver queue are clear. Ask Yoda now has a ready Codex `gpt-5.6-sol` backend with successful synthetic answers, but sampled logs contain no production-use evidence. Decision: retain recurring-value diary, guided activation, scoped evidence receipts, and managed/local attestation explanation as strategy candidates only; do not dispatch Developer work without explicit experiment approvals.

## Artifacts

- Run: [runs/memory-stargraph-divergent-product-discovery-20261018t040148-0700-85](http://127.0.0.1:8788/?slug=runs%2Fmemory-stargraph-divergent-product-discovery-20261018t040148-0700-85)
- Report: [reports/memory-stargraph-divergent-product-discovery-20261018t040148-0700-85](http://127.0.0.1:8788/?slug=reports%2Fmemory-stargraph-divergent-product-discovery-20261018t040148-0700-85)
- Learning: none; deduplicated to existing durable evidence.
