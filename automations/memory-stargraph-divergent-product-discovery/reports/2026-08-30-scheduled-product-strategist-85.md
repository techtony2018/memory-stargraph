---
type: report
title: Memory Stargraph Divergent Product Discovery 2026-08-30
goal: goals/memory-stargraph-continuous-learning-local-knowledge-os
product: products/memory-stargraph
status: completed_no_new_todo
automation_id: memory-stargraph-divergent-product-discovery
invocation_id: memory-stargraph-divergent-product-discovery-20260830t040141-0700-85
run_slug: runs/memory-stargraph-divergent-product-discovery-20260830t040141-0700-85
learning_slug: learnings/memory-stargraph-discovery-20260830-use-coverage-fields-for-search-health
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

# Memory Stargraph Divergent Product Discovery - 2026-08-30

## Executive Decision

The scheduled Product Strategy review completed on the .85 automation mirror. No product code was written, no deployment was attempted, no resolver proposal was approved, no production/user data was mutated, no private configured-target coordinates were exposed, and no SG TODO was created or promoted.

Decision: `completed_no_new_todo`.

The product is currently backlog-clean and operationally healthy on the dashboard-managed local service, but customer-readiness proof is still degraded by configured-target source mismatch. The strongest product opportunities are evidence and adoption lanes: explain or refresh configured-target attestation, move activation beyond 1/6, and distinguish synthetic Ask Yoda benchmark proof from production usage.

Product Strategy preserved these as strategy candidates only. They do not justify automatic SG promotion from this role because they either need Product Owner approval, deployment/attestation authority, production-usage evidence, or a live first-value walkthrough.

## Source-Sync Preflight

- workspace_path: `/Users/toddy/memory-stargraph`
- branch: `main`
- local_head: `c919ec704d6e895c74cb18aaee49438f035ee560`
- upstream_ref: `origin/main`
- upstream_head: `c919ec704d6e895c74cb18aaee49438f035ee560`
- dirty_state: clean before strategy artifact creation
- divergent_state: none
- deployed_service_version: V1.0.209
- gbrain_version: V0.46.28.0
- selected_source_path: `/Users/toddy/memory-stargraph`
- selected_source_surface: dashboard-managed local TLS service plus current checkout
- action_taken: `use_workspace`
- sync_applied: false
- source-sync schema: `memory-stargraph-source-sync-preflight-v1`
- worker routes: route listing completed through `python3 scripts/automation/gbrain_worker_api.py routes`

## Evidence Inspected

- Product, project, persistent goal, canonical SG TODO list, product-strategy TODO list, recent Product Strategy artifacts, recent worker Run/report/Learning surfaces, local Product Owner artifacts available in the checkout, SRE daily evidence, UX dogfood evidence, GBrain X Intelligence evidence, SG-0221 terminal evidence, and current dashboard API readiness surfaces.
- Health: `.85` service ok=true loaded=true, ui_version=V1.0.209, gbrain_version=V0.46.28.0, source mode `gbrain`, source status `lazy-root`, updated_at 2026-08-30T10:34:33Z.
- Persistent search worker: active=true, ready=true, busy=false, process_starts=10, restarts=9, tool_calls=1798, successes=1789, errors=9, timeouts=0, cli_fallbacks=9.
- Ask Yoda MCP pool: active=true, pool_size=5, ready_sessions=5, structured_only=true.
- Backlog: SG-0202 through SG-0221 are completed; SG-0166 remains historical failed/superseded; no planned or implementing root SG TODOs were observed.
- Active tags: `/api/pages?tag=active&limit=200` returned count=0.
- Weekly memory value digest: gates_total=9, gates_passed=8, gates_degraded=1, status=degraded. The degraded gate is configured-target deployment attestation source_mismatch.
- Customer readiness: checks_total=8, ready=6, degraded=1, source_mismatch=1, status=degraded. Ready checks include service health, activation, model configuration, durable storage, resolver pending, and SRE numeric evidence. Configured targets remain source_mismatch.
- Activation funnel: live-ready/privacy-safe, completed 1/6, next step `sample_brain_opened`.
- Resolver health: ready via `local_resolver_ledger_fallback`, pending=0, events_24h=0, auto_approval=false.
- Resolver events endpoint: `/api/resolver/events?limit=20` returned `GBrain backend does not expose resolver_events_list: Unknown tool: resolver_events_list`. Resolver summary health remained available, so this is a detailed-event coverage boundary, not a current product blocker.
- Ask Yoda config: backend `gbrain_think`, model `openai:gpt-5.5`, node runtime status `not_used`, api_key_available=false.
- Ask Yoda logs: latest sampled entries were marked `environment: test`, `synthetic: true`, and `test_run: true`; no production-user Ask Yoda usage or feedback evidence was observed in the sampled recent logs.
- Search probes: `/api/search` results must be read from `graph.source.coverage.search_slugs`, not from a nonexistent top-level `.results` array. Corrected probes for SG-0217, SG-0221, Ask Yoda MCP-only, Memory Stargraph, and people/stacey-soong returned status `complete` with expected slugs and fast elapsed times.
- SG-0221 terminal evidence: Capture Link enrichment readback mismatch was completed and deployed in V1.0.209 at commit `c919ec704d6e895c74cb18aaee49438f035ee560`; acceptance evidence showed first-attempt semantic readback, no failures, and active tags clean.
- SRE Daily 2026-08-30 evidence: retrieval benchmark passed 10/10 answers, 10/10 recall, and 9/9 expected sources; backup and restore evidence were current; search latency median remained the first bottleneck but no incident/TODO was created.
- UX Dogfood 2026-08-29 evidence: no new UX TODOs; search, settings, follow-ups, Ask Yoda evidence, mobile selected-node panel, and focus pass were adequate. Weekly/customer readiness degradation was the already-known configured-target source mismatch.
- GBrain X Intelligence 2026-08-30 evidence: run deferred earlier the same night due dirty source and active SG-0221 work; SG-0221 later terminalized and source is now clean. This is a scheduling/retry coverage boundary, not a product-code defect from this review.
- GBrain X Intelligence 2026-08-29 Learning: shared-memory readiness pressure now spans storage, integrations, latency, and decision context. It remains strategy input, not an implementation-ready SG TODO.

