# Memory Stargraph SRE incident response — GBrain/MCP recovery

- mode: incident_response
- started_at: 2026-07-22T07:55:00-07:00
- terminalized_at: 2026-07-22T07:42:00-07:00
- affected_target: authoritative GBrain/MCP/write path backing Memory Stargraph
- status: recovered_with_warnings
- run_slug: runs/memory-stargraph-sre-incident-response-2026-07-22-gbrain-mcp-recovery
- report_slug: reports/memory-stargraph-sre-incident-response-2026-07-22-gbrain-mcp-recovery

## Source-sync preflight

- workspace_path: /Users/tony/Documents/Collective Knowledge System
- branch: main
- local_head: adc05cbd04aa228c309795f3232a524516079e68
- upstream_ref: origin/main
- upstream_head: adc05cbd04aa228c309795f3232a524516079e68
- dirty_state: dirty, evidence/report-only paths already present
- divergent_state: not divergent
- selected_source_path: /Users/tony/Documents/Collective Knowledge System
- selected_source_surface: current checkout plus dashboard-managed service
- action_taken: proceeded with incident response; no product code or TODO mutation

## Diagnosis

- Local sandbox loopback initially reported local Memory Stargraph and dashboard as unreachable, but escalated process and curl checks showed both dashboard and local Memory Stargraph processes were present.
- Authoritative remote target A85 had GBrain MCP listening on 127.0.0.1:3131 and Memory Stargraph listening on 8788.
- Remote A85 OAuth discovery from the remote host returned HTTP 200.
- Local `gbrain remote doctor` recovered: connection OK, schema version 123, sync freshness OK, health score 80/100 with warnings.
- Local Memory Stargraph was still serving cached source with the prior remote MCP error until a documented dashboard-managed local restart.

## Remediation

- Applied documented dashboard-managed restart for local Memory Stargraph only.
- No code changes, TODO mutations, resolver events, destructive operations, migrations, privacy expansion, or credential changes.

## Verification

- Local Memory Stargraph health after restart: HTTP 200, ui_version V1.0.154, source.mode=gbrain, source.status=lazy-root, source.updated_at=2026-07-22T14:40:51Z.
- Entity write/readback succeeded through Memory Stargraph HTTP API for `runs/memory-stargraph-sre-incident-response-2026-07-22-gbrain-mcp-recovery`.
- Configured remote A85 health: HTTP 200, ui_version V1.0.154.
- Remote A85 MCP `/mcp` returned HTTP 405 Method Not Allowed to plain GET, which confirms the endpoint is reachable and rejecting the wrong method rather than transport failing.
- Attachment storage: local trusted-host endpoint available; remote A85 local durable root available.
- Backup freshness: dashboard summary reported last backup at 2026-07-21T10:06:35.475Z, backup status OK, with pending changes for next backup.

## Remaining warnings / follow-up

- `gbrain remote doctor` warnings remain: one stalled job older than 1h, older contextual retrieval coverage, and high unextracted edge coverage.
- Secondary configured target A102 is reachable by SSH but does not currently serve Memory Stargraph/GBrain on the checked ports; not the authoritative path for this incident.
- Product Owner should retry blocked Developer, Learning Intake, UX, Curator, and X Intelligence in dependency order after acknowledging this recovery.

## Product Owner notification

- destination_task_id: 019f707d-cad0-7d70-be3e-d78a3f7c78b2
- product_owner_notification_status: pending_unacknowledged_delivery
- product_owner_notification_pending: true
- evidence: cross-thread direct Product Owner messaging/readback is unavailable from this worker context; compact payload preserved here and in the GBrain report.
