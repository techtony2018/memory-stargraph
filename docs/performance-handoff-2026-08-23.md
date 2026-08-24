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
- Current merged and pushed source: `c85584a`
- Current performance code commit: `c85584a` (`perf: cache repeated settings evidence`)
- Previous pushed commit: `884be03` (`perf: overlap follow-up tag reads`)
- Earlier stale-refresh commit: `eeb3c2e` (`perf: refresh primary searches off request path`)
- Earlier pushed commit verified at the start of this window: `395cb22` (`perf: cache repeated primary searches`)
- Latest verification: 616 tests passed in 44.076 seconds.
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

After the repeated relationship-type cache follow-up, the full suite passed 591 tests in 40.526 seconds with the same static checks passing.

After the persistent paginated page-list follow-up, the full suite passed 594 tests in 42.077 seconds with the same static checks passing.

After the unique exact-label Search follow-up, the full suite passed 596 tests in 42.170 seconds with the same static checks passing.

After the concurrent Ask Yoda retrieval coalescing follow-up, the full suite passed 597 tests in 43.970 seconds with the same static checks passing.

After the concurrent Ask Yoda source-page coalescing follow-up, the full suite passed 598 tests in 42.759 seconds with the same static checks passing.

After the concurrent Ask Yoda stable-context coalescing follow-up, the full suite passed 600 tests in 43.176 seconds with the same static checks passing.

After the Ask Yoda status-reconciliation overlap follow-up, the full suite passed 601 tests in 43.310 seconds with the same static checks passing.

After the Ask Yoda relationship-evidence overlap follow-up, the full suite passed 602 tests in 42.785 seconds with the same static checks passing.

After the Ask Yoda status-search overlap follow-up, the full suite passed 602 tests in 41.764 seconds with the same static checks passing.

After the covered-entity targeted-lookup follow-up, the full suite passed 603 tests in 46.978 seconds with the same static checks passing.

After the targeted relationship direct-read fanout follow-up, the full suite passed 603 tests in 46.262 seconds with the same static checks passing.

After the exact prewarmed evidence-title Search follow-up, the full suite passed 604 tests in 45.575 seconds with the same static checks passing.

After the terminal-punctuation Search cache follow-up, the full suite passed 604 tests in 48.208 seconds with the same static checks passing.

After the deferred startup-data follow-up, the full suite passed 605 tests in 40.463 seconds. JavaScript syntax and `git diff --check` also passed. A targeted isolated-source browser run rendered a nonblank 242-node canvas with no runtime errors and exposed the graph in 614 milliseconds. The broader legacy browser smoke progressed through startup and several journeys, then failed on an existing backend-data assertion because the Chinese query `聊天室` returned zero matches; that failure is unrelated to startup ordering.

After the selection-metadata overlap follow-up, the full suite passed 606 tests in 51.096 seconds with JavaScript syntax and `git diff --check` passing. Isolated-source browser comparison against the previous commit completed with no runtime errors.

After the expanded-relationship evidence reuse follow-up, the full suite passed 607 tests in 42.217 seconds. Python compilation, JavaScript syntax, and `git diff --check` also passed.

After the repeated timeline-read cache follow-up, the full suite passed 608 tests in 40.765 seconds. Python compilation and `git diff --check` also passed.

After the raw entity-read coalescing follow-up, the full suite passed 609 tests in 46.912 seconds. Python compilation and `git diff --check` also passed.

After the expanded relationship-output reuse follow-up, the full suite passed 609 tests in 40.315 seconds. Python compilation and `git diff --check` also passed.

After the high-degree graph-glow follow-up, the full suite passed 609 tests in 44.742 seconds. JavaScript syntax and `git diff --check` also passed. An isolated browser run rendered a nonblank 276-node, 139-edge canvas with no runtime errors.

After the Search result-release follow-up, the full suite passed 609 tests in 47.081 seconds. JavaScript syntax, the 71 focused frontend tests, and `git diff --check` also passed after the final stale-selection guard.

After the batched node-cache touch follow-up, the full suite passed 610 tests in 48.274 seconds. JavaScript syntax, the 72 focused frontend tests, and `git diff --check` also passed.

After the node-cache serialization reuse follow-up, the full suite passed 610 tests in 46.764 seconds with the same focused and static checks passing.

After the node-cache content-write coalescing follow-up, the full suite passed 610 tests in 45.931 seconds with JavaScript syntax and `git diff --check` passing.

After the Settings evidence overlap follow-up, the full suite passed 612 tests in 42.917 seconds. Python compilation, JavaScript syntax, and `git diff --check` also passed. The Settings/readiness Playwright parity smoke passed against the isolated source server, including initial load, manual refresh, auto refresh, API/UI parity, and privacy checks.

After the shared Settings evidence snapshot follow-up, the full suite passed 613 tests in 61.334 seconds with the same static checks passing. The isolated Playwright parity smoke again passed initial load, manual refresh, auto refresh, API/UI parity, and privacy checks using the combined endpoint.

After the interactive Settings priority follow-up, the full suite passed 613 tests in 45.534 seconds with the same static checks passing. The Settings parity smoke passed and its initial settled request id was `1`, confirming hover and click shared one in-flight request.

