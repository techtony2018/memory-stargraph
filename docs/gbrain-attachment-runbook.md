---
type: runbook
title: GBrain Attachment Safety and Verification Runbook
tags:
  - attachments
  - gbrain
  - memory-stargraph
  - regression-prevention
  - runbook
---

# GBrain Attachment Safety and Verification Runbook

This is the canonical runbook for adding, replacing, repairing, verifying, backing up, and restoring files attached to GBrain pages through Memory Stargraph.

Use it for images, PDFs, audio, video, Office documents, and other files accepted by the configured GBrain storage backend. Other attachment documentation may add workflow-specific guidance, but it must not weaken or bypass this contract.

## The rule

An attachment is successful only when all three layers agree:

1. The GBrain page contains the canonical relative reference.
2. The GBrain file ledger contains exactly one matching page/path record.
3. The durable storage backend returns bytes whose size and SHA-256 match the source.

A Markdown reference, a ledger row, a successful HTTP response without durable evidence, or a warm Memory Stargraph cache is never enough by itself.

## Supported write boundary

All human and agent attachment writes must enter through Memory Stargraph:

```text
Finder or agent helper
        |
        v
POST /api/entity-attach-file/<URL-encoded-slug>
        |
        +--> validate and stage exact source bytes
        +--> canonicalize the filename once
        +--> optionally materialize a disposable local cache copy
        +--> call host GBrain directly or through the trusted SSH bridge
        +--> write/read the durable backing object
        +--> verify exact path + size + SHA-256
        +--> verify the ledger row
        +--> update page Markdown only after every check passes
        v
structured durable evidence returned to the caller
```

Do not call `gbrain files upload` directly from a thin client, capture skill, ad hoc agent script, or manual import workflow. It is a host-side implementation detail behind the Memory Stargraph boundary. This prevents callers from mistaking a ledger-only result or host-local cache for durable success.

## Non-negotiable invariants

1. **Preserve the source bytes.** Hash the source before mutation. Temporary chat-host paths must be copied into private recovery storage before creating durable GBrain state when the calling workflow supports recovery spooling.
2. **Canonicalize once.** Memory Stargraph uses one Unicode-NFC filename for staging, bridge transfer, storage path, ledger lookup, cache path, and Markdown. Whitespace becomes `-`; Unicode alphanumerics, `_`, `-`, and `.` are preserved.
3. **Storage precedes the ledger and Markdown.** Missing or unreadable storage fails the operation. No new Markdown reference may be committed.
4. **Read back the backing object.** Success requires an exact byte count and SHA-256 from storage, not only an upload return code.
5. **Verify the ledger.** The target page and canonical filename must have exactly one matching row.
6. **Make retries safe.** Re-uploading identical bytes to the same path returns `already_verified`. A ledger-present/blob-missing path is repaired. A different object at the same path is replaced only as an intentional same-path replacement.
7. **Treat caches as disposable.** Files under a Memory Stargraph `media/` directory accelerate reads. They are not authoritative storage and must be reconstructible.
8. **Never claim partial success.** If any required check fails, report the failure, preserve recovery evidence, and do not describe the attachment as complete.
9. **Never substitute content.** Do not regenerate, crop, transcode, rename to a guessed filename, or replace missing source bytes with a similar file.
10. **Keep destructive cleanup separate.** Do not delete old storage objects, legacy copies, or backups merely because a new attachment verifies. Cleanup requires explicit review.

## Prerequisites

Before attaching a file, verify the Memory Stargraph service and its storage route:

```bash
curl -sS http://127.0.0.1:8788/api/health | python3 -m json.tool
curl -sS http://127.0.0.1:8788/api/setup-diagnostics | python3 -m json.tool
```

The health response must report `ok: true`. `attachment_storage.available` must be `true`, using one of these modes:

- `local-durable-root`: the hosting Memory Stargraph can read the configured GBrain backing store.
- `trusted-host-endpoint`: a non-host Stargraph can recover files from the trusted hosting endpoint.

