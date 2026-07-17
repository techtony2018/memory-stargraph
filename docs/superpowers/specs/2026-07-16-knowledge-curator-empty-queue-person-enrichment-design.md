# Knowledge Curator Empty-Queue Person Enrichment Design

## Goal

Keep the Memory Stargraph Knowledge Curator productive when
[notes/memory-starmap-capture-list](http://127.0.0.1:8788/?slug=notes%2Fmemory-starmap-capture-list)
has no planned requests. Instead of ending with a no-op, each empty-queue
invocation enriches up to two existing entities using reliable public
evidence, prioritizing people before other entity types.

This is a development workflow capability, not an end-user product feature.

## Scope

The existing `memory-stargraph-capture-link-drain` automation remains the only
worker. Its ID, persistent task, schedule, manual-trigger behavior, queue
semantics, and capture responsibilities remain unchanged.

The new fallback runs only when the invocation's first authoritative capture
snapshot contains zero planned items. A non-empty frozen snapshot always takes
priority and is drained normally; entity enrichment does not run afterward.
On entering the empty-queue branch, the worker immediately creates an active
Goal-linked Run before it lists, selects, reserves, or mutates any entity. The
Run holds the invocation id, start time, mode, and empty-snapshot evidence so a
crash cannot disappear as an unrecorded no-op.

## Selection Contract

For an empty snapshot, fill a maximum of two enrichment slots. Select eligible
nodes whose effective type is `person` first.

Within every category, rank candidates deterministically by enrichment need:

1. missing or weak biography;
2. missing durable profile image;
3. missing authoritative public source links;
4. missing current or historically important roles;
5. sparse meaningful typed relationships or backlinks;
6. never-reviewed nodes first;
7. oldest successful enrichment or review timestamp;
8. lexical slug as the final stable tie-breaker.

Skip:

- an entity successfully enriched or reviewed within the previous 30 days;
- an entity reserved by another active enrichment Run;
- private or sensitive people for whom public enrichment would exceed existing
  authority;
- candidates for whom reliable public evidence cannot be found;
- nodes whose only available sources would require bypassing authentication,
  access controls, or privacy boundaries.

Continue through the ranked candidates until two people have been attempted or
the eligible person set is exhausted.

If fewer than two eligible people are available, fill the remaining slots from
other public entity types in this order:

1. organizations or companies;
2. teams or projects;
3. products or technologies;
4. other public entities with a clear evidence-backed enrichment opportunity.

Apply the exact same ordering to people, organizations or companies, teams or
projects, products or technologies, and other public entities: deficiency
first, never-reviewed first, oldest enrichment or review timestamp, then
lexical slug. Apply the same 30-day cooldown, active-Run exclusion, privacy
boundary, and evidence threshold to every category. The total cap remains two
attempted entities per invocation, regardless of type.

If no eligible candidates exist, record `no_eligible_candidates` in the
Goal-linked Run and finish successfully. Never force speculative or low-value
changes merely to fill the two slots.

## Active Run And Reservation Contract

Select and reserve entities one at a time in deterministic ranked order. Before
any entity mutation, persist and read back its exact slug, effective type,
reservation timestamp, and invocation id in the active Goal-linked Run. Then
re-read other active enrichment Runs.

If two invocations reserve the same entity, the earlier reservation timestamp
wins. If timestamps are equal, the lexically lowest invocation id wins. The
losing invocation records the collision, removes its
reservation, and selects the next eligible entity. No invocation may mutate an
entity until its reservation is persisted, read back, and confirmed as the
winner. This makes overlap deterministic even when two workers began from the
same candidate snapshot.

The active Run is finalized on success, failure, or caught interruption. Its
terminal evidence records each selected entity, verified reservation, attempted
operations, result, verification, and any reservation released without an
attempt. An unexpected hard crash leaves the Run active with its reservations,
last completed step, and start evidence; the Product Owner can therefore see
and explicitly resolve the stale Run instead of accepting false success.

## Enrichment Contract

For each selected entity:

1. read the current node, direct relationships, backlinks, files, and source
   provenance before changing anything;
2. use `agent-reach` for public-source discovery and prefer the most specific
   installed local GBrain/capture skill for the source;
3. inspect existing browser tabs first and reuse a suitable tab; use
   authenticated Chrome CDP only when the source requires the user's existing
   session;
4. collect only evidence-backed additions that improve biography, image,
   authoritative links, roles, or meaningful typed relationships;
5. preserve user-confirmed facts and never replace them with weaker inferred
   web evidence;
6. avoid duplicate pages, files, links, relationships, and repeated media
   storage;
7. preserve source URLs, source-native timestamps, and capture time in
   `America/Los_Angeles`;
8. verify node readback, searchability, relationships, backlinks, provenance,
   and any reused or newly attached media.

The Curator may add verified public facts and typed relationships. It must not
auto-approve resolver proposals, perform destructive merges or migrations,
capture privacy-sensitive data, or make broad schema changes.

## Results And Failure Handling

Each attempted entity reaches one invocation result:

- `enriched`: at least one material evidence-backed improvement passed all
  verification;
- `already_sufficient`: the node was reviewed and no responsible material
  improvement was available;
- `failed`: a real attempt failed, with the exact source, operation, evidence,
  retry path, and any human authority required.
If no entity is attempted, the invocation records `no_eligible_candidates`
because no responsible candidate existed after applying the people-first and
secondary-entity selection rules.

An `already_sufficient` result is not a failure and should update the
last-reviewed timestamp so the entity is not selected repeatedly.

The worker does not create capture backlog requests for this fallback.
Individual enrichment failures do not automatically create product TODOs.
Systemic defects in capture skills, Stargraph, GBrain, authentication,
verification, or media handling are included in the Goal-linked Run for the
Memory Stargraph Quality & Learning Analyst to judge during daily intake.

## Run Evidence

The invocation's Goal-linked Run records:

- the empty authoritative snapshot;
- candidate-ranking inputs and excluded candidates;
- reservation timestamps, collision decisions, and readback evidence;
- the selected entity slugs and types, or why fewer than two were eligible;
- sources and skills used;
- browser surface and tab-reuse evidence;
- before/after material changes;
- readback, search, relationship, backlink, provenance, and media verification;
- per-entity result;
- systemic issues requiring Learning, TODO consideration, or human action.

All user-facing GBrain slugs are exact-label links to:

```text
http://127.0.0.1:8788/?slug=<URL-encoded-slug>
```

## Testing

Automation contract tests verify that:

- enrichment runs only for an empty first authoritative snapshot;
- the active Goal-linked Run exists before selection or mutation;
- selected slugs are reserved and read back before mutation, with deterministic
  collision resolution;
- the cap is two attempted entities, with fewer allowed only when the eligible
  candidate set is exhausted;
- selection is deterministic in every category by deficiency, never-reviewed,
  oldest review, then lexical slug;
- secondary candidates fill unused slots in the order organizations/companies,
  teams/projects, products/technologies, then other public entities;
- recently enriched, private, conflicting, and unreliable-source candidates
  are skipped;
- an empty eligible set records `no_eligible_candidates` and succeeds without
  speculative changes;
- capture backlog work always takes priority;
- public evidence, browser-tab reuse, provenance, duplicate prevention, human
  control, and verification requirements remain explicit;
- failures are reported to the Quality & Learning Analyst rather than silently
  converted into TODOs.
- success, failure, and interruption terminalize the Run, while a hard crash
  remains visible as a stale active Run.

## Out Of Scope

- a separate person-enrichment worker or schedule;
- synthetic capture backlog items;
- enriching more than two entities per empty invocation;
- automatic resolver approval;
- speculative relationship creation;
- private-source research without explicit authority;
- product UI for choosing enrichment candidates.