After the general interactive startup-read deferral follow-up, the full suite passed 613 tests in 47.030 seconds with static checks passing. The Settings parity smoke also passed initial load, manual refresh, auto refresh, API/UI parity, and privacy checks.

After the repeated Follow-ups listing cache follow-up, the full suite passed 613 tests in 51.719 seconds. Python compilation and `git diff --check` also passed.

After the Follow-ups capability-status reuse follow-up, the full suite passed 614 tests in 41.344 seconds with the same static checks passing.

After the Follow-ups fallback-snapshot reuse follow-up, the full suite passed 614 tests in 40.162 seconds. Python compilation and `git diff --check` also passed.

After the Follow-ups parallel tag-read follow-up, the full suite passed 615 tests in 40.640 seconds with the same static checks passing.

After the repeated Settings evidence cache follow-up, the full suite passed 616 tests in 44.076 seconds. Python compilation, JavaScript syntax, and `git diff --check` also passed.

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

### Repeated entity relationship cache

Successful outbound-plus-inbound relationship type snapshots are cached for 30 seconds, up to 64 entities. Partial reads are never cached, returned sets are reconstructed per caller, and force refreshes or any GraphStore invalidation clear the cache.

- Before: six repeated `people/tony-guan` entity reads had a 181.8-millisecond median and a stable relationship signature.
- After: the first read was 353.6 milliseconds; the next five had a 10.25-millisecond median, a 94.4% warm-repeat improvement.
- Correctness: all 6/6 relationship signatures matched, and tests verify that the second read performs no additional graph-query or backlinks call.

### Persistent paginated page listing

The persistent GBrain read session now maps read-only `list` calls to MCP `list_pages`, preserving the existing tabular parser contract. It supports the current type/tag/limit/offset/date/sort/source options and paginates explicit limits above the MCP 100-row page cap under one session lock.

- Before: five representative CLI list calls had a 1.193-second median and each returned the default 50 rows because GBrain 0.46.28 no longer recognizes the caller's `-n` shorthand.
- After: the same calls had a 29.6-millisecond median, a 97.5% improvement; the 140-row seed request returned 140 rows and each evidence request returned exactly 40.
- Seed impact: fresh seed collection fell from 1.407 seconds with 75 discovered nodes to 137 milliseconds with 165 nodes, while keeping `root_index_loaded=true`.
- Evidence impact: concurrent startup prewarm completed all four 40-row learning/TODO/report/Run lists in 124 milliseconds with no fallback and an idle persistent lane afterward.
- Unsupported options and persistent-session failures retain the existing fail-closed CLI fallback.

### Unique exact-label Search fast path

Search now resolves a query locally when it exactly identifies one untruncated loaded label containing at least two words. Ambiguous labels, single-word categories, truncated labels, and broader queries retain the complete live Search path.

- Before: five representative exact-title queries had a 1.179-second median; the correct node ranked first in 5/5 cases among 21-35 results.
- After: the same queries had a 0.65-millisecond median, a 99.94% improvement, with zero GBrain calls.
- Correctness: all 5/5 resolved to the same top slug and each returned one unambiguous result.

### Concurrent Ask Yoda retrieval coalescing

Concurrent cold misses for the same normalized Ask Yoda retrieval key now share one owner query through the existing timed-cache single-flight primitive. Failed loads are not cached and still surface as retrieval errors.

- Before: two concurrent identical requests completed in 2.112 and 3.788 seconds, with a 3.789-second wall time and different dynamic outputs.
- After: both completed in about 1.276 seconds, with a 1.276-second wall time, a 66.3% improvement.
- Correctness: both callers received identical output from one cache entry, and the regression test verifies exactly one GBrain call.

### Concurrent Ask Yoda source-page coalescing

Question-specific source pages now single-flight cold loads per slug while preserving four-way parallelism inside one request. Concurrent prompts share each owner read; failed reads remain uncached.

- Before: two concurrent four-page requests completed with a 177-millisecond wall time.
- After: both completed in 111-112 milliseconds with a 112-millisecond wall time, a 36.7% improvement.
- Correctness: both callers received all 4/4 pages with identical 25,125-byte output, and tests verify one underlying read per slug.

### Concurrent Ask Yoda stable-context coalescing

Ask Yoda's five-minute stable selected-node, broad-graph, and backlink context cache now uses the shared timed-cache single-flight primitive. Concurrent cold requests for the same slug and bounded graph depth share one complete context build. Force refresh and invalidation still clear the cache by generation, expired entries are pruned, and the cache remains bounded to eight contexts.

- Before: two concurrent direct stable-context builds completed in 5.804 and 7.783 seconds, with a 7.783-second wall time. Both independently returned the same 2,323-byte selected node, 4,116,508-byte graph, and 1,764,474-byte backlink payload.
- After: both callers completed in 4.017 seconds with a 4.018-second wall time, a 48.4% reduction. The owner reported `miss`; the waiter reported `coalesced_hit` and reused the owner's result.
- Correctness: both callers received the same complete payload, the waiter launched no duplicate backend build, and regression tests cover coalescing, expiry pruning, capacity bounds, cache invalidation, and warm follow-up reuse.
- The benchmark invoked no model and caused no product-service, GBrain-data, resolver, or deployment mutation.

