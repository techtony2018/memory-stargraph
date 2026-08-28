# How We Made Memory Stargraph Faster

Release context: Memory Stargraph `V1.0.205`, August 2026.

## Executive summary

Memory Stargraph became faster by removing repeated process startup from its
critical paths, reusing bounded read results, and returning only the data the UI
actually needs. The most important architectural change was replacing repeated
`gbrain` CLI subprocess calls with long-lived MCP transport inside Memory
Stargraph, exposing that capability to background workers through stable HTTP
endpoints, and adding bounded MCP concurrency for Ask Yoda's context fan-out.

The result was quite satisfying:

- Persistent GBrain search reduced median transport time by 81.75%.
- Persistent entity reads reduced a representative `get` from about 1.15
  seconds to about 21 milliseconds in transport benchmarks.
- Compact paginated Backlinks reduced a representative response from 1.97 MB
  to 1.5 KB and improved median modal readiness by 34%.
- Bounded Search graph growth reduced final node count by 33.4%, response size
  by 30.8%, and median graph-ready time by 31.3%.
- The endpoint-first worker migration reduced a representative entity
  read from a 1,233 millisecond CLI median to a 116 millisecond HTTP median,
  a 10.65x speedup on the deployed primary host.
- The Ask Yoda MCP-only release reduced observed end-to-end p50 from 8.748
  seconds to 1.619 seconds (81.5%, or 5.40x) and p95 from 10.529 seconds to
  5.609 seconds (46.7%, or 1.88x), while preserving 1.0 retrieval recall.
- Deployed acceptance completed 8 of 8 structured MCP calls with five ready
  bounded sessions and zero CLI fallbacks.

All changes preserved the existing GBrain data model and administrative CLI
compatibility. Ask Yoda itself no longer uses a CLI fallback; it now fails
closed when its structured MCP context is unavailable. We did not modify or
upgrade GBrain to achieve these gains.

## The original performance problem

Memory Stargraph originally used the `gbrain` CLI as the integration boundary
for most reads and writes. That was simple and reliable, but each operation paid
for a new process:

1. Start the CLI runtime.
2. Load configuration and connect to storage.
3. Parse command-line arguments.
4. Execute one operation.
5. Serialize output and exit.

For an occasional administrative command, this overhead is acceptable. It is
expensive when one UI journey or worker invocation performs many reads.

The first measurements made the bottleneck obvious. A small entity read took
roughly 1.1 to 1.2 seconds through a fresh CLI process even though the actual
database operation was small. Ask Yoda, Search, Backlinks, Settings, and
background workers multiplied that fixed cost across several operations.

The key insight was:

> The query was often not slow. Repeatedly constructing the query runtime was
> slow.

## The architecture change

### Before

```text
UI or worker
    |
    +--> start gbrain CLI --> connect --> one operation --> exit
    +--> start gbrain CLI --> connect --> one operation --> exit
    +--> start gbrain CLI --> connect --> one operation --> exit
```

### After

```text
UI
  |
  +--> Memory Stargraph HTTP API
           |
           +--> persistent GBrain MCP sessions
           +--> bounded five-session Ask Yoda pool
           +--> bounded caches and request coalescing
           +--> fail-closed Ask Yoda context reads

Background worker
  |
  +--> Memory Stargraph worker endpoint
           |
           +--> persistent MCP transport
           +--> durable readback verification
           +--> CLI fallback when the endpoint is unavailable
```

Memory Stargraph now owns the long-lived transport. The product server starts
`gbrain serve --surface full` once, initializes an MCP session, and reuses it
for compatible operations. Background workers call Memory Stargraph endpoints
instead of starting their own GBrain process for every read or write.

This keeps GBrain as the source of truth while moving connection and process
lifecycle overhead out of the request path.

## The improvements

### 1. Reuse persistent MCP sessions

The server maps compatible CLI-shaped reads onto MCP tools:

| Existing operation | Persistent MCP tool |
| --- | --- |
| `search` | `search` |
| `query` | `query` |
| `get` | `get_page` |
| `backlinks` | `get_backlinks` |
| `graph-query` | `traverse_graph` |
| `list` | `list_pages` |
| tag read | `get_tags` |

The transport is deliberately bounded:

