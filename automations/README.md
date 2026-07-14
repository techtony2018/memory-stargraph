# Memory Stargraph Automations

This directory is the Git-tracked source of truth for Memory Stargraph and
GBrain Codex automations. Runtime copies live under:

```text
${CODEX_HOME:-$HOME/.codex}/automations/<automation-id>/automation.toml
```

The tracked definitions intentionally exclude runtime timestamps, automation
memory, logs, credentials, private deployment coordinates, and local service
configuration. Replace `{{PROJECT_ROOT}}` with the local Memory Stargraph
checkout before restoring a definition through the Codex automation UI/API.

## Pipeline

| Local time | Automation | Purpose |
| --- | --- | --- |
| Daily 12:15 AM | `gbrain-x-intelligence-capture` | Collect public GBrain usage, releases, explanations, and product inspiration from X. |
| Daily 1:00 AM | `memory-stargraph-daily-learning-intake` | Turn recent evidence into deduplicated, bounded planned TODOs. |
| Daily 2:00 AM | `memory-stargraph-wish-to-reallity` | Plan, implement, test, iterate, deploy, and learn from the selected TODO batch. |
| Sunday 4:00 AM | `memory-stargraph-divergent-product-discovery` | Explore usability, performance, customer value, and productization opportunities outside the existing backlog. |

All four automations work toward the persistent GBrain goal:

```text
goals/memory-stargraph-continuous-learning-local-knowledge-os
```

## Files

Each automation directory contains:

- `automation.toml`: portable metadata and schedule.
- `prompt.md`: the complete checked-in prompt.

The repository definition records the intended active state. The Codex app may
temporarily pause a runtime automation without changing this source definition.
When behavior changes, update the checked-in definition and the live automation
together in the same task.

## Restore Checklist

1. Open the matching `automation.toml` and `prompt.md`.
2. Replace `{{PROJECT_ROOT}}` with the absolute local checkout path.
3. Create or update the automation through the Codex automation UI/API.
4. Verify its id, schedule, model, reasoning effort, execution environment, and
   active/paused status in `${CODEX_HOME:-$HOME/.codex}/automations`.
5. Keep deployment targets in the private local file documented in
   `docs/automation-runbook.md`; never add them to these definitions.