### Concurrent Ask Yoda status reconciliation

Ask Yoda now builds authoritative current-TODO context and completed operational-remediation reconciliation concurrently. A lock preserves exactly one shared TODO-root read, and the final prompt keeps its prior deterministic section order.

- Before: two alternating read-only samples took 4.391 and 4.462 seconds for the two sections in sequence.
- After: two parallel samples took 4.242 and 3.860 seconds, reducing median wall time by about 8.5%.
- Full product-case cold prompt construction changed from 12.489 seconds to 11.202 seconds, a 10.3% sample improvement; warm construction changed from 5.137 to 4.848 seconds.
- Correctness: current-TODO text, operational text, counts, final prompt length, and grounding were unchanged. Tests verify true concurrent execution and deterministic current-before-operational output order.

### Concurrent Ask Yoda relationship evidence

After broader retrieval determines the likely source slugs and targeted exclusion set, Ask Yoda now loads direct source pages and targeted entity-relationship evidence concurrently. The final prompt still places direct reads before targeted evidence.

- Before: the two independent evidence sections took 6.919 and 8.182 seconds sequentially in the relationship-question profile; total prompt construction was 20.427 seconds.
- After: the same profile completed direct and targeted work in 3.987 and 4.368 seconds concurrently; total prompt construction was 10.194 seconds, a 50.1% sample improvement.
- A separate alternating microbenchmark reduced median direct-plus-targeted wall time from about 5.105 to 4.308 seconds, a 15.6% improvement.
- Correctness: prompt length remained 19,653 characters, with 6 search results, 4 direct reads, identical targeted counts, and unchanged degradation state. Tests verify true overlap and deterministic evidence ordering.

### Concurrent Ask Yoda status and broader search

After stable selected-node context is ready, Ask Yoda now starts broader query retrieval alongside current-TODO and completed-remediation reconciliation. These three question-dependent reads are independent; prompt assembly still emits status evidence before broader retrieval.

- Before: alternating microbenchmark samples took 6.725 and 6.303 seconds for parallel status reconciliation followed by broader query.
- After: concurrent samples took 4.415 and 3.952 seconds, reducing median wall time from about 6.514 to 4.184 seconds, or 35.8%.
- The full product-case cold prompt improved from the prior 11.202 seconds to 9.345 seconds, a further 16.6% sample reduction and about 25.2% versus the original 12.489-second sequential profile.
- Correctness: status text, query output and top slugs, final 26,456-character prompt, retrieval counts, grounding, and section order remained unchanged. Tests synchronize all three workers to prove overlap.

### Covered targeted-entity lookup elimination

Targeted relationship retrieval now compares each extracted named entity with the identity words of already selected direct-read slugs. When broader retrieval has already selected the exact entity, the targeted stage skips the duplicate entity search; uncovered entities retain the full search, backlink, and relationship-source path.

- In the real relationship profile, broader retrieval already selected `people/garry-tan`; the subsequent “Garry Tan” targeted search produced no evidence because that slug was intentionally excluded.
- Removing that duplicate lookup reduced prompt construction from the prior 10.194 seconds to 8.017 seconds, a further 21.4% sample improvement and 60.8% versus the original 20.427-second profile.
- Correctness: the final 19,653-character prompt, 6 search results, 4 direct reads, targeted counts, and degradation state were unchanged. Tests prove zero targeted calls for an exact covered identity and preserve the full relationship lookup for uncovered entities.

### Targeted relationship direct-read fanout

Named-entity relationship questions now read the first two broader-retrieval source pages instead of four. Ordinary questions retain the prior depth-bounded fanout up to four. If the named entity is not in the first two results, the unchanged targeted relationship path still searches and reads it directly.

- Four-page direct reads had a 2.789-second median in the alternating fanout benchmark; three pages took 2.169 seconds and two pages took 1.402 seconds.
- The real relationship prompt improved from 8.017 to 7.403 seconds, a further 7.7% sample reduction and 63.8% versus the original 20.427-second profile.
- The prompt shrank from 19,653 to 16,284 characters while retaining the selected platform and exact `people/garry-tan` entity. Tests verify the two-slug fanout and preserve targeted fallback coverage.

### Exact prewarmed evidence-title Search

Search now resolves a query locally when it uniquely matches a complete title in all four fresh prewarmed evidence lists: TODOs, Learnings, Reports, and Runs. Missing cache types, expired lists, ambiguous titles, and non-exact queries retain the complete live Search path.

- Before: the exact current Product Owner Run title took 3.318, 1.873, and 1.738 seconds; median 1.873 seconds. The correct Run ranked first in all three cases among broader results.
- After: the same title took 9.535, 8.988, and 7.752 milliseconds; median 8.988 milliseconds, a 99.5% reduction.
- Correctness: all 3/3 calls returned the same unique Run and made zero GBrain calls. The result exposes an explicit `search_exact_evidence_title` coverage marker.

### Terminal-punctuation Search cache keys

