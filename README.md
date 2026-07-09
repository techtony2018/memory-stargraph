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

### Interactive Stargraph

<p align="center">
  <img src="docs/assets/memory-stargraph-ui-2026-07-08.png" alt="Memory Stargraph interactive star-cloud UI showing clustered gbrain entities, relationship hover, Ask Yoda, Autopilot, and local cache controls">
</p>

### Shared AI Memory Architecture

<p align="center">
  <img src="docs/assets/shared-ai-memory-architecture.png" alt="Memory Stargraph and GBrain shared AI memory architecture diagram">
</p>

[Watch the demo video on YouTube](https://youtu.be/eQ5UJKYMKaA)

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

## Main Features

These are the highest-value capabilities for turning a `gbrain` knowledge base into an operational shared memory system.

1. **Ask Yoda** - The core differentiator: node-scoped AI Q&A grounded in the selected page, graph-depth context, media hints, relationship evidence, and targeted `gbrain` retrieval.
2. **Interactive entity graph exploration** - The main product surface: a star-cloud map for navigating `gbrain` entities with exact search, click-to-select, lazy neighbor loading, hover context, and drill-down from any node.
3. **Relationship and backlink traversal** - The knowledge-graph workbench: inspect outgoing relationships, incoming backlinks, relationship labels, and connected slugs so AI reasoning paths can be followed and debugged.
4. **Entity mutation from the UI** - More than a read-only viewer: edit tags, add timeline events, attach files, refresh embeddings, add/remove relationships, hide noisy nodes, and create new entities from one cockpit.
5. **Media and document attachments** - Knowledge is not only text: attach, reference, preview, and serve trusted local or remote media alongside markdown pages and graph relationships.
6. **Fast exact-slug and Unicode-aware search** - Built for real `gbrain` data: exact slugs resolve before indexed search, imported archive names stay usable, and non-English terms are preserved through search and navigation.
7. **Autopilot memory tour** - A strong demo and discovery mode: browse important nodes without starting from a blank map, customize the playback list, loop through a plan, and continue gracefully through partial node loads.
8. **Local caching** - Keeps the graph usable when `gbrain`, remote MCP, or media sources are slow: cache node content and media in the browser with a visible budget, usage readout, and one-click flush.
9. **Performance-optimized large graph rendering** - Required once memory gets big: culling, idle rendering, filtered edge work, hidden-node behavior, and bounded animation keep dense graphs responsive.
10. **Remote/dashboard operation and health checks** - Operational beyond one laptop: run through the local dashboard or remote hosts with version checks, health probes, host-specific config, and deployment verification.

## How Ask Yoda Works

Ask Yoda is a node-scoped chat workflow. When you open Ask Yoda from a selected node, the browser sends the node slug, current question, recent chat history, and configured Yoda depth to the local Memory Stargraph server. Yoda depth controls graph-query hop depth and how many related source nodes the server reads directly: lower values are faster, higher values provide broader graph context. V1.0.118 exposes that depth both in the Ask Yoda chat and in Settings, with both controls staying synchronized.

Under the hood, the server gathers the selected page with `gbrain get`, nearby relationships with graph/backlink queries, backlinks, targeted search snippets, media hints, and direct reads of likely related source nodes. It keeps the prompt focused on the selected node, relationship labels, summaries, and nearby slugs so the answer can cite concrete graph context without dumping raw command output. If the configured agent path is available, Memory Stargraph asks that local agent to produce the response. If the agent is unavailable or times out, the endpoint falls back to a concise GBrain-context response so the UI still gives an actionable answer.

The Ask Yoda **View Log** button opens a scrollable diagnostics window for the latest request. It shows the `request_id`, selected slug, depth, source, timing phases, fallback status, model/OpenClaw status, and safe stdout/stderr or error summaries when available. It is intended for debugging endpoint behavior without exposing full prompts, secrets, or raw private context.

## Posts about Memory Stargraph

- [GBrain AI agents post](https://www.linkedin.com/posts/realtony_gbrain-ai-aiagents-ugcPost-7480756078972989440-LAZY)
- [Memory Stargraph build post](https://www.linkedin.com/posts/realtony_gbrain-ai-aiagents-ugcPost-7477536967237242881-GMbC)

## Autopilot Plan

Autopilot can play a generated list from the currently visible map or a manually edited list. The Auto list is read-only and is enabled by default. Turn Auto list off in the Plan window to edit the Manual plan, use **Fill** to replace the manual list from visible nodes, **Add** for blank entries, or **Clear** to empty the plan after confirmation. Slug fields show cached matches after two characters; press Return for live GBrain search when the cached list is not enough. Delay starts after the selected node fully loads, or after the 20-second partial-info fallback. - Days controls the recency filter used when generating the list.

The chat panel stores the visible conversation in browser state for the current session. It does not create durable GBrain notes by itself; durable changes still go through explicit actions such as modifying markdown, adding relationships, tags, timeline events, or attachments.

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
- scripts/automation/preflight.sh
- python3 -m py_compile server.py
- python3 -m unittest discover -s tests
- node --check public/app.js
- node --check tests/browser_smoke.mjs
- node tests/browser_smoke.mjs
- If Playwright is not locally resolvable, use `npx --yes --package playwright node tests/browser_smoke.mjs`.
- For Chrome CDP verification, use `npx --yes --package playwright node scripts/automation/cdp_probe.mjs V1.0.xx http://127.0.0.1:8788`.

Supported node operations to preserve:
1. View
2. Ask Yoda
3. View media
4. Relationships
5. Backlinks
6. Edit tags
7. Attach file
8. Query
9. Timeline
10. History
11. Refresh embedding
12. Hide

Behavior requirements:
- Root `index` should always load eagerly.
- Search should be explicit via Return or the Search button.
- Hidden nodes are UI-only and persistent in the local backend.
- Relationships should be visible on graph hover in the 60% opacity mouse-near popup.
- Direct-neighbor labels should be visible when a node is selected.
- Path-style labels should be humanized, e.g. `companies/uber` to `Uber`.
- Aggregated part/report nodes should stay collapsed.

Safety:
- `Hide` is UI-only.
- `Delete from gbrain`, markdown edits, relationship edits, timeline events, and file attachments modify gbrain.
- Do not push until the verification commands pass and the browser smoke has been run or a specific blocker is reported.
- Any automation run lasting more than five minutes must append a short retrospective with `scripts/automation/retrospect.sh`, then implement or record at least one concrete process improvement.
```

## Project Layout

- `server.py` - Python stdlib web service and gbrain command adapter
- `public/index.html` - app shell
- `public/styles.css` - visual system and responsive layout
- `public/app.js` - graph rendering, interactions, and node operations
- `tests/test_graph_parsing.py` - backend parser and command-construction tests
- `tests/browser_smoke.mjs` - Playwright end-to-end smoke test
- `scripts/automation/` - preflight, deployment, Chrome CDP, and retrospective helpers for daily automation runs
- `docs/automation-runbook.md` - daily automation runbook with host routes, deploy checks, and the five-minute retrospective hook
- `dashboard-integration.json` - All Things Codex Dashboard launcher metadata

## Verification

```bash
scripts/automation/preflight.sh
python3 -m py_compile server.py
python3 -m unittest discover -s tests
node --check public/app.js
node --check tests/browser_smoke.mjs
npx --yes --package playwright node scripts/automation/cdp_probe.mjs V1.0.xx http://127.0.0.1:8788
```

Useful live checks:

```bash
curl -sS http://127.0.0.1:8788/api/health
curl -sS http://127.0.0.1:8788/api/graph
```

## License

Memory Stargraph is released under the MIT License. See [LICENSE](LICENSE).
