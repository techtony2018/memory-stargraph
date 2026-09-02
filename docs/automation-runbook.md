# Memory Stargraph Automation Runbook

Use this runbook for daily GBrain TODO implementation automation and any follow-up work that touches the user-facing Memory Stargraph services.

## Tracked Automation Definitions

Portable definitions for the Memory Stargraph/GBrain automation pipeline live
under `automations/`. They are the Git-tracked source of truth for prompts,
schedules, models, and execution environments. Runtime timestamps, memory,
private deployment configuration, and credentials remain local-only.

See `automations/README.md` for the pipeline order and restore checklist.

## Capture Link Backlog Operations

Initialize and inspect the queue, freeze a worker snapshot, compact completed
rows, and install the repository-canonical skills with:

```bash
python3 scripts/automation/manage_capture_backlog.py init --apply --json
python3 scripts/automation/manage_capture_backlog.py list --json
python3 scripts/automation/manage_capture_backlog.py snapshot --json
python3 scripts/automation/manage_capture_backlog.py compact --apply --json
python3 scripts/automation/install_capture_skills.py --json
```

The root queue is `notes/memory-starmap-capture-list`; its synchronized failure
view is `notes/memory-starmap-capture-list/failed-items`. Requests move through
`planned`, `capturing`, `completed`, and `failed`. A worker invocation takes one
authoritative frozen snapshot of the then-current `planned` rows. It must finish
every frozen row as `completed` or `failed`; rows added afterward remain planned
for the next invocation. The midnight schedule is the default, but operators may
trigger the persistent worker manually at any time.

Request nodes own uploaded attachments. Upload and verify each attachment once,
then let the final captured node reuse the durable reference and SHA-256 without
copying the bytes again. Link request to result with `captured_as` and result to
request with `captured_from`. Failed rows remain active in the failure view until
explicitly requeued or resolved. Compaction creates immutable archives for each
full batch of 50 completed rows while leaving active and residual rows at the
root.

All worker-generated timestamps and evidence use timezone-aware ISO 8601 in
`America/Los_Angeles`: PDT (`-07:00`) in summer and PST (`-08:00`) in winter,
never a fixed UTC-8 offset.

## Required Preflight

Run this before implementation work:

```bash
scripts/automation/preflight.sh
```

The preflight records the active `CODEX_HOME`, checks required binaries, probes the configured dashboard/local service, verifies Chrome CDP at `127.0.0.1:9333`, and checks configured remote health routes. Concrete deployment routes belong in the local-only config, not in the public repo.

Before any recurring Memory Stargraph worker performs role-specific work, it must
run a source-sync preflight for its local checkout. Record the workspace path,
branch, local `HEAD`, configured upstream, upstream `HEAD`, dirty/divergent
state, deployed Memory Stargraph version when applicable, and selected source
surface in the Run/report. If the checkout is clean and only behind the
configured upstream, the worker should fast-forward safely and continue from the
updated workspace. If the checkout is dirty, divergent, detached, fetch fails,
or the safe upstream is ambiguous, the worker must not overwrite local work; it
must block or defer truthfully with `source_sync_preflight=blocked` and request
Product Owner/Developer coordination. A worker may use a deployed service copy
only as an explicit fallback surface, and must record that choice instead of
presenting the stale local checkout as authoritative.

Shared recurring-worker source-sync evidence schema:

- `workspace_path`
- `branch`
- `local_head`
- `upstream_ref`
- `upstream_head`
- `dirty_state`
- `divergent_state`
- `deployed_service_version`
- `required_script_existence`
- `selected_source_path`
- `selected_source_surface`
- `action_taken`

Every recurring worker must record this schema before script-dependent work,
including Developer, UX, SRE daily, SRE weekly, Product Owner/Goal Steward,
Daily Learning Intake, Capture Link Drain, Product Strategist, and X
Intelligence Capture. Clean stale checkouts use fast-forward-only sync when
allowed. Dirty, divergent, detached, ambiguous-upstream, or fetch-failed
checkouts preserve unrelated local changes and record a blocker or explicit
fallback surface. Product Owner verification should not require raw terminal
logs to establish source identity.

Use the maintained helper when available:

```bash
python3 scripts/automation/source_sync_preflight.py --root . --dashboard-ui-version "$UI_VERSION" --sync-clean-fast-forward --json
```

The helper performs only fast-forward-only syncs for clean stale checkouts. It
does not overwrite dirty or divergent worktrees.

All recurring Memory Stargraph roles must be able to access GBrain data and the
configured local/remote Memory Stargraph APIs. Use top-level `curl -sS` calls to
the Memory Stargraph HTTP APIs for sandbox-safe GBrain reads, writes, search,
graph, backlinks, Ask Yoda logs, health, and configured remote Stargraph routes.
Use `python3 scripts/automation/gbrain_worker_api.py routes` only to list the
local and remote routes from the private deployment-target config; do not use
Python networking for worker API calls because sandboxed Python sockets may be
blocked. Direct `gbrain` CLI/MCP access is optional and must be preflighted; a
remote MCP transport failure is not a reason for a worker to stop if the HTTP API
can reach GBrain through Memory Stargraph.

Preflight health is tri-state: every target is `healthy`, `unhealthy`, or
`unverified`. A failed loopback or transport probe from a restricted or unknown
execution context is always `unverified`, never an outage by itself. Configure
`MEMORY_STARGRAPH_AUTHORITATIVE_LOCAL_HEALTH_URL` and, when available, an
independent `MEMORY_STARGRAPH_LOCAL_CORROBORATION_URL` in the private deployment
file. The analogous dashboard variables are
`MEMORY_STARGRAPH_AUTHORITATIVE_DASHBOARD_URL` and
`MEMORY_STARGRAPH_DASHBOARD_CORROBORATION_URL`. The preflight retries through
the authoritative host-context route and reports `unhealthy` only after that
route and an independent corroboration route both return explicit HTTP-unhealthy
responses. The preflight preserves typed outcomes: `healthy`,
`http_unhealthy`, and `transport_unverified`. Dual transport failures and mixed
transport-plus-HTTP failures remain `unverified`; only two explicit
HTTP-unhealthy observations may produce `unhealthy`. A single-route remote
failure stays `unverified`.