Primary Search cache keys now ignore trailing ASCII sentence punctuation (`?`, `!`, and `.`) after the existing case and whitespace normalization. The first request is still sent to GBrain exactly as entered; only a semantically equivalent repeat shares its result.

- Five real plain/punctuated query pairs produced exact parsed-result parity and top-ten slug parity in 5/5 cases.
- Before: punctuated variants took 1.643-2.894 seconds, with a 2.620-second median and another GBrain search for every pair.
- After: all variants were cache hits in 0.045-0.056 milliseconds, median 0.055 milliseconds, greater than 99.99% improvement, with zero additional GBrain calls.

### Deferred noncritical startup data

The frontend now preserves hidden-node loading before graph application, renders the graph and any requested deep link, and only then starts TODO backlog prefetch, persistent Yoda-log loading, and the Follow-ups badge request as one failure-isolated background group. These auxiliary reads no longer block the first usable graph.

- On the dashboard-managed endpoint, the previous serial sequence took 6.623, 6.103, and 5.660 seconds, with a 6.103-second median.
- The new first-graph critical path (`/api/hidden` followed by `/api/graph`) took 243, 238, and 198 milliseconds, with a 238-millisecond median: a 96.1% reduction.
- The dominant removed blocker was `/api/autopilot-findings?limit=1&offset=0`, sampled at 3.351-5.530 seconds. TODO backlog prefetch sampled at 1.147-1.557 seconds; hidden state and Yoda logs were each about 11-17 milliseconds.
- An isolated-source Playwright verification exposed the graph in 614 milliseconds, rendered 242 nodes on a nonblank canvas, and reported no page or console errors. Resource timing confirmed `/api/hidden` and `/api/graph` completed before the deferred auxiliary requests began.
- A static regression test locks the hidden-before-graph and graph/route-before-auxiliary ordering.

### Concurrent selected-entity metadata

After direct-neighbor expansion, entity detail now starts first and its independent timeline and media reads begin immediately alongside it. Detail rendering still waits for a successful entity response. Timeline/media failures remain isolated, stale-selection guards are unchanged, and the prefetched responses are reused instead of issuing duplicate requests after detail loads.

- Alternating read-only endpoint samples for `people/tony-guan` measured serial entity/timeline/media completion at 6.248 and 6.302 seconds. Concurrent samples took 5.372 and 3.966 seconds.
- In an isolated-source deep-link comparison, the previous commit completed the selected entity plus timeline in 6.050 seconds. The current implementation completed in 5.058 seconds, a 16.4% sample reduction.
- From direct-neighbor expansion completion to timeline completion, the same browser trace changed from 4.455 to 3.889 seconds, a 12.7% reduction.
- Resource timing verified that entity, timeline, and media started together after expansion. The current trace had no page errors, preserved the exact selected slug, and rendered the media preview normally.
- The endpoints share GBrain transport capacity, so the gain is bounded by backend contention rather than the full sum of the three serial durations. Regression tests lock request start order, response reuse, and the existing render dependency.

### Reused lazy-expansion relationship evidence

Successful lazy expansion already reads complete outbound `graph-query` and inbound `backlinks` evidence. The GraphStore now caches that full raw relationship-type map for the expanded center node, so the immediately following entity-detail request does not repeat the same two backend reads. The existing 30-second cache bound and global invalidation behavior remain unchanged.

- On `products/memory-stargraph`, the immediate detail baseline took 3.420 seconds and called `get`, `graph-query`, and `backlinks` after expansion.
- Reusing expansion evidence took 1.143 seconds and called only the still-required `get`, a 66.6% detail-stage reduction.
- The complete entity payload was exactly equal before and after. Neighbor order, all 27 direct neighbors, and every `link_types` list matched.
- A first implementation that reconstructed types from the bounded final graph was rejected: it preserved neighbors but lost valid backlink-derived types such as `doc_of`, `mentions`, and `runbook_for`. The accepted implementation captures the complete raw outbound/backlink type evidence before graph supplement bounding.
- Regression tests verify two total relationship backend calls during expansion, zero repeats during immediate detail, and preservation of a backlink type on an edge already discovered outbound.

### Repeated timeline read cache

Successful selected-node timeline output is cached for 30 seconds, up to 64 slugs. Failed reads are never cached. Any GraphStore invalidation clears the cache, and `timeline-add` invalidates before the next read, so new events cannot be hidden by a stale warm entry.

- Before: three repeated dashboard endpoint reads took 1.123-1.257 seconds for `products/memory-stargraph` and 1.159-1.179 seconds for `people/tony-guan`.
- After: the product timeline loaded once in 1.204 seconds, then returned in 9 and 3 microseconds. The person timeline loaded once in 1.103 seconds, then returned in 3 and 1 microseconds.
- Correctness: output hashes matched for all three reads of both an empty 21-byte timeline and a nonempty 4,547-byte timeline.
- Regression tests verify one backend read for warm repeats, immediate invalidation after `timeline-add`, and a fresh backend read afterward.
- This optimization does not reduce the first timeline read; it removes repeated backend work during reselection and repeated Timeline opening.

### Coalesced raw entity reads

