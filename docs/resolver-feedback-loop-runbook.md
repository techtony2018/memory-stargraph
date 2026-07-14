# Cross-Agent Resolver Feedback Loop Runbook

## Architecture

GBrain on the `.85` host is the source of truth for resolver events, proposals, releases, distribution acknowledgements, impact, and nightly learning runs. Codex and OpenClaw are the resolver consumers and telemetry producers. Memory Stargraph is the review and operations UI; it proxies every resolver action to hosted GBrain and does not maintain a second proposal database.

The safety invariant is strict: learning may create pending proposals, but no proposal is applied automatically. A person must accept the proposal and explicitly apply it in Memory Stargraph.

## Agent Instrumentation

The GBrain repository ships:

- `scripts/resolver-feedback-agent.py`: privacy-safe classifier, local atomic outbox, retry/drain, release sync, checksum verification, and ACK.
- `integrations/codex-resolver-feedback-marketplace`: Codex `UserPromptSubmit` and `Stop` hooks.
- `integrations/openclaw-resolver-feedback`: OpenClaw `before_prompt_build` and `agent_end` hooks.
- `scripts/install-resolver-agent-integrations.sh`: local installer.

Install both integrations from the GBrain checkout:

```bash
scripts/install-resolver-agent-integrations.sh --all
openclaw gateway restart
```

The hooks persist only a classified intent summary, candidate resolver IDs, selected route, resolver version, outcome, and correlation IDs. Raw prompts, credentials, and conversation text are not written to the outbox or central event table. Network delivery is best effort and does not block the agent response path.

Inspect or drain the local outbox:

```bash
find ~/.gbrain/resolver-feedback/outbox -type f -maxdepth 1
python3 ~/.gbrain/resolver-feedback-agent.py drain
```

## Review And Release

Use Memory Stargraph's Resolver Feedback panel to review evidence, accept or reject a proposal, and apply an accepted proposal. Apply performs both gates before GBrain creates a release:

```text
gbrain check-resolvable --strict --skills-dir <isolated-proposal-pack>
gbrain routing-eval --skills-dir <isolated-proposal-pack>
```

The isolated pack contains only the proposed trigger and approved route. This validates the proposed release without letting unrelated warnings in the user's entire skills directory mask or block the result.

After approval, each agent installs the active policy atomically, verifies the canonical SHA-256 checksum, and acknowledges the version:

```bash
python3 ~/.gbrain/resolver-feedback-agent.py sync --environment codex
python3 ~/.gbrain/resolver-feedback-agent.py sync --environment openclaw
gbrain call resolver_releases_current '{"environment":"codex"}'
gbrain call resolver_feedback_health '{}'
```

Distribution is `pending` until the matching client sends an ACK. A checksum mismatch is a hard failure and leaves the prior local policy in place.

## Nightly Learning

The `.85` host runs deterministic resolver learning before the existing GitHub backup:

```cron
30 2 * * * /Users/toddy/.gbrain/resolver-learning-nightly.sh
0 3 * * * /Users/toddy/.gbrain/backup-to-github.sh
```

The learning script runs:

```bash
gbrain dream --phase resolver_learning --json
```

It uses the normal GBrain cycle lock, records a durable `resolver_dream_runs` row, writes `~/.gbrain/resolver-feedback-nightly/latest.json`, and appends a timestamped summary to `nightly.log`. It never applies proposals and does not invoke an LLM.

## Backup And Restore

The 3:00 AM backup calls `resolver_feedback_backup` and commits the result to:

```text
_backups/resolver-feedback/resolver-feedback-latest.json
```

That export includes resolver events, proposal evidence and review state, releases, per-environment distribution/ACK state, and dream runs. The normal GBrain data backup then pushes the brain repository to `git@github.com:techtony2018/gbrain-data.git`.

To start recovery:

1. Restore the normal GBrain portable backup and file assets using the repository disaster-recovery runbook.
2. Call `resolver_feedback_restore` with the saved resolver feedback JSON.
3. Verify `resolver_feedback_health`, the active release checksum, and both environment distribution rows.
4. Run each agent bridge's `sync` command and confirm fresh ACKs before relying on the restored policy.

## Rollback

Rollback deactivates the selected release, marks its distributions `rolled_back`, reactivates the latest prior non-rolled-back release, and returns that release to `pending` until clients sync and ACK it.

```bash
gbrain call resolver_releases_rollback '{"version":"<resolver-version>","reason":"<reason>"}'
python3 ~/.gbrain/resolver-feedback-agent.py sync --environment codex
python3 ~/.gbrain/resolver-feedback-agent.py sync --environment openclaw
```

## Operational Checks

```bash
gbrain call resolver_feedback_health '{}'
gbrain call resolver_events_list '{"limit":20}'
gbrain call resolver_proposals_list '{"limit":20}'
curl -sS http://127.0.0.1:8788/api/resolver/health
```

A healthy loop has recent paired before/after events from both Codex and OpenClaw, a recent successful `resolver_learning` run with `auto_applied=0`, no stale accepted proposal awaiting an explicit decision, one active release at most, and `active` distribution rows whose checksums match that release.

