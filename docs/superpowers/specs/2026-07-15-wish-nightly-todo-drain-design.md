# Wish to Reallity TODO Drain And Worker Invocation Design

Date: 2026-07-15

## Purpose

Change the Memory Stargraph Wish to Reallity automation from a single-batch selector into an invocation-scoped queue drainer. Every TODO that is `planned` when a drain invocation begins must receive a real implementation attempt and reach a terminal state during that drain session.

The worker is not limited to one API, UI, product area, repository boundary, or implementation batch. Coherence applies only inside an individual batch; it must never be used to leave unrelated snapshot items planned.

The same invocation rule applies to all five persistent Memory Stargraph workers. Their recurrence rules define default trigger times only. A scheduled heartbeat or an explicit manual run request may invoke any worker at any time, and both trigger paths must execute the same current tracked prompt with the same evidence contract.

## Cross-Worker Invocation Invariant

These workers must be schedule-independent:

- `gbrain-x-intelligence-capture`;
- `memory-stargraph-daily-learning-intake`;
- `memory-stargraph-wish-to-reallity`;
- `memory-stargraph-divergent-product-discovery`;
- `memory-stargraph-goal-steward-daily-review`.

For every worker:

1. The trigger may be a configured heartbeat or an explicit manual invocation delivered to the persistent destination task.
2. The worker records its actual `started_at` timestamp and a unique invocation ID when it begins.
3. Relative windows such as “previous 24 hours” are calculated from that `started_at`, not from an assumed wall-clock schedule.
4. Terms such as “daily,” “nightly,” or “weekly” may describe the default recurrence or report family, but must not prevent an off-schedule run or change its correctness.
5. Run slugs and evidence must distinguish multiple invocations of the same worker on the same date.
6. The recurrence rules in `automation.toml` remain editable trigger configuration; worker prompts must not duplicate their clock times as business logic.

## Definitions

- **Drain invocation:** the complete work session beginning when a scheduled heartbeat or manual run request reaches the persistent Wish to Reallity task.
- **Cutoff snapshot:** the immutable set of TODO IDs whose parent rows are exactly `planned` in the first authoritative backlog read at the start of that invocation.
- **Batch:** one dependency-aware group of TODOs implemented and verified together.
- **Terminal item:** a snapshot TODO whose parent row and child node both read `completed` or `failed`.
- **Continuation:** an additional turn in the same persistent Wish to Reallity task that resumes the same cutoff snapshot.

## Cutoff And Queue Contract

At the beginning of every drain invocation, the worker must:

1. Record the actual `started_at` timestamp and unique drain ID.
2. Immediately read `notes/memory-starmap-todo-list` and snapshot every row whose status is exactly `planned`. This first authoritative read establishes the immutable cutoff; no clock hour is special.
3. Complete the normal preflight and remote sync while preserving the already-established snapshot.
4. Record the cutoff time, ordered snapshot IDs, priorities, and initial child-node status in a parent Goal-linked drain Run.
5. Order work by priority, age, and dependency. Dependencies may reorder items, but no snapshot item may be omitted.

TODOs created after the snapshot are outside the current drain. The final report must list them as post-cutoff items deferred to the next drain invocation, whether that invocation is scheduled or manual.

An empty snapshot produces a verified no-op Run. A non-empty snapshot cannot produce a no-op.

## Batch Execution

The worker may partition the snapshot into as many batches as needed. Each batch should minimize conflicting edits and make testing and rollback understandable, but the overall drain remains responsible for every snapshot item.

For each batch:

1. Re-read the parent rows and child nodes for the batch.
2. Resolve dependencies using other snapshot items first when possible.
3. Write a bounded plan with acceptance criteria, tests, rollout, rollback, and showcase evidence.
4. Move the selected parent rows and child nodes from `planned` to `implementing` and verify both representations.
5. Make a real implementation attempt using existing project patterns.
6. Test, inspect, iterate, commit, push, deploy, and verify according to each item's actual scope.
7. Record a Goal-linked batch Run connected to the parent drain Run.
8. Move every batch item to `completed` or `failed` with detailed evidence.

A batch may contain one item. Documentation-only work does not need a product deployment unless repository rules or its acceptance criteria require one. A failed batch must not prevent later independent batches from running.

## Continuation Scheduling

The preferred execution is sequential batches in one persistent task turn. If a checkpoint, context limit, or runtime limit makes another turn safer, the worker must:

1. Persist the drain ID, cutoff, remaining snapshot IDs, terminal results, current repository state, and next batch in automation memory and the parent drain Run.
2. Read the live Wish automation `target_thread_id` from `~/.codex/automations/memory-stargraph-wish-to-reallity/automation.toml`.
3. Send one immediate continuation message to that same persistent task using the Codex task-messaging capability.
4. Keep the parent drain Run `in_progress` and report that the drain is continuing, not complete.

Continuations must be sequential. Do not create parallel implementation tasks or overlapping worktrees for batches that share the repository or deployment targets.

The worker may finish only after the terminal verification succeeds. Time spent, batch count, unrelated scopes, or inconvenience are not valid reasons to stop.

## Completion Contract

Mark a TODO `completed` only when its acceptance criteria pass and required deployment targets are verified. Update the parent row and child node together. Completion evidence must include tests, changed artifacts, commit and push result when applicable, deployment state when applicable, showcase evidence, and rollback information.

After each completion, verify the parent and child read back as `completed` and no stale `planned` or `implementing` tag remains.

## Failure Contract

Mark a TODO `failed` only after a real attempt establishes a concrete blocker or unresolved acceptance failure. Difficulty, unrelated scope, low priority, elapsed time, or preference for another item are not failures.