Raw entity markdown now uses a 30-second, 128-entry single-flight cache shared by detail hydration, media extraction, View, and Ask Yoda source loading. Concurrent cold readers for one slug share one owner `get`; failed loads are not cached. All GraphStore invalidation paths clear the cache.

- Before: concurrent detail and media loading for `products/memory-stargraph` took 1.477 seconds and executed two identical `get` calls.
- After: the same pair took 1.134 seconds and executed one `get`, a 23.2% sample reduction and 50% fewer backend reads.
- Correctness: the detail retained all 27 neighbors and media extraction retained all 6 items. The single-flight regression test verifies identical raw markdown for owner and waiter.
- The cache also removes duplicate reads when View, media, or Ask Yoda source loading overlap within the TTL; writes and force refreshes still invalidate immediately.

### Reused expanded relationship outputs

Lazy expansion now retains the successful raw `graph-query --direction out --depth 1` and `backlinks` outputs in a 30-second cache bounded to 32 entries. The Relationships modal normalizes its equivalent `outgoing` direction alias for an exact cache-key match; typed, deeper, incoming, or both-direction queries remain distinct. All GraphStore invalidation paths clear the output cache.

- Real `out` and `outgoing` graph-query outputs for `products/memory-stargraph` were exactly equal: 2,300 bytes with SHA prefix `160ba8dbcb3bc00c`. Uncached calls took 1.081 and 1.176 seconds.
- Two uncached Backlinks calls were exactly equal: 183,013 bytes with SHA prefix `d7afb1a7ca32b191`, taking 1.284 and 1.107 seconds.
- After expansion, Relationships returned the same 2,300 bytes in 16 microseconds and Backlinks returned the same 183,013 bytes in 20 microseconds. Warm repeats took 12 and 4 microseconds, greater than 99.99% reductions from the uncached samples.
- Tests verify expansion makes exactly the original two backend calls, then both modal reads reuse the exact raw outputs without another call. The 32-entry bound limits memory exposure from large backlink payloads.

### Bounded high-degree graph glows

The canvas renderer no longer gives every direct neighbor an expensive radial glow when the focused node is a high-degree hub. Focus, hover, visible top hubs, globally high-degree nodes, and direct neighbors with degree at least 5 retain the glow at normal zoom. All direct neighbors retain it for focused nodes with degree 80 or lower, and zooming to 165% restores it for detailed inspection.

- On the 116-link `people/tony-guan` view, a fixed 20-frame benchmark reduced radial gradients from 141 to 31 per frame, a 78.0% reduction.
- The same forced-frame sequence fell from 2.303 seconds to 1.763 seconds, a 23.4% reduction.
- Chrome task time per draw fell from 120.45 milliseconds to 92.67 milliseconds, a 23.1% reduction in the same isolated software-rendering environment.
- A browser pixel check found 587,594 nontransparent canvas pixels and 516,916 bright pixels. The 276-node, 139-edge graph, selection details, focus treatment, and labels remained visible with no page errors.
- The change does not lower graph data, hide nodes or edges, disable flowing-edge animation, or alter lower-degree focus views. It only bounds the most expensive glow tier at the default zoom.

### Search results released before detail hydration

Natural-language Search now releases its loading state as soon as the result graph and preferred focus are available. The selected graph result is rendered immediately, while direct-neighbor expansion, entity markdown, media, and timeline hydration continue through the existing cancellable entity loader. A newer manual selection increments the selection version and prevents the older background completion from changing feedback or detail state.

- Before: three browser searches remained loading for another 270, 518, and 636 milliseconds after `/api/search` returned.
- After: the same result-ready tail was 8, 14, and 19 milliseconds. Median post-result wait fell from 518 to 14 milliseconds, a 97.3% reduction.
- Complete details still arrived 116-307 milliseconds after the result-ready state in the ordinary samples.
- With the entity endpoint intentionally delayed by 2 seconds, Search unlocked with the correct focus and loading-details state, then hydrated to the complete six-link entity at 3.132 seconds. The user can search or select another node during that delay.
- Backend Search time and retrieval semantics are unchanged. This improvement removes avoidable UI serialization after the ranked result already exists.

### Batched node-cache LRU touches

The browser node/media cache now parses its persisted JSON once into an in-memory store. Cache hits update LRU timestamps in memory and coalesce pure timestamp persistence into one write after 1 second. Cache additions, deletions, invalidations, limit enforcement, and flushes still persist immediately. A cross-tab `storage` listener cancels a pending touch write and reloads the external value, preventing a stale tab from overwriting a newer cache.

- The previous hit path synchronously parsed and rewrote the entire cache. Synthetic median hit cost was 19.3 milliseconds at 1 MB and 63.1 milliseconds at 4 MB; 4 MB p95 was 133.5 milliseconds.
- With a 4.21 MB real cache, five sequential full entity reselections completed in 11.9 milliseconds. Their entity and media reads produced zero synchronous cache writes and one merged 4.25 MB write after the delay.
- The same roughly ten hits would cost about 631 milliseconds at the measured old 4 MB median. Immediate cache-touch work fell by about 98%, while response payloads and eviction semantics stayed unchanged.

