# Memory Stargraph SRE Design

## Summary

Memory Stargraph needs one persistent Site Reliability Engineer that keeps the
deployed stack healthy and makes its scaling limits visible. The role performs
a daily reliability review and a separate weekly resilience exercise. It may
apply only documented, reversible remediation, and it runs operational work
only during verified quiet time when no other Memory Stargraph worker is
active.

The role is **Memory Stargraph SRE**. It owns reliability operations and
capacity evidence, not product implementation. Code defects and scaling work
outside its bounded authority are handed to the Memory Stargraph Engineer.

## Goals

- Detect outages, degradation, version drift, capacity pressure, backup gaps,
  and recurring worker failures before they become user-facing incidents.
- Restore service through documented, reversible operations when safe.
- Measure whether the complete stack can grow in nodes, relationships, files,
  queries, users, and worker activity without losing reliability.
- Exercise backup, restore, restart, failover, and rollback paths regularly.
- Preserve human control over destructive, privacy-sensitive, architectural,
  credential, and infrastructure-spending decisions.
- Keep every SRE probe out of genuine resolver and user-quality signals.

## Non-goals

- Implement product or GBrain code.
- Perform destructive production-data repair or restore.
- Approve resolver proposals.
- Purchase infrastructure or make broad topology changes.
- Run load or chaos tests against a target that is not explicitly safe.
- Compete with or duplicate another active Memory Stargraph worker.

## Persistent Task And Automations

Both automations target one reusable task titled `Memory Stargraph SRE`.
Scheduled, deferred, retry, and manual invocations remain in that task.

| Mode | Automation ID | Default trigger |
| --- | --- | --- |
| Daily reliability | `memory-stargraph-sre-daily-reliability` | Daily at 8:00 AM in `America/Los_Angeles` |
| Weekly resilience | `memory-stargraph-sre-weekly-resilience` | Sunday at 11:00 AM in `America/Los_Angeles` |

The two schedules are separate. Sunday still receives the daily 8:00 AM
reliability review and the additional 11:00 AM resilience exercise. Manual
triggers may run at any time and have no fixed cutoff, but they obey the same
quiet-time and authority contracts.

## Quiet-time Contract

The SRE performs no health probing, load testing, remediation, or GBrain writes
while another Memory Stargraph worker is active. A preflight reads both live
Codex task state and active Goal-linked Runs or leases for every other
Memory Stargraph worker, implementation or deployment, including another SRE
mode. A stale or conflicting state is not treated as quiet.

If another worker is active at the default trigger, the SRE records a concise
task-local deferral and schedules a retry in the same persistent task. It does
not create an SRE Run merely to report that the stack was busy. There is at
most one completed daily review and one completed weekly review for their
respective Pacific calendar dates.

When the stack appears quiet, the SRE creates an active Goal-linked SRE
Run/lease and immediately repeats the live-task and Goal-Run checks. If a race
is detected, the SRE terminalizes its lease as
`deferred_due_to_worker_activity` and stops.

The SRE rechecks worker and lease state before every mutating operation and
before every weekly load or fault-injection phase. If another worker starts,
the SRE stops, rolls back or contains any incomplete experiment, records
before/after evidence, terminalizes as `deferred_due_to_worker_activity`, and
retries later. Other workers take priority; the SRE never asks them to stop.

## Daily Reliability Mode

The daily run inspects all configured required targets without exposing
private deployment coordinates in tracked artifacts or reports. Coverage
includes:

- All Things Codex Dashboard and the dashboard-managed local Memory Stargraph.
- Configured remote Memory Stargraph endpoints and served asset identities.
- GBrain thin-client and remote health, graph availability, resolver health,
  attachment storage, and media retrieval.
- Service processes, expected cwd, versions, startup state, and version drift.
- Health, search, node-read, relationship/backlink, file, and synthetic query
  latency when a safe read-only probe exists.
- Error rates, timeouts, restart counts, CPU, memory, disk, cache, open files,
  and other available saturation evidence.
- Node, edge, file, storage, queue, and backlog growth.
- Worker success/failure/defer rates and duration trends.
- Backup freshness, backup completeness evidence, and the most recent verified
  restore rehearsal.

The SRE maintains 7-day and 30-day baselines. It reports absolute failures,
meaningful regressions, capacity headroom, version drift, the current estimated
safe scale, and the next likely bottleneck. Missing telemetry is evidence, not
permission to invent a metric.

The output is one dated reliability report and one Goal-linked Run containing
the deployment fingerprint, target results, trend comparisons, incidents,
remediation, verification, capacity assessment, blockers, and follow-ups.

## Weekly Resilience Mode

The separate Sunday run performs the daily health preflight again, then adds:

- Bounded synthetic load and latency tests with gradual ramp-up and explicit
  abort thresholds.
- Restore rehearsal into isolated temporary storage, never over production
  data.
- Documented restart, failover, recovery, and last-known-good rollback tests.
- One fault at a time on an explicitly designated synthetic, disposable, or
  redundant target.
- Capacity-envelope estimation and comparison with prior weekly evidence.
- A scaling-risk report identifying the first expected bottleneck and the
  smallest evidence-backed mitigation.

No production fault is injected merely because the weekly automation ran. If
there is no explicitly safe target, the SRE records
`chaos_skipped_no_safe_target` and creates a proposal requiring human review.
An exercise aborts immediately on user impact, unexpected saturation,
verification loss, rollback uncertainty, or worker activity.