Failure evidence must record:

- implementation and diagnostic steps attempted;
- exact error, failed acceptance criterion, or missing dependency/authority;
- relevant test, service, deployment, or readback evidence;
- repository and deployment state after rollback or containment;
- whether user input or human approval is required;
- the smallest next recovery action;
- whether an in-snapshot dependency should be retried first.

Human control remains mandatory. If a destructive migration, privacy-sensitive capture, resolver proposal action, broad architecture decision, credential, or external authority is required, the worker must stop before that action and mark the item `failed` with `human_approval_required` or the precise authority blocker. It must not infer approval.

Incomplete or unsafe code must not be pushed or deployed. Restore affected services to the last known-good version before terminalizing the item whenever rollback is possible.

## Failed-Item Collection

The collection `notes/memory-starmap-todo-list/failed-items` is currently absent. The worker must create it during the first drain if it still does not exist and connect it to `notes/memory-starmap-todo-list`.

Required enumerable links:

- parent backlog -> failed collection with `has_failed_collection`;
- failed collection -> parent backlog with `failed_items_for`;
- failed collection -> failed child with `has_failed_item`;
- failed child -> failed collection with `member_of`.

Failed items remain in the parent table with status `failed`. The collection is an additional operational view, not a replacement backlog. Existing failed items, if any, must be backfilled into the collection without altering their evidence.

## Run Evidence

Create one parent Run with a stable slug such as:

```text
runs/memory-stargraph-wish-to-reallity-drain-YYYY-MM-DDTHHMMSSZ
```

The parent Run begins as `in_progress`, contains the cutoff snapshot and batch queue, and is updated after every batch. Each batch creates its own Run and links to the parent with `part_of`.

When all snapshot items are terminal, set the parent Run to `completed` and record one of these results:

- `drained_all_completed`;
- `drained_with_item_failures`.

The parent report includes completed IDs, failed IDs, post-cutoff IDs, batch count, total elapsed time, tests, deployments, continuations, durable Learnings, and the authoritative final readback.

## Terminal Verification

Before the worker reports the drain complete:

1. Re-read the parent backlog.
2. Re-read every snapshot child node.
3. Prove every snapshot ID is `completed` or `failed` in both representations.
4. Prove every failed item belongs to the failed-item collection in both directions.
5. Prove no snapshot ID remains `planned` or `implementing`.
6. List post-cutoff planned items separately without modifying them.
7. Verify Goal links for the parent drain Run and every batch Run.

Any failed terminal verification must trigger correction or another continuation. It is not a successful drain.

## Files And Documentation

Implementation updates:

- `automations/memory-stargraph-wish-to-reallity/prompt.md` with the full drain loop and terminal contracts;
- every tracked worker `prompt.md`, heartbeat prompt, and thread bootstrap with the shared schedule-independent invocation contract;
- `automations/README.md` so the pipeline describes configurable default schedules, manual invocation, and invocation-scoped queue draining rather than one selected batch;
- `docs/automation-runbook.md` with cutoff, continuation, failure, failed-collection, and recovery behavior;
- automated contract tests that prevent future prompt changes from hard-coding trigger times or restoring single-batch selection or early exit.

The live automation destinations and recurrence rules remain unchanged. They are current defaults, not the only valid way or time to invoke a worker. Every scheduled or manually invoked worker must read the current tracked prompt; repository-mutating workers must sync merged instructions from `origin/main` according to their existing safety rules.

## Verification

Static contract tests must assert that the tracked prompt requires:

- an immutable invocation-start planned-item snapshot with no hard-coded clock hour;
- all snapshot items to reach `completed` or `failed`;
- multiple sequential batches and same-task continuation;
- detailed failure evidence and rollback state;
- failed-item collection creation and bidirectional links;
- terminal parent/child readback;
- post-cutoff deferral;
- preservation of human approval boundaries.

Tests must also reject the former behavior that allowed a non-empty backlog to select one batch and exit while other snapshot items remained planned.

Cross-worker contract tests must assert that:

- all five workers accept scheduled and manual invocation through the same persistent task;
- each worker anchors windows and evidence to its actual `started_at`;
- multiple same-day invocations produce distinct Run identities;
- fixed schedule times appear only in recurrence configuration or schedule documentation, never as execution cutoffs in worker logic.

Manual verification must compare the tracked prompts, runtime automation definitions, persistent target tasks, and heartbeat instructions. It must not trigger an extra production drain merely to test wording.

## Acceptance Criteria

- The tracked Wish prompt treats the planned queue at actual invocation start as an immutable drain obligation.
- All five workers run correctly from either their configured heartbeat or a manual invocation at any time.
- No worker prompt uses its configured schedule time as an execution cutoff or correctness assumption.
- Relative evidence windows are anchored to the invocation's actual `started_at`.
- No run-wide API, UI, feature, or architecture boundary limits selection.
- The worker can execute or schedule as many sequential batches as needed.
- Every cutoff item receives an attempt and becomes `completed` or `failed` during that drain session.
- Failures have detailed, truthful evidence and enumerable failed-collection membership.
- The drain Run cannot finish while a cutoff item remains `planned` or `implementing`.
- Risky actions still require explicit human approval.
- Automated tests protect the drain and failure contracts.

## Out Of Scope

- Automatically retrying previously failed items unless a person moves them back to `planned`.
- Processing TODOs created after an invocation's initial snapshot during the same drain.
- Parallel repository or deployment mutation from multiple batch tasks.
- Automatically approving resolver proposals or other high-risk actions.
- Treating queue drainage as permission to perform destructive or privacy-sensitive work.