## Developer and UX Deployment Quiescence

The Memory Stargraph Developer and UX Engineer use Goal-linked Runs as
cooperative change and UX leases. The protocol applies to scheduled and manual
invocations and has no fixed kickoff or cutoff time.

Before editing code, restarting a service, or deploying, the Developer creates
or updates an active Goal-linked Run with an `active-change` marker, invocation
id, start time, intended scope, and deployment fingerprint. Every health sample
records `health_observed_at` and any source timestamp as evidence. Stable deployment fingerprint fields: `health_state`, `ui_version`, `served_html_js_identity`, `process_cwd`, `source_deployment_identity`.
`served_html_js_identity` is the served HTML/JS asset version or hash;
`process_cwd` is the local process cwd when available; and
`source_deployment_identity` is included only when its source documents it as
stable. `health_observed_at` and source timestamp evidence are volatile and are
excluded from deployment fingerprint equality.

Before journeys, UX verifies there is no active Developer marker, records the
fingerprint, creates an active UX Run/lease, and re-reads active Runs. If an
Developer marker appeared concurrently, Developer priority wins and UX
terminalizes as `deferred_due_to_active_change`. UX rechecks the marker, health,
and stable fingerprint before and after every journey. It defers only when an
active-change marker appears, health is unhealthy or unstable, or the stable
fingerprint changes; different observation or source timestamps alone do not
cause deferral. On any qualifying instability it stops,
discards all observations from that invocation, creates or updates no TODOs,
and records before/after evidence.

Before restart or deployment, the Developer re-reads active UX leases. It waits
for UX to acknowledge and terminalize and must not silently deploy through an
active UX lease. The Developer clears its marker only after target health,
version, served HTML/JS, and process-cwd verification passes. Failure,
interruption, or crash evidence remains visible. A stale UX lease or stale
Developer marker requires Product Owner resolution and is never bypassed
automatically.

When resolving stale active metadata, Product Owner must clear both raw
markdown/frontmatter and GBrain page tags. A terminal Run can still block
quiescence if the tag API or page metadata contains `active` after the raw body
has been rewritten. Use the Stargraph tag endpoint, for example
`/api/entity-tags/<slug>`, or `gbrain untag <slug> active`, then verify raw
readback has no standalone `active` tag, no active title/body marker, and
semantic fields such as `ux_lease` and `active_change` are false.

Recurring Learning and Daily/Weekly SRE evidence execution runs through the host-managed
recurring worker bridge because restricted Codex worker tasks may have no
TCP/network access even when the host service is healthy. Canonical task workers
use `python3 scripts/automation/recurring_worker_bridge.py submit`, `status`,
and `write-bundle` as offline local-file operations only. They must not use
task-local curl, Python networking, direct `gbrain`, PostgreSQL, resolver
approval, loopback, dashboard TCP, or fallback transports for canonical
Learning/SRE evidence or persistence.

The bridge is a strict allowlisted spool for `daily_learning_intake` and
`sre_daily_reliability`, preserving the separate `capture_link_drain` runner
contract below. Each role supports only two operations:

- `evidence`: the canonical task submits a versioned local request containing
  role, automation id, operation, invocation id, expected commit, mode,
  created_at, nonce/idempotency key, and synthetic flag when applicable. The
  `.85` host runner gathers bounded authoritative evidence and writes a
  terminal local evidence bundle.
- `persist`: the canonical task reasons only over the local evidence bundle,
  writes a schema-valid decision/artifact bundle with `write-bundle`, submits a
  local persist request, and waits for the host runner to validate and persist
  artifacts with readback evidence.

The request/result protocol validates role and operation allowlists, ownership,
path confinement, size limits, freshness, nonce replay/idempotence,
single-runner concurrency, atomic claim/result rename, stale processing
recovery, crash recovery, subprocess timeouts, terminal cleanup, and bounded
audit state. Runner state and terminal results include daemon source identity:
`runner_host_commit`, `runner_started_at`, `runner_instance_id`, `runner_pid`,
supported request/evidence schema versions, deployed-source match, and
stale-reason evidence. A request whose expected commit or evidence schema does
not match the loaded daemon terminalizes before evidence collection or artifact
persistence. Deployments reload the launchd-managed `.85` recurring bridge
daemon after bridge code changes and attest the refreshed commit/schema before
accepting the deploy as complete. Runner state includes phase heartbeats with `phase`,
`phase_started_at`, `phase_updated_at`, `heartbeat_at`, active invocation,
runner ownership, and `processed/total` progress where known. Polling remains
local-file only for up to 10 minutes while daemon heartbeat is fresh and
ownership is stable; fail early only on terminal failure, stale heartbeat,
ownership change, stale source/schema identity, or hard deadline. Only `.85` enables the bridge with
`MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED=1`, normally through launchd label
`com.tony.memory-stargraph.recurring-worker-bridge` using the tracked
`scripts/automation/com.tony.memory-stargraph.recurring-worker-bridge.plist`.
`.102` receives code but keeps Learning/SRE evidence and mutation runner
operations disabled by default.

