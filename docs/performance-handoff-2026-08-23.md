# Memory Stargraph Performance Handoff - 2026-08-23

## Stop Point

- Workspace: `/Users/toddy/memory-stargraph`
- Branch: `main`
- Stop requested at: 2026-08-23 13:24 PDT
- Planned stop: 2026-08-23 13:54 PDT
- Actual stop: 2026-08-23 13:54 PDT
- Product code was not deployed or restarted during this work.
- All performance commits listed below were pushed to `origin/main`.

## Current Source State

- Current performance code commit: `8509431` (`perf: coalesce concurrent primary searches`)
- Previous pushed commit: `eeb3c2e` (`perf: refresh primary searches off request path`)
- Earlier pushed commit verified at the start of this window: `395cb22` (`perf: cache repeated primary searches`)
- Latest verification: 567 tests passed in 40.592 seconds.
- Static verification passed: Python compilation, JavaScript syntax checks, and `git diff --check`.

Do not stage, overwrite, revert, or include these unrelated Product Owner files in a performance commit:

```text
 M automations/memory-stargraph-goal-steward-daily-review/goal-progress-ledger.json
?? automations/memory-stargraph-goal-steward-daily-review/2026-08-23-report.md
?? automations/memory-stargraph-goal-steward-daily-review/2026-08-23-run.md
```

## Improvements Completed

### Repeated primary search cache

Commit `395cb22` caches complete primary `gbrain search` results for 30 seconds.

- Before: repeated exact queries took 1.580-1.956 seconds.
- After: repeated exact queries took 8-11 milliseconds.
- Observed reduction: about 99.5% on the repeated path.
- Result counts and top slugs remained unchanged.

### Stale-while-revalidate primary search

Commit `eeb3c2e` keeps complete primary results available for five minutes after the 30-second fresh window and refreshes them in the background. Cache invalidation still clears both fresh and stale values immediately.

- Before: the same query after a 31-second expiry blocked for 4.183 seconds.
- After: the expired query returned in 25 milliseconds with `stale_refresh_started`.
- Observed reduction: about 99.4% on that expired-cache request.
- After the background refresh, the next request was a 6-millisecond fresh `hit`.
- Concurrent stale requests start one refresh; later requests report `stale_refresh_joined`.

### Concurrent cold-search coalescing

Commit `8509431` coalesces simultaneous cache-miss requests for the same normalized query.

- Before: two concurrent requests launched two primary GBrain searches; request times were 3.634 and 3.767 seconds, with 3.768 seconds wall time.
- After: both requests shared one primary GBrain search; one reported `miss`, the other `coalesced_hit`.
- After sample: both returned the same 20 results in about 2.740 seconds, with one backend call.
- Treat the lower wall time as a sample, not a stable latency claim. The reliable improvement is two backend executions reduced to one.

## Earlier Performance Work

These prior commits are already pushed and should remain intact:

```text
6b68eee perf: parallelize search evidence lookups
335752c perf: cache search evidence listings
7935037 perf: overlap search retrieval phases
211598a perf: batch Ask Yoda context reads
38b676a perf: reuse Ask Yoda state source
e2ff723 perf: cache repeated Ask Yoda searches
c67f24c perf: cache Ask Yoda source reads
c409aad perf: narrow Ask Yoda remediation reads
6480303 perf: skip Ask Yoda query expansion
0d40b05 perf: refresh search evidence off request path
a354a5c perf: prewarm search evidence at startup
395cb22 perf: cache repeated primary searches
eeb3c2e perf: refresh primary searches off request path
8509431 perf: coalesce concurrent primary searches
```

Notable earlier measurements:

- Search evidence phase: 4.714 seconds to 2.539 seconds.
- Repeated Search median: 4.266 seconds to 1.674 seconds before the newer primary cache work.
- Ask Yoda full median: 15.005 seconds to 12.572 seconds.
- Exact repeated Ask Yoda search: 12.039 seconds to 7.509 seconds.
- Expired evidence cache: 3.214 seconds to 9 milliseconds.
- Startup evidence prewarm first Search: 6.056 seconds to 3.577 seconds.

## Rejected Experiment

Adding `--snippet-chars 300` to `gbrain search` was not implemented.

- The returned byte counts were identical in the sampled queries.
- One alternating run favored the flag: 1.661-second median versus 1.820 seconds.
- The reverse-order run favored the default: 1.715-second median versus 1.794 seconds.
- The contradictory result indicates ordinary backend/process variance, not a measured improvement.

## Next Bottleneck

Cold primary search is now the dominant remaining Search cost. The installed GBrain reports version `0.46.28.0`.

- `gbrain --version`: 931-millisecond median across five runs.
- `gbrain status`: 1.260-second median across five runs.
- Cold `gbrain search`: commonly 1.6-4.2 seconds in this session.

This shows that process startup is a material part of the remaining latency. The next bounded experiment should evaluate a persistent GBrain transport (`gbrain serve` over stdio or local HTTP) against the existing subprocess path.

The host already has a managed persistent service:

- Process: `gbrain serve --http --port 3131 --bind 127.0.0.1 ...`
- Read-only probe: `GET http://127.0.0.1:3131/health` returned HTTP 200 in 53 milliseconds.
- Probe payload: status `ok`, version `0.46.28.0`, engine `postgres`.
- A plain GET to `/mcp` returned HTTP 405, as expected for an MCP endpoint requiring the correct method and authentication flow.
- An unauthenticated MCP `initialize` POST returned HTTP 401 in 36 milliseconds with a `WWW-Authenticate` challenge.
- Reuse this existing managed service for the benchmark. Do not restart it or launch a competing GBrain server.

Recommended sequence:

1. Add a benchmark-only persistent stdio client that inherits the existing dashboard launcher's validated `remote_mcp` identity; do not replace production behavior first.
2. Compare cold and repeated Search latency, output parity, timeout behavior, and process recovery across at least 20 queries.
3. Require exact slug/result-order parity and fail-closed fallback to the current subprocess path.
4. Only integrate if the median and p95 gains are stable and lifecycle management does not require unauthorized service changes.
5. Run the full Python and browser/static suites before committing and pushing.

The benchmark must not hardcode the local port as a production transport or bypass the configured remote identity. Reuse the launcher's owner-only config validation and the runtime OAuth secret without printing, serializing, or committing credential material.

The GBrain MCP operation is named `search`. Its required argument is `query`; optional arguments are `limit`, `offset`, `mode`, `types`, and `snippet_chars`. The current Dashboard requirements contain `nats-py` only, and the managed Python environment does not provide `mcp`, `httpx`, `requests`, or `aiohttp`. A stdio proof avoids adding an HTTP/OAuth dependency before the performance case is established. It must still inherit the launcher's isolated `GBRAIN_HOME` and secret environment rather than reading or copying credentials itself.

Avoid lowering the current graph/search timeouts without new evidence. Earlier profiling found valid organization graph reads completing near 7.851 seconds, so a blanket timeout reduction would lose real evidence.

## Host Note

- Hostname: `toddys-mini-3.lan`
- Active LAN address observed during this session: `192.168.86.56` on `en1`.