Cold cache writes also reuse one serialized payload for limit enforcement, persistence, and the displayed usage byte count. The common under-limit path no longer sorts LRU entries or serializes the multi-megabyte store three times.

- In an alternating same-page 4 MB benchmark, the previous cold-write path had a 127.4-millisecond median and 142.1-millisecond mean.
- The single-serialization path measured 73.3 milliseconds median and 75.9 milliseconds mean, reductions of 42.5% and 46.6%.
- Over-limit writes still sort by `lastAccessed`, evict one entry at a time, and reserialize after each eviction until the configured byte cap is satisfied.

Entity and media cache additions now share a 500-millisecond content-persistence window. Each response still updates the in-memory store and enforces the byte limit immediately, but only the newest serialized payload is written. Mutations, invalidations, deletions, and Flush cancel the pending write and persist immediately.

- An alternating 4 MB two-add benchmark reduced median synchronous work from 178.4 to 105.0 milliseconds, a 41.1% reduction. Mean fell from 160.4 to 115.0 milliseconds, a 28.3% reduction.
- A real deep-link load initially wrote the 4 MB cache twice because entity and media arrived 406 milliseconds apart. The accepted 500-millisecond window wrote once, and final readback contained both the entity and media entries in the 4.32 MB payload.
- The delay affects only reconstructible browser cache persistence. In-memory responses are available immediately, and authoritative product or GBrain data is never delayed or mutated.

### Overlapped Settings evidence reads

The weekly Settings digest now runs its independent resolver-health read alongside weekly outcome evidence collection. Customer readiness reuses the resolver and deployment-attestation evidence already carried by that digest instead of reading both a second time. Missing or legacy digest fields retain the previous bounded fallback reads.

- Before, the isolated weekly digest took about 2.5-2.6 seconds: resolver health consumed 1.1-1.2 seconds and weekly outcomes another 1.3-1.5 seconds in series.
- Before the change, three concurrent Settings API pairs completed in 3.185, 3.223, and 3.304 seconds, for a 3.223-second median wall time.
- After the change, five pairs completed in 3.646 seconds cold and 1.706-2.051 seconds thereafter. Overall median wall time was 1.889 seconds, a 41.4% reduction from the baseline median.
- Deliberately running multiple browser and direct benchmarks together still saturated the local GBrain backend and produced 6-10 second samples. This is contention evidence, not a steady-state latency claim; request-level coalescing remains a candidate if concurrent Settings consumers become common.
- Tests require resolver and outcome reads to overlap and fail if customer readiness repeats resolver or deployment reads when complete weekly evidence is present.
- The API remains read-only. No service, resolver, GBrain, deployment, or production data was mutated.

The Settings panel now requests one `/api/settings-evidence` snapshot instead of separately requesting weekly digest and customer readiness. The combined endpoint builds the digest once and passes that exact object into readiness. The individual digest and readiness endpoints remain available for their existing detail views and compatibility callers.

- Five isolated combined requests completed in 1.149, 1.221, 1.233, 1.268, and 1.373 seconds; median was 1.233 seconds and mean was 1.249 seconds.
- This is another 34.7% median reduction from the preceding two-request 1.889-second result and a cumulative 61.7% reduction from the original 3.223-second Settings baseline.
- The response carried both complete card payloads in 17,076 bytes. UI/API parity held for all visible gate counts, readiness counts, statuses, and configured-target evidence.
- The endpoint test requires exactly one digest construction and verifies that readiness receives the same digest object. Existing standalone endpoints retain their prior behavior.

Settings refreshes now share one in-flight browser Promise. This removes the duplicate request caused when pointer hover opens the flyout immediately before its click handler pins it. Low-priority initial timeline-badge and deferred startup reads wait at least 2 seconds; if Settings evidence is then active, they wait for that user-requested snapshot to settle. Explicit Timeline opens and non-system selections keep their existing immediate reads.

- A same-server alternating Playwright comparison intercepted only `app.js`, so both variants used the same current workspace, GBrain, graph data, server process, and machine state.
- Baseline click-to-cards samples were 5.546, 6.332, and 7.255 seconds with two Settings requests each.
- Prioritized samples were 2.556, 3.654, and 4.289 seconds with one Settings request each.
- Median click-to-cards time fell from 6.332 to 3.654 seconds, a 42.3% reduction; request count fell 50%.
- The first attempted detached-worktree comparison was discarded because that checkout lacked current host-local runtime state and produced invalid 404/502 behavior. Its timings are not included in the result.
- Initial system selection still loads entity and media immediately. Timeline remains immediate for manual, Search, history, and deep-link selection, and explicit Timeline opens bypass the deferred badge path.

The combined Settings endpoint now caches its complete read-only snapshot for 10 seconds and coalesces simultaneous cold requests. This is shorter than the existing 15-second auto-refresh interval. Manual refresh sends `refresh=1`, and graph force-refresh or invalidation clears the snapshot immediately.

- Before, three repeated isolated-server requests took 1.257, 1.168, and 1.132 seconds, with a 1.168-second median and identical 17,073-byte payloads.
- After, the cold request took 1.285 seconds; the next two requests took 2.5 and 3.4 milliseconds, about 99.7% below the uncached median.
- A manual forced refresh took 1.696 seconds, confirming that the explicit refresh command was not served stale. Tests also verify two concurrent cold callers share one digest and readiness construction.

