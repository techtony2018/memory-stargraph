#!/bin/zsh
set -euo pipefail

# The dashboard owns the process lifecycle, while this version-controlled
# launcher owns the GBrain transport contract. Runtime credentials stay in a
# dedicated owner-only directory and are never copied into the repository.
export PATH="$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export GBRAIN_HOME="${MEMORY_STARGRAPH_GBRAIN_HOME:-$HOME/.codex/services/all-things-codex-dashboard/state/memory-stargraph-remote}"

GBRAIN_CONFIG_FILE="$GBRAIN_HOME/.gbrain/config.json"
GBRAIN_CREDENTIALS_FILE="$GBRAIN_HOME/credentials.env"
OPENCLAW_ACTIVATION_ENV_FILE="$HOME/.codex/services/all-things-codex-dashboard/state/openclaw-profile-activation/memory-stargraph.env"

require_owner_file() {
  local file_path="$1"
  [[ -f "$file_path" && ! -L "$file_path" ]] || {
    print -u2 "Memory Stargraph remote_mcp file is missing or unsafe: $file_path"
    return 1
  }
  [[ "$(/usr/bin/stat -f '%Lp' "$file_path")" = "600" ]] || {
    print -u2 "Memory Stargraph remote_mcp file must use mode 600: $file_path"
    return 1
  }
  [[ "$(/usr/bin/stat -f '%u' "$file_path")" = "$(/usr/bin/id -u)" ]] || {
    print -u2 "Memory Stargraph remote_mcp file must be owned by the service user: $file_path"
    return 1
  }
}

require_owner_file "$GBRAIN_CONFIG_FILE"
require_owner_file "$GBRAIN_CREDENTIALS_FILE"
require_owner_file "$OPENCLAW_ACTIVATION_ENV_FILE"

/opt/homebrew/bin/python3 - "$GBRAIN_CONFIG_FILE" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
try:
    config = json.loads(config_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Memory Stargraph remote_mcp config is invalid: {exc}")

remote = config.get("remote_mcp")
if not isinstance(remote, dict):
    raise SystemExit("Memory Stargraph remote_mcp config is unavailable")
for key in ("issuer_url", "mcp_url", "oauth_client_id"):
    value = remote.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Memory Stargraph remote_mcp config is missing {key}")
if any("secret" in key.lower() for key in remote):
    raise SystemExit("Memory Stargraph remote_mcp secret must not be stored in config.json")
PY

credential_lines="$(/usr/bin/grep -E '^GBRAIN_REMOTE_CLIENT_SECRET=[^[:space:]]+$' "$GBRAIN_CREDENTIALS_FILE" || true)"
[[ -n "$credential_lines" && "$(print -r -- "$credential_lines" | /usr/bin/wc -l | /usr/bin/tr -d ' ')" = "1" ]] || {
  print -u2 "Memory Stargraph remote_mcp credentials file must contain exactly one client secret"
  exit 1
}
export GBRAIN_REMOTE_CLIENT_SECRET="${credential_lines#GBRAIN_REMOTE_CLIENT_SECRET=}"
[[ -n "$GBRAIN_REMOTE_CLIENT_SECRET" ]] || {
  print -u2 "Memory Stargraph remote_mcp client secret is unavailable"
  exit 1
}

# The provisioning token and NATS credentials remain owner-only runtime state.
# Loading this existing environment restores OpenClaw activation visibility
# while the graph itself continues to use the dedicated remote_mcp identity.
source "$OPENCLAW_ACTIVATION_ENV_FILE"

exec /opt/homebrew/bin/python3 "$@"
