# Task 3 scope correction

The capture backlog is developer workflow tooling, not Memory Stargraph product-runtime functionality.

- Removed the capture queue authority API, lease, renewal, and fencing additions from `server.py` and its API tests.
- Restored the capture backlog manager and `/add-capture-link` skill to their state at `2a51f52`.
- Preserved the existing Stargraph attachment upload endpoint, local queue lock, transaction verification, and recovery-manifest retry behavior.
- No new product API remains for this workflow.

Verification is intentionally focused: `/add-capture-link` tests, capture backlog tests, Python compilation, and diff checks.