Daily Learning evidence includes service health, bounded raw Goal/product/TODO
and runbook context, a 10-question evaluator evidence slot with
model/fallback/context status, production feedback and no-action review state,
resolver metrics/proposals, duplicate-aware existing TODO/Learning context, and
evidence gaps. SRE evidence includes source/quiet-time confirmation, local and
configured-target health slots, retrieval-quality baseline evidence, and a
privacy-safe `memory-stargraph-sre-numeric-evidence-v1` block. That numeric
block is read-only and carries CPU, memory, disk, cache, open-file,
queue/backlog, health/search latency, 7-day and 30-day baseline, backup
freshness, and restore-rehearsal recency samples with explicit units, sampling
windows, thresholds, source/readback timestamps, and truthful
missing/stale/partial states. Weekly resilience uses the same offline bridge
with `--mode weekly_resilience` for the read-only evidence phase before any
separately authorized weekly synthetic load or safe-fault reasoning. Daily
Learning decision bundles may persist a no-action Run and
report, a Learning node under `notes/memory-stargraph-learnings/`, or a planned
TODO under `notes/memory-starmap-todo-list/` with duplicate-policy metadata.

Daily SRE evidence includes source/quiet-time confirmation, local/dashboard and
configured `.102` health slots, resolver status, bounded read-only latency,
resource, storage, and backup evidence, and incident/no-incident
classification. Daily SRE decision bundles persist Run/report/TODO decisions
only; restart, remediation, resolver mutation, or production changes require a
separate incident contract and explicit authority.

Persisted worker artifacts are constrained by role-specific slug prefixes,
frontmatter/status requirements, link requirements, duplicate TODO metadata,
and readback verification. The bridge exposes no arbitrary command execution,
arbitrary paths, arbitrary slugs outside allowed role prefixes, raw database
coordinates, resolver approval fallback, task-local network fallback, direct
GBrain fallback, or PostgreSQL fallback.

Canonical Capture Link execution runs through a host-managed local spool on
`.85` because restricted Codex worker tasks may have no TCP/network access even
when the host service is healthy. The Curator submits a local request file with
`python3 scripts/automation/capture_link_host_runner.py submit --invocation-id
<id> --expected-commit <commit> --mode auto --json` and reads terminal state
with `python3 scripts/automation/capture_link_host_runner.py status
--invocation-id <id> --json`. These submit/status commands are offline
local-file operations. The request schema is versioned and allowlisted to the
single `capture_link_drain` operation with invocation id, automation id,
expected commit, mode, created_at, and nonce/idempotency key. The host runner
validates path confinement, size limits, freshness, replay/idempotence,
expected source revision, single-runner lock, stale processing recovery, bounded
subprocess timeouts, and terminal result schema before writing a result file. Runtime state lives under
`var/capture-link-runner/` or `MEMORY_STARGRAPH_CAPTURE_RUNNER_DIR`, which is
gitignored. Only `.85` should enable the runner with
`MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED=1`; `.102` receives code but keeps the
runner disabled. `.102` receives code but keeps the runner disabled by default
to prevent duplicate canonical mutations. The
runner exposes no arbitrary command execution, arbitrary path or slug writes,
raw database coordinates, task-local network fallback, direct GBrain fallback,
or approval fallback.

Curator polling remains local-file only. Poll for up to 10 minutes unless a
Product Owner-approved runner maximum is longer. Continue while daemon
`heartbeat_at`/`phase_updated_at` values are fresh and runner ownership remains
stable; fail early only on terminal failure, stale heartbeat, runner ownership
change, or the hard overall deadline. Runner state includes `phase`,
`phase_started_at`, `phase_updated_at`, active invocation, and `processed/total`
progress where known.

For an empty authoritative snapshot, `completed_empty_snapshot_noop` is
forbidden. The host runner must run deterministic empty-queue enrichment or
terminalize with deterministic no-eligible-candidate evidence. Terminal results
include selection version, inspected scope, `scope_complete`,
`total_scope_count`, `inspected_count`, `uninspected_count`,
`selection_truncated`, `evidence_display_truncated`, candidate count, exclusion
counts/reasons, ordered candidates, reservation persistence/readback evidence
before entity mutation, outcomes, failures, metrics, and logically consistent
no-candidate fields. `no_eligible_candidate=true` is valid only when the
complete declared scope was inspected and no eligible candidate exists. If a
bounded inspected scope finds no candidate while uninspected rows remain, the
result must name that bounded claim and set `no_eligible_candidate=false`.
Daemon-produced ownership evidence includes `runner_host_role=.85-authoritative`,
`runner_enabled=true`, `runner_instance_id`, pid/start time, atomic request
claim, and `.102` runner-disabled verification. Offline `status` and `health`
commands must distinguish the submitter process context from daemon state so a
submitter-side `MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED=0` cannot be mistaken
for the authoritative `.85` daemon being disabled.

## SRE reliability and resilience

`memory-stargraph-sre-daily-reliability` runs daily at 3:00 AM and
`memory-stargraph-sre-weekly-resilience` runs Sunday at 11:00 AM in
`America/Los_Angeles`. Codex permits only one active heartbeat per task, so
they target distinct persistent Memory Stargraph SRE tasks while sharing the
same worker prompt, role, and quiet-time contract.

The SRE operates only when live task state and Goal-linked Runs/leases show no
other Memory Stargraph work. Busy or racing invocations defer as
`deferred_due_to_worker_activity`; other workers take priority. Daily work
checks deployed health, version and served-asset identity, resources, storage,
backups, attachments, resolver health, worker trends, and capacity headroom.
Bounded remediation uses only documented retry, dashboard-managed restart,
cache/routing recovery, or documented last-known-good rollback with before and
after verification.

The local MacBook alert monitor is documented in
`docs/memory-stargraph-alert-monitor-runbook.md`. It checks every configured
Memory Stargraph instance plus the read-only GBrain `index` path and sends
email only for persistent, deduplicated issues. Normal deployments and SRE
operations must suppress alerts before service mutation and clear suppression
after successful verification:

```bash
python3 scripts/automation/memory_stargraph_alert_monitor.py suppress --minutes 45 --reason "SRE documented remediation"
python3 scripts/automation/memory_stargraph_alert_monitor.py clear-suppression
```

`scripts/automation/deploy_targets.sh` applies that suppression automatically.
SRE incident response, daily reliability follow-up, and weekly resilience runs
must use the same suppress/clear commands around documented restart, rollback,
failover, or network-route remediation steps so Tony is alerted for unattended
problems rather than expected maintenance.

Warm-standby GBrain authority is documented in
`docs/memory-stargraph-gbrain-warm-standby-runbook.md`. A Secondary Mac mini may be
restored daily from backup and promoted only through the configured failover
helper after Primary failure, fresh Secondary restore/readiness, and post-switch
fleet verification are proven. This is warm standby, not multi-primary
replication; automatic failback is forbidden until a reconciliation path is
tested.

Weekly work adds gradual synthetic load, isolated temporary restore rehearsal,
and one safe fault at a time on an explicitly synthetic, disposable, or
redundant target. Without a safe target it records
`chaos_skipped_no_safe_target`. Resolver health checks are read-only. An
end-to-end resolver probe requires `environment=test`, `synthetic=true`,
`test_run=true`, and `pair_id=sre:{mode}:{invocation_id}:{probe_slug}`; when
isolation cannot be verified, record
`resolver_probe_skipped_isolation_unverified` and skip the probe.

Weekly resilience safe-fault target policy: until Product Owner approval is
recorded in the weekly Run/report, the only permitted fault target strategy is a
no-op synthetic harness that exercises SRE classification, abort gates,
rollback-evidence capture, and post-probe health verification without stopping,
restarting, throttling, deleting, mutating, or redirecting production Memory
Stargraph, GBrain, resolver, dashboard, backup, or remote services. The target
identity is `synthetic-noop-fault-harness`; its blast radius is report-only; its
rollback path is to remove the in-memory harness state and preserve
`chaos_skipped_no_safe_target` for any real fault. Any disposable service,
redundant node, restart drill, failover drill, or resource fault requires an
explicit Product Owner approval decision before provisioning or use.

### Product Owner incident handoff

The Product Owner also uses healthy, unhealthy, or unverified classification.
It must never report an outage from a transport failure alone. After a direct
failure it retries an authoritative host-context route and requires independent
corroboration from process, dashboard, user-impact, or separately authoritative
remote evidence. Conflicting or inaccessible evidence remains `unverified`.

On a confirmed outage, the Product Owner completes and terminalizes its own
review before dispatching an evidence-only `mode=incident_response` handoff to
the persistent daily SRE task. The handoff contains the originating Product
Owner task id, logical affected target, timezone-aware America/Los_Angeles
timestamp, authoritative failure, and independent corroboration, without
secrets or private coordinates. The SRE waits for verified quiet time, creates
a Goal-linked Run and incident report, diagnoses from authoritative context,
applies only bounded documented remediation, verifies recovery, releases its
lease, and sends a concise result back to the originating task. Incident mode
must not create resolver events or synthetic resolver/Ask Yoda traffic.

## Product Owner accountability and progress metric

The Product Owner owns progress across roles, not report forwarding. Each daily
review must reconcile the expected schedule, live automation state, persistent
destination task, latest heartbeat, latest terminal Run, and latest report for
every recurring Memory Stargraph role. Missing terminal evidence, a stale active
Run, wrong destination task, unexpected paused state, or a report that lacks the
required outcome evidence is treated as `blocked_or_silent`.

For each `blocked_or_silent` role, the Product Owner takes the next safe
coordination action in the same review: follow up in the persistent worker task,
dispatch the proper role for diagnosis, create or update one evidence-backed
TODO when a product fix is needed, or ask Tony only when human authority is
required. Examples, setup-only results, plans, and partial progress do not count
as completion. A Developer run that does not terminalize selected TODOs as
`completed` or `failed` with evidence is a failed coordination outcome.

Every Product Owner report includes a daily `Goal progress` percentage. The
stable rubric is:

| Dimension | Weight |
| --- | ---: |
| Usability and onboarding | 15% |
| Retrieval and Ask Yoda answer quality | 20% |
| Continuous-learning feedback loop | 20% |
| Reliability, backup, restore, and SRE readiness | 15% |
| Data quality, relationships, backlinks, and capture coverage | 10% |
| Productization, adoption readiness, and packaging | 10% |
| Automation governance, role health, and human-control safety | 10% |

Each dimension is scored from 0-100 using current Runs, TODO states, tests,
deployments, health checks, UX/SRE/Learning reports, resolver evidence, capture
quality, and user feedback. Missing evidence lowers confidence and becomes a
coordination action. The Product Owner records scores in
`automations/memory-stargraph-goal-steward-daily-review/goal-progress-ledger.json`
and reads that ledger before scoring. Reports include the delta from the latest
prior ledger entry, including previous score, date, and source slug. Use
`baseline established` only when the ledger has no previous entry and a recovery
search of prior Product Owner Run/report slugs also finds no previous score.
Every report and user-facing Product Owner briefing includes the seven dimension
scores with day-over-day deltas/trends from the prior ledger entry, not only the
weighted total. If a prior ledger entry lacks dimension scores, mark the
dimension trend as `no prior dimension baseline` while still reporting the
weighted total delta. Every report includes the one highest-leverage action to
improve the percentage.

Every Product Owner briefing also reports the latest running duration for each
recurring worker automation reviewed: start time, finished/deferred/failed time
when available, elapsed wall-clock duration, expected duration/window from the
Worker Watch contract, and classification (`within_expected`, `slow`,
`stale_or_missing`, `deferred`, or `unverified`). Missing or inconsistent
timestamps are evidence gaps and must be assigned to the owning worker or
Product Owner automation governance.