The output is one dated resilience report and one Goal-linked Run. It includes
load shape, synthetic provenance, target classification, abort gates, observed
limits, restore/failover/rollback results, containment, capacity estimate, and
proposals.

## Bounded Remediation

The SRE uses this escalation ladder:

1. Re-read and retry a transient health or routing check.
2. Use an existing documented dashboard-managed restart or service recovery.
3. Recover a documented cache or routing condition without deleting durable
   data.
4. Roll back to a documented last-known-good release only when the affected
   target, release identity, rollback procedure, and verification path are all
   explicit.
5. Verify health, version, served assets, process cwd, resolver isolation,
   attachment availability, and the originally failing path.

Every mutation records before state, exact action, after state, rollback path,
and verification. A failed remediation remains visible and never reports a
false recovery.

The SRE must not perform destructive cleanup, production-data restore,
migration, credential change, privacy expansion, infrastructure purchase,
undocumented topology change, or broad architecture change without explicit
human approval.

## Incident And Escalation Flow

Incidents are deduplicated by affected target, symptom, deployment identity,
and active time window. The Run records severity, user impact, detection,
timeline, evidence, attempted remediation, outcome, and recurrence.

If bounded remediation cannot solve a code or scaling defect, the SRE creates
or updates one evidence-backed planned TODO rather than duplicating work. The
TODO includes exact reproduction, affected targets, baseline/regression data,
acceptance criteria, rollback considerations, and verification.

For an unresolved critical outage, the SRE first contains the incident and
terminalizes/releases its own lease. It then sends the evidence-backed TODO to
the persistent Memory Stargraph Engineer task for immediate handling. Lower
severity work follows the normal Product Owner prioritization loop.

The Product Owner reviews SRE Runs, incidents, capacity headroom, deferred
runs, stale leases, failed remediation, and pending approvals. The Quality &
Learning Analyst may reuse repeated reliability patterns and data-quality
findings, while deduplicating existing SRE TODOs.

## Resolver Feedback Isolation

SRE activity must not pollute the resolver feedback loop.

- Daily runs use read-only resolver health and status operations that generate
  no resolver events.
- Weekly end-to-end resolver tests may use only the isolated synthetic path
  with `environment=test`, `synthetic=true`, `test_run=true`, and stable
  `pair_id=sre:{mode}:{invocation_id}:{probe_slug}`.
- Synthetic SRE events are excluded from production metrics, proposal
  generation, learning intake, resolver decisions, and user-quality scoring.
- Before an end-to-end probe, the SRE verifies that the isolation fields reach
  the telemetry record. If isolation cannot be verified, it records
  `resolver_probe_skipped_isolation_unverified` and does not send the probe.
- Raw or unclassified Ask Yoda and resolver requests are forbidden.

## Browser, Privacy, And Reporting

Browser use follows the project-wide reuse contract: inspect existing tabs,
reuse a suitable tab, never close a reused user tab, and close only a temporary
tab created by the SRE. Authenticated Chrome CDP is used only when a documented
check requires the user's existing session.

Reports never expose credentials, secrets, private host coordinates, or raw
private content. Every user-facing GBrain slug is an exact-label Markdown link
to `http://127.0.0.1:8788/?slug=<URL-encoded-slug>`.

All worker timestamps use timezone-aware ISO 8601 in
`America/Los_Angeles`, which means PDT in summer and PST in winter. Source
timestamps are preserved as provenance, but worker evidence is Pacific-time
normalized. No fixed UTC offset is permitted.

## Failure Handling

- Busy stack: defer task-locally and retry without creating a false incident.
- Race after lease creation: terminalize `deferred_due_to_worker_activity`.
- Missing telemetry: record the gap and use available evidence; do not infer
  health or capacity.
- Unhealthy target: attempt only the documented remediation ladder.
- Failed rollback or uncertain containment: stop, preserve evidence, and
  require human help.
- Unsafe weekly target: record `chaos_skipped_no_safe_target`.
- Unverified resolver isolation: record
  `resolver_probe_skipped_isolation_unverified`.
- Interrupted or crashed SRE run: leave the active/failed Run and last step
  visible for Product Owner resolution.

## Verification Contract

Tracked contract tests must prove:

- Both automation IDs, names, Pacific schedules, and one shared persistent
  task destination.
- Setup-only initialization performs no health checks or mutations.
- Quiet-time checks cover live task state and Goal-linked Runs or leases.
- Busy/racing workers cause deferral and no SRE remediation.
- Daily scope covers deployed targets, capacity trends, backups, storage,
  attachments, resolver, and worker health.
- Weekly scope uses isolated restore, bounded ramp-up, one safe fault at a
  time, abort gates, and `chaos_skipped_no_safe_target`.
- Remediation is documented, reversible, evidence-backed, and verified.
- Unresolved defects deduplicate into planned TODOs and critical escalation
  occurs only after the SRE releases its lease.
- Resolver health checks are read-only and synthetic weekly probes are fully
  isolated from production and learning behavior.
- Browser tab reuse, human-control boundaries, and Pacific/DST reporting are
  preserved.

Live registration verification must confirm two active heartbeat automations
target the same persistent SRE task. The initialization turn is setup-only and
must not run health probes, load tests, remediation, GBrain writes, or TODO
creation. The first operational review waits for its scheduled heartbeat or an
explicit manual trigger.
