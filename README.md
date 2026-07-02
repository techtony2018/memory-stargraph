# Memory Stargraph

<p align="center">
  <img src="public/assets/brand/logo-circle-transparent.png" alt="Memory Stargraph logo" width="96">
</p>

<p align="center">
  <img src="public/assets/brand/wordmark-line.png" alt="Memory Stargraph" width="420">
</p>

Memory Stargraph is a local web service for exploring a `gbrain` knowledge base as an interactive star-cloud entity graph.

It is built with Python stdlib plus vanilla HTML/CSS/Canvas JavaScript, so it runs without `npm install`.

## Showcase

![Memory Stargraph interactive star-cloud UI](docs/assets/memory-stargraph-ui.png)

![Shared AI memory architecture](docs/assets/shared-ai-memory-architecture.png)

[Watch the demo video on YouTube](https://youtu.be/GbWZo7g1ZBA)

## Run

```bash
python3 server.py
```

Optional:

```bash
python3 server.py --host 127.0.0.1 --port 8788
```

Open:

```text
http://127.0.0.1:8788
```

## Day-To-Day Features

### 1. Search and Drill Down

- Search by slug, title, tag, or summary.
- Press `Return` or click `Search` to run a gbrain search.
- Search input and button are disabled while active search is running.
- Click any graph node to select it and load its direct neighbors.
- Double-click a node to open read-only raw details.
- The root `index` is eagerly loaded so the graph starts with real structure.

### 2. Understand Relationships In Place

- Node size scales with direct connection count.
- Selected nodes reveal all direct-neighbor labels.
- Hovering a directly linked node shows a 60% opacity popup near the mouse.
- On mobile Safari, tap a node to show the same hover-style popup near your finger.
- On mobile Safari, long-press a node to show the hover-style popup only.
- Use the `...` button in the selected-node panel on mobile to open node operations.
- The hover popup shows entity name/category, a brief summary, then relationship type.
- The relationship is also drawn on the selected-node edge when hovering a direct neighbor.
- Direct-link chips in the sidebar show relationship type on hover/focus.

### 3. Navigate the Stargraph

- Drag the graph to rotate the 3D-like star cloud.
- Zoom with the `+` / `-` buttons.
- Use `Cmd + mouse wheel` to zoom quickly.
- Use category/type/min-link filters together; filters are ANDed and clearable.
- Toggle `Only show matches` to reduce visual noise.

### 4. Use GBrain From Node Menus

Right-click a node or use the `...` button beside the node summary. `View` is intentionally first for quick reading, followed by `Ask GBrain` for contextual questions.

Supported node operations:

1. `View` - renders the node's gbrain markdown read-only, shows `slug: <slug>` above the content, and includes a `Modify markdown` button that edits the page with `gbrain put`.
2. `Timeline` - renders the node timeline read-only, with an `Add timeline event` button in the same window.
3. `Ask GBrain` - opens a chat-style Q&A panel and answers with direct graph context, detected media when relevant, and targeted `gbrain query` retrieval.
4. `View media` - opens detected image/video/audio/PDF links from node markdown or frontmatter.
5. `Graph query from here` - runs typed/directional graph traversal with guided controls for relationship type, direction, and depth.
6. `View history` - shows page version history.
7. `Add relationship` - searches/selects a target node and relationship type, while still allowing a new relationship type.
8. `Remove relationship` - searches/selects from existing relationships only, then removes that edge with `gbrain unlink`.
9. `Show backlinks` - shows incoming links with `gbrain backlinks`.
10. `Edit tags` - selects existing tags to add, accepts a new tag, and removes only tags already applied to the entity.
11. `Attach file` - opens a browser file picker, uploads the selected file, appends a markdown media reference, and previews supported media.
12. `Refresh embedding` - runs `gbrain embed <slug>` where supported by the active backend.
13. `Hide` - hides a node in the web UI only.
14. `Delete from gbrain` - deletes after exact node-name confirmation.

`Add timeline event` uses four guided fields: selectable date, summary, detail, and source.

Node operation API contract:

- `GET /api/node-operations` - lists the supported operation endpoints.
- `GET /api/entity-media/<slug>` - lists detected media references from node markdown/frontmatter.
- `GET /api/entity-timeline-view/<slug>` - renders timeline entries read-only.
- `GET /media/<relative-path>` - serves configured local media files read-only.
- `POST /api/entity-ask/<slug>` - ask gbrain about a node.
- `POST /api/entity-backlinks/<slug>` - show backlinks.
- `POST /api/entity-graph-query/<slug>` - run typed/directional graph traversal.
- `POST /api/entity-history/<slug>` - show page history.
- `POST /api/entity-link/<slug>` - add a typed relationship.
- `POST /api/entity-unlink/<slug>` - remove a relationship.
- `POST /api/entity-tags/<slug>` - add/remove tags.
- `POST /api/entity-timeline/<slug>` - add a timeline event.
- `POST /api/entity-attach-file/<slug>` - attach a file to the node.
- `POST /api/entity-embed/<slug>` - refresh embedding where supported.

### 5. Keep The View Clean

- Hide nodes from the galaxy without modifying gbrain.
- Hidden nodes appear in the sidebar `Hidden List`.
- Hidden nodes can be restored with `Show`.
- Hidden-list state persists in the local web backend across launches.
- Repeated dated reports such as `agent/reports/gbrain-usage-YYYY-MM-DD` are collapsed into one aggregate node.
- Document parts like `The RFC - JTuner - Part xx` are collapsed into one parent node.
- Path-style labels are humanized, such as `companies/uber` to `Uber`.

### Local Media URLs

Use normal HTTP/HTTPS links when media is already hosted:

```yaml
cover_image: https://example.com/assets/project-cover.jpg
```

For local gbrain media, keep a relative path in the node:

```yaml
cover_image: projects/example-project/project-cover.jpg
```

When `View media` opens, Memory Stargraph first checks whether that file is already under `media_roots`. If not, it searches `media_discovery_roots`, copies the file into the first media root, and then serves it. By default, discovery stays inside app-owned directories such as `media`, `data/media`, and `data/uploads` so macOS does not ask for access to user folders like Downloads or Desktop. Add user folders only as an explicit local opt-in. If gbrain can produce a signed URL, the service can also fetch that URL into the media root.

When the web service runs on a different host than the gbrain data/media host, configure `remote_media_base_urls` on the web host. Each base URL should point to a trusted read-only `/media/` endpoint on a machine that can see the original media files. The web host will fetch missing media from that endpoint, cache it into its own first `media_roots` entry, and then serve it locally.

Example config:

```json
{
  "media_roots": ["media", "data/media"],
  "media_discovery_roots": ["media", "data/media", "data/uploads"],
  "remote_media_base_urls": ["https://gbrain-media.example.com/media/"],
  "media_fetch_timeout_seconds": 8,
  "max_upload_bytes": 26214400
}
```

For day-to-day use, choose `Attach file` from a node menu, pick the file in Finder, and optionally add a short description. The service saves the upload, copies supported media into `media_roots`, appends an `## Attachments` markdown reference to the node page using the description as the caption or alt text, and returns a `/media/...` preview URL. Host-local path attachment remains available through the JSON API for automation.

Memory Stargraph exposes supported image/video/audio/PDF files read-only at:

```text
http://<host>:8788/media/projects/example-project/project-cover.jpg
```

The media route rejects path traversal and non-media extensions.

### 6. Refresh and Freshness

- `Refresh Graph` is idempotent and disabled while refresh is in progress.
- Auto-refresh is optional from the top-right controls.
- Auto-refresh interval is editable in minutes.
- Latest refresh time is shown in the header.
- `/api/health` is intentionally lightweight and does not spend extra gbrain graph/query budget.

## GBrain Integration

Default backend path:

```text
/opt/homebrew/bin/gbrain
```

### GBrain Setup Requirements

Memory Stargraph works best when `gbrain` is already initialized and healthy on the machine running the web service. Before launching the service, verify:

- `gbrain` is installed and runnable from the service process. If it is installed through a user-local runtime, add that runtime's `bin` directory to `PATH` or set `"gbrain_path"` in `config/local.json`.
- The host has a valid gbrain configuration. A storage host should have a normal local database configuration; a client-only machine should have a working `remote_mcp` configuration and pass `gbrain remote doctor`.
- Basic read commands work: `gbrain list`, `gbrain get <slug>`, `gbrain graph <slug> --depth 1`, `gbrain backlinks <slug>`, and `gbrain search <query>`.
- Mutation commands you plan to expose from the UI work in your topology: `put`, `link`, `unlink`, `tag`, `untag`, `timeline-add`, `files upload`, and `delete`.
- Media files referenced by gbrain pages are reachable from the web service. Use local `media_roots` when the files are on the same host, or configure `remote_media_base_urls` when the web service is on a different host.
- The root `index` page exists and is useful, because Memory Stargraph expands it eagerly to give the graph a meaningful starting structure.

For multi-machine setups, run the service on each web host with its own `config/local.json`. Keep runtime state local, keep secrets out of the repo, and verify `/api/health` plus one known entity search after every deployment.

Upstream GBrain note: for remote-MCP installations with multiple clients, see the submitted GBrain PR [garrytan/gbrain#2501](https://github.com/garrytan/gbrain/pull/2501), which makes the OAuth token rate limit configurable. That helps avoid noisy refresh failures when several agents or web services share the same GBrain host.

Load strategy:

1. `gbrain list -n 140`
2. Eager root expansion with `gbrain graph index --depth 1` and `gbrain backlinks index`
3. Lazy node expansion with `gbrain graph <slug> --depth 1` and `gbrain backlinks <slug>`
4. Search enrichment with `gbrain search <query>`
5. Raw details with `gbrain get <slug>` on demand

If live gbrain access fails, the service:

1. Tries `data/graph_cache.json` from the last successful load.
2. Falls back to bundled demo data.
3. Surfaces cache/demo/error status in the UI.

## Local Configuration

Committed example:

```text
config/local.example.json
```

Local override, ignored by Git:

```text
config/local.json
```

Supported config keys include host, port, public directory, data directory, gbrain path, list count, graph depth, cache staleness, command limit, and command pause.

Runtime state is local-only:

```text
data/graph_cache.json
data/hidden_entities.json
data/deleted_entities.json
```

Deployment notes:

- Keep `config/local.json` uncommitted and machine-specific.
- For LAN or remote access, set `"host": "0.0.0.0"` in `config/local.json` or pass `--host 0.0.0.0`.
- Set `"gbrain_path"` to the absolute `gbrain` binary path on the target machine.
- If `gbrain` is installed in a user-local package manager path, export that path before starting or testing the service.
- If the web host is not the media storage host, set `"remote_media_base_urls"` to a trusted media endpoint on the storage host.
- Keep media roots local to the target machine and avoid committing uploaded media or runtime cache files.

## AI Agent Setup Prompt

Use this prompt when asking an AI coding agent to set up, verify, or continue Memory Stargraph:

```text
You are working on Memory Stargraph from a clean clone of `git@github.com:techtony2018/memory-stargraph.git`.

Goal:
- Set up and verify the local Memory Stargraph web service for a gbrain entity graph.
- Keep local runtime state separate from public repo files.
- Do not commit `data/*.json`, `config/local.json`, `.DS_Store`, caches, screenshots, or private `.project/` notes.

Repository and public layout:
- Public repo target: `git@github.com:techtony2018/memory-stargraph.git`
- Python service: `server.py`
- Public web files: `public/index.html`, `public/styles.css`, `public/app.js`
- Config example: `config/local.example.json`
- Local override: `config/local.json` (ignored by Git)
- Runtime state: `data/graph_cache.json`, `data/hidden_entities.json`, `data/deleted_entities.json` (ignored by Git)

Expected local service:
- URL: `http://127.0.0.1:8788`
- Health check: `curl -sS http://127.0.0.1:8788/api/health`
- Default gbrain path: `/opt/homebrew/bin/gbrain`
- On other machines, set `"gbrain_path"` to the installed gbrain binary, set `"host": "0.0.0.0"` only when remote access is intended, set `"remote_media_base_urls"` when media lives on another host, and export any required package-manager paths before starting the service.

Setup steps:
1. Inspect `git status --short` and do not revert unrelated user changes.
2. If needed, copy `config/local.example.json` to `config/local.json` and adjust only local machine values.
3. On remote or shared machines, set `config/local.json` to use the target machine's `"gbrain_path"` and a `media_roots` entry for any local gbrain image folder. If media is stored on a different host, add that host's `/media/` endpoint to `"remote_media_base_urls"`.
4. Start the service with `python3 server.py --host 127.0.0.1 --port 8788`.
5. Open `http://127.0.0.1:8788` and verify the graph loads.
6. Search for a known entity in your gbrain, select it, hover a direct neighbor, and confirm the mouse-near popup shows the relationship type.
7. Confirm `View` is the first node menu item and all node operations render.

HTTPS options:
- For Tailscale access, prefer keeping Memory Stargraph on local HTTP and putting Tailscale Serve in front of it:

```bash
python3 server.py --host 127.0.0.1 --port 8788
tailscale serve --https=443 http://127.0.0.1:8788
```

Then open `https://<machine>.<tailnet>.ts.net/`.

- If you already have a certificate and key, Memory Stargraph can serve HTTPS directly:

```bash
python3 server.py --host 0.0.0.0 --port 8788 --certfile /path/fullchain.pem --keyfile /path/privkey.pem
```

Direct TLS on port `8788` will use `https://<host>:8788/`; Tailscale Serve is usually cleaner because it manages the trusted tailnet certificate.

Verification commands:
- export PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
- python3 -m py_compile server.py
- python3 -m unittest discover -s tests
- node --check public/app.js
- node --check tests/browser_smoke.mjs
- node tests/browser_smoke.mjs
- If Playwright is not locally resolvable, use `npx --yes --package playwright node tests/browser_smoke.mjs`.

Supported node operations to preserve:
1. View
2. Timeline
3. Ask GBrain
4. View media
5. Graph query from here
6. View history
7. Add relationship
8. Remove relationship
9. Show backlinks
10. Edit tags
11. Attach file
12. Refresh embedding
13. Hide
14. Delete from gbrain

Behavior requirements:
- Root `index` should always load eagerly.
- Search should be explicit via Return or the Search button.
- Refresh Graph should disable while active.
- Hidden nodes are UI-only and persistent in the local backend.
- Relationships should be visible on graph hover in the 60% opacity mouse-near popup.
- Direct-neighbor labels should be visible when a node is selected.
- Path-style labels should be humanized, e.g. `companies/uber` to `Uber`.
- Aggregated part/report nodes should stay collapsed.

Safety:
- `Hide` is UI-only.
- `Delete from gbrain`, markdown edits, relationship edits, tags, timeline events, and file attachments modify gbrain.
- `Refresh embedding` may be unavailable in thin-client mode; surface the real gbrain error instead of hiding it.
- Do not push until the verification commands pass and the browser smoke has been run or a specific blocker is reported.
```

## Project Layout

- `server.py` - Python stdlib web service and gbrain command adapter
- `public/index.html` - app shell
- `public/styles.css` - visual system and responsive layout
- `public/app.js` - graph rendering, interactions, and node operations
- `tests/test_graph_parsing.py` - backend parser and command-construction tests
- `tests/browser_smoke.mjs` - Playwright end-to-end smoke test
- `dashboard-integration.json` - All Things Codex Dashboard launcher metadata

## Verification

```bash
python3 -m py_compile server.py
python3 -m unittest discover -s tests
node --check public/app.js
node --check tests/browser_smoke.mjs
node tests/browser_smoke.mjs
```

Useful live checks:

```bash
curl -sS http://127.0.0.1:8788/api/health
curl -sS http://127.0.0.1:8788/api/graph
```

## License

Memory Stargraph is released under the MIT License. See [LICENSE](LICENSE).

## Notes

- `Refresh embedding` depends on the active gbrain backend. Thin-client backends may report that `embed` is host-side/not routable.
- `Hide` is UI-only; it does not modify gbrain.
- `Delete from gbrain`, markdown edits, relationship edits, tag edits, timeline edits, and file attachments do modify gbrain.
