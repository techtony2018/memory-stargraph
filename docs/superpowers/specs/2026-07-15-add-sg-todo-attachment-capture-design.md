# Add SG TODO Attachment Capture Design

Date: 2026-07-15

## Purpose

Fix `/add-sg-todo` so a user-supplied attachment is preserved and durably attached to the generated TODO child node instead of being represented only by an expiring local path. SG-0124 demonstrated the failure: its description referenced a macOS `TemporaryItems` path, but the skill never uploaded the image and the operating system later removed it.

The fix applies to the personal skill source at `~/.codex/skills/add-sg-todo` and its installed OpenClaw mirror at `~/.openclaw/skills/add-sg-todo`.

## Decision

Use Memory Stargraph's existing file-attachment endpoint as the only upload boundary:

```text
POST /api/entity-attach-file/<encoded-node-slug>
```

The skill must not reproduce GBrain storage logic or call `gbrain files upload` directly. Memory Stargraph owns multipart parsing, GBrain file upload, ledger verification, local media materialization, and the durable Markdown reference.

The Stargraph base URL resolves in this order:

1. `--stargraph-url`;
2. `MEMORY_STARGRAPH_URL`;
3. `http://127.0.0.1:8788`.

## Command Contract

`add_sg_todo.py` gains:

```text
--attachment <local-path>     Repeatable user-supplied attachment
--stargraph-url <base-url>    Optional upload-service override
--json                        Structured result for the invoking agent
```

The skill instructions must require every attached local file supplied by the chat host to be passed as `--attachment`. Writing the file path into the description is not attachment capture and must never be used as a substitute.

## Successful Capture Flow

1. Validate title, description, priority, and every attachment path before any GBrain mutation.
2. Copy every attachment immediately into a private recovery directory under `${CODEX_HOME:-$HOME/.codex}/recovery/add-sg-todo/<timestamp>-<todo-slug>/`. Directories use owner-only permissions; preserved files are not committed or logged as bytes.
3. Confirm the configured Stargraph service responds to `/api/health` before creating the child.
4. Confirm the final child slug is not already occupied by a different TODO.
5. Create the provisional child node, but do not add its row to `notes/memory-starmap-todo-list` yet.
6. POST each preserved file as multipart field `file` to `/api/entity-attach-file/<encoded-node-slug>`. Include a concise attachment description when available.
7. Require an HTTP success response whose JSON contains `ok: true` and the expected child slug.
8. Read the child through GBrain and verify a durable `gbrain:files/<child-slug>/<filename>` reference exists for every attachment. A temporary absolute path does not satisfy verification.
9. Only after all attachments verify, add the parent table row, create the `has_todo` graph link, and report the TODO as `planned`.
10. Delete the private recovery bundle after successful parent/child/link readback.

Text-only TODO creation remains unchanged except for shared validation and structured output.

## Failure And Recovery Flow

If validation fails before spooling, make no GBrain changes and report the missing or unreadable input.

If the Stargraph health check or attachment request fails:

- do not add the original TODO to the parent backlog;
- preserve the recovery bundle with the exact attachment bytes and a sanitized request manifest;
- preserve an unlinked provisional child only when the attachment request may have persisted remote state; tag it as capture recovery rather than a planned backlog item;
- otherwise remove the newly created provisional child;
- never delete potentially persisted remote file bytes automatically;
- emit a structured blocker proposal and one-time reminder handoff.

The blocker output is a proposal, not an automatically filed TODO. It contains a proposed title, owner, evidence, acceptance criteria, and recovery verification:

- **Stargraph-owned:** health, routing, multipart, endpoint configuration, thin-client bridge, response-shape, or Markdown-update failures.
- **GBrain-owned:** a confirmed GBrain-host storage, ledger, quota, authorization, or file-integrity failure returned through the Stargraph endpoint.

Ambiguous failures default to Stargraph ownership because Stargraph owns the endpoint contract and must expose enough structured evidence to identify a downstream GBrain failure.

The helper writes a recovery manifest containing the preserved attachment paths, original title/description/priority, proposed blocker, failure evidence, retry command, and `remind_after` timestamp. It never stores credentials or private deployment coordinates.

## One-Time Reminder

The helper cannot know the invoking Codex/OpenClaw task destination, so it does not schedule automation directly. On attachment failure, its structured output uses `reminder_required: true`.

The `/add-sg-todo` skill then requires the invoking agent to create one reminder for the following local calendar day in the current task or equivalent user-visible destination. The reminder includes:

- the original TODO title;
- the recovery manifest path;
- the proposed Stargraph or GBrain blocker;
- the exact retry command;
- a warning not to substitute or regenerate attachment bytes.

The reminder does not automatically file either TODO. When it fires, the agent asks the user whether to file the blocker proposal or retry the original capture. A successful retry removes the recovery bundle. A dismissed reminder leaves cleanup under human control.

## Atomicity And Idempotency

- The parent row is the commit point: without verified attachments, the original TODO never enters the actionable backlog.
- A retry reuses the recovery manifest and exact preserved bytes.
- Existing parent IDs remain monotonic and are assigned at finalization time so failed captures do not consume an SG number.
- The helper refuses to overwrite a different existing child at the computed slug.
- Repeated endpoint responses or retries must not create duplicate parent rows or duplicate graph links.

## Security And Privacy

- Only explicit user-supplied local files are accepted.
- Recovery directories and files are owner-readable only.
- Attachment bytes, cookies, tokens, and deployment configuration are never printed.
- The Stargraph URL must be HTTP(S); credentials embedded in URLs are rejected.
- No blocker proposal is auto-approved or auto-filed.

## Testing

Add standard-library unit tests around the helper with subprocess and HTTP boundaries replaced by deterministic fakes. Tests must prove:

- an attached temporary file is spooled before mutation;
- a missing attachment aborts before any `gbrain put`;
- a successful Stargraph response plus child Markdown readback finalizes parent, child, and link;
- path-only description text never counts as attachment verification;
- Stargraph and GBrain failures receive the correct proposed owner;
- attachment failure leaves the parent backlog unchanged and produces a recovery manifest;
- structured output requests a one-time next-day reminder;
- retry uses the preserved bytes and removes recovery state after success;
- slug collisions and duplicate parent rows are rejected;
- the Codex source and OpenClaw installed copy remain identical.

Skill-pressure verification must also replay the SG-0124 scenario: given a chat attachment in a temporary directory, an agent must pass `--attachment`, verify durable capture, and never report success from a description containing only the temporary path.

## Acceptance Criteria

- `/add-sg-todo` uploads every supplied attachment through Memory Stargraph before adding the original TODO to the parent backlog.
- The generated child contains durable attachment references and no attachment depends on the original temporary path.
- A failed upload produces a human-reviewable Stargraph/GBrain blocker proposal and a one-time next-day reminder handoff.
- The original TODO is not actionable until its attachments verify.
- Text-only TODO capture continues to work.
- Both installed skill copies use the same tested implementation and instructions.

## Out Of Scope

- Repairing SG-0124 without the exact original image bytes being reattached.
- Implementing a new Stargraph or GBrain upload endpoint.
- Automatically filing blocker proposals.
- Automatically retrying uploads without human interaction.
- Regenerating, cropping, substituting, or otherwise changing attachment content.
