---
type: report
title: Memory Stargraph Divergent Product Discovery 2026-08-23
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
product: products/memory-stargraph
status: completed_strategy_candidate_promotion_blocked
automation_id: memory-stargraph-divergent-product-discovery
invocation_id: memory-stargraph-divergent-product-discovery-20260823t040212-0700-85
run_slug: runs/memory-stargraph-divergent-product-discovery-20260823t040212-0700-85
learning_slug: learnings/memory-stargraph-discovery-20260823-active-tag-metadata-drift-is-readiness-risk
created_todo_ids: []
updated_todo_ids: []
todo_promotion_status: blocked_by_add_sg_todo_high_water_gap
product_owner_notification_status: pending_unacknowledged_delivery
product_owner_notification_pending: true
tags:
  - completed
  - discovery
  - memory-stargraph
  - product-strategy
---

# Memory Stargraph Divergent Product Discovery - 2026-08-23

## Executive Decision

The scheduled Product Strategy review completed on the .85 automation mirror. No product code was written, no deployment was attempted, no resolver proposal was approved, no production/user data was mutated, and no manual backlog bypass was performed.

The strongest new evidence-backed product gap is stale active-tag metadata drift: `gbrain list --tag active -n 50` returned many historical terminal Run/report nodes, and raw readback of `reports/memory-stargraph-wish-sg0205-20260815t033202-0700-49bc24b` still contains `tags: active` despite `active_change: false` and later terminal evidence that global active tags had been clear. This can make quiet-time and readiness decisions look unsafe even when real work is terminal.

Product Strategy attempted to promote this as one bounded P1 TODO through the official `add-sg-todo` helper. The helper refused with:

```json
{"error": "TODO archive high-water evidence has gaps; refusing to allocate a duplicate id.", "ok": false, "reminder_required": false}
```

No planned TODO was created. The active-tag work is preserved as the top strategy candidate, and the TODO archive high-water gap is recorded as a promotion blocker requiring Product Owner/Developer governance before new SG backlog work can be safely allocated.

## Source-Sync Preflight

- workspace_path: `/Users/toddy/memory-stargraph`
- branch: `main`
- local_head: `af7c6f239bf24957c6c5445c6f76cf3811df7dc9`
- upstream_ref: `origin/main`
- upstream_head: `af7c6f239bf24957c6c5445c6f76cf3811df7dc9`
- dirty_state: clean before strategy artifact creation
- divergent_state: none
- deployed_service_version: V1.0.198
- required_script_existence: `scripts/automation/yoda_gap_evaluator.py` present; `automations/memory-stargraph-divergent-product-discovery/prompt.md` present
- selected_source_path: `/Users/toddy/memory-stargraph`
- selected_source_surface: dashboard-managed local TLS service plus current checkout
- action_taken: `use_workspace`; sync_applied=false
- source-sync schema: `memory-stargraph-source-sync-preflight-v1`

## Evidence Inspected

