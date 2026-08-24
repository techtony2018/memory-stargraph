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

- Resumed performance code commit: `47bc335` (`perf: reuse persistent GBrain search session`)
- Follow-up performance code commit: `ae3eda9` (`perf: reuse persistent GBrain read session`)
- Graph-context performance code commit: `d20d7fd` (`perf: accelerate bounded Yoda graph context`)
- Read-lane performance code commit: `592fbef` (`perf: queue short persistent GBrain reads`)
- Current merged and pushed source: `592fbef` (includes concurrent remote MCP activation fix `69baafc`)
- Current performance code commit: `8509431` (`perf: coalesce concurrent primary searches`)
- Previous pushed commit: `eeb3c2e` (`perf: refresh primary searches off request path`)
- Earlier pushed commit verified at the start of this window: `395cb22` (`perf: cache repeated primary searches`)
- Latest verification: 567 tests passed in 40.592 seconds.
- Static verification passed: Python compilation, JavaScript syntax checks, and `git diff --check`.

After the resumed iteration, the full suite passed 578 tests in 43.069 seconds. Python compilation, JavaScript syntax checks, and `git diff --check` also passed against the merged source.

After the persistent read-session follow-up, the full suite passed 582 tests in 68.913 seconds with the same static checks passing.

After the graph-context follow-up, the full suite passed 584 tests in 62.608 seconds with the same static checks passing.

After the read-lane follow-up, the full suite passed 584 tests in 40.152 seconds with the same static checks passing.

After the exact-slug Search follow-up, the full suite passed 588 tests in 40.715 seconds. `python3 -m py_compile openclaw_profile_activation.py server.py`, `node --check public/app.js`, and `git diff --check` also passed.

After the whitespace-equivalent Search cache follow-up, the full suite passed 588 tests in 42.631 seconds with the same static checks passing.

After the whitespace-equivalent Ask Yoda retrieval cache follow-up, the full suite passed 589 tests in 44.957 seconds with the same static checks passing.

After the bounded direct-relationship traversal follow-up, the full suite passed 591 tests in 59.892 seconds with the same static checks passing.

After the bounded graph expansion and seed-load follow-up, the full suite passed 591 tests in 41.911 seconds with the same static checks passing.

Do not stage, overwrite, revert, or include these unrelated Product Owner files in a performance commit:

```text
 M automations/memory-stargraph-goal-steward-daily-review/goal-progress-ledger.json
?? automations/memory-stargraph-goal-steward-daily-review/2026-08-23-report.md
?? automations/memory-stargraph-goal-steward-daily-review/2026-08-23-run.md
```

## Improvements Completed

### Persistent GBrain search session

Commit `47bc335` keeps one initialized `gbrain serve --surface starter` stdio process for read-only Search calls. Unsupported operations, a busy persistent lane, startup failures, process exits, and timeouts fail closed to the existing CLI subprocess path. Runtime config changes and server shutdown close the child cleanly; health output exposes active, ready, and busy state.

The committed 20-query transport benchmark measured:

- CLI subprocess median: 1.638 seconds; p95: 2.194 seconds; mean: 1.789 seconds.
- Persistent stdio median: 299 milliseconds; p95: 646 milliseconds; mean: 329 milliseconds.
- Median transport improvement: 81.75%.
- Exact parsed result parity: 20/20, including slug, order, score, label, and preview.
- Forced child termination recovered with a new process in 2.450 seconds and returned 20 results.

An isolated same-source end-to-end `/api/search` benchmark compared `HEAD` before the change with the resumed worktree. Both servers started fresh and received the same eight unique queries in alternating endpoint order:

- Before median: 4.161 seconds; p95: 6.082 seconds; mean: 3.993 seconds.
- After median: 960 milliseconds; p95: 2.771 seconds; mean: 1.097 seconds.
- Median end-to-end improvement: 76.92%.
- Final search slug order parity: 8/8; primary search completed in 8/8 cases on both paths.

No dashboard-managed product service or existing GBrain HTTP service was restarted or redeployed. The isolated acceptance servers were stopped after the benchmark.

### Persistent GBrain read session

Commit `ae3eda9` extends the same persistent stdio session to the existing read-only `query`, `get`, and `backlinks` commands. Unknown commands or options still fail closed to the CLI. A 250-millisecond bounded lane wait lets short concurrent reads reuse the process before falling back, while preserving the existing timeout budget.

Five-case transport samples for each operation measured:

- `query`: 2.201-second CLI median to 1.021-second persistent median, a 53.61% reduction.
- `get`: 1.146-second CLI median to 21 milliseconds, a 98.17% reduction.
- `backlinks`: 1.116-second CLI median to 17 milliseconds, a 98.48% reduction.
- Output parity: 5/5 for each operation. Query parsed results, canonical page markdown, and formatted backlink JSON were exact.

A four-case privacy-safe Ask Yoda context benchmark used a synthetic provider-down model and alternating transport order. It sent no production model prompt:

- Cold context median: 19.348 seconds to 8.454 seconds, a 56.30% reduction in that run.
- Grounding recall remained 1.0 in all four cases; degraded cases remained zero.
- Selected-node reads: 3.715 seconds to 142 milliseconds.
- Backlinks: 3.450 seconds to 250 milliseconds.
- Direct source reads: 2.888 seconds to 94 milliseconds.
- Query/search phase: 4.892 seconds to 2.640 seconds.
- Broad graph remained the dominant phase at 5.591 seconds after the change.

### Persistent and bounded Ask Yoda graph context

Commit `d20d7fd` maps the existing read-only `graph-query` CLI contract to MCP `traverse_graph` and reproduces GBrain's indented tree renderer. Unsupported flags still fail closed to the CLI. It also caps non-targeted broad graph context at depth 2 while preserving the user's requested retrieval depth; targeted relationship questions keep their existing depth-1 behavior.

The five-case graph-query transport benchmark measured:

- CLI median: 1.406 seconds; sample p95: 1.511 seconds.
- Persistent median: 42 milliseconds; sample p95: 218 milliseconds.
- Median reduction: 97.01%.
- Exact output parity: 5/5 across depth 1/2, out/both rendering, and a typed traversal.

High-degree depth-4 traversals exceeded 20 seconds on both CLI and MCP and therefore always exhausted Ask Yoda's optional eight-second broad-graph budget. Depth 2 changed product and goal samples from `optional_timeout` to `available` while preserving grounding recall 1.0.

The current ten-case privacy-safe Ask Yoda context matrix measured:

- Cold context median: 4.186 seconds; p95: 6.723 seconds.
- Improvement versus the prior 12.572-second full median: 66.70%.
- Mean grounding recall: 1.0; warm cache hits: 10/10; degraded cold cases: zero.
- One optional graph timeout remained, from the benchmark's deliberately forced slow-graph case.

Commit `592fbef` lets short `get`, `backlinks`, and `graph-query` calls wait up to two seconds for the persistent lane instead of falling back after 250 milliseconds. External `search` and `query` calls retain the 250-millisecond limit. In the same warm-database ten-case matrix:

- Cold context median: 1.550 seconds to 1.172 seconds.
- Cold context p95: 2.911 seconds to 1.902 seconds.
- Backlinks median/p95: 266/1772 milliseconds to 216/851 milliseconds.
- Mean grounding recall remained 1.0; degraded cases remained zero.

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

### Exact slug Search fast path

Commit `c3e74f3` resolves canonical slug-only queries before broad Search. A slug already present in the loaded graph is returned locally. An unloaded slug is verified with one bounded `get`; failed verification falls through to the existing full Search. Queries with extra words, fuzzy labels, missing slugs, and exact TODO IDs retain their existing paths.

The same five canonical slug queries measured:

- Before: 0.913-1.280 seconds, median 1.206 seconds; the requested slug ranked first in 5/5 cases among 18-24 results.
- After: 5-108 milliseconds, median 27 milliseconds; 97.76% median improvement.
- Correctness: 5/5 complete, 5/5 exact top slug, and 5/5 returned exactly one verified result.
- Loaded product/goal nodes completed in 5-7 milliseconds. Three unloaded document/list/organization nodes completed in 27-108 milliseconds through persistent `get` verification.

### Whitespace-equivalent primary Search cache keys

Primary Search cache keys now collapse internal whitespace in addition to the existing case and edge-whitespace normalization. The first request is still sent to GBrain exactly as entered; only semantically equivalent repeat lookups share the cached result.

Five real query pairs measured before and after using one normal-space query followed by the same words with doubled spaces:

- Before: every variant was a cache miss; variant median 2.006 seconds, with another GBrain search for all 5/5 pairs.
- After: every variant was a cache hit; variant median 0.058 milliseconds, greater than 99.99% median improvement.
- Correctness: cached result ordering matched the first query in 5/5 pairs, and the second query triggered zero additional GBrain calls.

### Whitespace-equivalent Ask Yoda retrieval cache keys

Ask Yoda's question-specific GBrain retrieval cache now collapses internal whitespace while preserving the original question in the assembled prompt and the first backend request. Equivalent follow-up inputs therefore reuse one evidence snapshot instead of issuing another dynamic hybrid query.

Five real question-and-slug pairs measured before and after using normal and doubled internal spaces:

- Before: variant median 2.412 seconds; all five variants performed another GBrain query, and dynamic result text differed in 5/5 pairs.
- After: variant median 0.088 milliseconds, greater than 99.99% median improvement; all five variants were cache hits.
- Correctness: cached output matched the first query in 5/5 pairs, with zero additional GBrain calls.

### Bounded direct-relationship traversal

Entity detail loading now obtains outbound relationship types through the existing depth-one `graph-query` surface and still merges inbound relationship types from `backlinks`. This replaces the unbounded legacy `graph` command while retaining both relationship directions.

Three representative nodes measured on the same host:

- Before: `graph` exceeded its 20-second timeout for all 3/3 nodes before backlinks could complete.
- After: complete outbound-plus-inbound relationship type reads finished in 51-345 milliseconds, with a 103-millisecond median; median improvement is greater than 99.4% against the timeout floor.
- Coverage: the three reads returned 199, 332, and 4,037 distinct edges, with 253, 445, and 4,369 relationship types respectively.
- The new parser accepts only depth-one outbound tree rows; backlinks remain the authoritative inbound supplement, and either source still fails independently without blocking the other.

### Bounded graph expansion and seed loading

Lazy node expansion and forced live-graph collection now use the same bounded depth-one outbound `graph-query` representation as entity details, then apply the existing backlinks supplement policy. This removes the legacy `graph` timeout from exact-slug navigation, root seed loading, and refresh collection.

- Before: `graph` exceeded 20 seconds and timed out for all 3/3 representative nodes, including small category/product nodes.
- After: complete lazy expansion finished in 45-395 milliseconds, with an 87-millisecond median; median improvement is greater than 99.5% against the timeout floor.
- Expanded center-node link counts were 27, 116, and 199, showing that the faster path retained substantial relationship coverage.
- A fresh seed collection completed in 1.407 seconds with 75 nodes and `root_index_loaded=true`; the old root expansion could spend 20 seconds and fall back to an unexpanded seed.

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

Persistent stdio removed most process startup cost. The remaining end-to-end Search median is about 960 milliseconds, with a 2.771-second p95 in the same-source sample. The next bounded Search profiling pass should separate primary retrieval from evidence ranking, graph merging, and finalization, then optimize only the dominant measured phase.

Ask Yoda context is still materially slower than Search. Its first fresh-session ten-case median is 4.186 seconds rather than 12.572 seconds, while the subsequent warm-database median is 1.172 seconds. The remaining candidate is hybrid `query`, not process startup or repeated operational/TODO reads.

In a subsequent warm-database profile, hybrid `query` was the remaining dominant phase at a 934-millisecond median. A `detail=low` experiment preserved slug order in 10/10 microbenchmark cases, but its full-matrix median/p95 were 1.221/2.029 seconds versus 1.172/1.902 seconds without the flag. The experiment was rejected as ordinary variance and was not committed. Do not replace hybrid query with plain search: its mean result-set overlap was only 0.447 in the same matrix.

A single-process JSON-RPC multiplexing experiment proved that the GBrain MCP server can accept concurrent requests, but the real Ask Yoda workload did not benefit. All changes were reverted before commit:

- Prefetching hybrid `query` as a fourth concurrent request changed the alternating 18-run median from 1.200 to 1.266 seconds, a 5.5% regression. Exact prompt parity was 15/18 because repeated hybrid queries can vary ranking.
- Multiplexing all three stable-context reads changed the alternating 20-run median from 1.260 to 1.285 seconds and mean from 1.359 to 1.419 seconds. P95 improved from 2.209 to 1.953 seconds, but the median and mean regressions failed the acceptance gate.
- Multiplexing only short `get` and `backlinks` reads while keeping `graph-query` exclusive changed the alternating 20-run median from 1.257 to 1.310 seconds and p95 from 2.096 to 2.308 seconds.
- Grounding recall remained 1.0 and degraded-case parity held throughout. The rejection is strictly a latency decision: concurrent requests contend inside the current GBrain backend, so keep the serialized persistent lane until backend-level profiling shows a different result.

Removing Ask Yoda's `adaptive_return` initially appeared to improve a cache-warmed ten-case matrix from 1.172 seconds to 609 milliseconds. Fresh paraphrases reversed the result: first-query median increased from 1.010 to 1.308 seconds, a 29.5% regression, with one prefix-order change. A narrower no-adaptive `limit=6` variant preserved the adaptive prefix in 10/10 cases but increased fresh-query median from 1.123 to 1.386 seconds, a 23.4% regression. Both were reverted. Stargraph's 90-second exact query cache already serves true repeats without paying the no-adaptive cold-path cost.

The `conservative` primary Search mode produced the same sampled top-ten ordering as `balanced`, but alternating measurements were dominated by second-call backend warmth. Looking only at first calls did not show a conservative-mode advantage. The mode also disables reranking, graph signals, relational recall, and contextual retrieval, so it was rejected without a quality-and-cold-latency win.

A warm-service phase profile over eight fresh Search queries confirmed that application overhead is no longer the general bottleneck: total median was 1.186 seconds, primary GBrain retrieval 1.164 seconds, evidence ranking 2 milliseconds, loaded-graph matching 3 milliseconds, merge 1 millisecond, and finalize 12 milliseconds.

The installed GBrain remains `0.46.28.0`. The dashboard's current local config selects the local GBrain binary, so the persistent stdio child uses the same configured identity and data source as the existing Search subprocess. The concurrent `69baafc` change separately routes profile activation through configured remote MCP when that surface is present; it was merged and verified with this performance change.

Avoid lowering graph/search timeouts without new evidence. Earlier profiling found valid organization graph reads completing near 7.851 seconds, so a blanket timeout reduction would lose real evidence.

## Host Note

- Hostname: `toddys-mini-3.lan`
- Active LAN address observed during this session: `192.168.86.56` on `en1`.
