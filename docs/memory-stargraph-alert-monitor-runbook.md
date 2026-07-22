# Memory Stargraph Local Alert Monitor Runbook

This monitor runs on Tony's local MacBook and checks every configured Memory
Stargraph instance plus the GBrain read path behind each instance. It is
intended to catch outages like the 2026-07-22 GBrain MCP/write-path incident
without alerting during normal development redeployments or active SRE work.

## What it checks

`scripts/automation/memory_stargraph_alert_monitor.py once` checks each target
with top-level `curl -sS` calls:

1. `GET <target>/api/health`
2. `GET <target>/api/entity-raw/index`

A target is treated as problematic when:

- `/api/health` is unreachable, non-2xx, or invalid JSON.
- health returns `ok=false`.
- health source is not live GBrain (`source.mode != gbrain`).
- health source is cached, unavailable, not loaded, unknown, or erroring.
- the read-only `index` entity cannot be read back from that same instance.

The monitor does not create GBrain writes, resolver traffic, synthetic Ask Yoda
events, TODOs, or browser tabs.

## Target configuration

The monitor reads the same private deployment config used by Memory Stargraph
automation:

```text
${MEMORY_STARGRAPH_AUTOMATION_CONFIG:-${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-wish-to-reallity/deployment-targets.env}
```

If `MEMORY_STARGRAPH_MONITOR_TARGETS` is set, it wins. Use this format for the
three production-like instances:

```bash
MEMORY_STARGRAPH_MONITOR_TARGETS="local=http://127.0.0.1:8788 remote_a=https://... remote_b=https://..."
```

If it is omitted, the monitor derives targets from `MEMORY_STARGRAPH_LOCAL_URL`,
`MEMORY_STARGRAPH_REMOTE_HEALTH_URLS`, and per-target
`MEMORY_STARGRAPH_TARGET_<id>_VERIFY_URLS`.

## Email configuration

Set the destination in the private monitor env file:

```bash
MEMORY_STARGRAPH_ALERT_EMAIL_TO=tony@example.com
```

Optional SMTP settings:

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=memory-stargraph-alerts@example.com
```

When SMTP is not configured, the monitor uses macOS `mail`:

```bash
mail -s "[Memory Stargraph Alert] ..." "$MEMORY_STARGRAPH_ALERT_EMAIL_TO"
```

## Install as a local LaunchAgent

Run:

```bash
scripts/automation/install_memory_stargraph_alert_monitor.sh
```

On first run it creates:

```text
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-alert-monitor/monitor.env
```

Edit that file to set `MEMORY_STARGRAPH_ALERT_EMAIL_TO`, then rerun the
installer. The LaunchAgent runs every 5 minutes by default:

```bash
MEMORY_STARGRAPH_ALERT_INTERVAL_SECONDS=300 scripts/automation/install_memory_stargraph_alert_monitor.sh
```

Logs are written to:

```text
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-alert-monitor/launchd.out.log
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-alert-monitor/launchd.err.log
```

The installer copies the runnable monitor script into the same private
`~/.codex/automations/memory-stargraph-alert-monitor/` directory before loading
launchd. This avoids macOS privacy restrictions that can prevent LaunchAgents
from reading scripts directly from `~/Documents`.

It also copies `memory_stargraph_failover.py` into that directory so the alert
monitor can run the optional warm-standby promotion hook without needing access
to the repository checkout.

## Optional warm-standby failover

Warm-standby setup is documented in
`docs/memory-stargraph-gbrain-warm-standby-runbook.md`.

Keep failover disabled until the private master/slave URLs, daily restore
command, switch command, and fleet verification URLs are configured and tested:

```bash
MEMORY_STARGRAPH_FAILOVER_ON_ALERT=0
```

When set to `1`, a persistent alert invokes:

```bash
python3 memory_stargraph_failover.py promote-slave --json
```

The promotion helper still refuses to switch if the master is healthy, the
slave is unhealthy, the slave restore is stale, or post-switch fleet checks
fail. The alert email includes the failover hook result.

## Suppressing expected maintenance windows

Normal deployments and SRE operations should suppress alerts before they mutate
or restart services:

```bash
python3 scripts/automation/memory_stargraph_alert_monitor.py suppress --minutes 45 --reason "Memory Stargraph deployment V1.0.xxx"
```

Clear suppression when the operation finishes successfully:

```bash
python3 scripts/automation/memory_stargraph_alert_monitor.py clear-suppression
```

`scripts/automation/deploy_targets.sh` does this automatically: it suppresses
alerts before deployment starts and clears suppression only after successful
verification. If the deploy fails or is interrupted, suppression expires by
time instead of immediately spamming Tony while the operator is already handling
the failed deploy.

SRE incident response or weekly resilience operations should use the same
suppress/clear commands around documented restart, rollback, failover, or
network-route remediation steps.

## Alert dedupe and thresholds

The monitor stores state in:

```text
${CODEX_HOME:-$HOME/.codex}/state/memory-stargraph-alert-monitor.json
```

Defaults:

- `MEMORY_STARGRAPH_ALERT_FAILURE_THRESHOLD=2`: two consecutive failing checks
  are required before email.
- Identical issue signatures are not emailed repeatedly.
- A fully healthy pass clears the last-alert signature so a future recurrence
  can alert again.

Run one dry check:

```bash
python3 scripts/automation/memory_stargraph_alert_monitor.py once --json --dry-run
```

Run one real check:

```bash
python3 scripts/automation/memory_stargraph_alert_monitor.py once --json
```