- Product, project, persistent goal, canonical SG TODO list, product-strategy TODO list, recent Product Strategy reports, Product Owner ledger/report evidence through local checkout, SRE weekly evidence, and SG-0207/SG-0208 terminal run/report.
- Health: `.85` V1.0.198 ok=true loaded=true; source mode `gbrain`, status `lazy-root`; durable attachment storage available/writable.
- Backlog: SG-0207 and SG-0208 are completed in V1.0.198; SG-0209 is completed in V1.0.197; SG-0166 remains historical failed but is explicitly superseded by SG-0167. Current canonical root TODO counts show planned=0 and implementing=0.
- Weekly digest: 9 gates total, 7 passed, 2 degraded. Degraded gates are stale SRE numeric evidence and configured-target deployment attestation source mismatch.
- Customer readiness: 8 checks total; ready=5, degraded=1, stale=1, source_mismatch=1. Safe next step is to inspect weekly outcomes.
- Configured targets: configured_target_count=2, verified_target_count=2, source_mismatch_count=2; no private target coordinates exposed.
- SRE numeric evidence: backup freshness itself is current, but daily/weekly SRE evidence is stale because current Daily or Weekly evidence is outside the allowed recency window.
- Activation funnel: live-ready/privacy-safe, but progress remains 1/6 with next step `sample_brain_opened`.
- Resolver health: ready via local resolver ledger fallback, pending proposals=0, events_24h=0, auto_approval=false.
- Ask Yoda config: backend `gbrain_think`, model `openai:gpt-5.2`, `api_key_available=false`, node runtime not used.
- Ask Yoda logs: recent entries are synthetic/unit test fixtures from 2026-08-17 plus older synthetic evaluator traffic; no production-user Ask Yoda feedback evidence was observed.
- Active tags: `gbrain list --tag active -n 50` returned many historical terminal Run/report nodes. Raw readback of SG-0205 report confirms a stale `active` tag remains in a completed report.
- Search probes: `/api/search` returned ok=true with zero results for known current terms, including active-tag lifecycle, configured-target source mismatch, SRE numeric staleness, and activation 1/6. This matches prior strategy evidence that search cannot be treated as authoritative discovery proof in this worker context.
- Product Owner local checkout evidence: latest local Product Owner report is 2026-08-12, with goal progress 97%, 9/9 weekly, 8/8 readiness, active tags none, and explicit carry-over for Stage 1 experiment approval. No newer local Product Owner report artifacts were present.
- External research / Agent Reach: not used. Current local evidence was sufficient and more directly relevant than external product-pattern research.

## Perspective Walkthrough

- First-time customer: the service is healthy, but readiness now presents stale/SRE/source-mismatch warnings and activation remains 1/6. A customer would not know whether the product is unsafe, merely unverifiable, or waiting on scheduled evidence refresh.
- Daily user: search and Ask Yoda have historical benchmark evidence, but current search discovery is empty and current Ask Yoda logs are synthetic. The user value story remains mostly internal proof, not observed recurring usage.
- Power user / agent builder: APIs expose health, readiness, resolver, activation, and logs, but metadata drift in active tags undermines automation composition because workers use active-tag readback as a coordination gate.
- Operator: SG-0207/SG-0208 closed the planned blocker from the prior strategy run, but operational proof has drifted stale. Active-tag false positives and source-mismatch attestations can create noise without proving a live product defect.
- Product Owner: the backlog is empty, but the official TODO helper blocks new ID allocation due archive high-water evidence gaps. The correct next move is to resolve governance/ID integrity, then decide whether to promote the active-tag drift candidate.

## Ranked Opportunities

| Rank | Opportunity | Score | Target user | Decision |
| ---: | --- | ---: | --- | --- |
| 1 | Reconcile stale active-tag metadata after reingestion | 92 | Operator, Product Owner, agent builder | Promotion attempted; blocked by helper |
| 2 | Readiness evidence freshness and attestation ownership lane | 88 | First-time customer, operator | Proposal only |
| 3 | Guided first-value activation checkpoint beyond 1/6 | 84 | First-time customer | Proposal only |
| 4 | Production Ask Yoda usage and feedback telemetry | 80 | Daily user, Product Owner | Proposal only |
| 5 | Search discovery health receipt | 76 | Daily user, agent builder | Proposal only |

## Opportunity Details

### 1. Reconcile Stale Active-Tag Metadata After Reingestion

- Target user: operator, Product Owner, agent builder.
- JTBD: "Trust active-tag readback as a live coordination signal, not a stale artifact of completed historical pages."
- Evidence: current `gbrain list --tag active -n 50` returned historical terminal artifacts; raw SG-0205 report still has `tags: active` with `active_change: false`; SG-0192/SG-0193 previously covered Capture Link lifecycle release and SG-0207/SG-0208 final readback proved active_tag_count=0 on 2026-08-17.
- Proposed capability: metadata reconciliation that prevents completed terminal Run/report pages from retaining or reintroducing standalone active lifecycle tags through raw frontmatter, page metadata, restore/reingestion, or save/readback.
- Expected value: restores reliable quiet-time gates and prevents false worker blocking.
- Success metric: `gbrain list --tag active` returns no completed terminal artifacts while preserving legitimate active leases.
- Smallest validation: inspect affected completed Run/report scope, remove only stale active metadata through explicit tag mutation or metadata-normalization path, and add regression coverage for frontmatter-versus-page-metadata drift.
- Risks/privacy: must not clear legitimate active work or rewrite private content.
- Why not already covered: SG-0192/SG-0193 addressed Capture Link terminalization; this evidence shows broader completed-artifact metadata drift after later reingestion/readback.