Do not continue when attachment storage reports `unavailable`.

## How to attach a file in the UI

1. Open the target node in Memory Stargraph.
2. Choose **Attach file**.
3. Select the exact source file.
4. Add a caption or description if useful.
5. Submit once and wait for completion.
6. Open **View** and **View media** to confirm the reference and preview.
7. Use the verification checklist below before reporting completion for important or automated work.

The UI and the agent helper use the same server endpoint and durable evidence contract.

## How to attach a file from Codex or a shell

Use the maintained helper from `gbrain-capture-link`:

```bash
python3 "$HOME/.codex/skills/gbrain-capture-link/scripts/upload_attachment_via_stargraph.py" \
  --slug "notes/example-node" \
  --file "/absolute/path/to/source.jpg" \
  --description "Source image" \
  --stargraph-url "http://127.0.0.1:8788"
```

Omit `--stargraph-url` to use this precedence:

1. `MEMORY_STARGRAPH_UPLOAD_URL`
2. `MEMORY_STARGRAPH_URL`
3. the helper's configured hosted Memory Stargraph default

The helper performs a health check, posts multipart form data to the URL-encoded attachment endpoint, requires durable evidence, downloads the served file, and compares its size and SHA-256 with the source. Treat a zero exit code and `remote_read_verified: true` as the minimum caller receipt.

Example success shape:

```json
{
  "ok": true,
  "slug": "notes/example-node",
  "ui_version": "V1.0.xxx",
  "served_url": "/media/notes/example-node/source.jpg",
  "bytes": 12345,
  "sha256": "<64 lowercase hex characters>",
  "remote_read_verified": true
}
```

The server response used by the helper must also contain `local_media` evidence:

| Field | Required meaning |
| --- | --- |
| `durable_storage_verified` | Must be exactly `true`. |
| `canonical_relative_path` | Safe path under the owning node slug. |
| `filename` | Canonical filename used by storage, ledger, and Markdown. |
| `size_bytes` | Exact source byte count. |
| `sha256` | Exact lowercase SHA-256 of the source bytes. |
| `upload_transport` | `local` or `ssh-bridge`. |
| `storage_disposition` | `uploaded`, `already_verified`, or `repaired`. |
| `served_url` | Local Memory Stargraph read URL used for caller verification. |

## How to attach files to a new Memory Stargraph TODO

Use `add-sg-todo` and pass every chat-host file as a separate `--attachment`. Do not paste a temporary file path into the description and call that attachment capture.

```bash
python3 "$HOME/.codex/skills/add-sg-todo/scripts/add_sg_todo.py" \
  --title "Short actionable title" \
  --description "Implementation and acceptance criteria." \
  --priority P2 \
  --attachment "/absolute/path/to/source.png" \
  --json
```

The TODO workflow privately spools the bytes, creates an unlinked provisional child, attaches and verifies every file, then commits the parent row and graph link. An attachment failure must leave the original TODO out of the actionable backlog and return a recovery manifest plus retry command.

## How to replace or repair an existing attachment

### Same canonical filename

Use the normal helper with the existing page slug and source filename.

- Identical durable bytes return `already_verified` without a duplicate ledger row.
- A missing backing object with an existing ledger row returns `repaired` after exact byte readback.
- Different bytes at the same canonical path are an intentional overwrite. Preserve the prior source or a verified backup first, record the old and new hashes, and verify every layer after upload.
- The Markdown reference remains idempotent when the canonical path is unchanged.

### Different filename

Attach the new file first and verify it completely. Then update the page to use the new canonical reference. Do not delete the old ledger/storage object in the same step. Review and perform cleanup separately only after cold-cache verification and explicit authorization.

### Missing original bytes

Do not invent or substitute them. Inventory trusted caches, backups, and original sources. If none match the expected path and available metadata, record the ledger row as unresolved.

## Full verification checklist

### 1. Source receipt

