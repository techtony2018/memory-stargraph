# Task 3 Report: Queue-Only Add Capture Link Skill

## Status

Complete. Added a repository-canonical `/add-capture-link` skill that only creates verified `planned` capture requests and never invokes final capture execution.

## Files

- `skills/add-capture-link/SKILL.md`
- `skills/add-capture-link/agents/openai.yaml`
- `skills/add-capture-link/scripts/add_capture_link.py`
- `skills/add-capture-link/tests/test_add_capture_link.py`

This report is written under `.superpowers/sdd/` and is intentionally ignored by that directory's existing `*` rule.

## Implemented interfaces and guarantees

- `queue_capture(...) -> dict` plus CLI flags for source, source kind, instructions, repeated attachments, target, collection, repeated relationships, Stargraph URL, recovery manifest, and JSON output.
- Queue-only guard and skill instructions that forbid calling the Capture Link worker or another final-capture skill.
- Canonical `notes/memory-starmap-capture-list` eight-column parent rows and `CAP-NNNN` allocation.
- America/Los_Angeles timestamps in parent rows, child documents, reminders, and recovery bundle names.
- Input validation before GBrain or upload calls.
- Exact-byte private spooling with `0700` bundle directories and `0600` attachment/manifest files.
- Multipart upload only through Memory Stargraph's encoded `POST /api/entity-attach-file/<slug>` endpoint.
- Stargraph-reported durable-reference, byte-count, and SHA-256 verification against the private spool before a planned parent row exists.
- Transaction order: spool, parent read, ID/slug allocation, provisional recovery child, uploads, planned child verification, planned parent verification, bidirectional graph writes/readbacks, final receipt readback, recovery removal.
- Parent-row-last rollback on parent or graph readback failure, including best-effort removal of partially written graph links.
- Recovery manifest retries preserve original source, source kind, instructions, target, collection, relationships, capture ID, child slug, and exact spooled paths/bytes.
- Failure results include `reminder_required`, a Pacific `remind_after`, a sanitized Stargraph/GBrain blocker, and the exact retry command.

## TDD evidence

1. The initial queue tests failed with `FileNotFoundError` because `scripts/add_capture_link.py` did not exist.
2. The minimal transaction implementation made text-only, attachment, partial-failure, metadata-preservation, graph, duplicate, validation, recovery-retry, and CLI tests green.
3. A red ordering regression showed the parent was read before private spooling; the transaction was reordered and passed.
4. A red parent-readback regression showed a possibly written planned row was not rolled back; commit-start tracking was moved before parent verification and passed.
5. A red text-only graph regression showed the planned row and first graph edge survived failed readback; rollback was extended to all queue transactions and graph cleanup, then passed.
6. Durable SHA mismatch and exact multipart endpoint/byte tests pass against the adapted upload primitives.

## Verification

Commands:

```text
python3 -m unittest discover -s skills/add-capture-link/tests -v
python3 -m unittest tests.test_capture_backlog tests.test_backlog_compaction -v
python3 -m py_compile skills/add-capture-link/scripts/add_capture_link.py skills/add-capture-link/tests/test_add_capture_link.py
python3 /Users/tony/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/add-capture-link
git diff --check
```

Result before commit: 14 skill tests and 28 capture-state regressions passed; compile, skill validation, and diff checks exited successfully.

## Self-review

- Confirmed the runtime does not import from `~/.codex`; multipart, spooling, sanitization, durable-reference, and recovery helpers are self-contained.
- Confirmed no code path calls `invoke_capture_skill` or a capture worker.
- Confirmed attachments are uploaded once from the spool and parent rows are written only after every receipt verifies.
- Confirmed attachment failures and integrity mismatches leave no planned parent row and retain exact spooled bytes.
- Confirmed parent/child rows use the Task 2 capture schema and both required graph relations are read back exactly.
- Confirmed explicitly supplied target, collection, and relationship values survive initial queueing and manifest retry.
- Confirmed only Task 3's `skills/add-capture-link` tree is included in the commit.

## Concerns

No blocking concerns. GBrain and Stargraph transaction behavior is verified through stateful command-boundary and HTTP-boundary tests; this task intentionally did not enqueue a real live backlog item or upload user data.

## Review-finding fix pass

Fix commit: `2a51f52` (`fix: harden capture queue recovery`).

