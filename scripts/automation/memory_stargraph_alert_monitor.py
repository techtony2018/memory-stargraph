#!/usr/bin/env python3
"""Local Memory Stargraph/GBrain alert monitor.

This monitor is designed for a local Mac LaunchAgent. It checks every configured
Memory Stargraph instance with top-level ``curl -sS`` calls, verifies the
read-only GBrain-backed ``index`` entity path, suppresses normal deploy/SRE
windows, and sends an email only when a problem is persistent and newly
actionable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.message
import json
import os
from pathlib import Path
import shlex
import smtplib
import subprocess
import sys
from typing import Any
from urllib.parse import quote


DEFAULT_LOCAL_URL = "http://127.0.0.1:8788"
GOOD_SOURCE_STATUSES = {
    "lazy-root",
    "lazy-expanded",
    "lazy-node",
    "gbrain",
    "ok",
}
BAD_SOURCE_STATUSES = {
    "cached",
    "error",
    "not-loaded",
    "unavailable",
    "unknown",
}


def now_pacific() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        return dt.datetime.now().astimezone()


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
            value = parsed[0] if parsed else ""
        except ValueError:
            value = raw_value.strip("\"'")
        values[key] = value
    return values


def load_config(env: dict[str, str]) -> dict[str, str]:
    config_path = Path(
        env.get(
            "MEMORY_STARGRAPH_AUTOMATION_CONFIG",
            str(
                Path(env.get("CODEX_HOME", str(Path.home() / ".codex")))
                / "automations/memory-stargraph-wish-to-reallity/deployment-targets.env"
            ),
        )
    ).expanduser()
    config = parse_env_file(config_path)
    config.update({key: value for key, value in env.items() if key.startswith("MEMORY_STARGRAPH_")})
    config.update({key: value for key, value in env.items() if key.startswith("SMTP_")})
    config.update({key: value for key, value in env.items() if key in {"CODEX_HOME", "HOME"}})
    config["_config_path"] = str(config_path)
    return config


def normalize_base_url(url: str) -> str:
    base = url.strip().rstrip("/")
    if base.endswith("/api/health"):
        return base[: -len("/api/health")]
    return base


def parse_monitor_targets(config: dict[str, str]) -> list[dict[str, str]]:
    explicit = config.get("MEMORY_STARGRAPH_MONITOR_TARGETS", "").strip()
    targets: list[dict[str, str]] = []
    if explicit:
        if explicit.startswith("["):
            for item in json.loads(explicit):
                targets.append(
                    {
                        "name": str(item["name"]),
                        "base_url": normalize_base_url(str(item["url"])),
                        "curl_flags": str(item.get("curl_flags") or ""),
                    }
                )
            return targets
        for index, item in enumerate(explicit.replace(",", " ").split(), start=1):
            if "=" in item:
                name, url = item.split("=", 1)
            else:
                name, url = f"target_{index}", item
            targets.append({"name": name.strip(), "base_url": normalize_base_url(url), "curl_flags": ""})
        return targets

    local_url = config.get("MEMORY_STARGRAPH_LOCAL_URL", DEFAULT_LOCAL_URL)
    targets.append({"name": "local", "base_url": normalize_base_url(local_url), "curl_flags": ""})
    seen = {targets[0]["base_url"]}
    for index, url in enumerate(config.get("MEMORY_STARGRAPH_REMOTE_HEALTH_URLS", "").split(), start=1):
        base_url = normalize_base_url(url)
        if base_url and base_url not in seen:
            targets.append({"name": f"remote_{index}", "base_url": base_url, "curl_flags": ""})
            seen.add(base_url)

    for target in config.get("MEMORY_STARGRAPH_DEPLOY_TARGETS", "").split():
        verify_urls = config.get(f"MEMORY_STARGRAPH_TARGET_{target}_VERIFY_URLS", "")
        for offset, url in enumerate(verify_urls.split(), start=1):
            base_url = normalize_base_url(url)
            if base_url and base_url not in seen:
                name = config.get(f"MEMORY_STARGRAPH_TARGET_{target}_NAME", target)
                suffix = "" if offset == 1 else f"_{offset}"
                targets.append(
                    {
                        "name": f"{name}{suffix}",
                        "base_url": base_url,
                        "curl_flags": config.get(f"MEMORY_STARGRAPH_TARGET_{target}_CURL_FLAGS", ""),
                    }
                )
                seen.add(base_url)

    return targets


def default_state_path(config: dict[str, str]) -> Path:
    root = Path(config.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return root / "state/memory-stargraph-alert-monitor.json"


def default_suppress_path(config: dict[str, str]) -> Path:
    root = Path(config.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return root / "state/memory-stargraph-alert-suppression.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def curl_json(url: str, timeout: int, curl_flags: str = "") -> tuple[bool, int | None, str, dict[str, Any] | None]:
    cmd = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "-w",
        "\n%{http_code}",
    ]
    if curl_flags:
        cmd.extend(shlex.split(curl_flags))
    cmd.append(url)
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    output = result.stdout
    code: int | None = None
    body = output
    if "\n" in output:
        body, raw_code = output.rsplit("\n", 1)
        if raw_code.isdigit():
            code = int(raw_code)
    if result.returncode != 0:
        return False, code, result.stderr.strip() or f"curl exited {result.returncode}", None
    if code is None or code < 200 or code >= 300:
        return False, code, body[:500], None
    try:
        return True, code, "", json.loads(body or "{}")
    except json.JSONDecodeError as exc:
        return False, code, f"invalid JSON: {exc}", None


def probe_target(target: dict[str, str], timeout: int) -> dict[str, Any]:
    base = target["base_url"]
    name = target["name"]
    curl_flags = target.get("curl_flags", "")
    issues: list[str] = []
    details: dict[str, Any] = {"name": name, "base_url": base}

    ok, code, error, health = curl_json(f"{base}/api/health", timeout, curl_flags)
    details["health_http_code"] = code
    if not ok or health is None:
        issues.append(f"health probe failed: {error or code}")
        return {**details, "ok": False, "issues": issues}

    details["ui_version"] = health.get("ui_version")
    details["health_ok"] = health.get("ok")
    source = health.get("source") or {}
    details["source_mode"] = source.get("mode")
    details["source_status"] = source.get("status")
    details["source_updated_at"] = source.get("updated_at")
    details["warnings"] = source.get("warnings") or health.get("warnings") or []

    if health.get("ok") is False:
        issues.append("health ok=false")

    raw_url = f"{base}/api/entity-raw/{quote('index', safe='')}"
    raw_ok, raw_code, raw_error, raw_body = curl_json(raw_url, timeout, curl_flags)
    details["entity_raw_index_http_code"] = raw_code
    if not raw_ok or raw_body is None or raw_body.get("slug") != "index":
        issues.append(f"GBrain read-only index probe failed: {raw_error or raw_code}")

    if source:
        source_status = str(source.get("status") or "unknown")
        source_mode = str(source.get("mode") or "unknown")
        if source_mode != "gbrain":
            issues.append(f"GBrain source mode is {source_mode}")
        if source_status in BAD_SOURCE_STATUSES or source_status not in GOOD_SOURCE_STATUSES:
            issues.append(f"GBrain source status is {source_status}")
        if source.get("error"):
            issues.append(f"GBrain source error: {source.get('error')}")
    elif raw_ok:
        details["health_source_details"] = "missing_but_index_readback_verified"

    return {**details, "ok": not issues, "issues": issues}


def suppression_state(path: Path, now: dt.datetime) -> tuple[bool, str]:
    data = read_json(path)
    suppress_until = data.get("suppress_until")
    if not suppress_until:
        return False, ""
    try:
        until = dt.datetime.fromisoformat(str(suppress_until))
    except ValueError:
        return False, ""
    if until.tzinfo is None:
        until = until.replace(tzinfo=now.tzinfo)
    if until > now:
        return True, str(data.get("reason") or "suppressed")
    return False, ""


def issue_signature(failing: list[dict[str, Any]]) -> str:
    compact = [
        {
            "name": item["name"],
            "base_url": item["base_url"],
            "issues": item["issues"],
            "ui_version": item.get("ui_version"),
            "source_mode": item.get("source_mode"),
            "source_status": item.get("source_status"),
        }
        for item in failing
    ]
    return json.dumps(compact, sort_keys=True)


def render_email(now: dt.datetime, failing: list[dict[str, Any]], all_results: list[dict[str, Any]]) -> tuple[str, str]:
    subject = f"[Memory Stargraph Alert] {len(failing)} instance(s) need attention"
    lines = [
        f"Detected at: {now.isoformat()} America/Los_Angeles",
        "",
        "Failing targets:",
    ]
    for item in failing:
        lines.append(f"- {item['name']} ({item['base_url']})")
        for issue in item["issues"]:
            lines.append(f"  - {issue}")
        if item.get("ui_version"):
            lines.append(f"  - ui_version: {item.get('ui_version')}")
        lines.append(f"  - source: mode={item.get('source_mode')} status={item.get('source_status')}")

    lines.extend(["", "All target summary:"])
    for item in all_results:
        status = "ok" if item.get("ok") else "problem"
        lines.append(
            f"- {item['name']}: {status}; version={item.get('ui_version')}; "
            f"source={item.get('source_mode')}/{item.get('source_status')}"
        )
    lines.extend(
        [
            "",
            "Normal development redeploys and SRE operations can suppress alerts by running:",
            "python3 scripts/automation/memory_stargraph_alert_monitor.py suppress --minutes 45 --reason '<reason>'",
        ]
    )
    return subject, "\n".join(lines)


def send_email(config: dict[str, str], subject: str, body: str) -> str:
    recipient = config.get("MEMORY_STARGRAPH_ALERT_EMAIL_TO", "").strip()
    if not recipient:
        raise RuntimeError("missing MEMORY_STARGRAPH_ALERT_EMAIL_TO")
    sender = config.get("MEMORY_STARGRAPH_ALERT_EMAIL_FROM", config.get("SMTP_FROM", recipient)).strip()

    smtp_host = config.get("SMTP_HOST", "").strip()
    if smtp_host:
        msg = email.message.EmailMessage()
        msg["To"] = recipient
        msg["From"] = sender
        msg["Subject"] = subject
        msg.set_content(body)
        port = int(config.get("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, port, timeout=20) as smtp:
            if config.get("SMTP_USE_TLS", "1") != "0":
                smtp.starttls()
            username = config.get("SMTP_USERNAME", "")
            password = config.get("SMTP_PASSWORD", "")
            if username or password:
                smtp.login(username, password)
            smtp.send_message(msg)
        return f"smtp:{smtp_host}"

    mail_cmd = config.get("MEMORY_STARGRAPH_ALERT_MAIL_COMMAND", "mail")
    result = subprocess.run(
        [mail_cmd, "-s", subject, recipient],
        input=body,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{mail_cmd} exited {result.returncode}")
    return f"command:{mail_cmd}"


def run_once(args: argparse.Namespace) -> int:
    config = load_config(os.environ)
    state_path = Path(args.state_file or config.get("MEMORY_STARGRAPH_ALERT_STATE_FILE", "") or default_state_path(config)).expanduser()
    suppress_path = Path(
        args.suppress_file or config.get("MEMORY_STARGRAPH_ALERT_SUPPRESS_FILE", "") or default_suppress_path(config)
    ).expanduser()
    now = now_pacific()
    suppressed, suppress_reason = suppression_state(suppress_path, now)
    targets = parse_monitor_targets(config)
    results = [probe_target(target, args.timeout) for target in targets]
    failing = [item for item in results if not item.get("ok")]

    state = read_json(state_path)
    signature = issue_signature(failing) if failing else ""
    previous_counts = state.get("counts", {})
    counts: dict[str, int] = {}
    for item in results:
        key = item["name"]
        counts[key] = previous_counts.get(key, 0) + 1 if not item.get("ok") else 0
    threshold = max(1, args.failure_threshold)
    persistent = [item for item in failing if counts.get(item["name"], 0) >= threshold]

    should_alert = bool(persistent) and not suppressed and signature != state.get("last_alerted_signature")
    email_status = "not_needed"
    subject = ""
    body = ""
    if persistent:
        subject, body = render_email(now, persistent, results)
    if should_alert:
        if args.dry_run:
            email_status = "dry_run"
        else:
            email_status = send_email(config, subject, body)

    state.update(
        {
            "checked_at": now.isoformat(),
            "targets": results,
            "counts": counts,
            "suppressed": suppressed,
            "suppress_reason": suppress_reason,
            "last_signature": signature,
        }
    )
    if should_alert:
        state["last_alerted_signature"] = signature
        state["last_alerted_at"] = now.isoformat()
        state["last_email_status"] = email_status
    if not failing:
        state["last_alerted_signature"] = ""
    write_json(state_path, state)

    output = {
        "ok": not failing,
        "checked_at": now.isoformat(),
        "target_count": len(targets),
        "failing_count": len(failing),
        "persistent_failing_count": len(persistent),
        "suppressed": suppressed,
        "suppress_reason": suppress_reason,
        "email_status": email_status,
        "state_file": str(state_path),
        "suppress_file": str(suppress_path),
        "targets": results,
    }
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"ok={output['ok']} targets={len(targets)} failing={len(failing)} email_status={email_status}")
        for item in results:
            print(f"{item['name']}: {'ok' if item.get('ok') else 'problem'} {', '.join(item.get('issues', []))}")
    return 2 if failing else 0


def suppress(args: argparse.Namespace) -> int:
    config = load_config(os.environ)
    path = Path(args.suppress_file or config.get("MEMORY_STARGRAPH_ALERT_SUPPRESS_FILE", "") or default_suppress_path(config)).expanduser()
    now = now_pacific()
    until = now + dt.timedelta(minutes=args.minutes)
    write_json(
        path,
        {
            "created_at": now.isoformat(),
            "suppress_until": until.isoformat(),
            "reason": args.reason,
        },
    )
    print(json.dumps({"ok": True, "suppress_file": str(path), "suppress_until": until.isoformat(), "reason": args.reason}))
    return 0


def clear_suppression(args: argparse.Namespace) -> int:
    config = load_config(os.environ)
    path = Path(args.suppress_file or config.get("MEMORY_STARGRAPH_ALERT_SUPPRESS_FILE", "") or default_suppress_path(config)).expanduser()
    if path.exists():
        path.unlink()
    print(json.dumps({"ok": True, "suppress_file": str(path), "cleared": True}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Run one monitor pass.")
    once.add_argument("--json", action="store_true")
    once.add_argument("--dry-run", action="store_true", help="Do not send email; still update state.")
    once.add_argument("--timeout", type=int, default=int(os.environ.get("MEMORY_STARGRAPH_ALERT_TIMEOUT_SECONDS", "10")))
    once.add_argument(
        "--failure-threshold",
        type=int,
        default=int(os.environ.get("MEMORY_STARGRAPH_ALERT_FAILURE_THRESHOLD", "2")),
        help="Consecutive failing checks required before email.",
    )
    once.add_argument("--state-file")
    once.add_argument("--suppress-file")
    once.set_defaults(func=run_once)

    suppress_cmd = sub.add_parser("suppress", help="Suppress alerts for normal deploy/SRE work.")
    suppress_cmd.add_argument("--minutes", type=int, default=45)
    suppress_cmd.add_argument("--reason", required=True)
    suppress_cmd.add_argument("--suppress-file")
    suppress_cmd.set_defaults(func=suppress)

    clear = sub.add_parser("clear-suppression", help="Clear an active suppression marker.")
    clear.add_argument("--suppress-file")
    clear.set_defaults(func=clear_suppression)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