After the daily report, the Product Owner runs a short retrospective comparing
today against the previous Product Owner report: metric values, role outcomes,
TODO movement, health and reliability evidence, user feedback, Ask Yoda quality,
capture/data-quality progress, and automation governance. Regressions, stalled
metrics, missing day-over-day evidence, and role failures receive an immediate
coordination action in the correct role boundary unless human approval is
required. If the current role set is insufficient, the Product Owner proposes a
new role or schedule change for Tony's review with scope, trigger, success
metrics, safety boundaries, and why existing roles cannot cover it. New
recurring roles require Tony's approval before creation.

Team/process retrospection is part of the daily ritual. Every Product Owner
Run/report and user-facing briefing includes the automation-duration table plus
a concise `Gaps found / improvements made` section with: gaps found today,
improvements already made during the review, verification evidence for those
improvements, gaps intentionally carried over, owner/role for each carry-over,
and whether human approval is needed. For slow, stale, missing, deferred, or
unverified durations, the briefing names the time sink, root cause if known,
permanent prevention added or assigned, and any remaining risk for tomorrow.

### Daily Yoda Evaluator

The Memory Stargraph Quality & Learning Analyst owns the daily Yoda Evaluator
inside `memory-stargraph-daily-learning-intake`; do not create a separate
recurring worker unless Product Owner proposes it and Tony approves it.

Each daily intake runs:

```bash
python3 scripts/automation/yoda_gap_evaluator.py run --output /tmp/yoda-evaluator-snapshot.json
```

The evaluator asks the Ask Yoda API at least 10 active questions over recent
daily dev, monitoring, TODO, logs, product, reliability, UX, and data-quality
evidence. It maintains a larger question pool. By default it reads the local
persistent no-gap log at `data/yoda_gap_evaluator_question_log.json`, skips
questions that previously produced `no_action` / no noticeable gap, and replaces
them from the remaining pool so the next run keeps probing new surfaces. Every
request uses `environment=test`, `synthetic=true`, `test_run=true`, and a stable
`pair_id` so resolver telemetry and user-quality scoring can isolate the
synthetic probes.

The Codex worker then answers the same question in Codex using the same
available evidence, compares the Codex answer to the Ask Yoda API answer, and
classifies the gap. Run:

```bash
python3 scripts/automation/yoda_gap_evaluator.py report --snapshot /tmp/yoda-evaluator-reviewed.json --output /tmp/yoda-evaluator-report.json
```

Create or update TODOs only for bounded, deduplicated, evidence-backed
`todo_candidate` gaps. Stylistic disagreement alone is not a TODO. The report
step appends reviewed `no_action` questions, no-gap summaries, and bounded Yoda
/ Codex answer excerpts to `data/yoda_gap_evaluator_question_log.json` for
operator review and future replacement. Preserve reviewed evaluator snapshots or
concise sanitized summaries in the Run/report; do not copy raw private
questions, answers, comments, secrets, or chain-of-thought into GBrain.

### Worker completion notification

Worker tasks remain the system of record for detailed execution reports. After
a terminal outcome or deferral, every recurring worker sends the canonical
Product Owner task a compact notification: worker task id, automation id,
invocation id, terminal status, Run/report slugs, changed TODO ids or no-op
reason, key metrics changed, blockers, approvals needed, and requested Product
Owner follow-up. The Product Owner then enters or inspects the worker task and
verifies the report, Run evidence, TODO/status transitions, deployment or
capture evidence, and metric claims before counting the work as progress. If
direct task messaging is unavailable, the worker records
`product_owner_notification_pending` with the same payload in its Run/report.

Delivery is not successful from a send call alone. The worker may set
`product_owner_notification_pending: false` only after the Product Owner task
acknowledges, starts a fresh turn, or readback shows the payload was appended to
the canonical Product Owner task. If the thread-message tool is unavailable,
exposed but not callable in the turn, errors, times out, or returns without
acknowledgment, the worker must record
`product_owner_notification_status: pending_unacknowledged_delivery`,
`product_owner_notification_pending: true`, the attempted timestamp, destination
task id, exact tool error or no-ack evidence, and the full compact payload in
both the Run and report. During Product Owner review, recover that payload from
the worker Run/report, verify the worker outcome, then update the worker
Run/report to `product_owner_notification_status: acknowledged_by_product_owner`
and `product_owner_notification_pending: false` before coordinating any retry or
blocker handoff.

Product Owner reviews and worker-watch cleanup turns must not depend solely on
inbound cross-thread notifications. At the start of each full review and after
any watched worker terminalizes, the Product Owner sweeps the latest terminal
Run/report evidence for `product_owner_notification_pending: true` or
`product_owner_notification_status: pending_unacknowledged_delivery`, recovers
the compact payload, verifies it against the worker task/Run/report, and
acknowledges it in both Run and report. A worker statement that direct Product
Owner messaging was unavailable is expected fallback behavior when the compact
payload is present; it is a governance blocker only when the payload is missing,
not verifiable, or cannot be acknowledged through Memory Stargraph.

### Manual worker dispatch verification

When the Product Owner manually dispatches or retries any recurring worker,
resolve the canonical destination with Codex `list_threads` first. Record the
destination task id, role title, and prompt purpose in the Product Owner Run.
Send the bounded prompt with Codex `send_message_to_thread`, then verify the
same destination task with Codex `read_thread`.

Do not claim dispatch success from a send call alone. A successful dispatch
requires readback evidence that the destination task has an active or terminal
turn for the requested prompt. If there is no active or terminal readback,
record `no active or terminal readback`, send at most one bounded recovery
follow-up to the same canonical task, and report the blocker or recovery result.
Never create a duplicate worker task merely to hide a failed dispatch.

### Product Owner Worker Watch

