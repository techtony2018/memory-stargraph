#!/usr/bin/env bash
set -euo pipefail

PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PATH

version="${1:?usage: deploy_targets.sh V1.0.xx [commit]}"
commit="${2:-HEAD}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
commit="$(git -C "$repo_root" rev-parse "$commit^{commit}")"
config_file="${MEMORY_STARGRAPH_AUTOMATION_CONFIG:-${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-wish-to-reallity/deployment-targets.env}"
alert_monitor="$repo_root/scripts/automation/memory_stargraph_alert_monitor.py"
dashboard_label="${MEMORY_STARGRAPH_DASHBOARD_LAUNCHD_LABEL:-com.tony.memory-stargraph}"
recurring_bridge_label="${MEMORY_STARGRAPH_RECURRING_BRIDGE_LAUNCHD_LABEL:-com.tony.memory-stargraph.recurring-worker-bridge}"

if [[ ! -f "$config_file" ]]; then
  echo "missing local deployment config: $config_file" >&2
  echo "Define local service and remote target variables there; do not commit concrete host details." >&2
  exit 2
fi

# shellcheck disable=SC1090
. "$config_file"

if [[ -f "$alert_monitor" ]]; then
  python3 "$alert_monitor" suppress --minutes "${MEMORY_STARGRAPH_DEPLOY_ALERT_SUPPRESS_MINUTES:-45}" --reason "Memory Stargraph deployment $version $commit" >/dev/null || true
fi

: "${MEMORY_STARGRAPH_LOCAL_SERVICE_DIR:?missing MEMORY_STARGRAPH_LOCAL_SERVICE_DIR}"
: "${MEMORY_STARGRAPH_LOCAL_URL:?missing MEMORY_STARGRAPH_LOCAL_URL}"
MEMORY_STARGRAPH_DASHBOARD_RESTART_URL="${MEMORY_STARGRAPH_DASHBOARD_RESTART_URL:-}"
MEMORY_STARGRAPH_DASHBOARD_RESTART_COMMAND="${MEMORY_STARGRAPH_DASHBOARD_RESTART_COMMAND:-}"
MEMORY_STARGRAPH_LOCAL_CURL_FLAGS="${MEMORY_STARGRAPH_LOCAL_CURL_FLAGS:-}"
MEMORY_STARGRAPH_DEPLOY_TARGETS="${MEMORY_STARGRAPH_DEPLOY_TARGETS:-}"
MEMORY_STARGRAPH_DEPLOY_EVIDENCE_SLUGS="${MEMORY_STARGRAPH_DEPLOY_EVIDENCE_SLUGS:-}"
if [[ -z "$MEMORY_STARGRAPH_DASHBOARD_RESTART_URL" && -z "$MEMORY_STARGRAPH_DASHBOARD_RESTART_COMMAND" ]]; then
  echo "missing MEMORY_STARGRAPH_DASHBOARD_RESTART_URL or MEMORY_STARGRAPH_DASHBOARD_RESTART_COMMAND" >&2
  exit 2
fi

tracked_files=(
  README.md
  dashboard-integration.json
  openclaw_profile_activation.py
  requirements-dashboard.txt
  server.py
  public/app.js
  public/index.html
  public/styles.css
  public/assets/brand/yoda-selection-avatar.png
  scripts/automation/gbrain_worker_api.py
  scripts/automation/start_memory_stargraph_dashboard.zsh
  scripts/automation/capture_link_host_runner.py
  scripts/automation/recurring_worker_bridge.py
  scripts/automation/retrieval_quality_benchmark.py
  scripts/automation/com.tony.memory-stargraph.capture-link-runner.plist
  scripts/automation/com.tony.memory-stargraph.recurring-worker-bridge.plist
  scripts/automation/manage_capture_backlog.py
  scripts/automation/source_sync_preflight.py
  scripts/automation/worker_persistence.py
  scripts/automation/yoda_gap_evaluator.py
  automations/memory-stargraph-capture-link-drain/prompt.md
  tests/browser_smoke.mjs
  tests/customer_readiness_smoke.mjs
  tests/memory_digest_smoke.mjs
  tests/search_api_ui_parity_smoke.mjs
  tests/settings_readiness_parity_smoke.mjs
  tests/test_frontend_static.py
  tests/test_source_sync_preflight.py
  tests/test_todo_backlog_compaction.py
  tests/test_capture_link_host_runner.py
  tests/test_recurring_worker_bridge.py
  tests/test_retrieval_quality_benchmark.py
  tests/test_yoda_gap_evaluator.py
)

