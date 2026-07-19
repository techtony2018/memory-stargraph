#!/usr/bin/env bash
set -euo pipefail

PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PATH

version="${1:?usage: deploy_targets.sh V1.0.xx [commit]}"
commit="${2:-HEAD}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
config_file="${MEMORY_STARGRAPH_AUTOMATION_CONFIG:-${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-wish-to-reallity/deployment-targets.env}"

if [[ ! -f "$config_file" ]]; then
  echo "missing local deployment config: $config_file" >&2
  echo "Define local service and remote target variables there; do not commit concrete host details." >&2
  exit 2
fi

# shellcheck disable=SC1090
. "$config_file"

: "${MEMORY_STARGRAPH_LOCAL_SERVICE_DIR:?missing MEMORY_STARGRAPH_LOCAL_SERVICE_DIR}"
: "${MEMORY_STARGRAPH_DASHBOARD_RESTART_URL:?missing MEMORY_STARGRAPH_DASHBOARD_RESTART_URL}"
: "${MEMORY_STARGRAPH_LOCAL_URL:?missing MEMORY_STARGRAPH_LOCAL_URL}"
: "${MEMORY_STARGRAPH_DEPLOY_TARGETS:?missing MEMORY_STARGRAPH_DEPLOY_TARGETS}"

tracked_files=(
  README.md
  server.py
  public/app.js
  public/index.html
  public/styles.css
  public/assets/brand/yoda-selection-avatar.png
  scripts/automation/gbrain_worker_api.py
  scripts/automation/source_sync_preflight.py
  scripts/automation/yoda_gap_evaluator.py
  tests/browser_smoke.mjs
  tests/test_frontend_static.py
  tests/test_source_sync_preflight.py
  tests/test_todo_backlog_compaction.py
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

echo "== local dashboard-managed service =="
for path in "${tracked_files[@]}"; do
  mkdir -p "$MEMORY_STARGRAPH_LOCAL_SERVICE_DIR/$(dirname "$path")"
  cp "$repo_root/$path" "$MEMORY_STARGRAPH_LOCAL_SERVICE_DIR/$path"
done
curl -sS -X POST "$MEMORY_STARGRAPH_DASHBOARD_RESTART_URL"
sleep 4
verify_url "$MEMORY_STARGRAPH_LOCAL_URL"
local_port="${MEMORY_STARGRAPH_LOCAL_URL##*:}"
local_port="${local_port%%/*}"
local_pid="$(lsof -nP -iTCP:"$local_port" -sTCP:LISTEN -t | head -1 || true)"
if [[ -n "$local_pid" ]]; then
  lsof -a -p "$local_pid" -d cwd -Fn | grep -F "n$MEMORY_STARGRAPH_LOCAL_SERVICE_DIR"
fi

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
    verify_url "$url" "$curl_flags"
  done
done

echo "deploy complete: $version $commit"