Completion notifications are not enough because a system error can prevent a
worker from ever reaching its terminal handoff. Because Codex permits only one
heartbeat per task, the canonical `memory-stargraph-goal-steward-daily-review`
heartbeat combines interim Worker Watch checks with the full morning Product
Owner review. The watch windows give the Product Owner role-specific estimated
durations after each scheduled worker heartbeat.

The watch is a control-tower check, not another implementation worker. It uses
`America/Los_Angeles` time, inspects only roles whose watch window is relevant
or overdue, and compares live automation state, canonical destination task,
latest task activity, Goal-linked Run/report evidence, and Product Owner
notifications. It treats missing starts, stale in-progress runs, wrong
destination tasks, unexpected pauses, duplicate recurring tasks, stale leases,
failed tool/auth gates, `system error`, `model out of capacity`, `modal out of
capacity`, and repeated retry loops as `blocked_or_silent`.

When a role is `blocked_or_silent`, the Product Owner takes the next safe action
immediately: send a bounded follow-up to the canonical worker task asking it to
resume from durable evidence, terminalize truthfully, or report the blocker;
route confirmed infrastructure or health failures to the daily SRE task using
the incident handoff contract; or ask Tony only when human authority is
required. If the same capacity or system error recurs twice in the same role
window, record it as a Product Owner-visible blocker and request a bounded retry
or reschedule instead of silently waiting for the next day. The watch reports
only anomalies and actions taken, or a short quiet status when all relevant
roles are inside their estimate.

If a worker truthfully defers because another worker is active, the Product
Owner owns the retry chain. The Product Owner must verify the blocking worker,
create or update a temporary 10-minute watch for that blocking worker, and
record which deferred worker must be retried after the blocker terminalizes.
When the blocking worker terminalizes, fails with evidence, truthfully defers,
or transfers ownership, the next watch immediately retries or dispatches the
originally blocked worker if quiet-time rules allow it. Do not leave
`deferred_due_to_worker_activity` for the next daily review when the blocking
worker has a terminal condition that can be watched.

## TODO Backlog Compaction

The root backlog `notes/memory-starmap-todo-list` must stay lightweight. Run this before selecting nightly work and again after final TODO status updates:

```bash
python3 scripts/automation/compact_sg_todo_backlog.py --apply --json
```

The helper moves each full batch of 50 completed TODO rows into immutable archive collection nodes named `notes/memory-starmap-todo-list/completed-archive-0001`, `completed-archive-0002`, and so on. The active root keeps all `planned`, `implementing`, and `failed` rows, followed by only the remaining 0-49 completed rows. Failed rows are also mirrored to `notes/memory-starmap-todo-list/failed-items`.

Use dry-run mode before risky manual repairs:

```bash
python3 scripts/automation/compact_sg_todo_backlog.py --json
```

Compaction is idempotent: existing completed archives are not rewritten or duplicated, but their rows are removed from the active root if a prior run stopped before the root rewrite. Treat compaction failure as a real automation failure unless GBrain itself is unreachable.

When GBrain is unreachable, do not bury the failure in logs. The worker must surface it to Product Owner before finalizing the Run: record the exact failed command, endpoint or host evidence, containment used, and smallest recovery action in a Product Owner-visible Run section or planned TODO under `notes/memory-starmap-todo-list`, then send an explicit Codex follow-up notification to the active Memory Stargraph Product Owner task. If the Product Owner task cannot be found or the send fails, record that failed notification attempt in the Run and final report. If the Wish/Developer worker files a TODO for a blocker in its own required workflow, that TODO is owned follow-up work for the next eligible Wish/Developer cycle unless Product Owner redirects it.

## GBrain Capture Quality Gate

Use this before completing any GBrain capture/import work, including WeChat, LinkedIn, X/Twitter, web pages, PDFs/text extraction, and personal notes.

1. Keep identity and display separate:
   - Stable slugs may use source IDs, dates, activity IDs, WeChat `tid` values, or hashes.
   - Visible node titles must be plain human content from the captured body, not generic labels such as `LinkedIn Post <id>`, `Tony WeChat Post <date>`, `X Post <id>`, or `Untitled` when meaningful content exists.
2. Sanitize title candidates before writing frontmatter `title:` or an H1:
   - Strip leading frontmatter fences and YAML-looking metadata such as `---`, `title:`, `tags:`, `type:`, `slug:`, source/platform/date fields, and YAML list-marker metadata.
   - Normal markdown/frontmatter metadata may still exist in the page; the rule is that metadata text must not leak into the node title.
3. Preserve provenance explicitly:
   - Keep source URLs, source IDs, timestamps, platform fields, and typed graph links in metadata or body sections.
   - Do not encode provenance by making the title a source ID.
4. Verify representative generated pages before import or final report:

```bash
rg -n "^# (LinkedIn Post|Tony WeChat Post|WeChat Post|X Post|Twitter Post|Untitled)" <generated-pages-dir>
rg -n "^(title: [\"\x27]?(---|title:|tags:|type:|slug:)|# (---|title:|tags:|type:|slug:))" <generated-pages-dir>
```

Both commands should return no matches for newly generated capture pages. Also spot-check at least one content-rich page and one low/no-text fallback page.

## Attachment Regression Release Gate

[GBrain Attachment Safety and Verification](gbrain-attachment-runbook.md) is the single source of truth for attachment writes, replacement, repair, evidence, cold-cache recovery, backup/restore, and release acceptance. The [remote media topology runbook](memory-stargraph-remote-gbrain-media-import-runbook.md) may extend host-routing guidance but must not define a competing upload path.

Attachment-related automation must obey these rules:

