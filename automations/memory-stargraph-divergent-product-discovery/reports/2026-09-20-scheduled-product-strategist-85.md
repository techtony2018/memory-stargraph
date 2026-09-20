---
type: report
title: Memory Stargraph Divergent Product Discovery 2026-09-20
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
product: products/memory-stargraph
run: runs/memory-stargraph-divergent-product-discovery-20260920t040057-0700-85
status: completed_no_new_todo_strategy_candidate_with_consistency_regression
automation_id: memory-stargraph-divergent-product-discovery
invocation_id: memory-stargraph-divergent-product-discovery-20260920t040057-0700-85
started_at: '2026-09-20T04:00:57-07:00'
completed_at: '2026-09-20T04:13:24-07:00'
source_commit: 0472003cbe887b2e4ea4af869f1eaa9ea73b5b89
ui_version: V1.0.224
gbrain_version: V0.46.28.0
product_owner_destination_task_id: 019faa62-6058-7643-b9cc-a2627083af07
product_owner_notification_status: acknowledged_by_product_owner
product_owner_notification_pending: false
tags:
  - completed
  - discovery
  - memory-stargraph
  - product-strategy
---

# Memory Stargraph Divergent Product Discovery 2026-09-20

## Outcome

This bounded review completed with no new SG TODO, no strategy-parent mutation, and no product, deployment, resolver, configuration, browser, or production-user-data mutation. It found one material consistency regression for Product Owner reconciliation: SG-0234 exists as a planned child and has the canonical `has_todo` relationship, but the canonical root backlog has no SG-0234 row, exact `SG-0234` search returns no slug, and the child still carries both `planned` and `capture-recovery` tags. The September 17 UX report says the helper created and verified SG-0234, so the current state is evidence of later convergence or stale-write loss, not authorization to create a duplicate TODO.

Completed SG-0227 already owns atomic add-sg-todo allocation and explicitly forbids planned orphans. Completed SG-0233 owns durable entity save under unavailable embedding capacity. Product Strategy therefore records a regression/ownership candidate and asks Product Owner to reconcile the existing SG-0234 transaction and choose the existing owner or a bounded follow-up. Strategy did not invoke add-sg-todo while the canonical allocator state is inconsistent.

## Source-Sync Preflight

- `workspace_path`: `/Users/toddy/memory-stargraph`
- `branch`: `main`
- `local_head`: `0472003cbe887b2e4ea4af869f1eaa9ea73b5b89`
- `upstream_ref`: `origin/main`
- `upstream_head`: `0472003cbe887b2e4ea4af869f1eaa9ea73b5b89`
- `dirty_state`: `clean_tracked`; no untracked paths
- `divergent_state`: ahead 0, behind 0
- `deployed_service_version`: V1.0.224; GBrain V0.46.28.0
- `required_script_existence`: prompt and `scripts/automation/gbrain_worker_api.py` present
- `selected_source_path`: `/Users/toddy/memory-stargraph`
- `selected_source_surface`: clean current checkout plus dashboard-managed TLS API at `https://127.0.0.1:8788`
- `action_taken`: `use_workspace`; fetch succeeded; no sync or overwrite required

## Evidence Inspected

