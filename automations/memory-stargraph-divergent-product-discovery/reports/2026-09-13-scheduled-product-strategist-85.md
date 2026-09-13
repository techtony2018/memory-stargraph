---
type: report
title: Memory Stargraph Divergent Product Discovery 2026-09-13
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
product: products/memory-stargraph
status: completed_no_new_todo_approval_packet
automation_id: memory-stargraph-divergent-product-discovery
invocation_id: memory-stargraph-divergent-product-discovery-20260913t040118-0700-85
run_slug: runs/memory-stargraph-divergent-product-discovery-20260913t040118-0700-85
learning_slug: learnings/memory-stargraph-discovery-20260913-critical-reranker-state-is-approval-packet-not-strategy-todo
created_todo_ids: []
updated_todo_ids: []
todo_promotion_status: no_new_bounded_sg_gap
product_owner_notification_status: acknowledged_by_product_owner
product_owner_notification_pending: false
tags:
  - completed
  - discovery
  - memory-stargraph
  - product-strategy
---

# Memory Stargraph Divergent Product Discovery - 2026-09-13

## Executive Decision

The scheduled Product Strategy review completed on the .85 automation mirror. No product code was written, no deployment was attempted, no GBrain configuration was changed, no resolver proposal was approved, no production/user data was mutated, no private configured-target coordinates were exposed, and no SG TODO was created or promoted.

Decision: `completed_no_new_todo_approval_packet`.

The strongest current product risks are not uncovered implementation gaps owned by Product Strategy. The first is a normal write-path persistence incident: dashboard `/api/entity-save` returned HTTP 502 for Strategy artifact persistence attempts, and Product Owner context confirms repeated X canary failures from the same write path. Direct `gbrain import --no-embed` recovered this Run/report/Learning, but that fallback is degraded artifact recovery, not proof that normal API persistence is healthy. The second is an approval-gated readiness state: GBrain reranker readiness is Critical after the 2026-09-04 ZeroEntropy sunset because no explicit supported reranker override is configured. Memory Stargraph already surfaced this through completed SG-0222, including the human-approved operator command and verification path. This run therefore preserves both issues as Product Owner/operator approval-packet or incident input, not duplicate SG TODOs or automatic mutation.

## Source-Sync Preflight

- workspace_path: `/Users/toddy/memory-stargraph`
- branch: `main`
- local_head: `a6d08dd9764fe7cb7b49a0530f30d965b5110560`
- upstream_ref: `origin/main`
- upstream_head: `a6d08dd9764fe7cb7b49a0530f30d965b5110560`
- dirty_state: clean before strategy artifact creation
- divergent_state: none
- deployed_service_version: V1.0.217
- gbrain_version: V0.46.28.0
- selected_source_path: `/Users/toddy/memory-stargraph`
- selected_source_surface: dashboard-managed local TLS service plus current checkout
- action_taken: `use_workspace`
- sync_applied: false
- source-sync schema: `memory-stargraph-source-sync-preflight-v1`
- worker routes: route listing completed through `python3 scripts/automation/gbrain_worker_api.py routes`

## Evidence Inspected