1. Upload only through Memory Stargraph's `POST /api/entity-attach-file/<URL-encoded-slug>` boundary, normally via the UI, `upload_attachment_via_stargraph.py`, or `add_sg_todo.py --attachment`.
2. Never call host-local file-upload commands directly from a thin client, capture skill, or ad hoc agent script.
3. Require `durable_storage_verified: true`, canonical relative path, exact byte count, exact SHA-256, one matching ledger row, and served-byte readback before reporting success.
4. Treat Stargraph `media/` directories as disposable caches. A warm cache or ledger row alone is not completion evidence.
5. On replacement, preserve prior bytes or a verified backup before a same-path overwrite. Keep deletion/legacy cleanup in a separate explicitly reviewed operation.
6. Do not mark an attachment/storage TODO completed until a real upload, idempotent retry, target durable-object check, and cold-cache recovery pass on every required target.

Every attachment/storage release must run:

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_documentation_contracts
python3 -m unittest discover -s "$HOME/.codex/skills/gbrain-capture-link/tests"
python3 -m unittest discover -s "$HOME/.codex/skills/add-sg-todo/tests"
```

Run the GBrain durable-storage tests and TypeScript check in the active GBrain implementation worktree, then follow the canonical runbook's real integration gate. If any required layer is unavailable, record a concrete failure and recovery action instead of weakening the contract.

## Add SG TODO Atomic Allocation

The canonical `add-sg-todo` source is `${CODEX_HOME:-$HOME/.codex}/skills/add-sg-todo`; keep its OpenClaw mirror byte-identical. Every mutating invocation must hold the helper's bounded process/file allocation guard across the authoritative parent high-water read and parent/child/`has_todo` commit.

- Include active root rows and every validated completed archive in the high-water calculation. Missing, duplicate, gapped, or inconsistent archive evidence fails closed.
- Stage a new child as `capture-recovery`; write the parent row and `has_todo` relationship before finalizing the child to `planned`. This prevents a crash or partial write from leaving an orphan child falsely marked planned.
- Return `ok: true` only after the parent row ID, child `todo_id`/status, and graph relationship all read back durably.
- Lock contention and failed commit/readback return a structured retryable result. Bounded rollback must restore the parent and prior child or remove the new child and relationship; cleanup uncertainty remains a failure.

Release verification must run both mirror suites and include concurrent text-only allocation, lock contention, partial parent/link failure, archive high-water, and mirror-identity coverage:

```bash
python3 -m unittest discover -s "$HOME/.codex/skills/add-sg-todo/tests"
python3 -m unittest discover -s "$HOME/.openclaw/skills/add-sg-todo/tests"
```

## Deployment Targets

Keep deployment target details in local Codex memory/config and GBrain, not in tracked GitHub files. The deploy helper reads:

```bash
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-wish-to-reallity/deployment-targets.env
```

That local file should define the dashboard-managed local service path, either `MEMORY_STARGRAPH_DASHBOARD_RESTART_URL` or `MEMORY_STARGRAPH_DASHBOARD_RESTART_COMMAND`, any local curl flags needed for TLS verification, remote SSH targets, remote repo paths, restart commands, and verification URLs. Hosts may set `MEMORY_STARGRAPH_DEPLOY_TARGETS` to an empty value for local-only deploy verification when no safe remote target is configured.

After commit and push, deploy the exact commit with:

```bash
scripts/automation/deploy_targets.sh V1.0.xx <commit>
```

Do not mark TODOs completed until all configured required targets report the expected `ui_version`, served HTML asset query strings, and served `public/app.js` version, or a target has a concrete unreachable/deployment reason recorded in local memory/GBrain.

For hosts where Memory Stargraph depends on Docker-backed GBrain Postgres and is exposed through Tailscale HTTPS, use [Memory Stargraph Docker Postgres and HTTPS Runbook](memory-stargraph-docker-postgres-https-runbook.md) before declaring the target down. In particular, check Docker Desktop startup, the existing Postgres container and volume, GBrain's HTTP LaunchAgent, Memory Stargraph's LaunchAgent, and the Tailscale Serve backend scheme in that order.

## Autopilot Follow-Up Loop

GBrain is the source of truth for Autopilot operational findings. Memory
Stargraph is the review surface and must read the ledger through:

```bash
gbrain call autopilot_findings_list '{"limit":50,"offset":0}'
gbrain call autopilot_findings_acknowledge '{"id":1}'
```

The lifecycle states are `open`, `queued`, `repairing`, `blocked`,
`awaiting_approval`, `escalated`, and `resolved`. A stable fingerprint
deduplicates repeated detector output. Authority determines routing:

- `remediable`: link the finding to a Minion repair job.
- `blocked`: preserve an owner-visible follow-up with the blocking evidence.
- `human_only`: require explicit approval; never auto-apply the decision.

A completed Minion job is not proof of resolution. The next fresh detector
pass must no longer observe the condition. If a completed repair still fails
its postcondition, retry once with a new idempotency key. If the second
completed repair also fails, mark the finding `escalated`. Acknowledgement
records human awareness but does not change the lifecycle state.

Explicit remediations always use this durable path, regardless of how many
recommendations a detector emits or their estimated duration. A full cycle is
only the fallback when no targeted remediation exists. Do not reintroduce a
`plan.length` or estimated-runtime cutoff before `reconcileAutopilotFindings`;
that leaves visible findings permanently `open` while unrelated full-cycle
jobs run without a verifiable finding-to-job link.

Memory Stargraph exposes the same ledger at:

```text
GET  /api/autopilot-findings
POST /api/autopilot-findings/<id>/acknowledge
```

The Follow-ups control lives beside the Autopilot plan control. Its badge,
filters, evidence, owner, repair count, failed-check count, and acknowledgement
state all come from GBrain. Do not recreate this state in Stargraph storage or
route these operational findings through `take_proposals`.

Deployment lesson from 2026-07-29: the remote host's live GBrain binary was a
custom deployment snapshot containing resolver and Take Review operations that
were absent from upstream. Build a new snapshot from the deployed source and
layer the tested follow-up diff; do not copy the upstream `autopilot.ts` over
the custom file because its imports and helper modules may not exist in the
snapshot. After
restarting Autopilot, verify the PID recorded in `~/.gbrain/autopilot.lock`.
The current launcher checks lock age rather than PID liveness, so a dead PID
with a fresh lock can delay restart for ten minutes. Confirm the PID is dead
before aging the lock past the takeover threshold.

Run retrospective: the main delay was discovering the custom deployment
snapshot and waiting on Intel-host typechecking. The staged deployment test
caught a missing `fts-language` dependency before activation. The improvement
was implemented immediately by testing a non-live snapshot, preserving custom
operations, and documenting the lock and compatibility checks here.

## Automation Host Ownership Switch

Memory Stargraph recurring Codex automations may be installed on both Tony's local Mac and the `.85` host, but only one host may own the schedule at a time. The global holder flag lives in Memory Stargraph/GBrain:

```bash
ops/memory-stargraph/automation-host-holder
```

Holder semantics:

- `tony`: Tony's local Codex automations are `ACTIVE`; `.85` automations are `PAUSED`.
- `timmy`: `.85` Codex automations are `ACTIVE`; Tony's local automations are `PAUSED`.

`config/memory-stargraph-automation-host.json` is host metadata only: automation IDs, host paths, and the coordination slug. Do not treat that file as the holder source of truth.

Incident fallback: if the Stargraph/GBrain coordination node cannot be read, the reconciler must use the configured `coordination.default_holder`. The default holder is `timmy`, so the `.85` host owns the schedule during a GBrain/Stargraph outage. This keeps recurring operations on the more resilient host until the coordination node becomes readable again or Tony explicitly flips it.

Use the reconciler instead of editing automation files by hand. It reads/writes the Stargraph holder node, then updates host-local automation TOML files and the Codex app-server scheduler SQLite rows where present:

```bash
python3 scripts/automation/switch_stargraph_automation_host.py --holder timmy --apply --json
python3 scripts/automation/switch_stargraph_automation_host.py --holder tony --apply --json
python3 scripts/automation/switch_stargraph_automation_host.py --status --json
```

The switch is not complete unless both TOML and scheduler DB status agree. A previous `.85` migration failed because TOML files existed but the scheduler still referenced a nonexistent project id.

## Remote Shell Rule

For remote host work, do not send complex inline SSH commands through the remote login shell. zsh/glob parsing has repeatedly broken commands that contain `[]`, `|`, `$()`, awk regexes, or nested quotes.

Use a heredoc into remote bash for anything beyond a trivial one-liner:

```bash
ssh toddy@host 'bash -s' <<'REMOTE'
set -euo pipefail
# commands here
REMOTE
```

Prefer simple process tools such as `pgrep -f`, `ps -p`, `case`, and `lsof` over fragile awk regexes inside quoted SSH strings. If a command must run under zsh and uses globs, explicitly guard with `setopt nonomatch`; otherwise avoid zsh parsing entirely by using `bash -s`.

## Unified GTasks Event Ingestion

Client applications that report durable facts for GTasks/GBrain processing must
follow the [Unified GTasks Event Ingestion Runbook](gtasks-event-ingestion-runbook.md).
It defines producers, one protected queue-ingress boundary, a separately
managed durable broker, asynchronous consumers, a strict versioned envelope,
deterministic handler registry, enqueue and mutation idempotency, restart-safe
leases, eventual consistency, ordering scope, terminal-failure observability,
and retry behavior. Producers stop waiting after durable queue acceptance and
never depend directly on the GTasks consumer. Canonical GBrain mutations occur
only inside explicit registered handlers.

The first planned event is `job_applied`. Career Path commits its local Applied
state, publishes from a durable outbox, and waits only for durable broker
acceptance. GTasks later consumes the event and owns canonical application,
evidence, quota-task, and once-only progress updates. A publish failure after
the local commit never rolls back or fails that user operation: retain the
event with the same IDs in a durable outbox, warn without blocking, and retry
later. Never use a synchronous direct-GTasks fallback.

NATS JetStream is selected as the independent queue, while GBrain remains the
downstream knowledge system. Local NATS service/transport, credentials,
stream/subject and durable-consumer names, ack/retry/dead-letter/redrive policy,
payload fields, canonical slug/relationship choices, quota-task key, and
progress representation remain provisional until tested implementations
publish their contracts. Do not fabricate those details or remove provisional
labels early.

## Browser Verification

Present user-facing GBrain slugs as exact-label Markdown links using `http://127.0.0.1:8788/?slug=<URL-encoded-slug>`. Before opening a browser tab, inspect existing tabs and reuse a suitable same-origin or same-source tab. Never close a reused user tab; close only a temporary tab created by the current run.

Use Chrome CDP first for UI verification:

```bash
npx --yes --package playwright node scripts/automation/cdp_probe.mjs V1.0.xx http://127.0.0.1:8788
```

Use `tests/browser_smoke.mjs` as broad regression coverage, but keep it from overfitting unrelated layout details. When smoke fails on stale layout assertions, add or update targeted CDP probes for the feature being shipped and fix stale smoke assertions separately.

## Five-Minute Retrospective Hook

Every automation run that lasts more than five minutes must end with a short retrospective before the final report. Capture:

- What slowed the run down.
- Any stale assumption, flaky check, missing command, or unreachable host.
- One concrete improvement to scripts, docs, automation prompt, or tests.
- Whether the improvement was implemented immediately.

Append the retrospective with:

```bash
scripts/automation/retrospect.sh memory-stargraph-wish-to-reallity <elapsed-seconds> /path/to/summary.md
```

If the run is under five minutes, note that the hook was skipped.
