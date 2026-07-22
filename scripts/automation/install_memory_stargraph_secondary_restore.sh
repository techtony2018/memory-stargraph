#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
codex_home="${CODEX_HOME:-$HOME/.codex}"
monitor_home="$codex_home/automations/memory-stargraph-alert-monitor"
env_file="${MEMORY_STARGRAPH_ALERT_MONITOR_ENV:-$monitor_home/monitor.env}"
failover_script="$monitor_home/memory_stargraph_failover.py"
label="com.tony.memory-stargraph-secondary-restore"
plist="$HOME/Library/LaunchAgents/$label.plist"
hour="${MEMORY_STARGRAPH_SECONDARY_RESTORE_HOUR:-${MEMORY_STARGRAPH_SLAVE_RESTORE_HOUR:-4}}"
minute="${MEMORY_STARGRAPH_SECONDARY_RESTORE_MINUTE:-${MEMORY_STARGRAPH_SLAVE_RESTORE_MINUTE:-30}}"

mkdir -p "$monitor_home" "$HOME/Library/LaunchAgents"
cp "$repo_root/scripts/automation/memory_stargraph_failover.py" "$failover_script"
chmod 755 "$failover_script"

if [[ ! -f "$env_file" ]]; then
  echo "missing private monitor/failover env: $env_file" >&2
  echo "run scripts/automation/install_memory_stargraph_alert_monitor.sh first" >&2
  exit 2
fi

# shellcheck disable=SC1090
. "$env_file"

: "${MEMORY_STARGRAPH_SECONDARY_URL:=${MEMORY_STARGRAPH_SLAVE_URL:-}}"
: "${MEMORY_STARGRAPH_SECONDARY_RESTORE_COMMAND:=${MEMORY_STARGRAPH_SLAVE_RESTORE_COMMAND:-}}"
: "${MEMORY_STARGRAPH_SECONDARY_URL:?missing MEMORY_STARGRAPH_SECONDARY_URL in $env_file}"
: "${MEMORY_STARGRAPH_SECONDARY_RESTORE_COMMAND:?missing MEMORY_STARGRAPH_SECONDARY_RESTORE_COMMAND in $env_file}"

cat >"$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>set -a; source "$env_file"; set +a; cd "$monitor_home"; /usr/bin/python3 "$failover_script" restore-secondary --json</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$hour</integer>
    <key>Minute</key>
    <integer>$minute</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$monitor_home/secondary-restore.out.log</string>
  <key>StandardErrorPath</key>
  <string>$monitor_home/secondary-restore.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$plist"
launchctl enable "gui/$(id -u)/$label"

echo "installed and loaded $label"
echo "plist: $plist"
echo "env: $env_file"
echo "script: $failover_script"