- Product, project, persistent goal, canonical SG TODO list, product-strategy TODO list, recent UX dogfood reports, recent SRE evidence, recent Developer completion reports, GBrain X Intelligence reports/Learnings, Ask Yoda configuration/logs, resolver health, activation funnel, settings evidence, search probes, and service health.
- Health: `.85` service ok=true loaded=true, ui_version=V1.0.217, gbrain_version=V0.46.28.0, source mode `gbrain`, source status `lazy-root`, updated_at 2026-09-13T03:46:24Z.
- GBrain reranker: `/api/customer-readiness` reports status `critical`, state `deprecated_default_unconfigured`, sunset_detected=true, sunset_date 2026-09-04, days_until_sunset=-9, configured_override=false. Operator action requires approval and no automatic mutation.
- Persistent search worker: active=true, ready=false, busy=false, operating contract status `uninitialized`; metrics include 74 process starts, 73 restarts, 1586 tool calls, 1512 successes, 74 errors, 50 timeouts, and 148 CLI fallbacks. `/api/search` still returned bounded results through lazy-search and lazy-search-partial paths.
- Ask Yoda MCP: pool_size=5, ready_sessions=5, semantic_ready_sessions=5, structured_only=true, but operating contract status `missing` with write_safety_ready=false across sessions.
- Canonical backlog: current planned root TODOs are SG-0229, SG-0230, and SG-0231; implementing count is 0; SG-0166 remains historical failed/superseded. Strategy did not treat the three planned items as already implemented or create duplicates.
- Active tags: `/api/pages?tag=active&limit=200` returned an empty `pages` array.
- Weekly memory value digest: gates_total=9, gates_passed=6, gates_degraded=3, status=degraded. Degraded gates are current unresolved planned blockers, stale SRE numeric evidence, and configured-target deployment attestation source_mismatch.
- Customer readiness: checks_total=9, ready=5, degraded=1, stale=1, critical=1, source_mismatch=1, status=degraded. The critical check is GBrain reranker; stale is SRE numeric evidence; source_mismatch is configured targets.
- Backup evidence: native GBrain backup coverage is unavailable; legacy `_backups/backup-latest` fallback is current with latest_backup_at 2026-09-13T10:00:01Z and age about 3,758 seconds at readback.
- SRE evidence: latest daily SRE evidence in readiness is 2026-09-04 and now stale for daily recency, while weekly evidence remains current. The latest detailed SRE report recorded retrieval 10/10 answers, 10/10 recall, 9/9 expected sources, backup current, restore warning recency, and no incident/remediation.
- Configured-target attestation: configured_target_count=2, verified_target_count=2, source_mismatch_count=2, source_timestamp 2026-09-07T21:30:25Z, readback 2026-09-13T11:02:39Z. Target coordinates were not exposed.
- Activation funnel: live-ready/privacy-safe, completed 1/6, next step `sample_brain_opened`.
- Resolver health: ready via local resolver ledger fallback, pending=0, events_24h=0, auto_approval=false.
- Ask Yoda config: backend `gbrain_think`, model `openai:gpt-5.5`, timeout 120 seconds, graph query timeout 30 seconds, node runtime status `not_used`.
- Ask Yoda logs: latest sampled entries are synthetic/test entries from 2026-09-07 and 2026-09-04; no production-user Ask Yoda usage or feedback evidence was observed.
- Search probes: exact SG-0229, SG-0230, and SG-0231 returned complete status and expected TODO slugs. Broader "GBrain reranker sunset readiness" and "linkedin posts" returned partial_timeout with useful slugs. "source_sync_preflight worker_task_id" returned partial_timeout with no slugs. Search remains usable for exact IDs but still has product-risk evidence around partial timeouts and fallback dependence.
- UX Dogfood 2026-09-12: completed_no_new_todos on V1.0.217. Startup, Search, Settings, Ask Yoda View Log, Follow-ups, mobile focus/Enter, and View reachability passed; existing SG-0229 and SG-0230 were reproduced without duplication. Relationship/backlink/history calls exceeded the bounded 30-second harness budget and were recorded as coverage limits, not UI findings.
- GBrain X Intelligence 2026-09-04: captured 8 items, 6/6 searches, 10/12 timelines, 331 unique rows, 30 direct candidates, 1 Learning, 0 TODOs. The Learning highlights vertical workflows, provenance, enterprise boundaries, concurrency readiness, stale/noisy ingestion telemetry, and cost visibility.
- Artifact persistence: top-level `/api/entity-save` returned HTTP 502 during initial saves for this report, Run, and Learning. After successful source-sync preflight, Strategy used direct `gbrain import --no-embed` fallback and verified `gbrain get` readback for all three slugs. This is degraded artifact recovery only; it does not prove the normal API write path has recovered.
- Product Owner context observed during delivery readback shows an ongoing P1 write-path incident: X canaries on 2026-09-11 and 2026-09-13 failed `/api/entity-save` with HTTP 502 while read health was green; Product Owner preserved the watermark and prohibited historical replay.

## Perspective Walkthrough