- General product reads retain a serialized default lane rather than using
  unbounded concurrent access.
- Ask Yoda has a bounded pool of five MCP sessions so its selected-page,
  graph, backlink, query, direct-read, and targeted-context phases do not
  contend for one lock.
- Search and query use a smaller wait budget to protect interactive latency.
- Process exits, protocol errors, and timeouts close the session before reuse.
- Compatible reads outside Ask Yoda can retain a bounded CLI compatibility
  path where their contract requires it.
- Ask Yoda does not shell out: unavailable, malformed, unauthorized, busy, or
  timed-out MCP context fails closed and is reported as degraded context.
- Mutating MCP calls fail closed instead of replaying an uncertain write.

This preserved the old command contract while removing most process startup
cost.

#### Why this became possible: GBrain MCP parity

GBrain `0.46.12.2`, released on 2026-08-16, was the enabling platform
milestone. Its `CHANGELOG.md` described the change this way:

> **Your agent can now do over MCP what it could only do from the CLI.** An
> audit of the CLI-versus-MCP surface found the gap was never that MCP filtered
> tools out — it was CLI commands that never got an operation entry, so a
> connected agent hit "unknown tool" and fell back to shelling out. This wave
> closes that: eleven new tools, so an agent can record and resolve predictions,
> capture a quick note, check queue health, and read search/cache diagnostics
> without leaving the MCP session.

That distinction mattered. Memory Stargraph did not need a new GBrain storage
API or a GBrain source patch. The operations already existed; the expanded MCP
surface made them available to a connected long-lived agent session. Memory
Stargraph could therefore replace shell fallbacks with structured tool calls
while keeping GBrain as the source of truth. The Stargraph release used the
already-installed GBrain `0.46.28.0`; it did not upgrade GBrain as part of this
work.

### 2. Move background workers to endpoint-first transport

Four worker surfaces now prefer Memory Stargraph endpoints:

- Capture backlog management
- The recurring reliability and learning bridge
- The Capture Link host runner
- The Add Capture Link skill

The endpoint contract covers raw entity reads and writes, links, graph queries,
tags, and bounded page listing. Each write is followed by authoritative
readback. The CLI remains a compatibility path when the endpoint cannot be
used.

This change has two benefits:

1. Workers share the already-warm MCP session rather than creating their own
   process trees.
2. Transport policy, metrics, timeouts, and validation live in one product
   boundary instead of being reimplemented by every worker.

The latest deployed read benchmark used seven samples per path:

| Path | Median | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| Fresh `gbrain get index` CLI | 1,233 ms | 1,173 ms | 1,479 ms |
| Memory Stargraph raw-entity endpoint | 116 ms | 106 ms | 451 ms |

The median endpoint path was 10.65x faster.

### 3. Return less data

Transport reuse helps, but sending unnecessary data still costs CPU, memory,
serialization time, and browser work.

The Backlinks UI previously downloaded every backlink, including metadata the
modal did not render. A compact paginated endpoint now returns only one page of
the three displayed fields.

For a representative high-degree entity:

- Response size fell from 1,973,531 bytes to 1,484 bytes.
- Median modal-ready time fell from 1,194 milliseconds to 788 milliseconds.
- Later pages remain server-paginated rather than preloading thousands of
  records.

Search received a similar boundedness fix. Old transient search nodes are
removed when they are unexpanded, unlinked, not current results, and have no
durable tags. That prevents a long browser session from accumulating every
historical result in its active graph.

### 4. Reuse work within short freshness windows

We added short, purpose-specific caches instead of one broad cache:

- Raw entity reads coalesce concurrent requests for the same slug.
- Relationship and history reads reuse recent results.
- Settings cards and their detail views share one bounded evidence snapshot.
- Follow-ups reuse capability and listing snapshots.
- Ask Yoda reuses stable context while still performing question-specific
  retrieval when needed.

The cache windows are deliberately short and existing refresh controls still
force fresh reads. This made repeated interaction fast without turning the UI
into a stale snapshot.

### 5. Bound expensive graph work

Ask Yoda originally allowed broad graph context to expand too deeply for common
questions. High-degree depth-four traversal could exceed 20 seconds and consume
the entire optional graph budget.

We separated two concepts:

- The user's requested answer depth
- The broad graph context depth used to ground the prompt

Broad context is now bounded at depth two, while targeted relationship queries
retain their specific behavior. Persistent MCP graph traversal reduced a
representative graph-query median from 1.406 seconds to 42 milliseconds, with
exact output parity across the benchmark set.

### 6. Make Ask Yoda MCP-only under concurrency

The first persistent implementation still had one important escape hatch.
Ask Yoda assembled context concurrently, but all MCP calls shared one serialized
session. When that lane was busy, context arms could fall back to one-shot
`gbrain` subprocesses. Live V1.0.204 telemetry recorded 43 CLI fallbacks, 39 of
them page reads. A controlled page-read transport benchmark measured a warm MCP
median of 20.8 milliseconds versus 1,237.9 milliseconds through a fresh CLI
process.

V1.0.205 replaced that contention pattern with a bounded five-session pool and
kept page, query, search, backlinks, traversal, listing, tags, and think results
structured until the final prompt-formatting boundary. `gbrain_think` is called
with `save=false` and `take=false`, and Ask Yoda has no
`run_gbrain_subprocess` fallback.

The deployed acceptance benchmark reported:

| Metric | Before | After | Observed change |
| --- | ---: | ---: | ---: |
| End-to-end p50 | 8.748 s | 1.619 s | 81.5% lower, 5.40x faster |
| End-to-end p95 | 10.529 s | 5.609 s | 46.7% lower, 1.88x faster |
| Retrieval recall | 1.0 | 1.0 | Preserved |
| Structured MCP calls | n/a | 8/8 successful | 0 errors/timeouts |
| CLI fallbacks | 43 observed in prior live telemetry | 0 in acceptance | Removed from Ask Yoda |

The baseline was a cold benchmark and the post-change result was a repeated
benchmark, so these figures describe the observed product-path improvement,
not a thermally identical microbenchmark. The separate warm transport test
isolated the fixed process-startup cost. Together, the measurements show both
why the old path was slow and what users experienced after the bounded MCP
pool shipped.

## Observability added with the optimization

Performance work is risky when the fast path is invisible. The health endpoint
now reports persistent MCP state and cumulative process metrics:

```json
{
  "persistent_search": {
    "active": true,
    "ready": true,
    "busy": false,
    "metrics": {
      "process_start_attempts": 1,
      "process_starts": 1,
      "process_restarts": 0,
      "tool_calls": 1,
      "tool_successes": 1,
      "tool_errors": 0,
      "tool_timeouts": 0,
      "tool_latency_ms_average": 17.383,
      "tool_calls_by_name": {
        "get_tags": 1
      },
      "cli_fallbacks": 0,
      "cli_fallbacks_by_command": {}
    }
  }
}
```

The metrics answer the questions that matter during rollout:

- Is the persistent session ready?
- Is the session restarting unexpectedly?
- Which tools are using it?
- What latency is it delivering?
- Are calls timing out or failing?
- Is traffic silently falling back to CLI?

No request payloads, page contents, credentials, or private host details are
included.

## Deployment reliability mattered too

Faster code is not useful if deployment verification can accept the wrong
process or an unreachable target.

The deployment path now:

1. Resolves every requested revision to a full commit hash.
2. Restarts the dashboard through its launchd owner when available.
3. Verifies the expected version, HTML asset references, JavaScript version,
   listener PID, and process working directory.
4. Requires the same local PID to pass three consecutive checks.
5. Retries remote verification and preserves any failed `curl` or content check
   as the function's final failure status.

That last point fixed a subtle shell bug: a cleanup command previously could
overwrite an earlier `curl` failure and make an unreachable target appear
verified. The corrected script failed the first remote check, retried, and only
completed after the target actually responded with the expected version.

## How we measured safely

We treated performance as a contract, not a stopwatch contest.

For each meaningful optimization we checked:

- The same inputs before and after
- Median and tail samples, not one lucky request
- Exact or structured output parity
- Retrieval coverage and grounding recall where relevant
- No increase in fallback or degraded results
- Bounded cache freshness
- Failure and recovery behavior
- Full regression tests and static checks

Optimizations that did not clear the acceptance threshold or preserve evidence
quality were rejected. Warm same-query timings were not presented as cold
product improvements.