- Product, project, persistent Goal, canonical SG backlog, strategy collection, current health, setup diagnostics, activation funnel, weekly digest, customer readiness, resolver health, Ask Yoda configuration/logs, active tags, backup evidence, exact and natural-language search, recent SRE recovery evidence, recent UX reports, recent Developer SG-0233 evidence, source history, setup/deployment documentation, Product Owner task state, and current worker-task coordination state.
- Health is loaded at V1.0.224. Persistent Search is active and ready, but its operating contract remains missing and write-safety readiness is false. Metrics show 12 process starts, 11 restarts, 584 tool calls, 573 successes, 11 errors, 11 timeouts, and 4 CLI fallbacks.
- Customer readiness is degraded at 6/9 ready: reranker Critical, weekly outcomes degraded, SRE numeric evidence stale, configured-target attestation ready/current, resolver ready with pending=0, and no automatic approval.
- Weekly verified memory outcomes are 7/9. Retrieval evidence remains 10/10 answer success, 10/10 recall, and 9/9 expected-source coverage. Backup fallback is current at 2026-09-20T10:00:02Z.
- Setup diagnostics have no failing checks. Activation is live-ready and privacy-safe but remains 1/6, next step `sample_brain_opened`.
- Ask Yoda is configured for `gbrain_think` with `openai:gpt-5.5`; the sampled recent log entries are synthetic/test fixtures only. No production-use value evidence was observed.
- Active-tag query returned zero pages. Resolver pending count is zero and auto-approval is false.
- The September 17 V1.0.223 SRE recovery report cleared the cross-worker write incident with HTTP 200, durable semantic readback, `mode=durable_no_embed`, and truthful `indexing_status=pending`. Current source advanced to V1.0.224.
- Recent UX on September 17 completed with one new finding, SG-0234. September 18 and 19 UX runs deferred under quiet-time coordination. The canonical Daily Learning task remains active/waitingOnApproval; Product Owner is idle and had reserved the serial Learning -> Capture -> X -> UX recovery order.

## Bounded Consistency Audit

The current canonical root lists three planned rows: SG-0229, SG-0230, and SG-0231. The planned-tag surface lists those three plus SG-0234. SG-0234 raw readback says `status: planned` and `todo_id: SG-0234`; graph readback shows the root `has_todo` relationship; tag readback includes `planned` and residual `capture-recovery`; the root contains no SG-0234 row; exact-ID search returns no slug; and the natural-language title query finds the child through partial search.

This is a real work-discovery and auditability gap. It is not evidence that the SG-0234 UX defect is invalid, and it is not permission to allocate SG-0235. The smallest safe next step is a Product Owner-owned read-only reconciliation of the existing parent/child/tag/link/index transaction, followed by one authorized canonical repair path and readback if needed.

## Perspective Review

- First-time customer: setup checks are green and the sample path is privacy-safe, but progress remains 1/6. The product explains readiness more clearly than it proves first value.
- Daily user: durable saves can now succeed with indexing pending, but the edit flow closes and refreshes without presenting the returned `indexing_status`. A user can know the content was saved only by later inspection and may confuse delayed search with data loss.
- Power user/agent builder: exact-ID search works for the three canonical root rows but misses the orphaned SG-0234 child. Child, parent, relationship, tag, and index surfaces need a convergent transaction receipt.
- Operator: backup is current, configured-target evidence is current, active tags are clear, and resolver is idle. SRE evidence remains stale and the serial recovery chain is blocked on an active approval state.
- Product Owner: four planned child tasks exist in practice, while the canonical root and weekly digest report only three. Backlog counts cannot be treated as authoritative until SG-0234 is reconciled.

## Ranked Opportunities

| Rank | Opportunity | Score | Decision |
| --- | --- | ---: | --- |
| 1 | Convergent canonical backlog transaction receipt and reconciliation | 96 | Strategy candidate / Product Owner incident input; no duplicate TODO |
| 2 | Guided first-value activation beyond 1/6 | 88 | Existing strategy candidate |
| 3 | Customer-visible saved-versus-searchable receipt | 86 | Strategy candidate, deduped to SG-0233 and prior Learnings |
| 4 | Privacy-safe production Ask Yoda value telemetry | 82 | Existing strategy candidate |
| 5 | Fresh, resumable serial recovery evidence | 80 | Productization/operations candidate |

## Opportunity Proposals

### 1. Convergent canonical backlog transaction receipt and reconciliation - 96

- Target user: Product Owner, Developer, automation operators, and agents consuming the SG backlog.
- Job to be done: know that a newly accepted TODO is represented consistently in the parent table, child frontmatter/tags, graph relation, and exact-ID search.
- Evidence: SG-0234 exists and is linked/planned, but the root row and exact-ID search entry are absent and `capture-recovery` remains. SG-0227 says `ok: true` requires all four durable readbacks.
- Capability/experiment: add a versioned transaction/convergence receipt or reconciliation check that detects stale parent overwrite after initial helper success.
- Expected value: prevents invisible work, incorrect backlog counts, duplicate allocation, and false completion claims.
- Success metric: one bounded synthetic allocation remains present and matching across parent, child, tags, graph, and exact-ID search after all authorized compaction/persistence paths complete.
- Smallest validation: Product Owner first reconciles SG-0234 read-only against its September 17 creation evidence and identifies the write that removed or failed to retain the parent row.
- Risk/privacy: use synthetic text only; no automatic deletion, ID reassignment, or unrelated backlog rewrite.
- Dedupe: SG-0227 owns atomic helper allocation and SG-0233 owns durable writes. This is preserved as regression evidence, not a duplicate TODO from Strategy.

