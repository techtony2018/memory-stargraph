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
curl -sS --max-time 5 "$local_url/api/health" || echo "warn: local health unavailable at $local_url"

echo
echo "== dashboard =="
if [[ -n "$dashboard_url" ]]; then
  dashboard_code="$(curl -sS --max-time 5 -o /tmp/memory-stargraph-dashboard-preflight.html -w "%{http_code}" "$dashboard_url/" || true)"
  if [[ "$dashboard_code" == "200" ]]; then
    echo "ok: dashboard root reachable"
    [[ -n "$dashboard_restart_url" ]] && echo "restart endpoint configured"
  else
    echo "warn: dashboard root unavailable, http_code=${dashboard_code:-none}"
  fi
else
  echo "warn: dashboard URL not configured in local deployment config"
fi

echo
echo "== Chrome CDP =="
curl -sS --max-time 5 http://127.0.0.1:9333/json/version || echo "warn: Chrome CDP unavailable on 127.0.0.1:9333"

echo
echo "== remote reachability =="
if [[ -n "$remote_health_urls" ]]; then
  for url in $remote_health_urls; do
    curl -k -sS --max-time 5 "$url" || echo "warn: remote health unavailable: $url"
  done
else
  echo "warn: remote health URLs not configured in local deployment config"
fi

exit "$missing"