### 2. Readiness Evidence Freshness And Attestation Ownership Lane

- Target user: first-time customer and operator.
- JTBD: "Know whether readiness is degraded because the product is unsafe or because scheduled proof is stale."
- Evidence: weekly outcomes are 7/9 and customer readiness is degraded despite healthy V1.0.198 service, no planned/implementing TODOs, and backup freshness current. The degraded gates are stale SRE numeric evidence and configured-target source mismatch.
- Proposed capability: an ownership lane or evidence receipt that separates product defects from stale scheduled evidence and explicitly names which recurring role should refresh the proof.
- Expected value: reduces false negative readiness and makes customer-facing readiness actionable.
- Success metric: degraded readiness includes owner, evidence age, safe next refresh action, and "not a product defect" classification when applicable.
- Smallest validation: Product Owner/SRE review of the current source_mismatch plus stale SRE state without deploying or mutating targets.
- Risks/privacy: must keep configured target details redacted.
- Why not already covered: SG-0209 makes stale/critical evidence visible; it does not assign the refresh lane or prevent ambiguity when the implementation backlog is empty.

### 3. Guided First-Value Activation Checkpoint Beyond 1/6

- Target user: first-time customer.
- JTBD: "Finish one sample-to-live workflow rather than only see readiness cards."
- Evidence: activation remains 1/6 with the next step `sample_brain_opened`, matching prior Product Strategy observations.
- Proposed capability: a guided checkpoint that walks sample brain, node selection, relationship/provenance, synthetic Ask Yoda question, setup diagnostics, and first live workflow confirmation.
- Expected value: turns readiness into first value.
- Success metric: browser/session evidence completes at least 4/6 activation steps without production-data mutation.
- Smallest validation: sample-only UI walkthrough and client-session proof.
- Risks/privacy: must avoid private prompts and clearly label sample versus live data.
- Why not already covered: SG-0164 built the activation funnel; no evidence shows guided progression beyond 1/6.

### 4. Production Ask Yoda Usage And Feedback Telemetry

- Target user: daily user and Product Owner.
- JTBD: "Distinguish synthetic benchmark quality from real Ask Yoda value."
- Evidence: Ask Yoda config is present and historical model-backed evaluator proof exists, but current logs are synthetic/unit tests and no production-user feedback evidence was observed.
- Proposed capability: privacy-safe aggregate usage/feedback summary for real Ask Yoda attempts, fallback/degraded state, and explicit feedback without prompt snippets.
- Expected value: aligns recurring value measurement with actual use.
- Success metric: weekly outcomes distinguish synthetic benchmark pass from production usage/no-activity.
- Smallest validation: aggregate read-only counts from existing log provenance fields.
- Risks/privacy: do not expose prompts, private selected nodes, traces, or credentials.
- Why not already covered: current weekly gates report benchmark evidence, not production usage.

### 5. Search Discovery Health Receipt

- Target user: daily user and agent builder.
- JTBD: "Know when search can be trusted for discovery and when raw slug reads are required."
- Evidence: this run's search probes returned zero results for known current topics while raw entity reads succeeded.
- Proposed capability: a search health receipt reporting corpus/source readiness, exact-ID coverage, archive index readiness, and last known-query success.
- Expected value: prevents false conclusions from empty search results.
- Success metric: worker reports can cite search health before using search as evidence.
- Smallest validation: read-only safe probes for public/synthetic terms.
- Risks/privacy: probes must avoid private content.
- Why not already covered: SG-0202/SG-0195 covered specific search regressions; this remains an observability proposal.

