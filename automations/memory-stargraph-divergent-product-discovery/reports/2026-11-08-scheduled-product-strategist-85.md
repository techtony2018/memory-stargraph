---
type: report
title: Memory Stargraph Divergent Product Discovery 2026-11-08
run: runs/memory-stargraph-divergent-product-discovery-20261108t035843-0800-85
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
status: completed_one_new_todo_strategy_candidates
product: products/memory-stargraph
started_at: '2026-11-08T03:58:43-08:00'
completed_at: '2026-11-08T04:03:39-08:00'
automation_id: memory-stargraph-divergent-product-discovery
invocation_id: memory-stargraph-divergent-product-discovery-20261108t035843-0800-85
source_commit: fa94da57899db3e88679e752728efb5c344ec8af
ui_version: V1.0.231
gbrain_version: V0.46.28.0
created_todo_ids:
  - SG-0247
updated_todo_ids: []
learning_slug: null
product_owner_destination_task_id: 019faa62-6058-7643-b9cc-a2627083af07
product_owner_notification_status: acknowledged_by_product_owner
product_owner_notification_pending: false
product_owner_acknowledged_at: '2026-11-08T04:08:59-08:00'
tags:
  - completed
  - discovery
  - memory-stargraph
  - product-strategy
---

# Memory Stargraph Divergent Product Discovery 2026-11-08

## Decision

This bounded .85 Product Strategy review completed with one new planned P1 TODO, SG-0247, and four retained strategy candidates. No strategy-parent row, Learning, product code, deployment, service, resolver, reranker, browser, backup/restore, production prompt, or production/user data was mutated.

SG-0247 is a current readiness-truth defect, not a duplicate capacity or restore task. The latest canonical SRE report says disk is critical at 92.450% with 18.935 GB free and restore evidence is critically stale at 6,382,447 seconds. A forced customer-readiness refresh simultaneously labels `sre_numeric_evidence` ready/current because backup freshness is current. Existing SG-0240 owns disk attribution and SG-0234 owns the restore rehearsal; completed SG-0209 only covers backup freshness. SG-0247 owns the missing interpretation contract so critical disk or restore evidence cannot still appear ready.

The official allocator verified SG-0247's parent row, child, durable readback, and graph link. The child nevertheless retained `capture-recovery` alongside `planned`, repeating the lifecycle cleanup gap already visible on SG-0246. Strategy did not mutate tags or create another TODO. Product Owner reconciliation is required under completed SG-0227.

## Source-Sync Preflight

- `workspace_path`: `/Users/toddy/memory-stargraph`
- `branch`: `main`
- `local_head`: `fa94da57899db3e88679e752728efb5c344ec8af`
- `upstream_ref`: `origin/main`
- `upstream_head`: `fa94da57899db3e88679e752728efb5c344ec8af`
- `dirty_state`: clean, with no untracked paths before Strategy artifacts
- `divergent_state`: ahead 0, behind 0
- `deployed_service_version`: V1.0.231; GBrain V0.46.28.0
- `required_script_existence`: role prompt and `scripts/automation/gbrain_worker_api.py` present
- `selected_source_path`: `/Users/toddy/memory-stargraph`
- `selected_source_surface`: current checkout plus dashboard-managed TLS API at `https://127.0.0.1:8788`
- `action_taken`: fetched origin with prune and used the current workspace; no source sync, overwrite, or deployment required
- Preserved unrelated deployment artifacts, including `config/tailscale-certs/`.

## Evidence Reviewed

