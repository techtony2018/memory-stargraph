# Memory Stargraph

Memory Stargraph is a local web service for exploring Tony's `gbrain` as an interactive star-cloud entity graph.

It is built with Python stdlib plus vanilla HTML/CSS/Canvas JavaScript, so it runs without `npm install`.

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

Right-click a node or use the `...` button beside the node summary. `Ask GBrain` is intentionally first because it is the most common daily action.

Supported node operations:

1. `Ask GBrain` - runs a contextual `gbrain query`.
2. `Show backlinks` - shows incoming links with `gbrain backlinks`.
3. `View media` - opens detected image/video/audio/PDF links from node markdown or frontmatter.
4. `Graph query from here` - runs typed/directional graph traversal.
5. `View history` - shows page version history.
6. `Add relationship` - creates a typed edge with `gbrain link`.
7. `Remove relationship` - removes an edge with `gbrain unlink`.
8. `Edit tags` - adds/removes tags with `gbrain tag` and `gbrain untag`.
9. `Add timeline event` - writes a dated entry with `gbrain timeline-add`.
10. `Attach file` - opens a browser file picker, uploads the selected file, and previews supported media.
11. `Refresh embedding` - runs `gbrain embed <slug>` where supported by the active backend.
12. `View raw details` - read-only `gbrain get`.
13. `Modify markdown` - edits the page with `gbrain put`.
14. `Hide` - hides a node in the web UI only.
15. `Copy slug` - copies the exact gbrain slug.
16. `Delete from gbrain` - deletes after exact node-name confirmation.

Node operation API contract:

- `GET /api/node-operations` - lists the supported operation endpoints.
- `GET /api/entity-media/<slug>` - lists detected media references from node markdown/frontmatter.
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
profile_image: https://example.com/people/witty-wang/witty-wang-profile.jpg
```

For local gbrain media, keep a relative path in the node:

```yaml
profile_image: people/witty-wang/witty-wang-profile.jpg
```

When `View media` opens, Memory Stargraph first checks whether that file is already under `media_roots`. If not, it searches `media_discovery_roots`, copies the file into the first media root, and then serves it. If gbrain can produce a signed URL, the service can also fetch that URL into the media root.

Example config:

```json
{
  "media_roots": ["media", "data/media"],
  "media_discovery_roots": ["media", "data/media", "~/Pictures", "~/Downloads", "~/Desktop", "~/.gbrain"],
  "media_fetch_timeout_seconds": 8,
  "max_upload_bytes": 26214400
}
```

For day-to-day use, choose `Attach file` from a node menu and pick the file in Finder. The service saves the upload, copies supported media into `media_roots`, and returns a `/media/...` preview URL. Host-local path entry remains available as a fallback for automation.

Memory Stargraph exposes supported image/video/audio/PDF files read-only at:

```text
http://<host>:8788/media/people/witty-wang/witty-wang-profile.jpg
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

Remote host notes:

- `.102` LAN host: `toddy@192.168.1.102` (`toddys-mac-mini-1`)
- Other live Mac mini: `toddy@100.100.126.85` (`toddys-mac-mini`, hostname observed as `toddys-mini-3.lan`)
- Clone target on both hosts: `/Users/toddy/memory-stargraph`
- Node and npx path: `/usr/local/bin`
- Bun and gbrain path: `/Users/toddy/.bun/bin`
- Use `config/local.json` with `"host": "0.0.0.0"` and `"gbrain_path": "/Users/toddy/.bun/bin/gbrain"` on those hosts.
- For SSH-run verification, export `PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"` first.

## AI Agent Setup Prompt

Use this prompt when asking an AI coding agent to set up, verify, or continue Memory Stargraph:

```text
You are working on Memory Stargraph in `/Users/tony/Documents/Collective Knowledge System`.

Goal:
- Set up and verify the local Memory Stargraph web service for Tony's gbrain entity graph.
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
- On remote Mac minis, use `/Users/toddy/.bun/bin/gbrain`, set `"host": "0.0.0.0"` in `config/local.json`, and export `PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"` for SSH-run checks.

Setup steps:
1. Inspect `git status --short` and do not revert unrelated user changes.
2. If needed, copy `config/local.example.json` to `config/local.json` and adjust only local machine values.
3. On remote Mac minis, set `config/local.json` to use `"host": "0.0.0.0"`, `"gbrain_path": "/Users/toddy/.bun/bin/gbrain"`, and a `media_roots` entry for any local gbrain image folder.
4. Start the service with `python3 server.py --host 127.0.0.1 --port 8788`.
5. Open `http://127.0.0.1:8788` and verify the graph loads.
6. Search `Tony Guan`, select the node, hover `Azul Systems`, and confirm the mouse-near popup shows `relationship: employed by`.
7. Confirm `Ask GBrain` is the first node menu item and all node operations render.

Verification commands:
- export PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
- python3 -m py_compile server.py
- python3 -m unittest discover -s tests
- node --check public/app.js
- node --check tests/browser_smoke.mjs
- node tests/browser_smoke.mjs
- If Playwright is not locally resolvable, use `npx --yes --package playwright node tests/browser_smoke.mjs`.

Supported node operations to preserve:
1. Ask GBrain
2. View media
3. Show backlinks
4. Graph query from here
5. View history
6. Add relationship
7. Remove relationship
8. Edit tags
9. Add timeline event
10. Attach file
11. Refresh embedding
12. View raw details
13. Modify markdown
14. Hide
15. Copy slug
16. Delete from gbrain

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

## Notes

- `Refresh embedding` depends on the active gbrain backend. Thin-client backends may report that `embed` is host-side/not routable.
- `Hide` is UI-only; it does not modify gbrain.
- `Delete from gbrain`, markdown edits, relationship edits, tag edits, timeline edits, and file attachments do modify gbrain.
