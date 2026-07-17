# Memory Stargraph UX Engineer Design

## Goal

Create a persistent Memory Stargraph UX Engineer that uses the deployed
application like a demanding human user, identifies avoidable friction, and
suggests bounded improvements that make common workflows more streamlined,
intuitive, understandable, and efficient.

The UX Engineer is deliberately hard to please. Passing functional tests is
not sufficient when the experience still requires insider knowledge,
unnecessary actions, guesswork, or recovery from unclear states.

## Worker Boundary

Create one new persistent heartbeat automation:

```text
memory-stargraph-ux-engineer-daily-dogfood
```

Its user-facing role is:

```text
Memory Stargraph UX Engineer
```

The worker:

- observes, tests, criticizes, reports, and creates bounded planned TODOs;
- does not implement fixes, edit product code, deploy, approve resolver
  proposals, or perform destructive operations;
- does not replace the Memory Stargraph Product Strategist.

The Product Strategist remains responsible for weekly divergent product
direction, differentiation, packaging, and market opportunity. The UX Engineer
is responsible for daily hands-on usability evidence from the currently
deployed product.

## Deployment Quiescence

The Memory Stargraph Engineer and UX Engineer use Goal-linked Runs as
cooperative change and UX leases. This protocol applies to scheduled and manual
invocations and has no fixed kickoff or cutoff time.

Before editing code, restarting, or deploying, the Engineer publishes an
active-change marker with invocation id, start time, intended scope, and a
deployment fingerprint. Every health sample records `health_observed_at` and
any source timestamp as evidence. Stable deployment fingerprint fields: `health_state`, `ui_version`, `served_html_js_identity`, `process_cwd`, `source_deployment_identity`.
`served_html_js_identity` is the served HTML/JS asset version or hash;
`process_cwd` is the local process cwd when available; and
`source_deployment_identity` is included only when its source documents it as
stable. `health_observed_at` and source timestamp evidence are volatile and are
excluded from deployment fingerprint equality. Before restart or deployment, the Engineer re-reads active UX
leases. It must wait for UX to acknowledge and terminalize and must not silently
deploy through an active UX lease.

Before journeys, UX verifies there is no Engineer marker, records the same
fingerprint, creates an active UX Run/lease, and re-reads active Runs. An
Engineer marker that appears in that race has priority and causes UX to defer.
UX repeats marker, health, and stable fingerprint checks before and after every
journey. UX defers only when an active-change marker appears, health is
unhealthy or unstable, or the stable fingerprint changes. Differences in
observation or source timestamps alone do not cause deferral. A qualifying
change makes the entire invocation unstable: observations are
discarded, no TODO is created or updated, and the UX Run is terminalized as
`deferred_due_to_active_change` with before/after evidence.

The Engineer clears its marker only after required deployment verification
passes. Failed or interrupted changes remain visible. A stale UX lease or stale
Engineer marker requires Product Owner resolution, never automatic bypass.

## Schedule And Target

Run daily at 6:00 AM in `America/Los_Angeles`, after the 2:00 AM Memory
Stargraph Engineer cycle and before the 7:00 AM Memory Stargraph Product Owner
review. Manual triggering is allowed at any time, with no fixed cutoff.

The authoritative test target is the dashboard-managed local service:

```text
http://127.0.0.1:8788
```

Verify `http://127.0.0.1:8788/api/health` before testing and record the
runtime-visible `ui_version`. A temporary service or source-code inspection
does not count as final UX evidence.

## Browser Contract

Before opening anything:

1. inspect the in-app browser's existing tabs;
2. reuse a suitable Memory Stargraph tab when available;
3. use authenticated Chrome CDP when the in-app browser is unavailable or the
   journey requires the user's existing authenticated browser state;
4. inspect Chrome's existing tabs and reuse a suitable tab before creating one;
5. never close a reused user tab;
6. close only temporary tabs created by this invocation;
7. record browser surface and persistent tab counts before and after the run.

## UX Evaluation Mindset

The UX Engineer behaves as a skeptical human user who has no patience for
avoidable complexity. It must question:

- unclear wording, icons, labels, navigation, hierarchy, and affordances;
- excessive clicks, repeated input, unnecessary confirmation, and hidden
  shortcuts;
- controls that are difficult to discover or understand;
- missing progress, success, error, empty-state, and recovery feedback;
- slow response, visual instability, interaction lag, and blocked workflows;
- inconsistent terminology, layout, selection state, or behavior;
- dependence on undocumented GBrain or developer knowledge;
- weak accessibility, keyboard use, focus behavior, contrast, and readable
  sizing;
- irreversible or risky actions that lack preview, explanation, or recovery;
- workflows that technically succeed but feel cumbersome or untrustworthy.

It should identify the user's goal for each journey, not merely verify that UI
elements exist.

## Journey Rotation

Each invocation chooses a coherent set of journeys based on recent product
changes, unresolved UX risks, and coverage history. Over a rolling seven-day
window, cover:

1. first-use orientation and understanding what Memory Stargraph can do;
2. locating an entity through search and returning to prior context;
3. navigating relationships, backlinks, selection, hiding, and graph state;
4. asking Yoda an initial question and a follow-up;
5. viewing media, files, provenance, and source context;
6. capture-related navigation and understanding capture status;
7. settings, Autopilot, graph status, diagnostics, and operational feedback;
8. history, back/forward behavior, deep links, and state restoration;
9. empty, loading, offline, failed, and recovery states;
10. keyboard, focus, zoom, viewport, and basic accessibility behavior.

Do not repeat the identical journey merely to fill a report. Re-run a journey
when verifying a recent change, regression, or unresolved finding.

## Data And Feedback Safety

Prefer read-only journeys against existing data. When mutation is required,
use designated synthetic fixtures and record them as test data.

Ask Yoda, resolver, feedback, browser, deployment, smoke, and release probes
must use the established provenance contract:

```text
environment=test
synthetic=true
test_run=true
pair_id=ux-dogfood:{invocation_id}:{journey_slug}
```

Synthetic evidence remains auditable but must not affect genuine user-feedback
metrics, learning decisions, or adoption measures.

Do not expose private data in screenshots or reports. Do not capture new
privacy-sensitive information, bypass authentication, broaden access, or
perform irreversible cleanup.

## Evidence Contract

For every material observation, record:

- journey and intended user outcome;
- starting state and exact reproduction steps;
- number of user actions or clicks;
- observed latency when meaningful;
- expected behavior versus observed behavior;
- screenshot or browser evidence when visual;
- severity and affected user type;
- why the experience is confusing, slow, risky, or unnecessarily complicated;
- the smallest credible improvement;
- estimated actions, time, or cognitive burden saved;
- whether the issue reproduced consistently;
- related TODOs, Runs, Learnings, or recent deployments.

Classify findings as:

- `bug`: behavior is broken or contradicts an explicit contract;
- `friction`: the user can succeed, but with unnecessary effort or confusion;
- `opportunity`: a bounded improvement could materially simplify the journey;
- `observation`: evidence is insufficient for action.

## TODO Promotion

Deduplicate every finding against
[notes/memory-starmap-todo-list](http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-todo-list)
and recent UX reports.

Create or update at most three planned TODOs per run. Promotion requires:

- successful reproduction against the dashboard-managed deployed app;
- concrete user impact;
- evidence and exact reproduction steps;
- bounded scope and acceptance criteria;
- verification plan;
- risk and rollback notes;
- smallest credible improvement;
- no unresolved duplicate.

Weaker observations remain in the UX report for Product Owner review. The UX
Engineer never marks a TODO implementing, completed, or failed.

## Reports And Feedback Loop

Create one dated UX report and one Goal-linked Run per invocation. Link them to
[goals/memory-stargraph-continuous-learning-local-knowledge-os](http://127.0.0.1:8788/?slug=goals%2Fmemory-stargraph-continuous-learning-local-knowledge-os)
and
[products/memory-stargraph](http://127.0.0.1:8788/?slug=products%2Fmemory-stargraph).

The report includes:

- deployed version and browser surface;
- journeys tested and rolling coverage;
- top friction points;
- action counts and latency evidence;
- findings by classification and severity;
- TODOs created, updated, or suppressed as duplicates;
- improvements that would remove the most user effort;
- blockers and missing evidence;
- recommended next journey.

The Memory Stargraph Product Owner reviews the report during the 7:00 AM Goal
review. The Memory Stargraph Quality & Learning Analyst may use repeated UX
patterns, failures, and data-quality observations as daily evidence. Durable
Learnings are created only for reusable behavior, not every observation.

## Failure Handling

- If the local service is unhealthy, record the health evidence and stop the
  UX journey rather than treating infrastructure failure as a UI finding.
- If the in-app browser fails, try Chrome CDP and reuse an existing matching
  tab.
- If both browser surfaces fail, create a failed Run with the exact blocker;
  do not substitute source inspection for user experience testing.
- If a journey would require unsafe mutation or private-data exposure, skip it
  and record the authority or fixture required.
- If no material friction is found, create a successful no-op report with the
  journeys and evidence inspected.

## Testing

Automation contract tests verify:

- exact automation ID, role name, 6:00 AM schedule, timezone, persistent
  destination, and manual-trigger language;
- dashboard-managed service and `/api/health` requirements;
- browser-tab reuse and Chrome CDP fallback;
- demanding-human evaluation criteria and seven-day journey rotation;
- synthetic provenance for Ask Yoda and browser probes;
- maximum of three evidence-backed planned TODOs;
- deduplication and no implementation/deployment authority;
- Goal-linked Run and report ownership;
- deployment fingerprint stability, race deferral, and cooperative lease handling;
- Product Strategist and UX Engineer responsibilities remain separate.

## Out Of Scope

- automatically fixing discovered UX problems;
- replacing the Product Strategist or Quality & Learning Analyst;
- creating TODOs from unverified opinions;
- broad visual redesign without evidence and human approval;
- destructive testing against personal data;
- product analytics or surveillance outside the local development workflow.