- Recovery retries now resolve and validate that the supplied path is exactly `recovery.json` in a direct child of the resolved recovery root. Symlink escapes and other locations are rejected before any manifest read, and successful cleanup removes only the revalidated bundle.
- A standard-library `fcntl.flock` lock at `<recovery-root>/.queue.lock` now covers manifest loading, private spooling, parent read, ID/slug allocation, child writes, uploads, parent mutation, graph verification, rollback, and recovery updates. The concurrency regression holds the first transaction mid-write and proves the second cannot read the parent until release, then observes `CAP-0001` and `CAP-0002`.
- Attachment acceptance now requires `served_available: true`, a `/media/<canonical-relative-path>` served reference on the trusted Stargraph origin, and a fresh GET whose byte count and SHA-256 match the private spool before the parent row is mutated. Cross-origin, unavailable, and mismatched served references fail closed.
- Each verified attachment receipt is written to the `0600` manifest immediately. Retry validates the saved receipt against both spooled and freshly served bytes, reuses it, and uploads only attachments without a durable receipt. The two-file regression proves the first successful upload is not repeated after the second upload fails.
- Text-only, parent-read, graph, attachment, input-validation, and other transactional failures preserve the exact supplied fields in a private manifest and return blocker, reminder, and retry data. Retry commands are assembled with `shlex.quote`; a recovery root containing spaces is covered.
- Parent-row-last behavior, provisional-child rollback, bidirectional graph verification, and queue-only behavior remain covered.

### Red/green evidence

The new tests first failed against commit `6750d16`: the symlink manifest was read, concurrent calls reached the parent together, parent-read failure escaped without a manifest, `_receipt` had no trusted-base served-byte argument, `fetch_served_attachment` did not exist, successful upload receipts were absent from partial-failure manifests, and invalid-input failures had no recovery result. After the fixes, all focused regressions pass.

### Fresh verification evidence

```text
python3 -W error::ResourceWarning -m unittest discover -s skills/add-capture-link/tests -v
# Ran 19 tests in 0.259s — OK

python3 -m unittest tests.test_capture_backlog tests.test_backlog_compaction -v
# Ran 28 tests in 0.062s — OK

python3 -m py_compile skills/add-capture-link/scripts/add_capture_link.py skills/add-capture-link/tests/test_add_capture_link.py
# exit 0

python3 /Users/tony/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/add-capture-link
# Skill is valid!

git diff --check
# exit 0
```

## Distributed-safety extension

Fix commit: `d18aeb9` (`fix: centralize capture queue authority`).

- Added `POST /api/capture-queue/reserve` and `POST /api/capture-queue/finalize` as the shared Stargraph queue authority. Reserve validates a URL-safe idempotency key and request metadata, derives a deterministic provisional child slug from the key, allocates the CAP id under a server-side thread plus `fcntl.flock` lock, persists the reservation ledger atomically, and returns the existing authoritative reservation on retry.
- Finalize accepts only the idempotency key and validated attachment receipts. It derives the child and reads CAP identity/status from the reservation, never from client authority fields; writes the planned child, appends the parent row once, repairs both typed links idempotently, and rejects a retry whose attachments differ from the authoritative finalized result.
- `/add-capture-link` now uses the shared reserve/finalize API instead of reading and replacing the parent itself. Its local lock remains only for private recovery-bundle integrity; cross-client CAP allocation and graph mutation are owned by Stargraph.
- Recovery retries fail closed unless every original `attachment_inputs` entry has one readable spooled path. `CODEX_HOME` is resolved before containment checks, and recovery root, bundle, manifest, and lock symlinks are rejected before chmod or deletion.
- Served-byte verification uses a no-auto-redirect opener and validates every redirect hop against the trusted Stargraph origin.
- Before upload, the manifest records each attachment's expected canonical child path. If an upload response is ambiguous, retry probes the hosted bytes/hash at that exact path before any repeat upload, reuses exact bytes, and fails closed on unavailable or mismatched ambiguous state.

### Red/green evidence

The new authority tests first failed because the reserve/finalize constants and functions did not exist. The new skill tests first failed because recovery manifests could omit original inputs, symlinked recovery components were accepted, a cross-origin final redirect was read, and ambiguous upload progress/canonical paths were absent. Implementing the shared authority and fail-closed recovery behavior made those tests green.

### Fresh verification evidence