The endpoint-first release passed:

- 675 repository tests
- 21 Add Capture Link skill tests
- Python compilation
- JavaScript syntax validation
- Shell syntax validation
- Independent primary and secondary deployment readback

The Ask Yoda MCP-only release additionally passed:

- 367 focused tests
- 150 graph parsing tests
- 80 static tests
- 698 full-suite tests in 90.691 seconds
- Python and Node syntax checks
- Five simultaneous MCP page reads
- Desktop 1280x900 and mobile 390x844 deployed TLS smoke
- 8/8 live structured calls, with zero errors, timeouts, busy rejections, or
  CLI fallbacks

## What we deliberately did not do

- We did not change the GBrain source code.
- We did not upgrade GBrain during the optimization.
- We did not bypass GBrain as the source of truth.
- We did not auto-approve resolver proposals.
- We did not remove the CLI as an administrative or worker compatibility
  surface; we removed it only from Ask Yoda's latency-critical retrieval path.
- We did not use unbounded concurrency to hide latency.
- We did not cache every response indefinitely.

These constraints kept the performance work reversible and operationally safe.

## A reusable optimization playbook

The approach generalizes beyond Memory Stargraph:

1. **Measure phase boundaries.** Separate process startup, transport, database,
   serialization, network, and rendering time.
2. **Remove fixed overhead first.** Reuse an initialized session before tuning
   the query itself.
3. **Keep the old contract.** Map existing operations onto the faster transport.
   Retain a bounded fallback only where it is needed; when a fallback recreates
   the dominant fixed cost, prefer explicit fail-closed behavior after the MCP
   surface reaches parity.
4. **Return only what the caller renders.** Paginate high-cardinality data and
   omit unused fields.
5. **Bound graph and fan-out work.** Depth, concurrency, page size, and timeout
   limits should be explicit.
6. **Cache narrowly.** Use short TTLs and request coalescing around known repeat
   work, with explicit refresh behavior.
7. **Instrument the fast path.** Track calls, latency, errors, restarts, and
   fallback rates without logging sensitive payloads.
8. **Verify deployment stability.** Validate the process identity and repeat
   checks long enough to catch supervisor restart races.
9. **Require quality parity.** A faster answer with weaker retrieval or missing
   evidence is a regression.
10. **Keep rejected experiments.** They prevent the team from repeating changes
    that looked promising but did not improve the product path.

## Implementation references

- Persistent MCP session and health metrics: [`server.py`](../server.py)
- Deployment stability checks: [`scripts/automation/deploy_targets.sh`](../scripts/automation/deploy_targets.sh)
- Capture backlog endpoint transport: [`scripts/automation/manage_capture_backlog.py`](../scripts/automation/manage_capture_backlog.py)
- Recurring bridge endpoint transport: [`scripts/automation/recurring_worker_bridge.py`](../scripts/automation/recurring_worker_bridge.py)
- Capture runner endpoint transport: [`scripts/automation/capture_link_host_runner.py`](../scripts/automation/capture_link_host_runner.py)
- Add Capture Link endpoint transport: [`skills/add-capture-link/scripts/add_capture_link.py`](../skills/add-capture-link/scripts/add_capture_link.py)
- Detailed benchmark history: [`docs/performance-handoff-2026-08-23.md`](performance-handoff-2026-08-23.md)
- Ask Yoda MCP-only acceptance: [reports/memory-stargraph-wish-sg0217-20260828t033324-0700-512d2b9](http://127.0.0.1:8788/?slug=reports%2Fmemory-stargraph-wish-sg0217-20260828t033324-0700-512d2b9)
- GBrain MCP surface milestone: `CHANGELOG.md` section `0.46.12.2`

## Closing thought

The biggest performance gain came from changing the unit of reuse. Instead of
making each command slightly faster, Memory Stargraph stopped rebuilding the
same execution environment for every command. Once that fixed cost was removed,
bounded concurrency let Ask Yoda use the same long-lived MCP architecture
without serializing every context arm. Smaller improvements such as pagination,
bounded graph traversal, cache reuse, and response pruning then became easier
to see and measure.

That is the core lesson: optimize the system boundary first, then optimize the
work inside it.
