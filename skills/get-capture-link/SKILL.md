---
name: get-capture-link
description: Read and filter Memory Stargraph capture backlog status from notes/memory-starmap-capture-list. Use when the user invokes /get-capture-link or asks which capture requests are planned, capturing, completed, or failed.
---

# Get Capture Link

Keep this workflow read-only.

1. Run `python3 "$SKILL_DIR/scripts/get_capture_link.py" --json`, adding `--status` or `--id` when requested.
2. Present every returned slug with its exact `link` value.
3. Report the summary counts and matching entries.

Never mutate capture status, trigger capture work, or invoke the worker.
