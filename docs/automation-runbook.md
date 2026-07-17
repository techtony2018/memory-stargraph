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

## Engineer and UX Deployment Quiescence

The Memory Stargraph Engineer and UX Engineer use Goal-linked Runs as
cooperative change and UX leases. The protocol applies to scheduled and manual
invocations and has no fixed kickoff or cutoff time.

Before editing code, restarting a service, or deploying, the Engineer creates
or updates an active Goal-linked Run with an `active-change` marker, invocation
id, start time, intended scope, and deployment fingerprint. At minimum, the
fingerprint records `ui_version`, health source state and timestamp, served
HTML/JS asset version or hash, and local process cwd when available.

Before journeys, UX verifies there is no active Engineer marker, records the
fingerprint, creates an active UX Run/lease, and re-reads active Runs. If an
Engineer marker appeared concurrently, Engineer priority wins and UX
terminalizes as `deferred_due_to_active_change`. UX rechecks the marker, health,
and fingerprint before and after every journey. On any instability it stops,
discards all observations from that invocation, creates or updates no TODOs,
and records before/after evidence.

Before restart or deployment, the Engineer re-reads active UX leases. It waits
for UX to acknowledge and terminalize and must not silently deploy through an
active UX lease. The Engineer clears its marker only after target health,
version, served HTML/JS, and process-cwd verification passes. Failure,
interruption, or crash evidence remains visible. A stale UX lease or stale
Engineer marker requires Product Owner resolution and is never bypassed
automatically.

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

## Deployment Targets

Keep deployment target details in local Codex memory/config and GBrain, not in tracked GitHub files. The deploy helper reads:

```bash
${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-wish-to-reallity/deployment-targets.env
```

That local file should define the dashboard-managed local service path, restart URL, remote SSH targets, remote repo paths, restart commands, and verification URLs.

After commit and push, deploy the exact commit with:

```bash
scripts/automation/deploy_targets.sh V1.0.xx <commit>
```

Do not mark TODOs completed until all configured required targets report the expected `ui_version`, served HTML asset query strings, and served `public/app.js` version, or a target has a concrete unreachable/deployment reason recorded in local memory/GBrain.

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
