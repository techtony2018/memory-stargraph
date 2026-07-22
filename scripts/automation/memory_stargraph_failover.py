#!/usr/bin/env python3
"""Warm-standby and failover helper for Memory Stargraph-backed GBrain.

This script intentionally keeps host coordinates, backup commands, restore
commands, and traffic-switch commands in the private deployment env file. The
git-tracked code only enforces the safety contract:

- Secondary restore is explicit and verified after command completion;
- promotion requires Primary failure unless --force is supplied;
- promotion requires a healthy, recently restored Secondary;
- failback is not automatic.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any
from urllib.parse import quote


DEFAULT_TIMEOUT_SECONDS = 10


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
        try:
            parsed = shlex.split(raw_value.strip(), comments=False, posix=True)
            value = parsed[0] if parsed else ""
        except ValueError:
            value = raw_value.strip().strip("\"'")
        values[key.strip()] = value
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
    config.update({key: value for key, value in env.items() if key in {"CODEX_HOME", "HOME"}})
    config["_config_path"] = str(config_path)
    return config


def default_state_path(config: dict[str, str]) -> Path:
    root = Path(config.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return root / "state/memory-stargraph-failover.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def curl_json(base_url: str, path: str, timeout: int, curl_flags: str = "") -> tuple[bool, int | None, str, dict[str, Any] | None]:
    url = f"{base_url.rstrip('/')}{path}"
    cmd = ["curl", "-sS", "--max-time", str(timeout), "-w", "\n%{http_code}"]
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


def probe_instance(name: str, base_url: str, timeout: int, curl_flags: str = "") -> dict[str, Any]:
    details: dict[str, Any] = {"name": name, "base_url": base_url}
    issues: list[str] = []
    ok, code, error, health = curl_json(base_url, "/api/health", timeout, curl_flags)
    details["health_http_code"] = code
    if not ok or health is None:
        issues.append(f"health failed: {error or code}")
        return {**details, "ok": False, "issues": issues}
    details["ui_version"] = health.get("ui_version")
    details["health_ok"] = health.get("ok")
    source = health.get("source") or {}
    details["source_mode"] = source.get("mode")
    details["source_status"] = source.get("status")
    details["source_updated_at"] = source.get("updated_at")
    if health.get("ok") is False:
        issues.append("health ok=false")
    if source:
        if source.get("mode") != "gbrain":
            issues.append(f"source.mode={source.get('mode')}")
        if source.get("status") in {"cached", "error", "not-loaded", "unavailable", "unknown"}:
            issues.append(f"source.status={source.get('status')}")
        if source.get("error"):
            issues.append(f"source.error={source.get('error')}")

    raw_ok, raw_code, raw_error, raw = curl_json(base_url, f"/api/entity-raw/{quote('index', safe='')}", timeout, curl_flags)
    details["entity_raw_index_http_code"] = raw_code
    if not raw_ok or raw is None or raw.get("slug") != "index":
        issues.append(f"entity-raw/index failed: {raw_error or raw_code}")
    elif not source:
        details["source_status"] = "index-readback-verified"
    return {**details, "ok": not issues, "issues": issues}


def run_private_command(command: str, *, dry_run: bool, timeout: int) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "dry_run": True, "command_configured": bool(command)}
    if not command:
        return {"ok": False, "error": "command not configured"}
    result = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=timeout, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def refresh_secondary_readiness(config: dict[str, str], state: dict[str, Any], *, timeout: int) -> dict[str, Any] | None:
    command = config.get("MEMORY_STARGRAPH_SECONDARY_READINESS_COMMAND", "").strip()
    if not command:
        return None
    result = run_private_command(command, dry_run=False, timeout=timeout)
    state["last_secondary_readiness_result"] = result
    if not result.get("ok"):
        return result
    stdout = str(result.get("stdout_tail") or "").strip()
    try:
        readiness = json.loads(stdout)
    except json.JSONDecodeError as exc:
        result["ok"] = False
        result["error"] = f"invalid readiness JSON: {exc}"
        return result
    restored_at = readiness.get("secondary_restored_at") or readiness.get("restored_at_pacific")
    if restored_at:
        state["secondary_restored_at"] = str(restored_at)
    state["secondary_ready"] = bool(readiness.get("secondary_ready", True))
    state["secondary_readiness"] = readiness
    return result


def require_config(config: dict[str, str], key: str) -> str:
    value = config.get(key, "").strip()
    if not value:
        raise RuntimeError(f"missing {key}")
    return value


def config_value(config: dict[str, str], primary_key: str, legacy_key: str = "") -> str:
    value = config.get(primary_key, "").strip()
    if value:
        return value
    if legacy_key:
        return config.get(legacy_key, "").strip()
    return ""


def require_config_value(config: dict[str, str], primary_key: str, legacy_key: str = "") -> str:
    value = config_value(config, primary_key, legacy_key)
    if not value:
        suffix = f" or {legacy_key}" if legacy_key else ""
        raise RuntimeError(f"missing {primary_key}{suffix}")
    return value


def readiness_age_hours(state: dict[str, Any], now: dt.datetime) -> float | None:
    restored_at = state.get("secondary_restored_at") or state.get("slave_restored_at")
    if not restored_at:
        return None
    try:
        restored = dt.datetime.fromisoformat(str(restored_at))
    except ValueError:
        return None
    if restored.tzinfo is None:
        restored = restored.replace(tzinfo=now.tzinfo)
    return (now - restored).total_seconds() / 3600


def command_status(args: argparse.Namespace) -> int:
    config = load_config(os.environ)
    state_path = Path(args.state_file or config.get("MEMORY_STARGRAPH_FAILOVER_STATE_FILE", "") or default_state_path(config)).expanduser()
    state = read_json(state_path)
    readiness = refresh_secondary_readiness(config, state, timeout=args.timeout)
    if readiness is not None:
        write_json(state_path, state)
    primary_url = config_value(config, "MEMORY_STARGRAPH_PRIMARY_URL", "MEMORY_STARGRAPH_MASTER_URL")
    secondary_url = config_value(config, "MEMORY_STARGRAPH_SECONDARY_URL", "MEMORY_STARGRAPH_SLAVE_URL")
    timeout = args.timeout
    results = {
        "checked_at": now_pacific().isoformat(),
        "state_file": str(state_path),
        "state": state,
        "secondary_readiness_result": readiness,
        "primary": probe_instance("Primary", primary_url, timeout, config_value(config, "MEMORY_STARGRAPH_PRIMARY_CURL_FLAGS", "MEMORY_STARGRAPH_MASTER_CURL_FLAGS")) if primary_url else None,
        "secondary": probe_instance("Secondary", secondary_url, timeout, config_value(config, "MEMORY_STARGRAPH_SECONDARY_CURL_FLAGS", "MEMORY_STARGRAPH_SLAVE_CURL_FLAGS")) if secondary_url else None,
    }
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if (results["primary"] and results["secondary"]) else 1


def command_restore_secondary(args: argparse.Namespace) -> int:
    config = load_config(os.environ)
    state_path = Path(args.state_file or config.get("MEMORY_STARGRAPH_FAILOVER_STATE_FILE", "") or default_state_path(config)).expanduser()
    secondary_url = require_config_value(config, "MEMORY_STARGRAPH_SECONDARY_URL", "MEMORY_STARGRAPH_SLAVE_URL")
    command = require_config_value(config, "MEMORY_STARGRAPH_SECONDARY_RESTORE_COMMAND", "MEMORY_STARGRAPH_SLAVE_RESTORE_COMMAND")
    now = now_pacific()
    restore_result = run_private_command(command, dry_run=args.dry_run, timeout=args.command_timeout)
    secondary = probe_instance("Secondary", secondary_url, args.timeout, config_value(config, "MEMORY_STARGRAPH_SECONDARY_CURL_FLAGS", "MEMORY_STARGRAPH_SLAVE_CURL_FLAGS")) if restore_result["ok"] else None
    ok = bool(restore_result["ok"] and secondary and secondary.get("ok"))
    state = read_json(state_path)
    state.update(
        {
            "last_restore_attempt_at": now.isoformat(),
            "last_restore_result": restore_result,
            "last_restore_secondary_probe": secondary,
        }
    )
    if ok:
        state.update(
            {
                "secondary_restored_at": now.isoformat(),
                "secondary_ready": True,
                "secondary_url": secondary_url,
                "backup_label": config.get("MEMORY_STARGRAPH_BACKUP_LABEL", "latest-configured-backup"),
            }
        )
        state.pop("slave_restored_at", None)
        state.pop("slave_ready", None)
        state.pop("slave_url", None)
    write_json(state_path, state)
    print(json.dumps({"ok": ok, "state_file": str(state_path), "restore_result": restore_result, "secondary": secondary}, indent=2, sort_keys=True))
    return 0 if ok else 2


def command_promote_secondary(args: argparse.Namespace) -> int:
    config = load_config(os.environ)
    state_path = Path(args.state_file or config.get("MEMORY_STARGRAPH_FAILOVER_STATE_FILE", "") or default_state_path(config)).expanduser()
    primary_url = require_config_value(config, "MEMORY_STARGRAPH_PRIMARY_URL", "MEMORY_STARGRAPH_MASTER_URL")
    secondary_url = require_config_value(config, "MEMORY_STARGRAPH_SECONDARY_URL", "MEMORY_STARGRAPH_SLAVE_URL")
    switch_command = config.get("MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND", "").strip()
    now = now_pacific()
    state = read_json(state_path)
    refresh_secondary_readiness(config, state, timeout=args.timeout)
    max_age = float(config.get("MEMORY_STARGRAPH_FAILOVER_MAX_BACKUP_AGE_HOURS", "30"))
    age = readiness_age_hours(state, now)

    primary = probe_instance("Primary", primary_url, args.timeout, config_value(config, "MEMORY_STARGRAPH_PRIMARY_CURL_FLAGS", "MEMORY_STARGRAPH_MASTER_CURL_FLAGS"))
    secondary = probe_instance("Secondary", secondary_url, args.timeout, config_value(config, "MEMORY_STARGRAPH_SECONDARY_CURL_FLAGS", "MEMORY_STARGRAPH_SLAVE_CURL_FLAGS"))
    blockers: list[str] = []
    if primary.get("ok") and not args.force:
        blockers.append("Primary still healthy; refusing promotion without --force")
    if not secondary.get("ok"):
        blockers.append("Secondary is not healthy")
    if not (state.get("secondary_ready") or state.get("slave_ready")):
        blockers.append("Secondary is not marked ready from a verified restore")
    if age is None:
        blockers.append("Secondary restore age unknown")
    elif age > max_age:
        blockers.append(f"Secondary restore age {age:.2f}h exceeds max {max_age:.2f}h")
    if not switch_command:
        blockers.append("MEMORY_STARGRAPH_FAILOVER_SWITCH_COMMAND is not configured")

    switch_result: dict[str, Any] | None = None
    fleet_results: list[dict[str, Any]] = []
    if not blockers:
        switch_result = run_private_command(switch_command, dry_run=args.dry_run, timeout=args.command_timeout)
        if switch_result["ok"]:
            urls = config.get("MEMORY_STARGRAPH_FLEET_CHECK_URLS", secondary_url).split()
            flags = config.get("MEMORY_STARGRAPH_FLEET_CURL_FLAGS", "")
            fleet_results = [probe_instance(f"fleet_{index}", url, args.timeout, flags) for index, url in enumerate(urls, start=1)]
            if any(not item.get("ok") for item in fleet_results):
                blockers.append("post-switch fleet verification failed")
        else:
            blockers.append("switch command failed")

    ok = not blockers
    state.update(
        {
            "last_promotion_attempt_at": now.isoformat(),
            "last_promotion_primary_probe": primary,
            "last_promotion_secondary_probe": secondary,
            "last_promotion_switch_result": switch_result,
            "last_promotion_fleet_results": fleet_results,
            "last_promotion_blockers": blockers,
        }
    )
    if ok:
        state.update({"active_authoritative_role": "Secondary", "promoted_at": now.isoformat(), "promoted_secondary_url": secondary_url})
    write_json(state_path, state)
    print(
        json.dumps(
            {
                "ok": ok,
                "state_file": str(state_path),
                "blockers": blockers,
                "primary": primary,
                "secondary": secondary,
                "switch_result": switch_result,
                "fleet_results": fleet_results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "restore-secondary", "promote-secondary", "restore-slave", "promote-slave"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--json", action="store_true")
        cmd.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
        cmd.add_argument("--state-file")
        if name in {"restore-secondary", "promote-secondary", "restore-slave", "promote-slave"}:
            cmd.add_argument("--dry-run", action="store_true")
            cmd.add_argument("--command-timeout", type=int, default=900)
        if name in {"promote-secondary", "promote-slave"}:
            cmd.add_argument("--force", action="store_true")
    sub.choices["status"].set_defaults(func=command_status)
    sub.choices["restore-secondary"].set_defaults(func=command_restore_secondary)
    sub.choices["promote-secondary"].set_defaults(func=command_promote_secondary)
    sub.choices["restore-slave"].set_defaults(func=command_restore_secondary)
    sub.choices["promote-slave"].set_defaults(func=command_promote_secondary)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
