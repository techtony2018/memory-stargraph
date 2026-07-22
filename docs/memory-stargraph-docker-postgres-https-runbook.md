# Memory Stargraph Docker Postgres and HTTPS Runbook

This runbook covers the deployment shape where Memory Stargraph runs on a Mac, GBrain uses a Docker-backed Postgres database, and Tailscale Serve exposes Memory Stargraph over tailnet HTTPS.

Use it when the browser shows a Tailscale `502`, Memory Stargraph loads but cannot reach GBrain, or `gbrain serve` exits with `connect ECONNREFUSED 127.0.0.1:<postgres-port>`.

## Topology

```text
Browser
  -> https://<tailscale-host>/
  -> Tailscale Serve on the Mac
  -> https+insecure://127.0.0.1:<stargraph-port>
  -> Memory Stargraph LaunchAgent
  -> local GBrain HTTP LaunchAgent
  -> Docker Postgres container
```

The public/tailnet route should be HTTPS. The backend route can also be HTTPS when Memory Stargraph is launched with a certificate and key.

GBrain MCP/OAuth paths may remain separate Tailscale Serve routes that proxy to GBrain's local HTTP port, for example:

```text
/mcp          -> http://127.0.0.1:<gbrain-port>/mcp
/token        -> http://127.0.0.1:<gbrain-port>/token
/authorize    -> http://127.0.0.1:<gbrain-port>/authorize
/.well-known/ -> http://127.0.0.1:<gbrain-port>/.well-known/
```

Those backend routes are local only. The public access path is still under the HTTPS Tailscale hostname.

## Fast Diagnosis

Run these on the host:

```bash
curl -sk https://127.0.0.1:<stargraph-port>/api/health
curl -sS http://127.0.0.1:<gbrain-port>/health
lsof -nP -iTCP:<postgres-port> -sTCP:LISTEN
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

Expected healthy state:

```text
Memory Stargraph: {"ok": true, ...}
GBrain:           {"status":"ok", "engine":"postgres", ...}
Postgres:         container port mapped from 127.0.0.1:<postgres-port> to 5432/tcp
Docker:           database container status is Up
```

If the Tailscale URL returns `502` while local health is good, inspect the Serve target:

```bash
/Applications/Tailscale.app/Contents/MacOS/tailscale serve status
```

A common error is proxying to `https+insecure://127.0.0.1:<stargraph-port>` while Memory Stargraph is only serving plain HTTP, or proxying to `http://...` while the backend has been changed to HTTPS. The Tailscale backend scheme must match the actual local server scheme.

## Docker Postgres Recovery

If GBrain exits with:

```text
Cannot connect to database: connect ECONNREFUSED 127.0.0.1:<postgres-port>
```

check Docker first:

```bash
docker info
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

If Docker is not running on macOS, start Docker Desktop:

```bash
open -gja Docker
```

Then wait for the daemon and container:

```bash
for i in $(seq 1 60); do
  docker info >/dev/null 2>&1 && break
  sleep 1
done

docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

The GBrain Postgres container should use a durable restart policy:

```bash
docker inspect <postgres-container> --format 'Name={{.Name}} RestartPolicy={{.HostConfig.RestartPolicy.Name}} Status={{.State.Status}}'
docker update --restart unless-stopped <postgres-container>
```

Do not create a new database container until you have checked for an existing container and volume. Creating a fresh container against a new volume can make the service look healthy while pointing at an empty brain.

## Ensure Docker Starts After Login

On macOS, Docker containers cannot restart until Docker Desktop itself starts. Add a user LaunchAgent:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.docker-desktop-start</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-gja</string>
    <string>Docker</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/docker-desktop-start.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/docker-desktop-start.err.log</string>
</dict>
</plist>
```

Install it under:

```text
~/Library/LaunchAgents/com.example.docker-desktop-start.plist
```

Then bootstrap it:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.docker-desktop-start.plist
launchctl kickstart -k "gui/$(id -u)/com.example.docker-desktop-start"
```

Verify:

```bash
docker info
docker inspect <postgres-container> --format 'RestartPolicy={{.HostConfig.RestartPolicy.Name}} Status={{.State.Status}}'
```

## Memory Stargraph LaunchAgent

Memory Stargraph should be owned by launchd, not a one-off SSH shell. A HTTPS-capable LaunchAgent should run:

```bash
cd /path/to/memory-stargraph
exec python3 server.py \
  --certfile /path/to/<tailscale-host>.crt \
  --keyfile /path/to/<tailscale-host>.key
```

Minimum verification:

```bash
launchctl print "gui/$(id -u)/<stargraph-label>"
lsof -nP -iTCP:<stargraph-port> -sTCP:LISTEN
curl -sk https://127.0.0.1:<stargraph-port>/api/health
```

If a previous ad hoc process owns the port, stop it before bootstrapping the LaunchAgent:

```bash
lsof -tiTCP:<stargraph-port> -sTCP:LISTEN
kill <pid>
launchctl kickstart -k "gui/$(id -u)/<stargraph-label>"
```

## Tailscale Serve

When Memory Stargraph serves HTTPS locally, the root Tailscale route should be:

```bash
/Applications/Tailscale.app/Contents/MacOS/tailscale serve --bg --yes \
  --set-path / https+insecure://127.0.0.1:<stargraph-port>
```

When Memory Stargraph serves plain HTTP locally, use:

```bash
/Applications/Tailscale.app/Contents/MacOS/tailscale serve --bg --yes \
  --set-path / http://127.0.0.1:<stargraph-port>
```

Verify from another tailnet machine:

```bash
curl -v https://<tailscale-host>/ -o /dev/null
curl -sk https://<tailscale-host>/api/health
```

The `curl -v` output should show:

```text
SSL certificate verify ok.
HTTP/2 200
```

## Restart Order

Use this order after reboot or outage:

1. Start Docker Desktop.
2. Verify Docker daemon is ready.
3. Verify the existing GBrain Postgres container is `Up`.
4. Restart or kick GBrain HTTP LaunchAgent.
5. Verify GBrain `/health`.
6. Restart or kick Memory Stargraph LaunchAgent.
7. Verify local Memory Stargraph `/api/health`.
8. Verify Tailscale Serve routes.
9. Verify public/tailnet HTTPS `/` and `/api/health`.

## Known Failure Patterns

- `502` from Tailscale with healthy local service usually means the Serve backend scheme or port is wrong.
- `gbrain serve` exits immediately with `ECONNREFUSED 127.0.0.1:<postgres-port>` when Docker Desktop or the Postgres container is down.
- A Docker container restart policy does not start Docker Desktop itself. Use a user LaunchAgent for Docker Desktop.
- Do not swap a configured Postgres brain to PGLite just because a PGLite directory exists. Confirm the active config and existing data source first.
- Do not create a new Postgres container until existing containers and volumes have been inspected.
- Keep public/private terminology precise: the Tailscale hostname is HTTPS public-within-tailnet; backend routes such as `127.0.0.1` are local implementation details.