```text
python3 -W error::ResourceWarning -m unittest tests.test_api_endpoints
# Ran 37 tests in 3.468s — OK

python3 -W error::ResourceWarning -m unittest discover -s skills/add-capture-link/tests
# Ran 23 tests in 0.264s — OK

python3 -W error::ResourceWarning -m unittest tests.test_capture_backlog tests.test_backlog_compaction
# Ran 28 tests in 0.063s — OK

python3 -m py_compile server.py tests/test_api_endpoints.py skills/add-capture-link/scripts/add_capture_link.py skills/add-capture-link/tests/test_add_capture_link.py
python3 /Users/tony/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/add-capture-link
git diff --check
# compile and diff checks exited 0; skill validation reported "Skill is valid!"
```

### Concerns

No blocking concerns. Distributed serialization assumes all clients use the same configured Stargraph queue-authority service; the API and skill tests use isolated fakes and intentionally do not enqueue a live item or upload user data.

## Authority-closure fix pass

- Replaced the projection-derived reservation behavior with a versioned atomic JSON ledger at `data/private-runtime/capture-queue/authority.json`. Both private runtime directories are `0700`; the ledger and authority lock are `0600`. The ledger alone stores the idempotency key, canonical request fingerprint, CAP id, deterministic child slug, `reserved`/`finalizing`/`finalized` state, verified receipts, graph-readback result, allocation counter, and external lease. Child metadata now contains only a non-authoritative fingerprint marker and cannot reconstruct a reservation.
- Reserve binds every normalized request field to a canonical SHA-256 fingerprint and rejects reuse of the key with different metadata. Child absence, tampering, and read failures are handled as projection repair or hard failure, never as authority reconstruction.
- Finalize re-reads every claimed attachment through the server-owned `/media/` storage resolution path and independently checks exact bytes, size, and SHA-256. Missing, unreadable, and fabricated hosted receipts fail before finalization.
- Finalize persists `finalizing` before projection work, repairs typed links idempotently, reads both exact graph edges back, and only then exposes planned child/parent projections. It writes `finalized` and `graph_verified: true` only after exact child, parent, and graph readbacks succeed. A retry repairs partial projection writes from ledger state.
- Added owner-token/expiry lease endpoints at `POST /api/capture-queue/lease/acquire` and `POST /api/capture-queue/lease/release`. Reserve/finalize reject active external leases. `manage_capture_backlog.py` acquires the same authority for init, list, snapshot, transition, compaction, and consistency-sensitive dry-run previews, retries acquisition safely, and releases in `finally`.
- The recovery manifest now durably records `upload_started` plus the expected canonical path before each upload POST. It clears `upload_started` only in the same fsynced atomic manifest write that records the verified receipt. Thus upload-response and `_receipt` ambiguity both force hosted-byte probing before any repeat upload.

### Red/green evidence

The new tests first failed because reserve returned child-derived `capture-recovery`, metadata conflicts were accepted, fabricated receipts reached finalize, lease functions did not exist, manager operations had no shared lease, and `_receipt` failure left no `upload_started` marker. The implementation then made ledger-tampering/read-failure, fingerprint-conflict, fabricated-receipt, partial-finalize recovery, queue-versus-worker lease, expiry/release, and `_receipt` ambiguity regressions green.

### Fresh verification evidence

```text
python3 -W error::ResourceWarning -m unittest tests.test_api_endpoints
# Ran 41 tests in 3.462s — OK

python3 -W error::ResourceWarning -m unittest discover -s skills/add-capture-link/tests
# Ran 24 tests in 0.296s — OK

python3 -m unittest tests.test_capture_backlog tests.test_backlog_compaction
# Ran 30 tests in 0.082s — OK

python3 -m unittest tests.test_todo_backlog_compaction
# Ran 5 tests in 0.042s — OK

python3 -m py_compile server.py scripts/automation/manage_capture_backlog.py skills/add-capture-link/scripts/add_capture_link.py skills/add-capture-link/tests/test_add_capture_link.py tests/test_api_endpoints.py tests/test_capture_backlog.py
# exit 0

python3 /Users/tony/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/add-capture-link
# Skill is valid!

git diff --check
# exit 0
```

### Concerns

No blocking concerns. The shared lease is intentionally fail-closed and expires after at most 300 seconds so a crashed worker cannot deadlock the queue. Direct deliberate GBrain writes outside the queue skill and managed backlog worker remain outside this authority boundary, as scoped by the review.
