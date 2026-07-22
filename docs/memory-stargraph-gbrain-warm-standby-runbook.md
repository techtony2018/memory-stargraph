# Memory Stargraph / GBrain Warm-Standby Runbook

This runbook defines a Primary/Secondary operating model for GBrain-backed Memory
Stargraph. The goal is to keep a second Mac mini ready from daily backup restore
and allow controlled promotion when the authoritative GBrain remote service
fails.

## Safety model

This is warm standby, not multi-primary replication.

- The Primary is the only normal write authority.
- The Secondary is restored daily from backup and verified read-ready.
- The Secondary must not accept normal writes until promotion.
- Automatic failback is forbidden until a reconciliation path is tested.
- Promotion is allowed only when the Primary is verified unhealthy/unreachable,
  the Secondary is healthy, and the Secondary restore is fresh enough.

This avoids split brain: two GBrain services accepting writes for the same brain
without conflict resolution.

## Private configuration

All concrete hosts, backup paths, credentials, Tailscale routes, and switch
commands live in the private env file used by the alert monitor:

```text
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-alert-monitor/monitor.env
```

Required keys:

```bash
MEMORY_STARGRAPH_PRIMARY_URL=https://primary-memory-stargraph.example
MEMORY_STARGRAPH_SECONDARY_URL=https://secondary-memory-stargraph.example
MEMORY_STARGRAPH_SECONDARY_RESTORE_COMMAND='ssh secondary-host "/path/to/restore-latest-gbrain-backup.sh"'
MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND='ssh control-host "/path/to/switch-gbrain-authority-to-secondary.sh"'
MEMORY_STARGRAPH_FLEET_CHECK_URLS="http://127.0.0.1:8788 https://remote-a https://remote-b"
```

Optional keys:

```bash
MEMORY_STARGRAPH_PRIMARY_CURL_FLAGS=
MEMORY_STARGRAPH_SECONDARY_CURL_FLAGS=-k
MEMORY_STARGRAPH_FLEET_CURL_FLAGS=-k
MEMORY_STARGRAPH_FAILOVER_MAX_BACKUP_AGE_HOURS=30
MEMORY_STARGRAPH_FAILOVER_ON_ALERT=0
MEMORY_STARGRAPH_SECONDARY_RESTORE_HOUR=4
MEMORY_STARGRAPH_SECONDARY_RESTORE_MINUTE=30
```

Keep `MEMORY_STARGRAPH_FAILOVER_ON_ALERT=0` until the restore command,
Secondary readiness, switch command, and fleet verification have been tested
end to end.

## Daily Secondary restore

Install the daily restore LaunchAgent after configuring `MEMORY_STARGRAPH_SECONDARY_URL`
and `MEMORY_STARGRAPH_SECONDARY_RESTORE_COMMAND`:

```bash
scripts/automation/install_memory_stargraph_secondary_restore.sh
```

It runs:

```bash
python3 memory_stargraph_failover.py restore-secondary --json
```

The restore helper:

1. runs only the private restore command;
2. probes the Secondary `/api/health`;
3. probes the Secondary read-only `GET /api/entity-raw/index`;
4. records `secondary_ready=true` and
   `secondary_restored_at=<Pacific ISO timestamp>` only after verification
   passes.

State is stored at:

```text
${CODEX_HOME:-$HOME/.codex}/state/memory-stargraph-failover.json
```

Manual restore check:

```bash
python3 scripts/automation/memory_stargraph_failover.py restore-secondary --json --dry-run
python3 scripts/automation/memory_stargraph_failover.py restore-secondary --json
```

## Current local-only Secondary standby

As of the 2026-07-22 setup, the standby topology uses these roles:

- Primary: `toddys-mac-mini.taildb46a7.ts.net`
- Secondary: `toddys-mac-mini-1.taildb46a7.ts.net`

The Secondary host runs local-only standby services:

- PostgreSQL 17 + pgvector on `127.0.0.1:5432`
- isolated standby GBrain home at `~/.gbrain-secondary-home`
- local-only GBrain HTTP on `127.0.0.1:3132`
- daily restore LaunchAgent `com.tony.gbrain.secondary.restore`
- restore script `~/.gbrain-secondary-home/restore-from-primary.sh`
- restore readiness marker `~/.gbrain-secondary-home/last-restore.json`

The Secondary standby GBrain and Postgres ports must stay bound to loopback
only. External hosts should not reach `3132` or `5432`; promotion must use the
configured switch command to expose or redirect only the approved authority path.

## Promotion / failover

Manual promotion command:

```bash
python3 scripts/automation/memory_stargraph_failover.py promote-secondary --json
```

Promotion refuses to run when:

- the Primary still passes health and GBrain readback;
- the Secondary is unhealthy;
- the Secondary has not been verified by a restore;
- the verified restore is older than
  `MEMORY_STARGRAPH_FAILOVER_MAX_BACKUP_AGE_HOURS`;
- `MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND` is missing;
- post-switch fleet verification fails.

The switch command should atomically redirect the fleet to the Secondary. Depending
on the current topology, that may mean updating a stable Tailscale/DNS alias,
updating client `remote_mcp` configuration, or changing the authoritative
Memory Stargraph/GBrain route consumed by all three instances. The command must
be idempotent and must not mutate user data.

Forced promotion exists only for human-led emergency recovery:

```bash
python3 scripts/automation/memory_stargraph_failover.py promote-secondary --json --force
```

Use `--force` only when the Primary probe is falsely healthy or the Primary must
be drained despite still responding.

## Alert-triggered promotion

The local alert monitor can invoke promotion after it detects a persistent
issue:

```bash
MEMORY_STARGRAPH_FAILOVER_ON_ALERT=1
```

This is intentionally opt-in. Even when enabled, the failover helper still
checks Primary failure, Secondary readiness, backup age, switch-command success, and
fleet verification before declaring success. The alert email includes the
failover hook result.

## Failback

Failback is manual. Before returning authority to the original Primary:

1. freeze writes or put the fleet in maintenance mode;
2. export/compare the Secondary's promoted-state changes;
3. reconcile the original Primary from the promoted Secondary;
4. verify Primary health and GBrain read/write paths;
5. switch the fleet back;
6. restore the Secondary again from the reconciled backup;
7. clear `active_authoritative_role` only after verification.

Do not point clients back to the original Primary merely because it is
reachable.