- First-time customer: the product loads and sample/live readiness is available, but readiness currently presents Critical reranker state, stale SRE evidence, and configured-target source mismatch. A customer needs a clear approval and ownership lane before trusting this as multi-target ready.
- Daily user: exact TODO search, View, Settings, Follow-ups, and Ask Yoda log inspection continue to work, but production Ask Yoda value is still not visible because current sampled logs are synthetic/test only.
- Power user / agent builder: APIs expose useful health and readiness structure, but persistent Search and Ask Yoda MCP operating contracts are not fully attested. That limits confidence for automation composition and write-safety reasoning.
- Operator: backup freshness is current, active tags are clear, and resolver has no pending proposals. The actionable operator state is approval-gated reranker migration plus stale daily SRE refresh and configured-target attestation refresh, none of which Strategy is authorized to mutate.
- Product Owner: there are already three planned root TODOs. Strategy should not add backlog pressure until the current planned items are dispatched or explicitly re-prioritized and the approval-gated reranker/configured-target questions are settled.

## Ranked Opportunities

| Rank | Opportunity | Score | Target user | Decision |
| ---: | --- | ---: | --- | --- |
| 1 | Normal API write-path durability recovery and ownership | 94 | Daily user, operator, Product Owner | Existing incident/candidate only |
| 2 | Reranker migration approval packet and post-approval verification lane | 91 | First-time customer, operator, Product Owner | Strategy candidate only |
| 3 | Customer-readiness evidence freshness and attestation ownership lane | 87 | First-time customer, operator | Strategy candidate only |
| 4 | Persistent MCP/search operating-contract readiness for agent builders | 83 | Power user, agent builder, operator | Strategy candidate only |
| 5 | Guided sample-to-live activation checkpoint beyond 1/6 | 80 | First-time customer | Strategy candidate only |

## Opportunity Details

### 1. Normal API Write-Path Durability Recovery And Ownership

- Target user: daily user, operator, Product Owner.
- JTBD: "Trust that normal dashboard/API saves persist without requiring degraded fallback channels."
- Evidence: this Strategy run's top-level `/api/entity-save` attempts returned HTTP 502 for all three artifacts; direct `gbrain import --no-embed` fallback succeeded and read back. Product Owner context also shows 2026-09-11 and 2026-09-13 X canaries failed the same write path while read health stayed green.
- Proposed capability/experiment: preserve a single write-path incident/candidate with bounded reproduction, root-cause ownership, and post-fix canary criteria for normal `/api/entity-save`.
- Expected value: restores durable automation output, X capture continuity, and confidence in write-side health.
- Success metric: normal `/api/entity-save` can persist a bounded canary and read it back through `/api/entity-raw` without 502, replay, or fallback.
- Smallest validation: authorized Developer/SRE incident owner runs a bounded write-path canary after health/source gates pass.
- Risks/privacy: do not replay missed X data, reconstruct expired temporary evidence, or mutate user data while diagnosing persistence.
- Why not already covered: Product Owner already treats this as an ongoing P1 incident/candidate, so Strategy records evidence but does not create a duplicate TODO or dispatch Developer work.

### 2. Reranker Migration Approval Packet And Post-Approval Verification Lane

- Target user: first-time customer, operator, Product Owner.
- JTBD: "Know exactly what human approval is needed before search/reranker readiness can be considered customer-safe."
- Evidence: customer readiness marks GBrain reranker `critical`; ZeroEntropy sunset date is 2026-09-04 and the current run is 2026-09-13; configured_override=false; SG-0222 already surfaced the condition and human-approved commands without mutating configuration.
- Proposed capability/experiment: a Product Owner approval packet that records the current Critical state, approval boundary, fixed migration command, verification commands, rollback expectation, and no-auto-mutation rule.
- Expected value: turns an alarming readiness state into a controlled operator decision.
- Success metric: after explicit approval and operator execution outside Strategy, readiness shows reranker configured/current and bounded search verification passes.
- Smallest validation: Product Owner confirms whether to approve the SG-0222 operator command path, defer it, or keep readiness Critical.
- Risks/privacy: configuration may affect local retrieval behavior; commands must not expose credentials or private search results.
- Why not already covered: SG-0222 covered detection and presentation; it intentionally did not apply configuration. This run does not add a new TODO because the remaining step is human approval/operator action.

### 3. Customer-Readiness Evidence Freshness And Attestation Ownership Lane