The same low-priority startup gate now waits while any foreground busy operation is active, polling at 100-millisecond intervals. This prevents initial timeline-badge and TODO/Yoda/Follow-ups prefetches from entering the GBrain lane during Search, View, relationship, history, or other explicitly requested work. The callback runs as soon as foreground work and any Settings snapshot settle.

- Three matched-pattern fresh startup Search samples before the general gate were 6.495, 4.309, and 3.572 seconds; median was 4.309 seconds.
- Three fresh matched-pattern samples after the gate were 2.912, 3.118, and 2.649 seconds; median was 2.912 seconds, a 32.4% reduction.
- Before, startup timeline and Follow-ups reads entered 1.2-1.6 seconds after Search began and remained active during primary retrieval.
- After, neither startup request entered during Search. The only observed timeline request began exactly when a successful Search selected its result, preserving the existing non-system selection contract.
- Query wording used the same three semantic patterns with distinct suffixes to avoid the 30-second exact-query cache. Treat the result as a bounded startup-interaction benchmark rather than a backend-wide Search claim.

### Repeated Follow-ups listing cache

Normalized read-only Autopilot Follow-ups list results now use a 30-second cache bounded to 16 filter combinations. The cache includes the supported tag fallback used when the installed GBrain backend does not expose `autopilot_findings_list`. Graph refresh/invalidation and successful acknowledgement clear it immediately.

- Three uncached identical badge queries took 3.533, 3.559, and 3.270 seconds; median was 3.533 seconds.
- In the accepted run, the cold fallback took 6.031 seconds. The next three same-filter reads took 0.143, 0.039, and 0.015 milliseconds, greater than 99.99% below the uncached median.
- Tests verify repeated fallback reads perform one tool capability attempt and one pass over the two bounded fallback tags, while returning the exact same normalized payload.
- Cache keys include normalized state, limit, and offset. Different views do not share incompatible pagination, and external changes become visible after at most 30 seconds even without an explicit invalidation.

The same short-lived cache now records whether `autopilot_findings_list` is supported. When one filter proves the installed backend lacks the tool, other filter or pagination combinations skip only the redundant capability call and still execute the supported tag fallback. Expiry or any existing cache invalidation causes a fresh capability check.

- The cold path split into a 1.360-second missing-tool probe and a 2.860-second tag fallback.
- With capability status reused, two different uncached filters completed through fallback in 2.176 and 2.211 seconds instead of repeating the roughly 4.220-second full path, reductions of 48.4% and 47.6%.
- Tests verify two different filters make one capability call while independently performing their required bounded tag reads.

The fallback now also caches its unfiltered, normalized, sorted page snapshot by bounded read budget. Badge, modal, and state-filtered requests sharing the same 20-page budget apply filtering and pagination locally. Larger offsets retain an independent larger-budget snapshot, while expiry, graph invalidation, force refresh, and acknowledgement preserve the existing freshness contract.

- A real cold badge request took 3.452 seconds and populated the 20-page fallback snapshot.
- The subsequent modal request with a different limit completed in 0.042 milliseconds; a different state filter completed in 0.025 milliseconds. Both are more than 99.99% below the prior 2.176-2.211-second repeated fallback samples.
- Tests verify the badge and modal paths perform one two-tag scan total, and that a later state filter returns the correct subset without another tag or page read.

The two independent read-only fallback tag listings now run concurrently. Detail-page reads remain bounded and sequential, so this removes avoidable list latency without increasing page-read fanout.

- Two alternating serial tag-list samples took 2.172 and 2.185 seconds; concurrent samples took 1.451 and 1.393 seconds with identical output lengths, reducing this phase by 33.6% and 36.3%.
- A three-round alternating isolated-server comparison used the same host configuration and a fresh process for every request. The previous commit took 4.842, 5.251, and 5.819 seconds; the concurrent version took 4.201, 4.394, and 6.308 seconds. Median cold API latency fell from 5.251 to 4.394 seconds, a 16.3% reduction. The third round shows the ordinary backend variance and is why the median, not the best sample, is the acceptance result.
- Direct-import implementation samples, which do not enable the product server's persistent GBrain session, measured a 2.513-second post-change median versus one preceding 3.452-second serial cold sample. This 27.2% sample is retained only as supporting phase evidence, not as the user-facing result.
- A barrier-based regression test verifies both tag reads overlap. The full fallback tests still cover missing-tool handling, bounded reads, state filtering, and snapshot reuse.

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

Reducing primary Search from the default 20 results to 10 was not implemented. With the supported persistent-session `--limit 10` option, top-ten prefix order matched the default in 8/8 sampled queries, but median transport latency regressed from 0.295 to 1.052 seconds. An earlier `-n 10` attempt was discarded because that unsupported persistent option correctly fell back to the CLI and did not limit results.

Changing all non-targeted broad graph retrieval from depth 2 to depth 1 was not implemented. In the alternating ten-case provider-down matrix, depth 1 preserved measured grounding and slightly lowered the mean, but regressed median cold prompt construction from 7.192 to 7.751 seconds. It also removes second-hop evidence globally, so the mixed latency result did not justify the quality risk.