verify_url() {
  local base="$1"
  local curl_flags="${2:-}"
  echo "verify: $base"
  # shellcheck disable=SC2086
  curl $curl_flags -sS --max-time 10 "$base/api/health" | grep -E "\"ui_version\"[[:space:]]*:[[:space:]]*\"$version\""
  # shellcheck disable=SC2086
  curl $curl_flags -sS --max-time 10 "$base/" | grep -E "styles.css\\?v=${version#V}|app.js\\?v=${version#V}|>${version}<" >/dev/null
  # shellcheck disable=SC2086
  local app_tmp
  app_tmp="$(mktemp)"
  # Avoid curl|head under pipefail: head can close the pipe early and turn a
  # successful fetch into curl exit 23.
  curl $curl_flags -sS --max-time 10 "$base/app.js?v=${version#V}" -o "$app_tmp"
  head -1 "$app_tmp" | grep "const UI_VERSION = \"$version\""
  rm -f "$app_tmp"
}

verify_url_with_retries() {
  local base="$1"
  local curl_flags="${2:-}"
  local attempts="${3:-12}"
  local delay_seconds="${4:-5}"
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if verify_url "$base" "$curl_flags"; then
      return 0
    fi
    if [[ "$attempt" -lt "$attempts" ]]; then
      echo "verify retry $attempt/$attempts: target not ready yet"
      sleep "$delay_seconds"
    fi
  done
  return 1
}

restart_local_dashboard() {
  if launchctl print "gui/$(id -u)/$dashboard_label" >/dev/null 2>&1; then
    echo "reload dashboard launchd service: $dashboard_label"
    launchctl kickstart -k "gui/$(id -u)/$dashboard_label"
  elif [[ -n "$MEMORY_STARGRAPH_DASHBOARD_RESTART_URL" ]]; then
    curl -sS -X POST "$MEMORY_STARGRAPH_DASHBOARD_RESTART_URL"
  else
    sh -c "$MEMORY_STARGRAPH_DASHBOARD_RESTART_COMMAND"
  fi
}

verify_local_runtime_stable() {
  local base="$1"
  local curl_flags="$2"
  local port="$3"
  local attempts="${4:-12}"
  local delay_seconds="${5:-2}"
  local stable_checks="${6:-3}"
  local attempt pid stable current_pid
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    pid="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t | head -1 || true)"
    if [[ -n "$pid" ]] \
      && verify_url "$base" "$curl_flags" \
      && lsof -a -p "$pid" -d cwd -Fn | grep -F "n$MEMORY_STARGRAPH_LOCAL_SERVICE_DIR" >/dev/null; then
      stable=1
      while [[ "$stable" -lt "$stable_checks" ]]; do
        sleep "$delay_seconds"
        current_pid="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t | head -1 || true)"
        if [[ "$current_pid" != "$pid" ]] || ! verify_url "$base" "$curl_flags"; then
          break
        fi
        stable=$((stable + 1))
      done
      if [[ "$stable" -eq "$stable_checks" ]]; then
        echo "stable local dashboard: pid=$pid checks=$stable"
        lsof -a -p "$pid" -d cwd -Fn
        return 0
      fi
    fi
    if [[ "$attempt" -lt "$attempts" ]]; then
      echo "stable verify retry $attempt/$attempts: local dashboard not settled"
      sleep "$delay_seconds"
    fi
  done
  echo "local dashboard did not remain stable on $version" >&2
  return 1
}

verify_recurring_bridge_identity() {
  local expected_commit="$1"
  local expected_schema="${2:-memory-stargraph-sre-numeric-evidence-v1}"
  local output
  output="$(python3 "$repo_root/scripts/automation/recurring_worker_bridge.py" health --json)"
  printf '%s\n' "$output"
  python3 - "$expected_commit" "$expected_schema" "$output" <<'PY'
import json
import sys

expected_commit, expected_schema, raw = sys.argv[1], sys.argv[2], sys.argv[3]
payload = json.loads(raw)
state_identity = ((payload.get("daemon_state") or {}).get("runner_identity") or {})
identity = state_identity or payload.get("runner_identity") or {}
if identity.get("runner_host_commit") != expected_commit:
    raise SystemExit(f"recurring bridge commit mismatch: {identity.get('runner_host_commit')} != {expected_commit}")
schemas = set(identity.get("supported_evidence_schemas") or [])
if expected_schema not in schemas:
    raise SystemExit(f"recurring bridge does not support expected schema: {expected_schema}")
if identity.get("stale_runner"):
    raise SystemExit(f"recurring bridge stale: {identity.get('stale_reason')}")
daemon_state = payload.get("daemon_state") or {}
if daemon_state.get("runner_enabled") is not True:
    raise SystemExit("recurring bridge daemon is not enabled on authoritative host")
if daemon_state.get("runner_host_role") != ".85-authoritative":
    raise SystemExit(f"unexpected bridge host role: {daemon_state.get('runner_host_role')}")
PY
}

