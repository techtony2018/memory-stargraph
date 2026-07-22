#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
codex_home="${CODEX_HOME:-$HOME/.codex}"
monitor_home="$codex_home/automations/memory-stargraph-alert-monitor"
env_file="${MEMORY_STARGRAPH_ALERT_MONITOR_ENV:-$monitor_home/monitor.env}"
monitor_script="$monitor_home/memory_stargraph_alert_monitor.py"
failover_script="$monitor_home/memory_stargraph_failover.py"
label="com.tony.memory-stargraph-alert-monitor"
plist="$HOME/Library/LaunchAgents/$label.plist"
interval="${MEMORY_STARGRAPH_ALERT_INTERVAL_SECONDS:-300}"

mkdir -p "$monitor_home" "$HOME/Library/LaunchAgents"
cp "$repo_root/scripts/automation/memory_stargraph_alert_monitor.py" "$monitor_script"
chmod 755 "$monitor_script"
if [[ -f "$repo_root/scripts/automation/memory_stargraph_failover.py" ]]; then
  cp "$repo_root/scripts/automation/memory_stargraph_failover.py" "$failover_script"
  chmod 755 "$failover_script"
fi

if [[ ! -f "$env_file" ]]; then
  cat >"$env_file" <<EOF
# Private local config for Memory Stargraph alert monitor.
# Keep this file out of git.
#
# Required for email:
# MEMORY_STARGRAPH_ALERT_EMAIL_TO=tony@example.com
#
# Optional SMTP. If omitted, macOS mail(1) is used.
# SMTP_HOST=smtp.example.com
# SMTP_PORT=587
# SMTP_USERNAME=
# SMTP_PASSWORD=
# SMTP_FROM=memory-stargraph-alerts@example.com
#
# Target format: label=url label=url label=url
# If omitted, the monitor derives targets from deployment-targets.env.
# MEMORY_STARGRAPH_MONITOR_TARGETS=local=http://127.0.0.1:8788 remote_a=https://example-a/memory-stargraph remote_b=https://example-b
#
# Optional warm-standby failover. Keep disabled until master/slave URLs,
# restore command, switch command, and fleet verification URLs are tested.
# MEMORY_STARGRAPH_FAILOVER_ON_ALERT=0
# MEMORY_STARGRAPH_MASTER_URL=
# MEMORY_STARGRAPH_SLAVE_URL=
# MEMORY_STARGRAPH_SLAVE_RESTORE_COMMAND=
# MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND=
# MEMORY_STARGRAPH_FLEET_CHECK_URLS=
#
MEMORY_STARGRAPH_ALERT_FAILURE_THRESHOLD=2
MEMORY_STARGRAPH_ALERT_TIMEOUT_SECONDS=10
EOF
  chmod 600 "$env_file"
  echo "created private config: $env_file"
  echo "edit MEMORY_STARGRAPH_ALERT_EMAIL_TO before loading the LaunchAgent"
  exit 2
fi

if ! grep -q '^MEMORY_STARGRAPH_ALERT_EMAIL_TO=.\+' "$env_file"; then
  echo "missing MEMORY_STARGRAPH_ALERT_EMAIL_TO in $env_file" >&2
  exit 2
fi

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
    <string>set -a; source "$env_file"; set +a; cd "$monitor_home"; /usr/bin/python3 "$monitor_script" once --json</string>
  </array>
  <key>StartInterval</key>
  <integer>$interval</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$monitor_home/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$monitor_home/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$plist"
launchctl enable "gui/$(id -u)/$label"

echo "installed and loaded $label"
echo "plist: $plist"
echo "env: $env_file"
echo "script: $monitor_script"
[[ -f "$failover_script" ]] && echo "failover: $failover_script"