Replacing full backlinks with `graph-query --direction in --depth 1` was not implemented. It reduced formatted bytes by roughly five to six times and retained 93.1-100% of sampled backlink edges, but did not improve latency: the high-degree sample regressed from 1.417 to 2.337 seconds and ordinary samples were flat. Compact output alone does not remove backend traversal cost.

Changing Ask Yoda broad graph traversal from `direction=both` to `direction=out` was not implemented. The graph-only microbenchmark preserved parsed root-outbound edges in 5/5 samples and substantially reduced bytes, including 4.12 MB to 175 KB for the high-degree person node. End-to-end prompts reversed that apparent win: the relationship case regressed from 6.963 to 7.790 seconds and the product case from 8.330 to 9.446 seconds. Grounding and counts were unchanged, but both total-latency samples failed the acceptance gate.

## Next Bottleneck

Frontend startup no longer waits for TODO prefetch, Yoda logs, or the slow Follow-ups badge. Selection metadata overlaps after direct-neighbor expansion, immediate detail and relationship views reuse expansion evidence, repeated timeline reads are cached, concurrent raw page consumers single-flight, high-degree graph views bound their expensive glow tier, Search no longer waits for detail hydration after ranked results arrive, and browser cache hits no longer synchronously parse and rewrite multi-megabyte storage. First-time timeline reads still cost about 1.1-1.2 seconds in isolation but run in the background. The next measured user-facing bottleneck remains uncached primary GBrain Search, where backend retrieval accounts for nearly all result-ready latency.

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

Adding an explicit `--limit 10` to primary keyword Search preserved the default top-ten prefix in 10/10 queries, but changed the alternating median from 430 milliseconds to 1.060 seconds and the mean from 552 milliseconds to 1.065 seconds. GBrain's explicit-limit path was slower than its default 20-result path, so the experiment was rejected and no code was changed.

Treating full-width Chinese sentence punctuation (`？`, `！`, and `。`) as cache-key-only punctuation was rejected. Two of five initial plain/punctuated pairs matched exactly, but three did not. Follow-up repeated samples were stable within each exact query (top-ten Jaccard 1.0) while plain-versus-punctuated overlap was only 0.429-0.667. `Tony Guan！` changed the top result from an X media node to `people/tony-guan`, and `聊天？` changed the top result from a WeChat post to a person. Full-width punctuation currently has retrieval semantics in GBrain and must not share the ASCII terminal-punctuation cache rule.

Switching uncached primary Search from the default balanced mode to `tokenmax` was rejected. On the same 12 queries, the two modes returned exact top-ten parity in 12/12 cases, but same-query second-call warmth made the first timing pass invalid. A corrected 24-query cold distribution used disjoint, alternating queries: balanced median was 0.973 seconds and tokenmax median was 1.028 seconds, a 5.6% regression. Tokenmax did not meet the 15% latency-improvement gate despite result parity.

Skipping passive 3D reprojection after rotation fell below its animation threshold was rejected. The change removed about 1,104 projection sine/cosine calls per frame on the 276-node high-degree view, but fixed-frame task time did not improve: the accepted glow baseline was 92.67 milliseconds per draw, while the no-reprojection samples were 96-104 milliseconds per draw. Canvas gradient filling remained dominant, so the theoretical arithmetic reduction was reverted rather than presented as a user-visible win.

Caching the 21 stable cluster-cloud gradients on an offscreen canvas was rejected. It reduced stable-frame gradient creation from 31 to about 10.5 per draw, but six alternating in-page samples showed only a 1% task-time median improvement: 40.82 milliseconds per direct draw versus 40.43 milliseconds per cached draw. Offscreen `drawImage` composition replaced most of the gradient cost instead of removing it, so the cache and its invalidation state were fully reverted.

Restricting high-degree flowing-edge animation to direct focus edges was not implemented. The measured 116-link view animated only 23 second-ring edges beyond its 116 direct edges. Those 23 extra dashed strokes were about 4% of the 569 total canvas strokes per frame, below the acceptance threshold before accounting for unchanged nodes, clouds, and background work.

A warm-service phase profile over eight fresh Search queries confirmed that application overhead is no longer the general bottleneck: total median was 1.186 seconds, primary GBrain retrieval 1.164 seconds, evidence ranking 2 milliseconds, loaded-graph matching 3 milliseconds, merge 1 millisecond, and finalize 12 milliseconds.

The installed GBrain remains `0.46.28.0`. The dashboard's current local config selects the local GBrain binary, so the persistent stdio child uses the same configured identity and data source as the existing Search subprocess. The concurrent `69baafc` change separately routes profile activation through configured remote MCP when that surface is present; it was merged and verified with this performance change.

Avoid lowering graph/search timeouts without new evidence. Earlier profiling found valid organization graph reads completing near 7.851 seconds, so a blanket timeout reduction would lose real evidence.

## Host Note

- Hostname: `toddys-mini-3.lan`
- Active LAN address observed during this session: `192.168.86.56` on `en1`.
