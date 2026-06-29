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
3. `Graph query from here` - runs typed/directional graph traversal.
4. `View history` - shows page version history.
5. `Add relationship` - creates a typed edge with `gbrain link`.
6. `Remove relationship` - removes an edge with `gbrain unlink`.
7. `Edit tags` - adds/removes tags with `gbrain tag` and `gbrain untag`.
8. `Add timeline event` - writes a dated entry with `gbrain timeline-add`.
9. `Attach file` - uploads a local file with `gbrain files upload --page`.
10. `Refresh embedding` - runs `gbrain embed <slug>` where supported by the active backend.
11. `View raw details` - read-only `gbrain get`.
12. `Modify markdown` - edits the page with `gbrain put`.
13. `Hide` - hides a node in the web UI only.
14. `Copy slug` - copies the exact gbrain slug.
15. `Delete from gbrain` - deletes after exact node-name confirmation.

### 5. Keep The View Clean

- Hide nodes from the galaxy without modifying gbrain.
- Hidden nodes appear in the sidebar `Hidden List`.
- Hidden nodes can be restored with `Show`.
- Hidden-list state persists in the local web backend across launches.
- Repeated dated reports such as `agent/reports/gbrain-usage-YYYY-MM-DD` are collapsed into one aggregate node.
- Document parts like `The RFC - JTuner - Part xx` are collapsed into one parent node.
- Path-style labels are humanized, such as `companies/uber` to `Uber`.

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

Remote host note for `toddy@192.168.1.102`:

- Clone target: `/Users/toddy/memory-stargraph`
- Node and npx path: `/usr/local/bin`
- Bun and gbrain path: `/Users/toddy/.bun/bin`
- Use `config/local.json` with `"gbrain_path": "/Users/toddy/.bun/bin/gbrain"` on that host.
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
- On `toddy@192.168.1.102`, use `/Users/toddy/.bun/bin/gbrain` and export `PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"` for SSH-run checks.

Setup steps:
1. Inspect `git status --short` and do not revert unrelated user changes.
2. If needed, copy `config/local.example.json` to `config/local.json` and adjust only local machine values.
3. On `.102`, set `config/local.json` to use `"gbrain_path": "/Users/toddy/.bun/bin/gbrain"`.
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

Supported node operations to preserve:
1. Ask GBrain
2. Show backlinks
3. Graph query from here
4. View history
5. Add relationship
6. Remove relationship
7. Edit tags
8. Add timeline event
9. Attach file
10. Refresh embedding
11. View raw details
12. Modify markdown
13. Hide
14. Copy slug
15. Delete from gbrain

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