### 2. Guided first-value activation beyond 1/6 - 88

- Target user: first-time customer.
- Job to be done: complete one safe sample-to-live workflow and understand why it matters.
- Evidence: setup is healthy and activation is live-ready, but progress has remained 1/6 across repeated Strategy runs.
- Capability/experiment: a guided sample-only sequence through sample node, provenance, synthetic Ask Yoda, diagnostics, and first live readiness confirmation.
- Expected value: converts readiness into an observable first-value moment and lowers support burden.
- Success metric: a new browser session completes at least 5/6 steps in under ten minutes with no private content persisted.
- Smallest validation: one fresh UX run after the current serial recovery chain terminalizes.
- Risk/privacy: sample-only questions and client booleans; no production node text or prompts in telemetry.
- Dedupe: ST-0001 and SG-0164 created the funnel; this candidate is the unproven guided-completion slice.

### 3. Customer-visible saved-versus-searchable receipt - 86

- Target user: daily editor and agent builder.
- Job to be done: know whether a write is durably saved, searchable now, or waiting for indexing.
- Evidence: SG-0233 now returns `persisted`, `mode`, and `indexing_status`; V1.0.223 SRE verified pending indexing. The edit UI only closes and refreshes after HTTP success and does not use `indexing_status`.
- Capability/experiment: show a compact save receipt with durable/readback/indexing state and a non-destructive recheck path.
- Expected value: reduces false data-loss reports and makes degraded indexing understandable.
- Success metric: synthetic pending-index save displays `Saved; search indexing pending`, while ready saves remain low-friction and no raw content enters telemetry.
- Smallest validation: static prototype plus one synthetic API fixture; no production write required.
- Risk/privacy: do not expose backend paths, credentials, content, or imply indexing completion before proof.
- Dedupe: SG-0233 supplies the response contract; prior receipt/index-scope Learnings establish the principle. Strategy does not create another TODO yet.

### 4. Privacy-safe production Ask Yoda value telemetry - 82

- Target user: daily user and Product Owner.
- Job to be done: distinguish test reliability from recurring user value.
- Evidence: recent logs are synthetic/test only despite a configured model and five ready sessions.
- Capability/experiment: aggregate production request count, success/fallback class, latency band, and explicit helpful/not-helpful feedback without storing question or answer text.
- Expected value: supports retention, packaging, quality, and cost decisions.
- Success metric: ten consented production workflows produce aggregate outcomes with zero raw prompt/content leakage.
- Smallest validation: approve the event schema and run it only against synthetic fixtures before any production collection.
- Risk/privacy: opt-in, aggregate-only, bounded retention, no slugs or private text by default.
- Dedupe: retained from earlier Strategy reports; no new evidence justifies promotion today.

### 5. Fresh, resumable serial recovery evidence - 80

- Target user: operator and Product Owner.
- Job to be done: recover scheduled lanes after a persistence incident without stale active tasks blocking days of evidence.
- Evidence: SRE cleared the write incident on September 17, but Daily Learning remains active/waitingOnApproval on September 20; later UX and SRE runs correctly deferred, and readiness now marks SRE evidence stale.
- Capability/experiment: a human-controlled recovery checklist that names current owner, approval needed, last verified persistence receipt, and next serial lane.
- Expected value: lowers coordination time and keeps readiness evidence current without weakening quiet-time safety.
- Success metric: after an incident-clear receipt, each lane terminalizes in order with no overlapping mutation and freshness recovers within one scheduled cycle.
- Smallest validation: Product Owner resolves or terminalizes the existing Learning approval state, then resumes the already-defined serial chain.
- Risk/privacy: preserve explicit approval and quiescence; never auto-interrupt, auto-approve, or replay historical work.
- Dedupe: this is Product Owner/operations input, not an implementation-ready SG TODO from Strategy.