```bash
SOURCE="/absolute/path/to/source.jpg"
stat -f '%z bytes' "$SOURCE"
shasum -a 256 "$SOURCE"
```

Record the exact byte count and hash before uploading.

### 2. Page reference

```bash
gbrain get "notes/example-node"
```

Confirm the page contains the canonical relative path, `/media/...` path, or `gbrain:files/...` reference reported by Memory Stargraph. It must not contain the original absolute temporary path.

### 3. File ledger

Run this on the GBrain storage host because file commands can be host-local in thin-client topologies:

```bash
gbrain files list "notes/example-node"
```

Confirm exactly one row matches the page and canonical filename.

### 4. Durable backend

On the GBrain host:

```bash
gbrain files verify
```

This reads backing objects and compares their byte counts and hashes with the ledger. Any `MISSING` or `MISMATCH` is a failure that must remain visible and enumerable. Do not hide unrelated historical failures; state whether the target attachment itself passed.

### 5. Served-byte readback

The maintained helper performs this automatically. For an independent check:

```bash
curl -sS "http://127.0.0.1:8788/media/notes/example-node/source.jpg" -o /tmp/attachment-readback
stat -f '%z bytes' /tmp/attachment-readback
shasum -a 256 /tmp/attachment-readback
```

The values must equal the source receipt.

### 6. Idempotence

Run the same helper command again with the same bytes. Require:

- `storage_disposition: already_verified` in the server evidence;
- the same size and SHA-256;
- exactly one ledger row;
- one Markdown reference for the canonical path.

### 7. Cold-cache recovery

For every required Memory Stargraph target:

1. Rename the specific cached file instead of deleting it.
2. Request both `/media/<canonical-relative-path>` and `/gbrain-files/<canonical-relative-path>`.
3. Compare both responses with the source size and SHA-256.
4. Confirm Memory Stargraph rebuilt its local cache.
5. Remove only the temporary backup created by this test after byte-for-byte comparison succeeds.

Do not bulk-delete cache roots. Do not touch durable storage during a cache test.

### 8. Browser verification

Reuse an existing matching Memory Stargraph tab when possible. Refresh it, confirm the expected UI version, and verify **View** and **View media**. Record browser console/page errors and the tab count before and after. Close only temporary tabs created by the test.

## Storage topology

### GBrain storage host

GBrain must have a configured backend. A trusted single-host local backend may use:

```json
{
  "storage": {
    "backend": "local",
    "bucket": "brain-files",
    "localPath": "/path/to/durable/gbrain-data/files"
  }
}
```

The hosting Memory Stargraph sets `gbrain_file_store_roots` to that same durable root. Never set it to a Memory Stargraph `media/` cache.

### Non-host Memory Stargraph

A client Stargraph uses:

- `gbrain_files_bridge_ssh` and optional `gbrain_files_bridge_path` for trusted uploads when its local CLI cannot execute file operations;
- `gbrain_file_base_urls` for durable read recovery from the hosting Stargraph;
- a local `media/` root only as a rebuildable cache.

Do not configure a hosting Stargraph to call its own `/media/` or `/gbrain-files/` endpoint as an upstream source. That creates recursive cache misses.

## Failure semantics and containment

| Failure | Required result |
| --- | --- |
| No storage backend | Nonzero failure; no ledger-only success; no Markdown mutation. |
| Storage write/read failure | Nonzero failure with storage evidence; preserve source/recovery bytes. A staged or cached copy may exist, but it is not success. |
| Size or SHA mismatch | Nonzero failure; do not report completion. |
| Durable evidence missing or malformed | Caller rejects the response even if HTTP returned success. |
| Ledger row missing | No Markdown mutation; investigate bridge/host behavior. |
| Ledger exists but blob is missing | Re-upload exact original bytes and require `repaired`. |
| Served bytes differ | Fail caller verification; do not trust the cache. |
| Temporary source disappears | Retry only from preserved exact recovery bytes; never substitute. |
| Multi-attachment partial failure | Retain recovery state; do not finalize the parent workflow. |
| Remote host unavailable | Record the concrete target failure and keep the item incomplete. |