- Target user: first-time customer and operator.
- JTBD: "Distinguish real product danger from stale or mismatched proof."
- Evidence: weekly outcomes are 6/9 and customer readiness is 5/9 because unresolved planned TODOs, stale daily SRE evidence, critical reranker state, and configured-target source_mismatch remain. Backup fallback evidence itself is current, and active tags are clean.
- Proposed capability/experiment: a readiness explanation lane that groups failures by owner: Developer backlog, SRE refresh, Product Owner approval, and deployment attestation.
- Expected value: makes degraded readiness actionable without exposing private target coordinates.
- Success metric: readiness UI/report can say which owner should act next and whether the user should wait, approve, dispatch, or verify.
- Smallest validation: Product Owner review of the current degraded checks and owner mapping, with no deployment or target mutation.
- Risks/privacy: configured target details must stay redacted; stale evidence must not be mislabeled as safe.
- Why not already covered: existing readiness surfaces list checks and next steps; they do not yet package the cross-role ownership decision as a customer-facing product explanation.

### 4. Persistent MCP/Search Operating-Contract Readiness For Agent Builders

- Target user: power user, agent builder, operator.
- JTBD: "Trust search and Ask Yoda as automation substrates, not just UI features."
- Evidence: health shows persistent_search ready=false with operating contract uninitialized, 50 timeouts, 148 CLI fallbacks, and many restarts; Ask Yoda MCP has ready sessions but operating contract status missing/write_safety_ready=false. Exact search probes worked, but broader probes returned partial_timeout.
- Proposed capability/experiment: an agent-builder readiness card that distinguishes exact-search pass, broad-search partial timeout, persistent MCP contract readiness, CLI fallback dependence, and Ask Yoda write-safety attestation.
- Expected value: prevents automation builders from over-trusting a partially degraded search/MCP layer.
- Success metric: a read-only diagnostic can classify the layer as exact-search usable, broad-search degraded, write-safe unavailable, or fully ready.
- Smallest validation: collect existing `/api/health` persistent_search and ask_yoda_mcp contract fields with bounded exact and broad search probes.
- Risks/privacy: do not expose raw MCP instructions, private query results, or credentials.
- Why not already covered: SG-0226 exposed operating-contract diagnostics, but current V1.0.217 evidence shows the surfaced state is still not ready and needs product interpretation for agent builders.

### 5. Guided Sample-To-Live Activation Checkpoint Beyond 1/6

- Target user: first-time customer.
- JTBD: "Complete one trustworthy sample-to-live workflow rather than stop at readiness cards."
- Evidence: activation remains live-ready and privacy-safe but completed 1/6 with next step `sample_brain_opened`. This repeats the prior Product Strategy finding.
- Proposed capability/experiment: a guided sample-only flow through sample brain, node selection, relationship/provenance, synthetic Ask Yoda, setup diagnostics, and first live-readiness confirmation.
- Expected value: converts readiness into first value and lowers onboarding friction.
- Success metric: a sample-only session completes at least 4/6 activation steps without private data mutation.
- Smallest validation: bounded browser walkthrough using sample data and existing activation API readback.
- Risks/privacy: must not mix sample and live private content; no production prompt submission.
- Why not already covered: SG-0164 made activation measurable, but current evidence still shows no progression beyond 1/6.

## Required Product Opportunities

- Make it easier for a new customer: package the current Critical/degraded readiness state into clear approval, SRE, deployment, and Developer ownership lanes.
- Maximize recurring user value: restore normal API write-path confidence and add agent-builder search/MCP readiness interpretation.

## TODO Decision

No SG TODOs were created or updated.

Reasons:

- SG-0229, SG-0230, and SG-0231 are already planned root TODOs and should be dispatched through the normal Developer loop rather than expanded by Strategy.
- Reranker Critical state is already surfaced by completed SG-0222 and requires explicit approval/operator execution, not Strategy mutation or duplicate TODO creation.
- Normal API write-path failure is already being handled as a Product Owner/SRE/Developer incident candidate; this run adds evidence but does not allocate or dispatch work.
- Configured-target source_mismatch requires authorized deployment verification/attestation, not Strategy deployment.
- Stale SRE evidence belongs to the SRE cadence/refresh lane.
- Activation and production Ask Yoda telemetry remain strategy candidates, but this run did not gather new browser or production-usage evidence strong enough to promote them.

## Duplicates Suppressed

