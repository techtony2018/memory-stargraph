#!/usr/bin/env bash
set -euo pipefail

automation_id="${1:?usage: retrospect.sh automation-id elapsed-seconds summary-file}"
elapsed_seconds="${2:?usage: retrospect.sh automation-id elapsed-seconds summary-file}"
summary_file="${3:?usage: retrospect.sh automation-id elapsed-seconds summary-file}"
codex_home="${CODEX_HOME:-$HOME/.codex}"
memory_file="$codex_home/automations/$automation_id/memory.md"

if [[ "$elapsed_seconds" -lt 300 ]]; then
  echo "retrospective skipped: elapsed ${elapsed_seconds}s is under 300s"
  exit 0
fi

mkdir -p "$(dirname "$memory_file")"
if [[ ! -f "$memory_file" ]]; then
  printf '# %s Automation Memory\n' "$automation_id" > "$memory_file"
fi

{
  printf '\n## Retrospective %s\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf -- '- Elapsed: %ss\n' "$elapsed_seconds"
  printf -- '- Source: %s\n\n' "$summary_file"
  cat "$summary_file"
  printf '\n'
} >> "$memory_file"

echo "retrospective appended: $memory_file"
