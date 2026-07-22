# Memory Stargraph / GBrain Warm-Standby Runbook

This runbook defines a Primary/Secondary operating model for GBrain-backed Memory
Stargraph. The goal is to keep a second Mac mini ready from daily backup restore
and allow controlled promotion when the authoritative GBrain remote service
fails.

Tony may casually call this “master-slave.” In docs, scripts, alerts, and
briefings use **Primary/Secondary**:

- **Primary** means the normal authoritative GBrain writer.
- **Secondary** means the warm standby restored from Primary backups.
- Do not introduce a second active writer unless a human explicitly promotes
  the Secondary and freezes or redirects the old Primary.

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

## Architecture

```text
Normal operation
----------------

Memory Stargraph fleet
  ├─ local MacBook instance
  ├─ Primary Mac mini Memory Stargraph
  └─ Secondary Mac mini Memory Stargraph
        │
        └── all use the Primary GBrain authority
            https://toddys-mac-mini.taildb46a7.ts.net/mcp

Primary host: toddys-mac-mini.taildb46a7.ts.net
  ├─ GBrain HTTP/MCP: 127.0.0.1:3131 behind the host's public route
  └─ GBrain Postgres: Docker pgvector/pgvector:pg16, 127.0.0.1:5433->5432

Secondary host: toddys-mac-mini-1.taildb46a7.ts.net
  ├─ normal thin-client GBrain config still points at the Primary
  ├─ standby GBrain home: ~/.gbrain-secondary-home
  ├─ standby GBrain HTTP: 127.0.0.1:3132 only
  ├─ standby Postgres: PostgreSQL 17 + pgvector, 127.0.0.1:5432 only
  └─ daily restore job pulls a Primary logical dump and refreshes standby DB

Promotion
---------

Promotion redirects the fleet to the approved Secondary authority route only
after:
  1. Primary failure is verified;
  2. Secondary restore readiness is fresh;
  3. Secondary health/readback passes;
  4. the configured switch command succeeds;
  5. every configured fleet check verifies the promoted authority.
```

The Secondary standby GBrain/Postgres ports intentionally bind to loopback.
They are not exposed through Tailscale or LAN during normal operation. External
clients should reach only the approved Memory Stargraph service route, not
`3132` or `5432`.

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
MEMORY_STARGRAPH_SECONDARY_READINESS_COMMAND='ssh secondary-host "cat ~/.gbrain-secondary-home/last-restore.json"'
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

Legacy `MEMORY_STARGRAPH_MASTER_*` and `MEMORY_STARGRAPH_SLAVE_*` keys are
accepted by the helper for backward compatibility only. New config should use
Primary/Secondary names.

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

As of the 2026-07-22 setup, the standby topology uses these concrete roles:

- Primary: `toddys-mac-mini.taildb46a7.ts.net`
- Secondary: `toddys-mac-mini-1.taildb46a7.ts.net`

The Primary host runs:

- GBrain CLI at `/Users/toddy/.bun/bin/gbrain`
- LaunchAgent `com.tony.gbrain.http`
- GBrain HTTP command:
  `gbrain serve --http --port 3131 --bind 127.0.0.1 --public-url https://toddys-mac-mini.taildb46a7.ts.net --enable-dcr --suppress-bootstrap-token`
- Postgres container `gbrain-postgres`
- Docker image `pgvector/pgvector:pg16`
- Postgres port binding `127.0.0.1:5433->5432`

The Secondary host runs:

- PostgreSQL 17 + pgvector on `127.0.0.1:5432`
- isolated standby GBrain home at `~/.gbrain-secondary-home`
- local-only GBrain HTTP on `127.0.0.1:3132`
- local-only GBrain HTTP LaunchAgent `com.tony.gbrain.secondary.http`
- daily restore LaunchAgent `com.tony.gbrain.secondary.restore`
- restore script `~/.gbrain-secondary-home/restore-from-primary.sh`
- restore readiness marker `~/.gbrain-secondary-home/last-restore.json`

The latest verified restore at setup time had:

- pages: `8725`
- restore timestamp: `2026-07-22T12:38:09-07:00`
- readiness marker: `secondary_ready=true`
- GBrain HTTP bind: `127.0.0.1:3132`
- Postgres bind: `127.0.0.1:5432`

## Verification commands

Run these from the MacBook checkout unless noted otherwise.

Check Primary/Secondary status from the alert monitor environment:

```bash
cd ~/.codex/automations/memory-stargraph-alert-monitor
set -a
. ./monitor.env
set +a
python3 memory_stargraph_failover.py status --json --timeout 8
```

