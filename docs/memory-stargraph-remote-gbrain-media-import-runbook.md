---
type: runbook
title: Memory Stargraph Remote GBrain Media Import Runbook
tags:
  - gbrain
  - media
  - memory-stargraph
  - remote-hosts
  - runbook
---

# Memory Stargraph Remote GBrain Media Import Runbook

Use this when importing images, videos, PDFs, or other supported attachments into a remote GBrain backend so every Memory Stargraph web-service host can later render the media without manual file copying.

This runbook complements [[docs/memory-stargraph-remote-media-runbook]], which focuses on rendering and cache-miss recovery after media already exists in GBrain.

## Goal

For every attachment, store both layers:

1. The page reference: a relative media path in the GBrain node markdown or frontmatter.
2. The file bytes: the actual media file uploaded into GBrain files/storage at the same relative path.

If only the markdown is updated, remote Stargraph hosts may show a broken image. If only the file is uploaded, users cannot discover it from the node. Both layers are required.

## Recommended Path Convention

Use stable relative paths that are safe to serve under `/media/...`.

Examples:

```text
people/example-person/profile.jpg
companies/example-company/logo.png
assets/posts/example-post/001-photo.jpg
assets/blogs/example-blog/diagram.pdf
```

Rules:

- Use relative paths only.
- Do not use absolute paths, `..`, or machine-specific folders.
- Prefer lowercase slugs and simple filenames.
- Keep the path aligned with the owning node slug when possible.
- Use supported preview formats for browser display: images, video, audio, and PDFs.

## Web UI Attach Flow

The easiest path is Memory Stargraph's node menu:

1. Select the target node.
2. Open `Attach file`.
3. Pick the file from Finder.
4. Add an optional description.
5. Submit.

The Stargraph service should then:

1. Accept the browser upload.
2. Save a temporary copy under its runtime upload area.
3. Materialize a stable relative media path for the selected node.
4. Run `gbrain files upload <local-file> --page <node-slug>`.
5. Copy supported preview media into the local web media root.
6. Copy the same file into any configured local GBrain file-store mirror if available.
7. Append a markdown reference such as `![description](relative/path.jpg)` or `[description](relative/path.pdf)` to the selected node.
8. Refresh the graph/cache for the selected node.

This is the preferred user-facing workflow because it updates the page reference and the stored file bytes together.

## Manual Single-File Import

Use this when operating from a shell or an agent.

1. Choose the target page slug:

```bash
PAGE_SLUG="people/example-person"
```

2. Choose the intended relative media path:

```bash
REL_PATH="people/example-person/profile.jpg"
```

3. Upload the local file to GBrain storage/files:

```bash
gbrain files upload "/path/to/profile.jpg" --page "$PAGE_SLUG"
```

4. Update the GBrain page markdown/frontmatter so it references the same relative path:

```markdown
profile_image: people/example-person/profile.jpg

![Profile image](people/example-person/profile.jpg)
```

5. Verify readback:

```bash
gbrain get "$PAGE_SLUG"
gbrain files list "$PAGE_SLUG"
```

If `gbrain files list "$PAGE_SLUG"` does not show the file, also check the relative directory or exact path used by your GBrain storage implementation.

## Batch Import Pattern

For many files:

1. Build a manifest with columns like:

```text
page_slug,local_file,relative_path,description
```

2. For each row:

- Validate that `local_file` exists.
- Validate that `relative_path` is relative and safe.
- Upload the file with `gbrain files upload`.
- Update the page markdown with the relative path and description.
- Record success/failure in a progress file so the import can resume.

3. After the batch:

- Run spot checks with `gbrain get`.
- Run `gbrain files list` for representative pages/directories.
- Open Memory Stargraph `View` and `View media` for representative nodes on each web-service host.

Existing Stargraph helper scripts should follow this resumable pattern and never rely on a local-only media mirror as the source of truth.

## Remote Stargraph Rendering Requirement

After import, a Stargraph host that does not already have the file in its local `media/` cache should still work.

Expected cache-miss behavior:

1. The node markdown/frontmatter references either a normal relative media path, such as `people/example/profile.jpg`, or an explicit `gbrain:files/...` path. Both forms must work and neither form should overwrite or disable the other.
2. `/api/entity-media/<slug>` or rendered `View` detects that path.
3. The service checks its local media root first.
4. If missing, it tries configured discovery roots, configured GBrain file-store roots, and trusted `remote_media_base_urls` or `gbrain_file_base_urls` HTTP endpoints.
5. **Do not call `gbrain files signed-url` from Memory Stargraph.** Stargraph has its own media resolution path, and signed-url is unsafe in this deployment because GBrain may have no storage backend and the CLI may be a remote thin-client. Calling it can spawn many stuck `bun ... gbrain files signed-url ...` processes and overload the GBrain host.
6. The service downloads/copies the file into its local media root.
7. The browser receives a local `/media/<relative-path>` URL.

On the GBrain host itself, do not configure `remote_media_base_urls` or `gbrain_file_base_urls` to point back to the same Stargraph service unless a non-recursive backing file store is configured. Otherwise a cache miss can recursively call the same host.

This means new web-service hosts should not need a full pre-synced `media/` mirror. The mirror is a cache, not the durable source of truth.

## Attachment Consistency Rule

The attach flow must never create a markdown-only media reference. A successful
attachment requires both:

1. `gbrain files upload <file> --page <slug>` succeeds.
2. `gbrain files list <slug>` shows the uploaded filename.

Only after both checks pass may Stargraph append or update markdown/frontmatter
references such as `![Label](people/example/photo.jpg)`. If the upload command
fails, or the file ledger does not show the file after upload, report the error
and leave the page markdown unchanged.

If an older node already contains a relative media reference but
`gbrain files list <slug>` says `No files for page`, treat that as a data
consistency bug. Repair it by uploading the original bytes to the GBrain files
ledger for the same page; copying into one web service's `media/` directory is
only a cache repair and is not sufficient.

## Verification Checklist

For a representative imported node:

```bash
gbrain get <node-slug>
gbrain files list <node-slug>
```

Then test from each Memory Stargraph host:

1. Open the node.
2. Open `View`; markdown images/links should render.
3. Open `View media`; the same media should appear.
4. Delete or rename the local cached file on a non-storage web host.
5. Reload `View media`.
6. Confirm the service recreates the local cached file from GBrain storage/files or a trusted remote media endpoint.

## Common Failure Modes

- Markdown references a local filesystem path like `/Users/...`; fix it to a relative media path.
- The file was copied into one host's `media/` directory but never uploaded to GBrain files/storage; remote hosts cannot recover it.
- The file was uploaded but the page markdown/frontmatter was not updated; users cannot discover it from the node.
- The relative path in markdown does not match the storage path.
- The web-service host lacks `media_roots`, `gbrain_file_store_roots`, trusted `remote_media_base_urls`, or trusted `gbrain_file_base_urls` for its topology. Stargraph must not depend on `gbrain files signed-url`.
- Browser cache is serving old markdown or old JS/CSS; refresh after verifying the backend response.

## Related Notes

- [[docs/memory-stargraph-remote-media-runbook]]
- [[docs/memory-stargraph-three-host-deployment-runbook]]
- [[products/memory-stargraph]]