## Perspective Walkthrough

- First-time customer: the local service is healthy and live-ready, but readiness still says degraded because configured-target proof is stale or mismatched. A new customer needs a clear distinction between product risk and evidence/attestation drift, plus a guided path beyond activation step 1/6.
- Daily user: recent functional evidence is strong, but recurring value is still mostly proven through tests, dogfood, and SRE benchmarks. Production Ask Yoda usage and feedback are not yet visible in privacy-safe aggregate form.
- Power user / agent builder: SG-0221 restored Capture Link readback reliability, active tags are clean, and MCP-only Ask Yoda retrieval has terminal evidence. The remaining value gap is knowing which readiness dimensions are proven for live agent workflows versus synthetic checks.
- Operator: backlog and active tags are clean; backup/restore/SRE evidence is current. The main operator ambiguity is configured-target source mismatch, which requires an authorized attestation or deployment-verification lane rather than strategy-role mutation.
- Product Owner: no immediate SG backlog work should be dispatched by Strategy. The useful output is an approval packet: readiness attestation lane, activation walkthrough, production Ask Yoda telemetry, and Stage 1 scale/readiness constraints remain explicit decision points.

## Ranked Opportunities

| Rank | Opportunity | Score | Target user | Decision |
| ---: | --- | ---: | --- | --- |
| 1 | Configured-target attestation recovery and customer explanation lane | 88 | First-time customer, operator, Product Owner | Strategy candidate only |
| 2 | Guided sample-to-live activation checkpoint beyond 1/6 | 85 | First-time customer | Strategy candidate only |
| 3 | Privacy-safe production Ask Yoda usage and feedback telemetry | 82 | Daily user, Product Owner | Strategy candidate only |
| 4 | Shared-memory readiness matrix for storage, integrations, latency, and decision context | 78 | Power user, agent builder, Product Owner | Strategy candidate only |
| 5 | Same-night deferred X Intelligence recovery receipt | 74 | Operator, Product Owner | Strategy candidate only |

## Opportunity Details

### 1. Configured-Target Attestation Recovery And Customer Explanation Lane

- Target user: first-time customer, operator, Product Owner.
- JTBD: "Understand whether degraded readiness means the product is unsafe, or only that configured-target proof has not caught up to current source."
- Evidence: V1.0.209 service is healthy and loaded; SG-0221 was completed and deployed at `c919ec704d6e895c74cb18aaee49438f035ee560`; SRE numeric evidence, backup, restore, resolver, and active tags are current/clean; weekly outcomes are 8/9 and customer readiness is 6/8 only because configured-target attestation has source_mismatch.
- Capability/experiment: a read-only customer-facing explanation or operator receipt that names the attestation source, evidence age, mismatch class, safe next owner, and privacy-preserving status without exposing target coordinates.
- Expected value: reduces false readiness anxiety and makes "degraded" actionable.
- Success metric: readiness source_mismatch includes owner, age, current local source, last attested source, and safe next step; no target coordinates are exposed.
- Smallest validation: Product Owner or authorized operator confirms the intended owner path for refreshing configured-target attestation after V1.0.209, without deployment or target mutation from Strategy.
- Risks/privacy: configured target details must stay redacted; this role must not deploy or refresh attestation directly.
- Why not already covered: SG-0209 and later readiness work made degradation visible; they did not turn source_mismatch into an explicit customer explanation/ownership lane.