reload_recurring_bridge_if_present() {
  if ! launchctl print "gui/$(id -u)/$recurring_bridge_label" >/dev/null 2>&1; then
    echo "recurring bridge launchd label not loaded; skipping reload: $recurring_bridge_label"
    return 0
  fi
  echo "reload recurring bridge daemon: $recurring_bridge_label"
  launchctl kickstart -k "gui/$(id -u)/$recurring_bridge_label"
  for _ in {1..30}; do
    if verify_recurring_bridge_identity "$commit" >/tmp/memory-stargraph-recurring-bridge-verify.json 2>/tmp/memory-stargraph-recurring-bridge-verify.err; then
      cat /tmp/memory-stargraph-recurring-bridge-verify.json
      rm -f /tmp/memory-stargraph-recurring-bridge-verify.json /tmp/memory-stargraph-recurring-bridge-verify.err
      return 0
    fi
    sleep 2
  done
  cat /tmp/memory-stargraph-recurring-bridge-verify.json 2>/dev/null || true
  cat /tmp/memory-stargraph-recurring-bridge-verify.err 2>/dev/null || true
  rm -f /tmp/memory-stargraph-recurring-bridge-verify.json /tmp/memory-stargraph-recurring-bridge-verify.err
  echo "recurring bridge identity did not reach expected commit/schema" >&2
  return 1
}

write_deployment_attestation() {
  local service_dir="$1"
  local local_verified_at="$2"
  local configured_count="$3"
  local verified_count="$4"
  python3 - "$service_dir" "$version" "$commit" "$local_verified_at" "$configured_count" "$verified_count" "$MEMORY_STARGRAPH_DEPLOY_EVIDENCE_SLUGS" <<'PY'
import datetime as dt
import json
import pathlib
import sys

service_dir, version, commit, local_verified_at, configured_count, verified_count, evidence_raw = sys.argv[1:8]
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
evidence_slugs = [
    item.strip()
    for item in evidence_raw.split()
    if item.strip().startswith(("runs/", "reports/", "notes/", "learnings/", "goals/", "products/"))
]
payload = {
    "schema_version": 1,
    "generated_at": now,
    "ui_version": version,
    "source_commit": commit,
    "privacy": "Sanitized deployment attestation: aggregate counts and evidence slugs only; hostnames, IPs, credentials, paths, and target coordinates are withheld.",
    "evidence_slugs": evidence_slugs,
    "local": {
        "verified": bool(local_verified_at),
        "observed_at": local_verified_at or now,
        "status": "current" if local_verified_at else "missing",
    },
    "configured_remote": {
        "configured_target_count": int(configured_count or 0),
        "verified_target_count": int(verified_count or 0),
        "status": "current" if int(configured_count or 0) and int(configured_count or 0) == int(verified_count or 0) else ("no_activity" if int(configured_count or 0) == 0 else "partial"),
        "observed_at": now,
    },
}
target = pathlib.Path(service_dir) / "data" / "deployment_attestations.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"deployment attestation written: {target}")
PY
}

echo "== local dashboard-managed service =="
for path in "${tracked_files[@]}"; do
  mkdir -p "$MEMORY_STARGRAPH_LOCAL_SERVICE_DIR/$(dirname "$path")"
  source_path="$repo_root/$path"
  destination_path="$MEMORY_STARGRAPH_LOCAL_SERVICE_DIR/$path"
  if [[ "$(cd "$(dirname "$source_path")" && pwd -P)/$(basename "$source_path")" == "$(cd "$(dirname "$destination_path")" && pwd -P)/$(basename "$destination_path")" ]]; then
    continue
  fi
  cp "$source_path" "$destination_path"
done
local_port="${MEMORY_STARGRAPH_LOCAL_URL##*:}"
local_port="${local_port%%/*}"
restart_local_dashboard
verify_local_runtime_stable "$MEMORY_STARGRAPH_LOCAL_URL" "$MEMORY_STARGRAPH_LOCAL_CURL_FLAGS" "$local_port" 12 2 3
local_verified_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
reload_recurring_bridge_if_present