## Ideas Rejected Or Deferred

- Automatic reranker configuration: rejected for this role. The Critical post-sunset state is real, but completed SG-0222 already exposes the approval-gated command and verification path.
- New SG TODO for SG-0234 consistency: deferred. SG-0227 and SG-0233 already own the adjacent contracts, the allocator state is inconsistent, and Product Owner reconciliation should identify whether this is reopening, repair, or a new bounded regression.
- New search-health TODO: rejected. Exact search works for canonical SG-0229/0230/0231; SG-0234 absence is tied to the missing canonical parent row and incomplete convergence evidence.
- New Learning: not created. The saved-versus-searchable insight is already covered by `learnings/gbrain-x-intelligence-20260731-reliable-memory-needs-visible-write-and-enrichment-receipts`, `learnings/gbrain-x-intelligence-20260809-memory-needs-explicit-source-index-scope-and-side-effect-contracts`, and the September 13 Strategy Learning about degraded persistence evidence.
- External research: not needed. Current local evidence was sufficient and the bounded run avoided unnecessary external collection.

## Required Opportunities

- Make it easier for a new customer: guided first-value activation beyond 1/6.
- Maximize recurring user value: customer-visible saved-versus-searchable receipts plus privacy-safe production Ask Yoda outcome telemetry.

## TODO Decision

No SG TODO was created, updated, dispatched, or promoted. No strategy row was mutated. SG-0229, SG-0230, SG-0231, and the existing SG-0234 child remain the current planned work set pending canonical reconciliation. No add-sg-todo skill was invoked because the review did not authorize a duplicate allocation and the canonical parent/child state is inconsistent.

## Missing Evidence And Approvals

- Approval is still required for any reranker configuration change.
- Product Owner needs to resolve or terminalize the Daily Learning waitingOnApproval state before resuming Learning -> Capture -> X -> UX.
- Product Owner needs to reconcile SG-0234 across parent, child, tags, graph, and exact-ID search, then choose the existing ownership path.
- No production Ask Yoda usage evidence exists in the sampled logs.
- No fresh post-recovery UX journey has run after the September 18/19 quiet-time deferrals.

## Artifacts

- Run: `runs/memory-stargraph-divergent-product-discovery-20260920t040057-0700-85`
- Report: `reports/memory-stargraph-divergent-product-discovery-20260920t040057-0700-85`
- Learning: none; deduplicated to existing receipt/index-scope and approval-boundary Learnings.

## Product Owner Delivery

Product Owner acknowledged and read back this invocation as `completed_no_new_todo_strategy_candidate_with_consistency_regression`. The acknowledgement preserves the no-new-TODO decision, assigns SG-0234 reconciliation once to canonical allocator/SG-0227 ownership without duplicate allocation or manual Product Strategy repair, prohibits Developer dispatch and product/config/resolver/production mutation from Strategy, and retains Daily Learning as the serial recovery blocker.

Compact payload: Product Strategy 2026-09-20 completed on .85 V1.0.224 / GBrain V0.46.28.0 / commit `0472003cbe887b2e4ea4af869f1eaa9ea73b5b89`; source-sync current and clean; no code/deploy/config/resolver/browser/production mutation and no SG TODO promotion; customer readiness 6/9 and weekly outcomes 7/9; backup and configured-target attestation current; reranker remains Critical and approval-gated; SRE evidence stale; activation remains 1/6; Ask Yoda sample remains synthetic-only; SG-0233 durable write recovery is verified; material new evidence is SG-0234 child planned/link present but canonical parent row absent, exact-ID search absent, and residual capture-recovery tag present, contradicting completed SG-0227 convergence guarantees; Daily Learning remains active/waitingOnApproval and later UX/SRE deferred under the serial recovery hold; requested Product Owner follow-up is acknowledge this no-new-TODO result, reconcile the existing SG-0234 transaction and ownership, then resolve Learning approval and resume Learning -> Capture -> X -> UX serially. No Developer dispatch or repair mutation is authorized by this Strategy run.