### 2. Guided Sample-To-Live Activation Checkpoint Beyond 1/6

- Target user: first-time customer.
- JTBD: "Complete one trustworthy sample-to-live workflow instead of only seeing readiness cards."
- Evidence: activation funnel is live-ready and privacy-safe but remains completed 1/6 with next step `sample_brain_opened`.
- Capability/experiment: guided sample flow that opens the sample brain, selects a node, inspects relationships/provenance, asks a synthetic Ask Yoda question, checks setup diagnostics, and confirms the first live-ready workflow boundary.
- Expected value: turns readiness into first value and makes onboarding less expert-dependent.
- Success metric: sample-only evidence completes at least 4/6 activation steps in one browser session without private data mutation.
- Smallest validation: bounded browser walkthrough using sample data and existing activation API readback.
- Risks/privacy: must clearly separate sample from live GBrain content and avoid private prompts.
- Why not already covered: SG-0164 made activation measurable; current evidence still shows no progression beyond 1/6.

### 3. Privacy-Safe Production Ask Yoda Usage And Feedback Telemetry

- Target user: daily user, Product Owner.
- JTBD: "Know whether Ask Yoda is delivering recurring value in real use, not only passing synthetic checks."
- Evidence: Ask Yoda MCP pool is ready, model config is on `openai:gpt-5.5`, and UX/SRE synthetic evidence is strong; recent logs sampled in this run are synthetic/test only, with no production-user feedback evidence.
- Capability/experiment: aggregate-only usage/feedback summary that separates synthetic/test attempts, real attempts, fallbacks, degraded context, latency, and explicit feedback counts.
- Expected value: aligns recurring value measurement with actual use while preserving privacy.
- Success metric: weekly value digest can distinguish benchmark pass, production usage present, production usage absent, and feedback quality without exposing prompts or node details.
- Smallest validation: read-only count aggregation from existing log provenance fields.
- Risks/privacy: do not expose prompts, private selected-node text, traces, credentials, or user identifiers.
- Why not already covered: SG-0214 labels synthetic entries and SG-0217 hardened retrieval, but neither proves production usage or satisfaction.

### 4. Shared-Memory Readiness Matrix For Storage, Integrations, Latency, And Decision Context

- Target user: power user, agent builder, Product Owner.
- JTBD: "Decide whether Memory Stargraph is ready as a shared local knowledge OS across real agent workflows."
- Evidence: the 2026-08-29 GBrain X Intelligence Learning identifies market/user pressure across storage backend readiness, shared harness/device context, MCP transport latency, nightly synthesis outputs, integrations, forgetting/pruning, and decision-context recall. Current readiness evidence covers some operational dimensions but not a unified product matrix.
- Capability/experiment: an approval-packet matrix that maps each readiness dimension to current evidence, missing proof, privacy boundary, and smallest validation.
- Expected value: converts broad product pressure into an explicit staged readiness plan without premature SG implementation.
- Success metric: Product Owner can approve or reject Stage 1 readiness scope from a single bounded matrix.
- Smallest validation: read-only synthesis of existing SRE, UX, GBrain X, and Product Strategy evidence.
- Risks/privacy: integrations and shared-memory workflows may involve private external accounts; Stage 1 must remain consented and isolated.
- Why not already covered: prior scale/readiness work is approval-gated; current product evidence is distributed across worker reports rather than a customer-facing readiness map.

### 5. Same-Night Deferred X Intelligence Recovery Receipt

- Target user: operator, Product Owner.
- JTBD: "Know when a scheduled intelligence run safely deferred because source was dirty, and whether it needs a later retry."
- Evidence: the 2026-08-30 GBrain X Intelligence capture run deferred before SG-0221 terminalized because source was dirty and active SG-0221 work was in progress. Later evidence shows SG-0221 completed, source clean, and active tags clear.
- Capability/experiment: a recovery receipt or Product Owner sweep rule for same-night worker deferrals caused by legitimate active implementation work.
- Expected value: prevents silent missed learning cycles without creating duplicate product defects.
- Success metric: deferred runs have a terminal owner status: retried, intentionally skipped, or carried to next scheduled cycle.
- Smallest validation: Product Owner read-only review of the deferred X run after source cleanliness is restored.
- Risks/privacy: do not replay captures or mutate watermarks without explicit role authority.
- Why not already covered: Capture Link readback was fixed by SG-0221; this is about schedule recovery governance after a blocked worker deferral.

## Required Product Opportunities

- Make it easier for a new customer: clarify configured-target readiness degradation and guide activation beyond the first recorded step.
- Maximize recurring user value: measure real Ask Yoda usage/feedback separately from synthetic benchmark success, and maintain clean recovery paths for deferred recurring intelligence runs.

## TODO Decision

No SG TODOs were created or updated.