## Backup and restore

The disaster-recovery set includes all of these:

- GBrain page Markdown and graph links;
- the files ledger;
- durable attachment bytes at their canonical relative paths;
- byte counts, MIME types, and content hashes;
- private configuration needed to reconnect storage, without committing credentials.

Restore in this order:

1. Restore the GBrain database/ledger and page content.
2. Restore durable objects to their canonical relative paths.
3. Run `gbrain files verify` on the storage host.
4. Start the hosting Memory Stargraph with the durable root configured.
5. Start non-host Stargraph instances with the trusted host read endpoint.
6. Perform a cold-cache read and compare exact bytes.
7. Verify **View** and **View media** in a browser.

Do not declare restore complete from a database-only backup or a warm media cache.

## Regression firewall

Any change to Memory Stargraph attachment code, GBrain file storage, capture helpers, media routing, backup/restore, or deployment configuration must pass all applicable checks below.

### Memory Stargraph repository

```bash
python3 -m unittest discover -s tests
python3 -m py_compile server.py
node --check public/app.js
python3 -m unittest tests.test_documentation_contracts
```

Required behavioral coverage includes:

- filename canonicalization for ordinary spaces, Unicode whitespace, underscores, hyphens, and non-ASCII characters;
- exact path/size/SHA durable evidence parsing;
- no Markdown mutation on storage or ledger failure;
- trusted SSH bridge behavior;
- idempotent Markdown references;
- health diagnostics when storage is unavailable;
- remote/cache materialization.

### Capture helpers

```bash
python3 -m unittest discover -s "$HOME/.codex/skills/gbrain-capture-link/tests"
python3 -m unittest discover -s "$HOME/.codex/skills/add-sg-todo/tests"
```

Mirror relevant helper changes to OpenClaw and run its matching tests before release.

### GBrain repository

From the active GBrain implementation worktree:

```bash
bun test test/durable-file-storage.test.ts test/files-command.test.ts test/storage.test.ts
bunx tsc --noEmit
```

Required behavioral coverage includes missing-backend rejection, exact backing-object readback, idempotent retry, ledger-present/blob-missing repair, storage path safety, and full-ledger verification.

### Real integration gate

Unit tests are necessary but insufficient. Before completing an attachment/storage release:

1. Upload one representative file through the dashboard-managed local Stargraph.
2. Verify structured evidence, one ledger row, durable object size/hash, and page reference.
3. Repeat the upload and prove idempotence.
4. Run cold-cache recovery on every required target.
5. Verify the hosting endpoint and browser with the exact expected UI version.

If any gate is skipped, record that release as incomplete rather than silently reducing the contract.

## Release checklist

- [ ] Source size and SHA-256 recorded.
- [ ] Supported Memory Stargraph endpoint/helper used.
- [ ] Canonical filename/path consistent everywhere.
- [ ] `durable_storage_verified: true` returned.
- [ ] Response size and SHA-256 match the source.
- [ ] `remote_read_verified: true` returned to agent callers.
- [ ] Exactly one matching ledger row.
- [ ] Page reference uses the canonical path and no temporary absolute path.
- [ ] Idempotent retry verified.
- [ ] Target attachment passes durable backend verification.
- [ ] Cold-cache recovery verified on every required target.
- [ ] Browser **View** and **View media** verified after refresh.
- [ ] Backup/restore coverage remains valid.
- [ ] Memory Stargraph, capture-helper, and GBrain regression tests pass.
- [ ] No destructive cleanup or source substitution occurred.

## Related documentation

- [Remote GBrain media topology and cache recovery](memory-stargraph-remote-gbrain-media-import-runbook.md)
- [Memory Stargraph automation runbook](automation-runbook.md)
- [Add SG TODO attachment capture design](superpowers/specs/2026-07-15-add-sg-todo-attachment-capture-design.md)
