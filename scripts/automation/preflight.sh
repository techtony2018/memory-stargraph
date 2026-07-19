#!/usr/bin/env bash
set -u

PATH="$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PATH

config_file="${MEMORY_STARGRAPH_AUTOMATION_CONFIG:-${CODEX_HOME:-$HOME/.codex}/automations/memory-stargraph-wish-to-reallity/deployment-targets.env}"
if [[ -f "$config_file" ]]; then
  # Local-only file. Do not commit concrete deployment target values.
  # shellcheck disable=SC1090
  . "$config_file"
else
  echo "warn: local deployment config missing: $config_file"
fi

local_url="${MEMORY_STARGRAPH_LOCAL_URL:-http://127.0.0.1:8788}"
dashboard_url="${MEMORY_STARGRAPH_DASHBOARD_URL:-}"
dashboard_restart_url="${MEMORY_STARGRAPH_DASHBOARD_RESTART_URL:-}"
remote_health_urls="${MEMORY_STARGRAPH_REMOTE_HEALTH_URLS:-}"
authoritative_local_health_url="${MEMORY_STARGRAPH_AUTHORITATIVE_LOCAL_HEALTH_URL:-}"
local_corroboration_url="${MEMORY_STARGRAPH_LOCAL_CORROBORATION_URL:-}"
authoritative_dashboard_url="${MEMORY_STARGRAPH_AUTHORITATIVE_DASHBOARD_URL:-}"
dashboard_corroboration_url="${MEMORY_STARGRAPH_DASHBOARD_CORROBORATION_URL:-}"

probe_http_outcome() {
  local url="$1"
  local code
  if ! code="$(curl -k -sS --max-time 5 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)"; then
    printf 'transport_unverified'
    return
  fi
  if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
    printf 'healthy'
  else
    printf 'http_unhealthy'
  fi
}

classify_health() {
  local target="$1"
  local direct_url="$2"
  local authoritative_url="${3:-}"
  local corroboration_url="${4:-}"
  local direct_outcome
  local authoritative_outcome
  local corroboration_outcome

  direct_outcome="$(probe_http_outcome "$direct_url")"
  if [[ "$direct_outcome" == "healthy" ]]; then
    echo "health_state=healthy target=$target source=direct"
    return
  fi

  # A transport or loopback failure can be an execution-context restriction.
  # It is never outage evidence by itself.
  if [[ -z "$authoritative_url" ]]; then
    echo "health_state=unverified target=$target reason=direct_$direct_outcome"
    return
  fi
  authoritative_outcome="$(probe_http_outcome "$authoritative_url")"
  if [[ "$authoritative_outcome" == "healthy" ]]; then
    echo "health_state=healthy target=$target source=authoritative_host"
    return
  fi
  if [[ -z "$corroboration_url" ]]; then
    echo "health_state=unverified target=$target reason=authoritative_failure_without_corroboration"
    return
  fi
  corroboration_outcome="$(probe_http_outcome "$corroboration_url")"
  if [[ "$corroboration_outcome" == "healthy" ]]; then
    echo "health_state=unverified target=$target reason=conflicting_authoritative_evidence"
    return
  fi

  if [[ "$authoritative_outcome" == "http_unhealthy" && "$corroboration_outcome" == "http_unhealthy" ]]; then
    echo "health_state=unhealthy target=$target source=authoritative_host corroboration=independent"
  else
    echo "health_state=unverified target=$target reason=authoritative_or_corroboration_transport_unverified"
  fi
}

echo "== Memory Stargraph automation preflight =="
echo "cwd: $(pwd)"
echo "CODEX_HOME: ${CODEX_HOME:-$HOME/.codex}"

missing=0
for bin in git python3 node ssh curl grep head lsof; do
  if command -v "$bin" >/dev/null 2>&1; then
    echo "ok: $bin -> $(command -v "$bin")"
  else
    echo "missing: $bin"
    missing=1
  fi
done

if command -v npx >/dev/null 2>&1; then
  echo "ok: npx -> $(command -v npx)"
else
  echo "warn: npx missing; CDP/Playwright probes may need a local Playwright module"
fi

echo
echo "== local service =="
classify_health \
  "local_service" \
  "$local_url/api/health" \
  "$authoritative_local_health_url" \
  "$local_corroboration_url"

echo
echo "== dashboard =="
if [[ -n "$dashboard_url" ]]; then
  classify_health \
    "dashboard" \
    "$dashboard_url/" \
    "$authoritative_dashboard_url" \
    "$dashboard_corroboration_url"
  [[ -n "$dashboard_restart_url" ]] && echo "restart endpoint configured"
else
  echo "health_state=unverified target=dashboard reason=route_not_configured"
fi

echo
echo "== Chrome CDP =="
curl -sS --max-time 5 http://127.0.0.1:9333/json/version || echo "warn: Chrome CDP unavailable on 127.0.0.1:9333"

echo
echo "== remote reachability =="
if [[ -n "$remote_health_urls" ]]; then
  remote_index=0
  for url in $remote_health_urls; do
    remote_index=$((remote_index + 1))
    remote_outcome="$(probe_http_outcome "$url")"
    if [[ "$remote_outcome" == "healthy" ]]; then
      echo "health_state=healthy target=remote_target_$remote_index source=configured_route"
    else
      echo "health_state=unverified target=remote_target_$remote_index reason=single_route_$remote_outcome"
    fi
  done
else
  echo "health_state=unverified target=remote_targets reason=routes_not_configured"
fi

echo
echo "== source sync =="
dashboard_version="unknown"
if command -v python3 >/dev/null 2>&1 && [[ -f scripts/automation/source_sync_preflight.py ]]; then
  dashboard_version="$(curl -sS --max-time 5 "$local_url/api/health" 2>/dev/null | python3 -c 'import json,sys; print((json.load(sys.stdin).get("ui_version") or "unknown"))' 2>/dev/null || echo unknown)"
  python3 scripts/automation/source_sync_preflight.py \
    --root . \
    --dashboard-ui-version "$dashboard_version" \
    --required-path scripts/automation/yoda_gap_evaluator.py \
    --json || echo "warn: source-sync preflight recorded a blocker"
else
  echo "source_sync_status=unverified reason=helper_or_python_missing"
fi

exit "$missing"