No helper-backed promotion was attempted in this run because the available evidence did not establish a distinct bounded implementation gap under the role prompt. The top items are strategy candidates and approval-packet inputs, not implementation-ready root TODOs.

## Duplicates Suppressed

- SG-0221 already fixed Capture Link enrichment readback mismatch and was completed in V1.0.209.
- SG-0217 already made Ask Yoda GBrain retrieval MCP-only.
- SG-0214 already labels synthetic Ask Yoda test entries.
- SG-0211 and SG-0215 already cover Ask Yoda window height and mobile selected-node panel usability.
- SG-0212 already displays GBrain version beside Stargraph version.
- SG-0213, SG-0216, SG-0210, SG-0209, and SG-0208 cover SRE/readiness backup and restore recency surfaces.
- SG-0218 prevents bare filenames from external links.
- SG-0219 supports graph-query direction for Relationships.
- SG-0220 removes duplicate duration reporting from the Search toolbox.
- SG-0195/SG-0202 and this run's corrected `/api/search` parsing show no current search-health TODO should be created from the initial zero-result parser mistake.
- The 2026-08-11 scale/readiness validation remains `strategy_candidate_no_action` and approval-packet input only until consent manifest, isolated namespace, cost caps, readiness-current gate, and Stage 1 scope are approved.
- The Aug 23 active-tag drift candidate is not current in this run; active tag API count is 0.

## Productization Insight

Memory Stargraph has moved from "can the local system work" toward "can a customer trust the proof surfaces without expert interpretation." The product gap is now the translation layer between healthy internal evidence and customer-adoptable readiness: attestation status, first-value progress, production usage, and staged readiness controls.

## Missing Evidence And Boundaries

- Configured-target source_mismatch is present, but Strategy is not authorized to deploy, refresh attestation, or expose private target coordinates.
- Production Ask Yoda usage/feedback was not observed in sampled logs.
- No browser activation walkthrough was run, so activation remains an API/readiness observation rather than a newly validated UX flow.
- Detailed resolver event listing is unavailable through the backend route, though resolver summary health is ready.
- No direct Product Owner readback had been verified at initial artifact creation time.
- No Agent Reach or external web research was used; local product evidence was sufficient and more authoritative for this scheduled bounded review.

## Artifacts

- Run: `runs/memory-stargraph-divergent-product-discovery-20260830t040141-0700-85`
- Report: `reports/memory-stargraph-divergent-product-discovery-20260830t040141-0700-85`
- Learning: `learnings/memory-stargraph-discovery-20260830-use-coverage-fields-for-search-health`

## Product Owner Delivery Payload

Delivery status after Product Owner readback: `acknowledged_by_product_owner`.

Delivery attempt evidence: `codex_app.send_message_to_thread` accepted the compact payload for destination task `019faa62-6058-7643-b9cc-a2627083af07`. A follow-up `codex_app.read_thread` reached the Product Owner task and showed the Product Strategy delivery payload. A later Product Owner readback accepted the result and explicitly kept all five outputs as strategy candidates only.

Attempted at: 2026-08-30T04:28:00-07:00.

Product Owner acknowledgement received at 2026-08-30T04:30:00-07:00: preserve terminal status `completed_no_new_todo`; accept the V1.0.209/GBrain V0.46.28.0 baseline, clean source/tags, SG-0221 acceptance, retrieval and backup/restore evidence, corrected search-health interpretation, and zero-mutation result as reported; retain configured-target attestation explanation/recovery, guided activation, privacy-safe production Ask Yoda telemetry, shared-memory readiness, and X recovery receipt as strategy candidates only; no SG TODO promotion, Developer dispatch, deployment authorization, resolver approval, or production mutation is approved from this run.

Compact payload: Product Strategy 2026-08-30 completed on .85 V1.0.209 / GBrain V0.46.28.0 / commit `c919ec704d6e895c74cb18aaee49438f035ee560`; source-sync current and clean; no code, deploy, resolver approval, production mutation, private target exposure, or SG TODO promotion; backlog has no planned/implementing root TODOs and active tags count is 0; weekly outcomes 8/9 and customer readiness 6/8 are degraded only by configured-target source_mismatch; SG-0221 Capture Link readback fix is completed/deployed with clean final evidence; SRE retrieval is 10/10 answers, 10/10 recall, 9/9 expected sources; activation remains 1/6; recent Ask Yoda logs are synthetic/test only; corrected `/api/search` parsing shows search probes complete with expected slugs, so no search TODO is justified; top strategy candidates are configured-target attestation explanation/recovery, guided activation beyond 1/6, production Ask Yoda usage telemetry, shared-memory readiness matrix, and same-night X Intelligence deferral recovery receipt; requested Product Owner action is acknowledgement and approval/ownership decisions only, not Developer dispatch.