configured_target_count=0
verified_target_count=0
verified_remote_repos=()
verified_remote_hosts=()
for target in $MEMORY_STARGRAPH_DEPLOY_TARGETS; do
  prefix="MEMORY_STARGRAPH_TARGET_${target}"
  name_var="${prefix}_NAME"
  ssh_var="${prefix}_SSH"
  repo_var="${prefix}_REPO"
  port_var="${prefix}_PORT"
  start_var="${prefix}_START_CMD"
  verify_var="${prefix}_VERIFY_URLS"
  curl_flags_var="${prefix}_CURL_FLAGS"
  name="${!name_var:-$target}"
  ssh_host="${!ssh_var:?missing $ssh_var}"
  remote_repo="${!repo_var:?missing $repo_var}"
  remote_port="${!port_var:-8788}"
  start_cmd="${!start_var:?missing $start_var}"
  verify_urls="${!verify_var:?missing $verify_var}"
  curl_flags="${!curl_flags_var:-}"

  echo "== remote target: $name =="
  configured_target_count=$((configured_target_count + 1))
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$ssh_host" "
    set -e
    cd '$remote_repo'
    git fetch origin main
    git checkout main
    git reset --hard '$commit'
    pid=\$(lsof -nP -iTCP:$remote_port -sTCP:LISTEN -t | head -1 || true)
    if [ -n \"\$pid\" ]; then kill \"\$pid\"; fi
    sleep 2
    $start_cmd
    sleep 5
  "
  for url in $verify_urls; do
    verify_url_with_retries "$url" "$curl_flags" 18 5
  done
  verified_target_count=$((verified_target_count + 1))
  verified_remote_hosts+=("$ssh_host")
  verified_remote_repos+=("$remote_repo")
done

write_deployment_attestation "$MEMORY_STARGRAPH_LOCAL_SERVICE_DIR" "$local_verified_at" "$configured_target_count" "$verified_target_count"
for index in "${!verified_remote_hosts[@]}"; do
  ssh_host="${verified_remote_hosts[$index]}"
  remote_repo="${verified_remote_repos[$index]}"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$ssh_host" "
    set -e
    cd '$remote_repo'
    MEMORY_STARGRAPH_ATTEST_VERSION='$version' \
    MEMORY_STARGRAPH_ATTEST_COMMIT='$commit' \
    MEMORY_STARGRAPH_ATTEST_LOCAL_VERIFIED_AT='$local_verified_at' \
    MEMORY_STARGRAPH_ATTEST_CONFIGURED_COUNT='$configured_target_count' \
    MEMORY_STARGRAPH_ATTEST_VERIFIED_COUNT='$verified_target_count' \
    MEMORY_STARGRAPH_ATTEST_EVIDENCE_SLUGS='$MEMORY_STARGRAPH_DEPLOY_EVIDENCE_SLUGS' \
    python3 - <<'PY'
import datetime as dt
import json
import os
import pathlib

now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
configured_count = int(os.environ.get('MEMORY_STARGRAPH_ATTEST_CONFIGURED_COUNT') or 0)
verified_count = int(os.environ.get('MEMORY_STARGRAPH_ATTEST_VERIFIED_COUNT') or 0)
evidence_slugs = [
    item.strip()
    for item in os.environ.get('MEMORY_STARGRAPH_ATTEST_EVIDENCE_SLUGS', '').split()
    if item.strip().startswith(('runs/', 'reports/', 'notes/', 'learnings/', 'goals/', 'products/'))
]
payload = {
    'schema_version': 1,
    'generated_at': now,
    'ui_version': os.environ.get('MEMORY_STARGRAPH_ATTEST_VERSION', ''),
    'source_commit': os.environ.get('MEMORY_STARGRAPH_ATTEST_COMMIT', ''),
    'privacy': 'Sanitized deployment attestation: aggregate counts and evidence slugs only; hostnames, IPs, credentials, paths, and target coordinates are withheld.',
    'evidence_slugs': evidence_slugs,
    'local': {
        'verified': True,
        'observed_at': os.environ.get('MEMORY_STARGRAPH_ATTEST_LOCAL_VERIFIED_AT') or now,
        'status': 'current',
    },
    'configured_remote': {
        'configured_target_count': configured_count,
        'verified_target_count': verified_count,
        'status': 'current' if configured_count and configured_count == verified_count else ('no_activity' if configured_count == 0 else 'partial'),
        'observed_at': now,
    },
}
target = pathlib.Path('data') / 'deployment_attestations.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')
print(f'deployment attestation written: {target}')
PY
  "
done

if [[ -f "$alert_monitor" ]]; then
  python3 "$alert_monitor" clear-suppression >/dev/null || true
fi

echo "deploy complete: $version $commit"
