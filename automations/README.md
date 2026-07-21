# Memory Stargraph Automations

This directory is the Git-tracked source of truth for Memory Stargraph and
GBrain Codex automations. Runtime copies live under:

```text
${CODEX_HOME:-$HOME/.codex}/automations/<automation-id>/automation.toml
```

The tracked definitions intentionally exclude runtime timestamps, automation
memory, logs, credentials, private deployment coordinates, and local service
configuration. Worker schedules use heartbeats so every run returns to one
persistent task instead of creating a new task. Replace the documented
placeholders before restoring a definition through the Codex automation UI/API.

## Pipeline

| Local time | Role | Automation ID | Purpose |
| --- | --- | --- | --- |
| Daily 12:00 AM | Memory Stargraph Knowledge Curator | `memory-stargraph-capture-link-drain` | Freeze and drain every planned Capture Link request; when the first snapshot is empty, enrich up to two evidence-backed entities with people first. |
| Daily 12:15 AM | GBrain Intelligence Researcher | `gbrain-x-intelligence-capture` | Collect public GBrain usage, releases, explanations, and product inspiration from X. |
| Daily 1:00 AM | Memory Stargraph Quality & Learning Analyst | `memory-stargraph-daily-learning-intake` | Turn recent evidence into deduplicated, bounded planned TODOs, including the daily Yoda Evaluator comparison loop. |
| Daily 2:00 AM | Memory Stargraph UX Engineer | `memory-stargraph-ux-engineer-daily-dogfood` | Dogfood the dashboard-managed app, record journey evidence, and promote at most three reproduced UX findings into planned TODOs. |
| Daily 3:00 AM | Memory Stargraph SRE | `memory-stargraph-sre-daily-reliability` | During verified quiet time, inspect deployed-stack reliability, apply bounded documented remediation, and report capacity headroom. |
| Daily 3:30 AM | Memory Stargraph Developer | `memory-stargraph-wish-to-reallity` | Plan, implement, test, iterate, deploy, and learn from the selected TODO batch. |
| Sunday 4:00 AM | Memory Stargraph Product Strategist | `memory-stargraph-divergent-product-discovery` | Explore usability, performance, customer value, and productization opportunities outside the existing backlog. |
| Daily 7:30 AM | Memory Stargraph Product Owner | `memory-stargraph-goal-steward-daily-review` | Perform the full Goal health review and create temporary 10-minute worker-watch timers only for newly kicked off or blocked active worker runs. |
| Sunday 11:00 AM | Memory Stargraph SRE | `memory-stargraph-sre-weekly-resilience` | During verified quiet time, run safe-target load, isolated restore, failover, rollback, and capacity-envelope exercises. |

The midnight Capture Link drain and the 12:15 AM X intelligence capture are
independently scheduled; neither depends on the other finishing. The Capture
Knowledge Curator may also be triggered manually at any time without a cutoff.
The UX Engineer now runs before SRE and Developer so the Developer can include
fresh UX findings in the daily implementation batch before the Product Owner
review.
Codex permits only one active heartbeat per task, so the two SRE automations
target distinct persistent tasks while sharing one SRE prompt, role, and
quiet-time contract. Busy runs defer task-locally, and Sunday receives both the
daily review and the separate weekly exercise.

All recurring Memory Stargraph automations work toward the persistent GBrain goal:

```text
goals/memory-stargraph-continuous-learning-local-knowledge-os
```

The Product Owner review is an accountability gate, not a passive digest. Codex
permits only one heartbeat per task, so the Product Owner automation is now a
single daily full review plus temporary 10-minute worker-watch timers created
only when a worker is newly kicked off, retried, recovered, or observed running
without terminal evidence. These temporary watch windows keep role-specific
estimated durations so silent failures are caught before the morning summary.
They check expected start/progress/terminal windows, detect system errors such
as model or modal capacity failures, and send bounded follow-ups to the
canonical role task or route confirmed infrastructure issues to SRE. The full daily Product Owner
review must detect blocked or silent roles, take the next safe coordination
action in the correct persistent task, clean up duplicate recurring
destinations, and report a stable daily Goal progress percentage with the
highest-leverage action to improve it. After the daily report, Product Owner
runs a retrospective that compares the current metrics and role outcomes against
the previous day, assigns actions for regressions or stalls, and proposes new
roles only for Tony's review when existing roles cannot cover the gap.

## Worker Watch ETA Table

| Role | Scheduled start | First watch | Expected terminal/deferral window |
| --- | --- | --- | --- |
| Memory Stargraph Knowledge Curator | Daily 12:00 AM | 12:30 AM | 60 minutes unless a large frozen snapshot has fresh progress |
| GBrain Intelligence Researcher | Daily 12:15 AM | 12:30 AM | 45 minutes |
| Memory Stargraph Quality & Learning Analyst | Daily 1:00 AM | 1:30 AM | 45 minutes |
| Memory Stargraph UX Engineer | Daily 2:00 AM | 2:30 AM | before the Developer run |
| Memory Stargraph SRE daily reliability | Daily 3:00 AM | 3:30 AM | 75 minutes |
| Memory Stargraph Developer | Daily 3:30 AM | 4:00 AM | progress within 30 minutes; terminal, failed evidence, or owned continuation by 7:00 AM |
| Memory Stargraph Product Owner | Daily 7:30 AM | 9:00 AM if still active | 45 minutes |
| Memory Stargraph Product Strategist | Sunday 4:00 AM | 5:30 AM | 90 minutes |
| Memory Stargraph SRE weekly resilience | Sunday 11:00 AM | 12:30 PM | terminal, owned continuation, or quiet-time deferral by 2:30 PM |

Worker tasks remain the system of record for detailed reports. Every recurring
worker sends the canonical Product Owner task a compact completion/deferral
notification after terminal outcome; Product Owner then inspects the worker task
and verifies evidence before counting it as progress.

## Files

Each automation directory contains:

- `automation.toml`: portable metadata, schedule, and persistent-task placeholder.
- `heartbeat-prompt.md`: the short message delivered to the persistent task on schedule.
- `prompt.md`: the complete worker instructions read by the task for each run.
- `thread-bootstrap.md`: initialization prompt for recreating a persistent worker task.
- `steward-thread-prompt.md`, when present: bootstrap context for recreating the dedicated owner thread.

The repository definition records the intended active state. The Codex app may
temporarily pause a runtime automation without changing this source definition.
When behavior changes, update the checked-in definition and the live automation
together in the same task.

## Restore Checklist

1. Open the matching `automation.toml` and `prompt.md`.
2. Create the persistent task from `thread-bootstrap.md` or
   `steward-thread-prompt.md`. Use a project-local task for evidence/review
   workers and a dedicated worktree task for Memory Stargraph Developer.
3. Replace the automation-specific `{{..._THREAD_ID}}` placeholder with the
   resulting task id.
4. Create or update the heartbeat automation through the Codex automation UI/API.
5. Verify its id, schedule, destination task, and active/paused status in
   `${CODEX_HOME:-$HOME/.codex}/automations`.
6. Keep deployment targets in the private local file documented in
   `docs/automation-runbook.md`; never add them to these definitions.
