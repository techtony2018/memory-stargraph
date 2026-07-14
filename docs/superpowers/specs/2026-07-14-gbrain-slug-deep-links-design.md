# GBrain Slug Deep Links and Browser Tab Reuse Design

## Goal

Make every GBrain slug in Memory Stargraph-related Codex chat output a clickable link that opens the referenced node in the dashboard-managed local Memory Stargraph, while keeping browser testing and intelligence collection from accumulating unnecessary Chrome tabs.

## Canonical Link Contract

The canonical local link for a GBrain slug is:

```text
http://127.0.0.1:8788/?slug=<URL-encoded GBrain slug>
```

The visible Markdown label must remain the exact slug. For example:

```markdown
[runs/example](http://127.0.0.1:8788/?slug=runs%2Fexample)
```

This contract applies to final reports, progress updates, TODO references, Goal and product nodes, Run and Learning evidence, showcase slugs, and any other GBrain slug presented to the user. Ordinary filesystem paths, command arguments, and source-code examples remain code unless they are also being presented as navigable evidence.

## Memory Stargraph Deep-Link Behavior

`public/app.js` will own the client-side deep-link behavior. No new server route is required because the existing single-page application already accepts query strings at `/`.

On startup, the app will:

1. Read the `slug` query parameter with `URLSearchParams`.
2. Load the normal seed graph.
3. If a non-empty slug was supplied, expand and load that exact slug using the existing entity expansion and loading APIs.
4. Leave the graph usable if the slug is missing or unknown, and show a concise non-blocking status message for an unknown slug.

After explicit node navigation, the app will replace the current URL with the canonical `?slug=` URL using `history.replaceState`. Replacing rather than pushing avoids flooding browser history because Memory Stargraph already maintains its own selection history. Initial root loading and background refreshes will not invent a slug query parameter when the user opened the bare root URL.

The URL serializer will use `URL` and `URLSearchParams`, so spaces, Unicode, and reserved characters are encoded by the browser. Empty slugs remove the query parameter.

## Chat Enforcement

A repository-root `AGENTS.md` will define the rule for any Codex task operating in this project. The tracked automation documentation and each executable worker/steward prompt will repeat the concise requirement because persistent automation tasks may be bootstrapped from those files independently.

The rule will require:

- Exact slug text as the Markdown link label.
- The dashboard-managed local base URL `http://127.0.0.1:8788/`.
- URL encoding through the `slug` query parameter.
- No bare or backticked evidence slugs in user-facing chat reports when a link can be emitted.

## Chrome Tab Reuse

The browser-hygiene contract is:

1. Inspect existing browser pages before opening a new page.
2. Reuse an existing page whose origin matches the target application or intelligence source.
3. Navigate or refresh that page as needed.
4. Open a new page only when no suitable existing page is available or isolation is required for a destructive/auth-sensitive flow.
5. Close only temporary pages created by the current run; never close a reused user page.

`scripts/automation/cdp_probe.mjs` will implement this directly. It will prefer an existing page on the same origin as the requested Memory Stargraph URL. If it reuses a page, it will leave that page open after verification. If it must create a page, it will close that page in cleanup. It will disconnect from Chrome without shutting down the user browser.

The automation runbook and intelligence/testing prompts will apply the same behavior to interactive browser work. Non-browser collectors such as Agent Reach remain preferred when they satisfy the task without opening Chrome.

## Error Handling

- Missing `slug`: retain current root behavior.
- Empty `slug`: treat as missing.
- Unknown or unavailable slug: keep the loaded graph available and display a concise status; do not redirect or crash initialization.
- Existing Chrome page has crashed or cannot navigate: skip it and create one temporary page.
- CDP unavailable: retain the probe's current explicit connection failure rather than silently starting another browser.

## Testing and Verification

Test-first coverage will include:

- Static frontend tests asserting query parsing, canonical URL synchronization, and startup deep-link loading are wired into `public/app.js`.
- A browser regression that opens a known slug URL and verifies `focusSlug` equals the requested node.
- Static automation tests asserting the CDP probe searches existing pages before calling `newPage`, tracks whether it created the page, and closes only created pages.
- Contract checks ensuring the repository and automation instructions contain the canonical link and tab-reuse rules.
- Full Python unit tests and JavaScript syntax checks.
- Deployment to the dashboard-managed local service followed by verification against `http://127.0.0.1:8788` using the already-open Memory Stargraph tab when available.

## Scope Boundaries

This change does not add public/remote URL routing, change GBrain storage, modify node permissions, auto-open links, manage unrelated browser tabs, or add a generic URL-shortening service. It does not turn filesystem-looking strings into links unless they are identified as GBrain slugs in user-facing output.
