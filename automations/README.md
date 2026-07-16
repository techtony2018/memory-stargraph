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
| Daily 1:00 AM | Memory Stargraph Quality & Learning Analyst | `memory-stargraph-daily-learning-intake` | Turn recent evidence into deduplicated, bounded planned TODOs. |
| Daily 2:00 AM | Memory Stargraph Engineer | `memory-stargraph-wish-to-reallity` | Plan, implement, test, iterate, deploy, and learn from the selected TODO batch. |
| Daily 6:00 AM | Memory Stargraph UX Engineer | `memory-stargraph-ux-engineer-daily-dogfood` | Dogfood the dashboard-managed app, record journey evidence, and promote at most three reproduced UX findings into planned TODOs. |
| Sunday 4:00 AM | Memory Stargraph Product Strategist | `memory-stargraph-divergent-product-discovery` | Explore usability, performance, customer value, and productization opportunities outside the existing backlog. |
| Daily 7:00 AM | Memory Stargraph Product Owner | `memory-stargraph-goal-steward-daily-review` | Review all worker runs, Goal health, risks, approvals, and the next coordination action in the dedicated Product Owner task. |

The midnight Capture Link drain and the 12:15 AM X intelligence capture are
independently scheduled; neither depends on the other finishing. The Capture
Knowledge Curator may also be triggered manually at any time without a cutoff.
The UX Engineer runs after the Engineer and before the Product Owner so the
morning steward review includes fresh journey evidence and UX TODO decisions.

All seven automations work toward the persistent GBrain goal:

```text
goals/memory-stargraph-continuous-learning-local-knowledge-os
```

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
   workers and a dedicated worktree task for Wish to Reallity.
3. Replace the automation-specific `{{..._THREAD_ID}}` placeholder with the
   resulting task id.
4. Create or update the heartbeat automation through the Codex automation UI/API.
5. Verify its id, schedule, destination task, and active/paused status in
   `${CODEX_HOME:-$HOME/.codex}/automations`.
6. Keep deployment targets in the private local file documented in
   `docs/automation-runbook.md`; never add them to these definitions.
