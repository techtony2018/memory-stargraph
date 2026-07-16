---
name: add-capture-link
description: Queue URLs, files, PDFs, text, GBrain slugs, profiles, or attached media for the Memory Stargraph Capture Link worker under notes/memory-starmap-capture-list. Use when the user invokes /add-capture-link or asks to add source material to the capture backlog.
---

# Add Capture Link

This skill is queue-only. It creates a `planned` capture request and never performs the final capture.

1. Pass every chat-host attachment as a repeated `--attachment` argument. Pass each path literally; do not copy, rename, or transform the source file first.
2. Use the most specific `--source-kind`; use `mixed` only when one request intentionally combines source types.
3. Preserve an explicitly supplied target, collection, and every requested relationship with `--target`, `--collection`, and repeated `--relationship` arguments.
4. Run `python3 "$SKILL_DIR/scripts/add_capture_link.py" ... --json`.
5. Report success only after the result has `ok: true` and confirms parent, child, graph, and durable attachment verification.
6. On `ok: false`, preserve the recovery manifest. When `reminder_required` is true, create exactly one user-visible reminder for `remind_after` and include the proposed blocker; never file the original request as planned.

Do not call `gbrain-capture-link`, any capture worker, or any other final-capture skill from this workflow. The persistent Capture Link worker owns execution after queueing.
