---
type: sre_outage_evidence
title: Memory Stargraph SRE GBrain/MCP outage evidence - 2026-07-22
status: preserved_locally
automation_id: memory-stargraph-sre-daily-reliability
mode: daily_reliability
recorded_at: 2026-07-22T07:09:10-07:00
timezone: America/Los_Angeles
source_sync_preflight: passed
local_head: adc05cbd04aa228c309795f3232a524516079e68
upstream_head: adc05cbd04aa228c309795f3232a524516079e68
deployed_service_version: V1.0.154
gbrain_write_available: false
remediation_performed: none
---

# Memory Stargraph SRE GBrain/MCP outage evidence - 2026-07-22

This task-local record preserves additional Product Owner evidence for the existing remote GBrain/MCP/OAuth discovery outage. It was created locally because GBrain write/read path was unavailable.

## Current SRE verification

- Source-sync preflight passed: workspace clean/current at `adc05cbd04aa228c309795f3232a524516079e68`; local source and deployed service version are `V1.0.154`.
- Local Memory Stargraph `/api/health` returned HTTP 200, `ok=true`, `ui_version=V1.0.154`, but `source.status=cached`.
- Local health message: `Using cached graph because seed gbrain load failed: Cannot reach https://toddys-mac-mini.taildb46a7.ts.net/mcp. Run gbrain remote doctor for details.`
- All Things Codex Dashboard reported local Memory Stargraph `ok`, but remote GBrain `down`.
- Dashboard remote GBrain message: `ssh: connect to host toddys-mac-mini.taildb46a7.ts.net port 22: Operation timed out`.
- Configured remote Memory Stargraph health routes timed out.
- Independent SSH corroboration timed out: `ssh: connect to host toddys-mac-mini.taildb46a7.ts.net port 22: Operation timed out`.
- Direct MCP evidence: `gbrain remote doctor` failed with `OAuth discovery failed: OAuth discovery network error: The operation was aborted.`

## Product Owner supplied Developer blocker payload

- worker_task_id: `019f61e6-0d69-7d10-a9f3-f9471b7b460e`
- automation_id: `memory-stargraph-wish-to-reallity`
- invocation_id: `adc05cb-20260722-033046-0700-memory-stargraph-wish`
- terminal_status: `deferred_source_gbrain_unreachable`
- attempted_run_slug: `runs/memory-stargraph-wish-20260722t033046-0700-adc05cb`
- run_record_status: `not_created_gbrain_write_unavailable`
- report_slug: `none_gbrain_write_unavailable`
- source_sync: succeeded; clean worktree fast-forwarded from `af8269e52bf351eca98ccdee931b14406e097cb3` to origin/main `adc05cbd04aa228c309795f3232a524516079e68` with safe `git pull --ff-only origin main` after sandbox FETCH_HEAD permission error.
- preflight: `scripts/automation/preflight.sh` passed local service, dashboard, Chrome CDP, and source sync; remote reachability routes were unverified by preflight.
- health: local `/api/health` returned HTTP 200 and `ui_version=V1.0.154`, but `source.status=cached` with error `Cannot reach https://toddys-mac-mini.taildb46a7.ts.net/mcp. Run gbrain remote doctor for details.`
- blocking_gate: required active Run marker creation failed; `POST /api/entity-save/runs%2Fmemory-stargraph-wish-20260722t033046-0700-adc05cb` returned HTTP 502 with remote MCP unreachable.
- required_compaction: failed before selection; `compact_sg_todo_backlog.py` could not read `notes/memory-starmap-todo-list`.
- direct_mcp_evidence: `gbrain remote doctor` failed with `OAuth discovery failed: OAuth discovery network error: The operation was aborted.`
- containment: no code edits, no TODO selection, no deployment, no resolver mutation, no destructive action.

## Prior same-root evidence

- UX invocation `73d081fc` deferred due source cache/unreachable MCP and 502 writes; no UX journeys/TODOs.
- SRE invocation `d7d34bfb` blocked because local app is healthy from cache but remote GBrain/MCP/SSH is unreachable; Run/report writes could not complete.
- Developer invocation `adc05cb-20260722-033046-0700-memory-stargraph-wish` deferred for the same root cause.

## SRE decision

No remediation was performed. The current evidence shows remote transport/MCP/OAuth discovery unavailability, not two explicit HTTP-unhealthy observations from an authoritative healthy transport path. Under the SRE contract, this evidence preserves the outage and requests recovery verification when the remote path returns.

## Requested recovery

When remote GBrain/MCP recovers, run or await a bounded SRE recovery that verifies:

- local Memory Stargraph live GBrain source, not cache-only;
- GBrain write/read path by creating and reading the SRE Run/report;
- configured remote Memory Stargraph health;
- backup freshness and completeness;
- resolver read-only health and proposal counts;
- no unsafe remediation, resolver mutation, or destructive action.