## Required Product Opportunities

- Make it easier for a new customer: separate readiness evidence staleness/source-mismatch from actual customer risk, then guide activation beyond 1/6.
- Maximize recurring user value: reconcile stale active-tag metadata so recurring workers and agent builders can trust coordination gates.

## TODO Decision

No SG TODOs were created or updated.

Product Strategy attempted exactly one official helper-backed promotion:

- title: Reconcile stale active-tag metadata after reingestion
- priority: P1
- helper result: `ok=false`
- blocker: `TODO archive high-water evidence has gaps; refusing to allocate a duplicate id.`
- reminder_required: false

Manual TODO creation was intentionally not attempted because the helper refused ID allocation. This preserves backlog integrity and human control.

## Duplicates Suppressed

- SG-0192 and SG-0193 already cover Capture Link terminal lifecycle tag release and readback, so the current candidate is scoped to broader completed-artifact metadata drift after reingestion/readback.
- SG-0207 already covers repeated already-sufficient enrichment selections and is completed.
- SG-0208 already covers backup freshness restoration and is completed.
- SG-0209 already covers degrading readiness when backup evidence is critical or stale; the new readiness proposal is about evidence ownership and customer interpretation, not the degradation rule itself.
- The Aug 11 scale/readiness validation remains approval-packet input only.
- Prior activation and search proposals remain unpromoted because the active-tag/readiness evidence is currently stronger.

## Productization Insight

Memory Stargraph now has enough internal proof surfaces that stale proof can become the product problem. The next adoption risk is not only whether the service works; it is whether readiness, active leases, search, and operational evidence distinguish "unsafe", "stale proof", and "needs human approval" in a way a customer or operator can act on.

## Missing Evidence

- No Product Owner report artifacts after 2026-08-12 were present in the checkout.
- No production Ask Yoda usage/feedback evidence was observed.
- Search returned empty for known current topics.
- The official TODO helper blocked promotion due TODO archive high-water gaps.
- No browser walkthrough was run; API/raw evidence was sufficient for this bounded review.
- No deployment or configured-target verification was authorized or attempted.

## Artifacts

- Run: `runs/memory-stargraph-divergent-product-discovery-20260823t040212-0700-85`
- Report: `reports/memory-stargraph-divergent-product-discovery-20260823t040212-0700-85`
- Learning: `learnings/memory-stargraph-discovery-20260823-active-tag-metadata-drift-is-readiness-risk`

## Product Owner Delivery Payload

Delivery status after task readback: `pending_unacknowledged_delivery`.

Delivery attempt evidence: `codex_app.send_message_to_thread` accepted the compact payload for destination task `019faa62-6058-7643-b9cc-a2627083af07`. A follow-up `codex_app.read_thread` reached the Product Owner task, but the newest visible turn was already in progress on the same stale-active-tag blocker from the Developer task and the Product Strategy payload was not visible in readback. Product Owner sweep should reconcile this Run/report.

Attempted at: 2026-08-23T04:05:00-07:00.

Compact payload: Product Strategy 2026-08-23 completed on .85 V1.0.198 / commit `af7c6f239bf24957c6c5445c6f76cf3811df7dc9`; source-sync current; no code/deploy/resolver approval/production mutation; SG-0207/SG-0208 are completed and no planned/implementing SG root TODOs remain; weekly outcomes are 7/9 and customer readiness degraded because SRE numeric evidence is stale and configured-target attestation has source_mismatch; `gbrain list --tag active` returned stale completed artifacts and raw SG-0205 report still contains `tags: active`; Product Strategy attempted to promote P1 active-tag metadata reconciliation but official `add-sg-todo` blocked with TODO archive high-water gaps, so no TODO was created; top proposals are active-tag metadata reconciliation, readiness evidence freshness ownership, guided activation beyond 1/6, production Ask Yoda telemetry, and search health receipt; requested Product Owner follow-up: acknowledge the no-code strategy result, decide ownership for TODO archive high-water repair, then consider promoting active-tag metadata reconciliation through the normal SG path.