Expected healthy status:

- `primary.ok=true`
- `secondary.ok=true`
- `state.secondary_ready=true`
- `state.secondary_restored_at` is within
  `MEMORY_STARGRAPH_FAILOVER_MAX_BACKUP_AGE_HOURS`

Verify Secondary local-only service bindings:

```bash
ssh toddy@toddys-mac-mini-1.taildb46a7.ts.net 'bash -s' <<'REMOTE'
lsof -nP -iTCP -sTCP:LISTEN | grep -E '3132|5432|8788'
cat ~/.gbrain-secondary-home/last-restore.json
curl -sS --max-time 5 http://127.0.0.1:3132/.well-known/oauth-authorization-server
REMOTE
```

Expected listener shape:

- `postgres` listens on `127.0.0.1:5432` and `[::1]:5432`
- standby `bun`/GBrain listens on `127.0.0.1:3132`
- no external listener exists for `3132` or `5432`

Verify non-exposure from the MacBook:

```bash
curl -sS --max-time 5 http://toddys-mac-mini-1.taildb46a7.ts.net:3132/.well-known/oauth-authorization-server
curl -sS --max-time 5 http://toddys-mac-mini-1.taildb46a7.ts.net:5432/
```

Both should fail to connect during normal standby operation.

Run one alert monitor dry-run:

```bash
python3 scripts/automation/memory_stargraph_alert_monitor.py once --dry-run --json --timeout 8
```

Expected result:

- `ok=true`
- `failing_count=0`
- `email_status=not_needed`

## Daily restore implementation

The Secondary restore script:

1. SSHes from the Secondary to the Primary.
2. Runs `pg_dump -Fc --no-owner --no-acl` inside the Primary
   `gbrain-postgres` container.
3. Copies the dump to the Primary host `/tmp`, then to the Secondary backup
   directory.
4. Verifies SHA-256 of the copied dump.
5. Recreates only the Secondary standby `gbrain` database.
6. Installs/keeps `vector`.
7. Restores the logical dump.
8. Re-grants ownership and app-user privileges to the Secondary standby
   `gbrain` role.
9. Restarts `com.tony.gbrain.secondary.http`.
10. Verifies local OAuth discovery on `127.0.0.1:3132`.
11. Writes `~/.gbrain-secondary-home/last-restore.json`.

Manual end-to-end restore on the Secondary:

```bash
ssh toddy@toddys-mac-mini-1.taildb46a7.ts.net /Users/toddy/.gbrain-secondary-home/restore-from-primary.sh
```

Do not run this while the Secondary is promoted and accepting writes unless a
human has explicitly approved overwriting promoted Secondary state from a
Primary backup.

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

Current promotion status:

- automatic promotion is disabled with `MEMORY_STARGRAPH_FAILOVER_ON_ALERT=0`;
- `MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND` is intentionally not configured
  until the exact fleet-routing mechanism is chosen and tested;
- `promote-secondary --dry-run` must refuse while the Primary is healthy.

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

Normal redeployments and SRE operations must suppress alerts before expected
service mutation:

```bash
python3 scripts/automation/memory_stargraph_alert_monitor.py suppress --minutes 45 --reason "SRE documented remediation"
python3 scripts/automation/memory_stargraph_alert_monitor.py clear-suppression
```

Leave suppression to expire if remediation fails or the operator loses
verification; do not clear suppression just because a command exited.

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

## Operator checklist

Use this checklist during an incident:

1. Confirm whether the alert is suppressed for expected deploy/SRE work.
2. Probe Primary and all Memory Stargraph instances.
3. Probe Secondary readiness and restore age.
4. If Primary is healthy, do not promote.
5. If Primary is unhealthy but Secondary is stale, restore Secondary first only
   if overwriting Secondary standby state is safe.
6. If Primary is unhealthy and Secondary is fresh/healthy, run
   `promote-secondary --json` only after the switch command is configured.
7. Verify every fleet URL after switch.
8. Notify Product Owner and SRE with Primary/Secondary status, restore age,
   switch result, and fleet verification.

## Known gaps / next hardening work

- Choose and implement the actual
  `MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND`.
- Decide whether promotion should expose Secondary GBrain directly, redirect a
  stable route, or rewrite fleet `remote_mcp` config.
- Add a weekly SRE drill that performs a promotion dry-run and verifies the
  refusal reasons while Primary is healthy.
- Add backup retention pruning for `~/.gbrain-secondary-home/backups` after an
  agreed retention window.
- Document manual failback only after a tested reconciliation path exists.