- SG-0222 already surfaces GBrain reranker sunset readiness and fixed human-approved remediation commands.
- SG-0225 already integrates native GBrain backup coverage into readiness with a backup-latest fallback.
- SG-0226 already exposes GBrain MCP operating-contract diagnostics.
- SG-0228 already fixes first-open Ask Yoda View Log persistence/loading.
- SG-0229 owns terminal TODO lifecycle tag cleanup.
- SG-0230 owns View markdown underscore corruption.
- SG-0231 owns the stale generic CDP Follow-ups probe.
- SG-0232 already keeps readiness evidence summaries grammatically complete.
- The ongoing `/api/entity-save` 502 condition is preserved as the existing P1 write-path incident/candidate from Product Owner context, not duplicated by Strategy.
- Prior Strategy runs already preserved configured-target attestation, activation, production Ask Yoda telemetry, shared-memory readiness, and X recovery as strategy candidates.
- The 2026-08-11 scale/readiness validation remains approval-packet input only until consent manifest, isolated namespace, cost caps, readiness-current gate, and Stage 1 scope are approved.

## Productization Insight

The product has enough diagnostic depth that the next customer-facing gap is decision clarity. A readiness surface that says "Critical" is useful only if it also tells the customer which role owns the next step and whether the next step is approval, operator execution, Developer dispatch, SRE refresh, or deployment verification.

## Missing Evidence And Boundaries

- No explicit approval was granted to change GBrain reranker config.
- Normal `/api/entity-save` persistence failed with HTTP 502 during this Strategy run and remains unproven; direct `gbrain import --no-embed` fallback is degraded artifact recovery only.
- No deployment verification or configured-target attestation refresh was authorized.
- No production Ask Yoda usage/feedback evidence was observed in sampled logs.
- No browser activation walkthrough was run.
- SRE daily evidence is stale in readiness, though backup-latest fallback is current.
- Persistent Search and Ask Yoda MCP write-safety contracts are not ready/attested, but Strategy did not inspect raw MCP instructions or mutate sessions.
- No Agent Reach or external web research was used; local product evidence was sufficient and more authoritative for this bounded review.

## Artifacts

- Run: `runs/memory-stargraph-divergent-product-discovery-20260913t040118-0700-85`
- Report: `reports/memory-stargraph-divergent-product-discovery-20260913t040118-0700-85`
- Learning: `learnings/memory-stargraph-discovery-20260913-critical-reranker-state-is-approval-packet-not-strategy-todo`

## Product Owner Delivery Payload

Delivery status after Product Owner readback: `acknowledged_by_product_owner`.

Delivery attempt evidence: `codex_app.send_message_to_thread` accepted the compact payload for destination task `019faa62-6058-7643-b9cc-a2627083af07`. Product Owner acknowledged the run as `completed_no_new_todo_approval_packet`, preserved SG-0229/SG-0230/SG-0231 as the only planned root TODOs, preserved SG-0222 as completed, preserved the reranker sunset condition as approval-packet input only, and explicitly did not authorize reranker/config/deployment mutation, resolver approval, TODO promotion, or Developer dispatch. Product Owner also clarified that direct `gbrain import --no-embed` is degraded artifact recovery, not proof that normal `/api/entity-save` persistence is healthy.

Acknowledged at: 2026-09-13T04:24:00-07:00.

Compact payload: Product Strategy 2026-09-13 completed on .85 V1.0.217 / GBrain V0.46.28.0 / commit `a6d08dd9764fe7cb7b49a0530f30d965b5110560`; source-sync current and clean; no code, deployment, GBrain config mutation, resolver approval, production mutation, private target exposure, or SG TODO promotion; current planned root TODOs are SG-0229, SG-0230, SG-0231 with implementing=0; active tags empty; weekly outcomes 6/9 and customer readiness 5/9 degraded by planned blockers, stale daily SRE evidence, configured-target source_mismatch, and Critical reranker state; reranker Critical is post-2026-09-04 ZeroEntropy sunset with configured_override=false and fixed approval-gated operator command already surfaced by SG-0222; normal `/api/entity-save` returned HTTP 502 for Strategy artifact writes, so direct `gbrain import --no-embed` fallback was used and read back; backup-latest fallback current; exact SG-0229/0230/0231 search works while broader search remains partial-timeout/fallback-dependent; recent Ask Yoda logs sampled are synthetic/test only; top strategy candidates are normal API write-path durability recovery, reranker approval packet, readiness ownership lane, persistent MCP/search readiness interpretation, and activation beyond 1/6; requested Product Owner action is acknowledgement and approval/ownership decisions only, not Developer dispatch or config/deployment authorization from this Strategy run.
