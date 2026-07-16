---
type: runbook
title: Memory Stargraph Remote Media Topology and Cache Recovery Runbook
tags:
  - gbrain
  - media
  - memory-stargraph
  - remote-hosts
  - runbook
---

# Memory Stargraph Remote Media Topology and Cache Recovery Runbook

Use this runbook to configure and verify remote Memory Stargraph hosts after attachment bytes have entered the supported durable upload boundary.

The canonical write, replacement, repair, evidence, backup, and release contract is [GBrain Attachment Safety and Verification](gbrain-attachment-runbook.md). Follow that runbook for every attachment mutation. This document only adds multi-host read routing and cache-recovery guidance.

## Goal

Every Memory Stargraph host must render the same attachment from the same canonical relative path without manual copying. A host with an empty local media cache must recover exact bytes from durable GBrain storage or the trusted hosting endpoint.

## Source of truth and cache roles

| Layer | Role | Authoritative? |
| --- | --- | --- |
| GBrain page Markdown/frontmatter | Makes the attachment discoverable from the node. | Yes, for the reference. |
| GBrain files ledger | Maps page, filename, storage path, size, and content hash. | Yes, for metadata, but insufficient alone. |
| Configured GBrain storage backend | Stores the exact backing object. | Yes, for bytes. |
| Hosting Stargraph `media/` | Accelerates browser reads. | No; rebuildable cache. |
| Non-host Stargraph `media/` | Accelerates local browser reads. | No; rebuildable cache. |
| Original source/recovery bundle | Enables rollback or repair. | Preserve until durable verification and backup succeed. |

Never promote a Stargraph `media/` directory to the durable source simply because it currently renders.

## Hosting topology

### GBrain storage host

The storage host needs:

1. A configured GBrain storage backend.
2. A stable durable root outside Memory Stargraph caches when using the local backend.
3. Hosting Stargraph `gbrain_file_store_roots` set to that durable root.
4. Read and write permissions for the service user.
5. Backup coverage for the durable root, ledger, page Markdown, and graph links.

Example shape, with deployment-specific paths kept in private configuration:

```json
{
  "storage": {
    "backend": "local",
    "bucket": "brain-files",
    "localPath": "/path/to/durable/gbrain-data/files"
  }
}
```

```json
{
  "gbrain_file_store_roots": [
    "/path/to/durable/gbrain-data/files"
  ]
}
```

Do not configure the hosting Stargraph to fetch from its own `/media/` or `/gbrain-files/` URL. A self-reference can recurse forever on a cache miss.

### Non-host Stargraph

A non-host service needs:

1. A writable local `media/` cache.
2. `gbrain_file_base_urls` pointing to the trusted hosting Stargraph.
3. A trusted `gbrain_files_bridge_ssh` route when the local GBrain CLI cannot perform host-local file operations.
4. An optional `gbrain_files_bridge_path` when `gbrain` is not on the bridge host's deterministic PATH.

Example shape:

```json
{
  "media_roots": ["media"],
  "gbrain_file_store_roots": [],
  "gbrain_file_base_urls": ["https://trusted-memory-stargraph.example"],
  "gbrain_files_bridge_ssh": "user@trusted-gbrain-host",
  "gbrain_files_bridge_path": "/absolute/path/to/gbrain"
}
```

Do not commit concrete private hosts, usernames, credentials, keys, or local storage paths.

## Supported attachment entry points

Remote topology does not change the write contract. Use one of these:

- Memory Stargraph **Attach file** UI.
- `gbrain-capture-link`'s `upload_attachment_via_stargraph.py` helper.
- `add-sg-todo.py --attachment` for TODO capture with recovery spooling.

All three routes call `POST /api/entity-attach-file/<URL-encoded-slug>` and require the canonical runbook's durable evidence. Direct file-ledger commands from a thin client or ad hoc script are unsupported.

## Cache-miss flow

When a page references `notes/example/photo.jpg` or `gbrain:files/notes/example/photo.jpg`:

1. Memory Stargraph validates the path and rejects traversal.
2. It checks its local media cache.
3. A hosting service checks configured durable file-store roots.
4. A non-host service tries trusted remote media/file endpoints.
5. It downloads or copies the bytes into the local media cache.
6. The browser receives `/media/notes/example/photo.jpg`.

Memory Stargraph must not call `gbrain files signed-url` during this flow. Signed URLs are unnecessary for this topology and can create stuck processes when the active CLI is a remote thin client.

## Cold-cache verification

Test every required host independently:

1. Record the source size and SHA-256.
2. Locate the specific cached file under that host's Memory Stargraph media root.
3. Rename only that file to a temporary backup.
4. Request `/media/<canonical-relative-path>`.
5. Request `/gbrain-files/<canonical-relative-path>`.
6. Confirm both responses return HTTP 200 with the source size and SHA-256.
7. Confirm the local cache was rebuilt with the same bytes.
8. Remove only the test backup after a byte-for-byte comparison succeeds.
9. Open **View** and **View media** in a refreshed browser.

Do not bulk-delete cache directories. Do not copy a file into a cache as the "fix". A cache must rebuild from the durable route without manual intervention.

## Adding a new host

1. Create a host-local `config/local.json` from the tracked example.
2. Configure only that host's cache and trusted durable read route.
3. Start the service and check:

   ```bash
   curl -sS http://127.0.0.1:8788/api/health | python3 -m json.tool
   curl -sS http://127.0.0.1:8788/api/setup-diagnostics | python3 -m json.tool
   ```

4. Require `attachment_storage.available: true`.
5. Choose an existing verified attachment and run the cold-cache procedure.
6. Verify the served UI version and browser behavior.

The host is not ready for attachments if it can render only after someone manually copies media into its cache.

## Troubleshooting

### The ledger has a row but the host returns 404

The backing object may be missing, or the host's durable read route may be wrong. Find the exact original bytes, upload them through the supported Memory Stargraph attachment boundary, require `storage_disposition: repaired`, then rerun cold-cache verification.

### Hosting works but a non-host returns 404

Check `gbrain_file_base_urls`, network reachability, TLS trust, and the requested canonical path. Do not add a one-off cache copy.

### Only a warm cache works

Treat the attachment as incomplete. Rename the cache file and verify recovery. If recovery fails, inspect storage and routing before changing page Markdown.

### The hosting service loops or times out on a file request

Check for a self-referential upstream URL. The host that reads the durable root must not call itself as a remote media source.

### The filename differs between Markdown and the ledger

Reattach the exact source through Memory Stargraph so the one canonical filename is used for staging, bridge transfer, storage, ledger, and Markdown. Do not patch each layer by hand.

### A remote upload reports success but no durable evidence

The caller must reject it. Verify that the deployed GBrain build emits structured durable evidence and that Memory Stargraph requires exact path, size, and SHA-256 before updating Markdown.

## Release gate

Any change to remote media routing or caching must still pass the full [attachment regression firewall](gbrain-attachment-runbook.md#regression-firewall). In addition:

- test at least one hosting Stargraph with a local durable root;
- test at least one non-host Stargraph with an empty cache;
- compare exact bytes from both `/media/` and `/gbrain-files/`;
- verify the expected UI version and service process directory on each target;
- preserve unrelated remote files and private configuration.

## Related documentation

- [GBrain Attachment Safety and Verification Runbook](gbrain-attachment-runbook.md)
- [Memory Stargraph Automation Runbook](automation-runbook.md)
- [Add SG TODO Attachment Capture Design](superpowers/specs/2026-07-15-add-sg-todo-attachment-capture-design.md)