- Canonical product, project, [goals/memory-stargraph-continuous-learning-local-knowledge-os](http://127.0.0.1:8788/?slug=goals%2Fmemory-stargraph-continuous-learning-local-knowledge-os), canonical SG backlog, [notes/memory-stargraph-product-strategy-todo-list](http://127.0.0.1:8788/?slug=notes%2Fmemory-stargraph-product-strategy-todo-list), prior Strategy report, recent SRE/UX/Capture/X Runs and reports, recent Learnings, resolver state, service health, setup and deployment docs, git history, Search, activation, readiness, Ask Yoda configuration/logs, backup, and active-tag surfaces.
- Source and deployment remained unchanged for the week: clean/current `main == origin/main == fa94da57`, dashboard-managed V1.0.231, GBrain V0.46.28.0, healthy and loaded.
- Canonical backlog before promotion was planned=11, implementing=0, failed=2, completed=33. After SG-0247, planned=12. No planned item advanced during the week.
- The November 8 SRE report records disk 92.450%, 7.450 points above warning and 0.450 points beyond critical, with 18,934,697,984 bytes free. This is 4.890 percentage points higher than the November 1 Strategy sample. SG-0240 remains the attribution/headroom owner and grants no deletion authority.
- Restore rehearsal age is 6,382,447 seconds, 3,704,047 seconds beyond critical. The November 1 weekly resilience cycle aborted before restore because normalized load was 1.304 and disk was already 87.264%. SG-0234 remains the execution owner.
- A forced Settings refresh still labels SRE numeric evidence ready/current, while its summary only mentions current backup fallback. Read-only source inspection confirms readiness tests presence and recency of capacity/restore evidence but does not propagate explicit critical capacity or restore values. SG-0247 now owns this distinction.
- SG-0246 remains open: forced weekly evidence still reports planned=2, completed=32, failed=2 from the stale October 17 local mirror while authoritative state was planned=11, completed=33, failed=2 before SG-0247. SG-0246 and SG-0247 both retained stale `capture-recovery` tags after successful allocation.
- Customer readiness remains 5/9 ready: Ask Yoda model degraded, weekly outcomes degraded, reranker Critical and approval-gated, configured-target attestation source-mismatched, and SRE numeric evidence incorrectly ready.
- Ask Yoda is unchanged: backend `codex`, model `gpt-5.6-sol`, runtime unavailable. Of 30 sampled rows, 29 are test/synthetic and one is production. The production attempt at source timestamp `2026-10-28T02:18:05Z` fell back after 7.551 seconds with `Codex runtime is unavailable`. SG-0238 remains the owner.
- Persistent Search is ready/idle. Cumulative metrics grew from 13,428 to 24,431 calls during the week, with errors 307 to 524, timeouts 270 to 474, and CLI fallbacks 171 to 300. The latest UX browser journey added 129 calls with 129 successes and zero errors, timeouts, or fallbacks. The latest SRE report still names a 10.728-second 7/30-day median as the first known application bottleneck. Mixed cumulative automation traffic does not establish a distinct user-facing defect.
- Retrieval remains 10/10 answers, 10/10 recall, and 9/9 expected sources. Backup is current. Resolver is ready through the read-only local ledger fallback, pending=0, auto-approval=false. Active-tag count was zero before SG-0247 creation.
- Activation remains privacy-safe at 1/6 complete. SG-0241 owns the broken sample details and false receipts.
- New Learnings add evidence for cost-adjusted task-specific reader evaluation, perturbation and trajectory audits, normalized performance receipts, scoped/revocable cross-user access, connector provenance/release gates, and shallow multi-agent handoffs with one human review queue.
- No external research or browser run was needed. Current deployed evidence and already-captured primary-source-backed Learnings were sufficient.

## Perspective Review

- First-time customer: setup can be healthy while the sample first-value path is still 1/6 and operational readiness overstates safety. SG-0241 and SG-0247 are prerequisites for a trustworthy activation claim.
- Daily user: Ask Yoda remains unavailable for model-backed recurring use, while deterministic retrieval remains strong. SG-0238 must close before value telemetry or reader-routing experiments use production prompts.
- Power user and agent builder: recent Learnings support shallow coordination, durable handoffs, scoped cross-user grants, revocation, provenance, and one review queue. These need synthetic contract tests before UI or connector implementation.
- Operator: critical disk, critically stale restore proof, stale weekly backlog evidence, and misleading SRE readiness are the immediate constraints. Existing SG-0240, SG-0234, SG-0246, and new SG-0247 provide bounded ownership.
- Product Owner: implementation inventory increased to twelve planned rows with no source movement this week. Prioritize critical operating truth and recovery before expanding feature scope.

## Discovery Exercises

- Readiness parity audit: compared forced Settings evidence against the current canonical SRE report. It reproduced the SG-0247 false-ready state without production mutation.
- Capacity trajectory review: compared November 1 and November 8 disk samples and found a 4.890-point increase crossing the explicit critical threshold.
- Backlog parity audit: confirmed SG-0246 remains reproducible and authoritative planned count advanced from 11 to 12 after SG-0247 while weekly evidence remains at 2.
- Search signal separation: compared cumulative service metrics with the bounded UX journey. Aggregate failures rose, while the current user journey was 129/129 successful, so instrumentation segmentation is warranted before promotion.
- New-user walkthrough evidence: activation remains 1/6 and privacy-safe; no direct customer completion session exists.

## Ranked Opportunities

Scores combine user impact, evidence strength, strategic differentiation, effort, risk, reversibility, and measurability on a 100-point scale.

| Rank | Opportunity | Score | Decision |
| ---: | --- | ---: | --- |
| 1 | Make critical SRE evidence degrade readiness truthfully | 98 | Promoted as SG-0247 P1 |
| 2 | Recover capacity and restore proof before expansion | 96 | Deduped to SG-0240 and SG-0234 |
| 3 | Complete a trustworthy sample-to-live first-value session | 92 | Deduped to ST-0001 and SG-0241 |
| 4 | Validate readers and agent workflows with cost-adjusted perturbation receipts | 89 | Strategy candidate; no TODO |
| 5 | Test scoped grants, durable handoffs, and one human review queue | 87 | Strategy candidate under ST-0005/ST-0009/ST-0010 |

## Opportunity Proposals

### 1. Make Critical SRE Evidence Degrade Readiness Truthfully

- Target user: new customer, Product Owner, and operator.
- Job to be done: know whether the system is operationally ready without reading separate SRE prose.
- Evidence: disk and restore evidence are critical while customer readiness marks SRE numeric evidence ready/current.
- Capability or experiment: parse structured current capacity and restore status and propagate warning/critical/stale states into weekly outcomes and customer readiness.
- Expected value: prevents false-safe onboarding and prioritization decisions while preserving human remediation authority.
- Success metric: readiness status and evidence slugs agree with the selected canonical SRE Run/report for healthy, warning, critical, stale, missing, and malformed fixtures.
- Smallest validation: focused API/Settings fixtures plus one deployed read-only parity check.
- Risks/privacy: ambiguous prose and transient evidence could over-degrade readiness. Prefer structured fields and selected current terminal evidence.
- Dedupe: SG-0209 covers backup freshness; SG-0234 and SG-0240 own remediation evidence. Promoted as [notes/memory-starmap-todo-list/degrade-customer-readiness-for-critical-disk-and-restore-evidence](http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-todo-list%2Fdegrade-customer-readiness-for-critical-disk-and-restore-evidence).

### 2. Recover Capacity And Restore Proof Before Expansion

- Target user: operator and Product Owner.
- Job to be done: regain measurable headroom and current recovery proof without destructive improvisation.
- Evidence: disk is 92.450% and restore proof is more than 73 days old; the latest weekly rehearsal aborted before mutation at the capacity gate.
- Capability or experiment: execute SG-0240's read-only attribution first, approve only a documented reversible cleanup target if justified, then run SG-0234's bounded restore rehearsal when quiet-time and capacity gates pass.
- Expected value: restores safe operating margin and credible recovery claims.
- Success metric: disk below approved headroom threshold with source-backed attribution, current restore checksum/cleanup proof, and no production-data loss.
- Smallest validation: Product Owner prioritizes SG-0240 read-only work; no deletion or restore is authorized by Strategy.
- Risks/privacy: deleting user data, consuming remaining capacity, or restoring into production. Keep attribution read-only and restoration disposable.
- Dedupe: SG-0240 and SG-0234 are canonical owners; no new TODO.

### 3. Complete A Trustworthy Sample-To-Live First-Value Session

- Target user: first-time customer.
- Job to be done: inspect one synthetic memory, relationship, provenance trail, and truthful activation receipt before connecting private data.
- Evidence: activation remains 1/6 and SG-0241 still owns sample View/live-lookup and receipt defects.
- Capability or experiment: after SG-0241, run one moderated sample-only desktop/mobile session and measure time, comprehension, and privacy-boundary accuracy.
- Expected value: turns installation readiness into a credible first successful outcome.
- Success metric: 5/6 steps in under ten minutes, no live/private read, and correct sample-versus-live explanation.
- Smallest validation: one synthetic walkthrough after SG-0241 acceptance.
- Risks/privacy: demo/live identity mixing and accidental private prompts. Keep the session synthetic and client-local.
- Dedupe: ST-0001 is the strategy parent and SG-0241 owns the current product defect.

### 4. Validate Readers And Agent Workflows With Cost-Adjusted Perturbation Receipts

- Target user: daily user, agent builder, and Product Owner.
- Job to be done: choose model/skill/harness combinations that remain useful on nearby real tasks, not only frozen benchmarks.
- Evidence: [learnings/gbrain-x-intelligence-20261102-memory-reader-selection-needs-cost-adjusted-task-specific-evals](http://127.0.0.1:8788/?slug=learnings%2Fgbrain-x-intelligence-20261102-memory-reader-selection-needs-cost-adjusted-task-specific-evals), [learnings/gbrain-x-intelligence-20261106-agent-platform-velocity-needs-normalized-throughput-coverage-and-cost-receipts](http://127.0.0.1:8788/?slug=learnings%2Fgbrain-x-intelligence-20261106-agent-platform-velocity-needs-normalized-throughput-coverage-and-cost-receipts), and [learnings/gbrain-x-intelligence-20261108-agent-evals-need-perturbation-suites-and-trajectory-audits](http://127.0.0.1:8788/?slug=learnings%2Fgbrain-x-intelligence-20261108-agent-evals-need-perturbation-suites-and-trajectory-audits).
- Capability or experiment: ten public synthetic scenarios with two requirement-preserving variants each; freeze retrieval and compare reader correctness, advice quality, latency, tokens, cost, instruction compliance, and trajectory failure causes.
- Expected value: improves recurring answer value and avoids optimizing to one familiar score.
- Success metric: reproducible cost per correct answer, stable quality across variants, understandable failures, and no routing change without human approval.
- Smallest validation: read-only replay after SG-0238 restores a supported model runtime; no production prompts or purchases.
- Risks/privacy: benchmark overfitting, judge bias, and hidden customer content. Use public fixtures, report judge dependence, and keep routing unchanged.
- Dedupe: existing Learnings and ST-0004/ST-0007 provide strategy ownership; current runtime/capacity state does not justify implementation work.

### 5. Test Scoped Grants, Durable Handoffs, And One Human Review Queue

- Target user: multi-user customer, power user, and Product Owner.
- Job to be done: let agents collaborate across accounts and machines while one owner can inspect, approve, revoke, and recover every consequential boundary.
- Evidence: [learnings/gbrain-x-intelligence-20261107-cross-user-agent-access-needs-owner-controlled-scoped-and-revocable-approvals](http://127.0.0.1:8788/?slug=learnings%2Fgbrain-x-intelligence-20261107-cross-user-agent-access-needs-owner-controlled-scoped-and-revocable-approvals), [learnings/gbrain-x-intelligence-20261108-multi-agent-work-needs-shallow-hierarchies-durable-handoffs-and-one-human-review-queue](http://127.0.0.1:8788/?slug=learnings%2Fgbrain-x-intelligence-20261108-multi-agent-work-needs-shallow-hierarchies-durable-handoffs-and-one-human-review-queue), and the connector provenance Learning.
- Capability or experiment: two synthetic users and agents, one sandbox account, one shared workspace, one revocable grant matrix, and one review queue with fixed handoff packets.
- Expected value: tests the productization promise of shared memory without hiding authority, retention, provenance, or pending human decisions.
- Success metric: no implicit grant broadening; future calls stop after revocation; copied test content has visible retention/deletion behavior; handoffs preserve objective, owner, evidence, decision, next action, rollback, and expiry.
- Smallest validation: tabletop and read-only prototype only; no production account connection.
- Risks/privacy: credential crossover, retained copied data, fragmented approval, and false authority. Use sandbox accounts and hard stop on cross-scope access.
- Dedupe: ST-0005, ST-0009, ST-0010, prior access-path/shared-write candidates, and existing Learnings; no implementation-ready SG TODO.

## Duplicates Suppressed And Ideas Deferred

- SG-0234 owns critically stale restore rehearsal. SG-0240 owns disk attribution/headroom; Strategy grants no deletion, compaction, or cleanup authority.
- SG-0238 owns managed Codex runtime recovery. Production Ask Yoda evidence is unchanged and insufficient for telemetry or routing changes.
- SG-0241 owns sample details and activation receipts; ST-0001 remains the strategy parent.
- SG-0243 owns configured .102 health; no remote service mutation is authorized.
- SG-0246 owns stale weekly backlog evidence and remains reproducible.
- SG-0247 retained `capture-recovery` after successful allocation, repeating the SG-0246 lifecycle symptom against completed SG-0227. Product Owner reconciliation is required; Strategy made no tag mutation or duplicate TODO.
- Persistent Search cumulative errors, timeouts, and fallbacks grew, but the bounded current UX journey was error-free. Keep segmented telemetry as a strategy experiment until a distinct user-facing reproduction exists.
- Reranker configuration remains explicitly approval-gated. Configured-target source mismatch remains evidence drift, not deployment authority.
- No new Learning was created because all new strategy insights already exist as durable Learnings.

## Productization Insight

Memory Stargraph's immediate product constraint is truthful operational gating. Strong retrieval and broad agent-memory ideas do not compensate for a readiness surface that says ready while disk and restore evidence are critical. The differentiated product is an inspectable memory operating system: every claim about readiness, cost, identity, permission, handoff, and recovery must preserve source, freshness, owner, and human authority.

## Required Opportunities

- Make it easier for a new customer: make SG-0247 and SG-0241 truthful first, then test one sample-to-live activation session with no private data.
- Maximize recurring user value: restore SG-0238, then run the public-fixture cost-adjusted perturbation experiment before any production reader routing or Ask Yoda diary.

## Missing Evidence And Boundaries

- No direct first-time-customer completion session exists.
- No new production Ask Yoda use exists; the only sampled production attempt still fell back.
- No explicit approval exists for disk cleanup, restore retry, reranker change, model purchase, production telemetry, connector access, or cross-user grant testing.
- No operation-specific split explains Persistent Search cumulative worker/test failures versus current interactive success.
- SG-0246 and SG-0247 retain stale `capture-recovery` tags despite verified planned allocation.
- Detailed resolver events remain unavailable although aggregate resolver health is ready.
- No product code, deployment, service restart, resolver approval, reranker configuration, browser mutation, backup/restore action, production prompt, or production/user-data mutation occurred.

## Product Owner Delivery

- Destination task: `019faa62-6058-7643-b9cc-a2627083af07`.
- Status: `acknowledged_by_product_owner` at `2026-11-08T04:08:59-08:00`.
- Readback: accepted `completed_one_new_todo_strategy_candidates` and SG-0247's readiness-interpretation scope as distinct from SG-0234/SG-0240 operational ownership. No operational, deployment, cleanup, restore, reranker, resolver, telemetry, connector, or production mutation is authorized. The stale lifecycle tags remain unchanged.
- Compact payload: Product Strategy 2026-11-08 completed_one_new_todo_strategy_candidates on clean/current `fa94da57`, V1.0.231 / GBrain V0.46.28.0. Promoted SG-0247 P1 because customer readiness reports SRE numeric ready/current while canonical evidence says disk 92.450% critical and restore age 6,382,447 seconds critical; SG-0234/SG-0240 retain remediation ownership and SG-0247 only makes readiness truthful. Backlog was 11 planned/2 failed/33 completed before promotion and is now 12 planned. SG-0246 remains reproducible at stale 2/32/2 weekly counts. SG-0247 parent/child/link readback passed but retained `capture-recovery`, repeating SG-0246 and requiring SG-0227 lifecycle reconciliation without manual Strategy tag mutation. Retrieval remains 10/10, 10/10, 9/9; Ask Yoda and activation remain under SG-0238/SG-0241. Retain four strategy-only candidates: capacity/restore sequence, first-value session, cost-adjusted perturbation receipts, and scoped grants/handoffs/review queue. Requested follow-up: acknowledge SG-0247 once, urgently prioritize SG-0240/SG-0234, route SG-0247 when appropriate, reconcile stale lifecycle tags, and do not infer deployment, cleanup, restore, reranker, resolver, telemetry, connector, or production-mutation authority.

## Artifacts

- Run: [runs/memory-stargraph-divergent-product-discovery-20261108t035843-0800-85](http://127.0.0.1:8788/?slug=runs%2Fmemory-stargraph-divergent-product-discovery-20261108t035843-0800-85)
- Report: [reports/memory-stargraph-divergent-product-discovery-20261108t035843-0800-85](http://127.0.0.1:8788/?slug=reports%2Fmemory-stargraph-divergent-product-discovery-20261108t035843-0800-85)
- Promoted TODO: [notes/memory-starmap-todo-list/degrade-customer-readiness-for-critical-disk-and-restore-evidence](http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-todo-list%2Fdegrade-customer-readiness-for-critical-disk-and-restore-evidence)
- Learning: none; current insights were deduplicated to existing durable Learnings.
