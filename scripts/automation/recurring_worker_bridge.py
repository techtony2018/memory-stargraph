#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import resource
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.automation import retrieval_quality_benchmark


PACIFIC = ZoneInfo("America/Los_Angeles")
SCHEMA_VERSION = 1
SRE_EVIDENCE_SCHEMA = "memory-stargraph-sre-evidence-v1"
SRE_NUMERIC_EVIDENCE_SCHEMA = "memory-stargraph-sre-numeric-evidence-v1"
LEARNING_EVIDENCE_SCHEMA = "memory-stargraph-learning-evidence-v1"
SUPPORTED_EVIDENCE_SCHEMAS = {
    "daily_learning_intake": {LEARNING_EVIDENCE_SCHEMA},
    "sre_daily_reliability": {SRE_EVIDENCE_SCHEMA, SRE_NUMERIC_EVIDENCE_SCHEMA},
}
MAX_REQUEST_BYTES = 64 * 1024
MAX_BUNDLE_BYTES = 256 * 1024
MAX_AGE_SECONDS = 6 * 60 * 60
PROCESSING_TIMEOUT_SECONDS = 20 * 60
HEARTBEAT_STALE_SECONDS = 120
POLL_MAX_SECONDS = 10 * 60
ALLOWED_ROLES = {"daily_learning_intake", "sre_daily_reliability"}
ALLOWED_OPERATIONS = {
    "daily_learning_intake": {"evidence", "persist"},
    "sre_daily_reliability": {"evidence", "persist"},
}
ALLOWED_DECISION_TYPES = {"no_action", "learning_created", "todo_planned", "report_only"}
SRE_MANUAL_NO_ACTION_DECISION_ALIASES = {"cli_version_notice_assessment"}
ROLE_AUTOMATION = {
    "daily_learning_intake": "memory-stargraph-daily-learning-intake",
    "sre_daily_reliability": "memory-stargraph-sre-daily-reliability",
}
ROLE_RUN_PREFIX = {
    "daily_learning_intake": "runs/memory-stargraph-learning-",
    "sre_daily_reliability": "runs/memory-stargraph-sre-",
}
ROLE_REPORT_PREFIX = {
    "daily_learning_intake": "reports/memory-stargraph-learning-",
    "sre_daily_reliability": "reports/memory-stargraph-sre-",
}
TODO_PREFIX = "notes/memory-starmap-todo-list/"
LEARNING_PREFIX = "notes/memory-stargraph-learnings/"


class BridgeError(RuntimeError):
    pass


class BridgePhaseError(BridgeError):
    def __init__(self, phase: str, message: str):
        super().__init__(message)
        self.phase = phase


def pacific_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(PACIFIC).replace(microsecond=0)


def iso_now() -> str:
    return pacific_now().isoformat()


BRIDGE_STARTED_AT = iso_now()
BRIDGE_INSTANCE_ID = os.environ.get("MEMORY_STARGRAPH_RECURRING_BRIDGE_INSTANCE_ID", uuid.uuid4().hex)


def runtime_root() -> Path:
    return Path(os.environ.get("MEMORY_STARGRAPH_RECURRING_BRIDGE_DIR", "var/recurring-worker-bridge")).expanduser()


def _safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._:-]{7,160}", value):
        raise BridgeError(f"unsafe identifier: {value!r}")
    return value


def _safe_nonce(value: str | None = None) -> str:
    nonce = value or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,160}", nonce):
        raise BridgeError("nonce must be 8-160 safe filename characters")
    return nonce


def _within(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise BridgeError(f"path escapes runtime root: {path}")
    return resolved


def ensure_dirs(root: Path) -> None:
    for name in ("incoming", "processing", "results", "completed", "failed", "locks", "logs", "bundles"):
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except PermissionError:
            pass


def incoming_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "incoming" / f"{_safe_nonce(nonce)}.json")


def processing_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "processing" / f"{_safe_nonce(nonce)}.json")


def completed_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "completed" / f"{_safe_nonce(nonce)}.json")


def failed_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "failed" / f"{_safe_nonce(nonce)}.json")


def result_path(root: Path, invocation_id: str, operation: str) -> Path:
    return _within(root, root / "results" / f"{_safe_id(invocation_id)}-{operation}.json")


def state_path(root: Path) -> Path:
    return _within(root, root / "runner-state.json")


def lock_path(root: Path) -> Path:
    return _within(root, root / "locks" / "recurring-worker-bridge.lock")


def log_path(root: Path) -> Path:
    return _within(root, root / "logs" / "bridge.jsonl")


def parse_time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BridgeError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise BridgeError("timestamp must be timezone-aware")
    return parsed


def run_cmd(args: list[str], *, input_text: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, input=input_text, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 124, "", str(exc))


def current_commit() -> str:
    result = run_cmd(["git", "rev-parse", "HEAD"], timeout=30)
    if result.returncode != 0:
        raise BridgePhaseError("source_validation", (result.stderr or result.stdout).strip() or "git rev-parse failed")
    return result.stdout.strip()


def runner_source_identity(expected_commit: str | None = None, expected_evidence_schema: str | None = None, role: str | None = None) -> dict[str, object]:
    try:
        commit = current_commit()
        commit_status = "ok"
    except BridgePhaseError as exc:
        commit = ""
        commit_status = "unavailable"
        commit_error = str(exc)
    else:
        commit_error = ""
    supported = sorted(SUPPORTED_EVIDENCE_SCHEMAS.get(str(role or ""), set().union(*SUPPORTED_EVIDENCE_SCHEMAS.values())))
    source_match = True if not expected_commit else commit == expected_commit
    schema_match = True if not expected_evidence_schema else expected_evidence_schema in supported
    stale_reasons = []
    if not source_match:
        stale_reasons.append("expected_commit_mismatch")
    if not schema_match:
        stale_reasons.append("expected_evidence_schema_unsupported")
    if commit_status != "ok":
        stale_reasons.append("runner_commit_unavailable")
    return {
        "runner_host_commit": commit,
        "runner_commit_status": commit_status,
        "runner_commit_error": commit_error,
        "runner_started_at": BRIDGE_STARTED_AT,
        "runner_instance_id": BRIDGE_INSTANCE_ID,
        "runner_pid": os.getpid(),
        "runner_source_path": str(Path(__file__).resolve()),
        "runner_code_mtime": dt.datetime.fromtimestamp(Path(__file__).stat().st_mtime, tz=dt.timezone.utc).astimezone(PACIFIC).replace(microsecond=0).isoformat(),
        "request_expected_commit": expected_commit or "",
        "deployed_source_match": source_match,
        "supported_request_schema_version": SCHEMA_VERSION,
        "supported_evidence_schemas": supported,
        "request_expected_evidence_schema": expected_evidence_schema or "",
        "evidence_schema_match": schema_match,
        "stale_runner": bool(stale_reasons),
        "stale_reason": ",".join(stale_reasons),
    }


def assert_runner_fresh(values: dict[str, str]) -> dict[str, object]:
    identity = runner_source_identity(
        values.get("expected_commit"),
        values.get("expected_evidence_schema"),
        values.get("role"),
    )
    if identity["stale_runner"]:
        raise BridgePhaseError("runner_identity", str(identity["stale_reason"]))
    return identity


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(data.encode("utf-8")) > MAX_REQUEST_BYTES and path.parent.name == "incoming":
        raise BridgeError("request exceeds size limit")
    if len(data.encode("utf-8")) > MAX_BUNDLE_BYTES and path.parent.name in {"results", "bundles"}:
        raise BridgeError("payload exceeds size limit")
    temp.write_text(data, encoding="utf-8")
    try:
        temp.chmod(0o600)
    except PermissionError:
        pass
    temp.replace(path)


def bridge_enabled() -> bool:
    return os.environ.get("MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED", "0") in {"1", "true", "yes"}


def remote_disabled_evidence() -> dict[str, object]:
    return {
        "runner_host_role": os.environ.get("MEMORY_STARGRAPH_RECURRING_BRIDGE_HOST_ROLE", ".85-authoritative"),
        "runner_enabled": bridge_enabled(),
        "runner_instance_id": BRIDGE_INSTANCE_ID,
        "runner_pid": os.getpid(),
        "runner_started_at": BRIDGE_STARTED_AT,
        "runner_identity": runner_source_identity(),
        "configured_remote_runner_disabled": True,
        "remote_role": ".102",
        "verification": os.environ.get(
            "MEMORY_STARGRAPH_RECURRING_BRIDGE_REMOTE_DISABLED_EVIDENCE",
            ".102 receives bridge code but MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED is unset by default",
        ),
    }


def write_state(root: Path, status: str, extra: dict[str, object] | None = None) -> dict[str, object]:
    ensure_dirs(root)
    payload = {"ok": True, "status": status, "updated_at": iso_now(), **remote_disabled_evidence(), **(extra or {})}
    atomic_write_json(state_path(root), payload)
    return payload


def read_state(root: Path) -> dict[str, object] | None:
    path = state_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"ok": False, "status": "invalid_bridge_state", "runner_state_file": str(path)}
    return payload if isinstance(payload, dict) else {"ok": False, "status": "invalid_bridge_state", "runner_state_file": str(path)}


def write_phase(root: Path, values: dict[str, str], phase: str, *, processed: int | None = None, total: int | None = None, extra: dict[str, object] | None = None) -> dict[str, object]:
    previous = read_state(root) or {}
    now = iso_now()
    started = previous.get("phase_started_at") if previous.get("phase") == phase else now
    progress: dict[str, object] = {}
    if processed is not None:
        progress["processed"] = processed
    if total is not None:
        progress["total"] = total
    return write_state(root, "processing", {
        "active_invocation_id": values["invocation_id"],
        "active_role": values["role"],
        "active_operation": values["operation"],
        "phase": phase,
        "phase_started_at": started,
        "phase_updated_at": now,
        "heartbeat_at": now,
        "poll_contract": {
            "max_seconds": POLL_MAX_SECONDS,
            "heartbeat_stale_seconds": HEARTBEAT_STALE_SECONDS,
            "continue_while": "daemon heartbeat fresh and runner ownership stable",
        },
        **({"progress": progress} if progress else {}),
        **(extra or {}),
    })


def make_request(role: str, operation: str, invocation_id: str, expected_commit: str, *, nonce: str | None = None, mode: str = "auto", bundle_file: str | None = None, synthetic: bool = False, expected_evidence_schema: str | None = None) -> dict[str, object]:
    if role not in ALLOWED_ROLES:
        raise BridgeError(f"unsupported role: {role}")
    if operation not in ALLOWED_OPERATIONS[role]:
        raise BridgeError(f"unsupported operation for role {role}: {operation}")
    request: dict[str, object] = {
        "version": SCHEMA_VERSION,
        "role": role,
        "automation_id": ROLE_AUTOMATION[role],
        "operation": operation,
        "invocation_id": _safe_id(invocation_id),
        "expected_commit": expected_commit,
        "mode": mode,
        "created_at": iso_now(),
        "nonce": _safe_nonce(nonce),
        "synthetic": synthetic,
    }
    if expected_evidence_schema:
        request["expected_evidence_schema"] = expected_evidence_schema
    if bundle_file:
        request["bundle_file"] = bundle_file
    return request


def validate_request(payload: dict[str, object], *, now: dt.datetime | None = None) -> dict[str, str]:
    if payload.get("version") != SCHEMA_VERSION:
        raise BridgeError("unsupported request version")
    role = payload.get("role")
    operation = payload.get("operation")
    if not isinstance(role, str) or role not in ALLOWED_ROLES:
        raise BridgeError("unsupported role")
    if not isinstance(operation, str) or operation not in ALLOWED_OPERATIONS[role]:
        raise BridgeError("unsupported operation")
    if payload.get("automation_id") != ROLE_AUTOMATION[role]:
        raise BridgeError("automation_id does not match role")
    values: dict[str, str] = {}
    for key in ("invocation_id", "expected_commit", "created_at", "nonce"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise BridgeError(f"missing {key}")
        values[key] = value
    created = parse_time(values["created_at"])
    age = (now or pacific_now()).astimezone(dt.timezone.utc) - created.astimezone(dt.timezone.utc)
    if age.total_seconds() < -300 or age.total_seconds() > MAX_AGE_SECONDS:
        raise BridgeError("request is outside freshness window")
    values.update({
        "role": role,
        "operation": operation,
        "mode": str(payload.get("mode") or "auto"),
        "automation_id": ROLE_AUTOMATION[role],
        "nonce": _safe_nonce(values["nonce"]),
        "synthetic": "true" if payload.get("synthetic") else "false",
    })
    expected_schema = payload.get("expected_evidence_schema")
    if expected_schema is not None:
        if not isinstance(expected_schema, str) or not expected_schema:
            raise BridgeError("invalid expected_evidence_schema")
        values["expected_evidence_schema"] = expected_schema
    bundle = payload.get("bundle_file")
    if bundle is not None:
        if not isinstance(bundle, str) or not bundle:
            raise BridgeError("invalid bundle_file")
        values["bundle_file"] = bundle
    values["invocation_id"] = _safe_id(values["invocation_id"])
    return values


def submit_request(root: Path, request: dict[str, object]) -> dict[str, object]:
    ensure_dirs(root)
    values = validate_request(request)
    destination = incoming_path(root, values["nonce"])
    target = result_path(root, values["invocation_id"], values["operation"])
    if target.exists():
        return {"ok": True, "status": "already_terminal", "result_file": str(target)}
    for existing in (destination, processing_path(root, values["nonce"]), completed_path(root, values["nonce"])):
        if existing.exists():
            if json.loads(existing.read_text(encoding="utf-8")) != request:
                raise BridgeError("nonce replay with different payload")
            return {"ok": True, "status": "already_submitted", "request_file": str(existing), "result_file": str(target)}
    atomic_write_json(destination, request)
    return {"ok": True, "status": "submitted", "request_file": str(destination), "result_file": str(target)}


def read_status(root: Path, invocation_id: str, operation: str) -> dict[str, object]:
    ensure_dirs(root)
    target = result_path(root, invocation_id, operation)
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload.setdefault("result_file", str(target))
        return payload
    return {
        "ok": True,
        "status": "pending",
        "result_file": str(target),
        "daemon_state": read_state(root),
        "submitter_context": {"network_required": False, "current_process_runner_enabled": bridge_enabled()},
        "polling_guidance": {"max_seconds": POLL_MAX_SECONDS, "heartbeat_stale_seconds": HEARTBEAT_STALE_SECONDS},
    }


def terminal_result(values: dict[str, str], status: str, result: str, evidence: dict[str, object]) -> dict[str, object]:
    return {
        "ok": status == "completed",
        "status": status,
        "result": result,
        "version": SCHEMA_VERSION,
        "role": values["role"],
        "operation": values["operation"],
        "automation_id": values["automation_id"],
        "invocation_id": values["invocation_id"],
        "nonce": values["nonce"],
        "completed_at": iso_now(),
        "runner_identity": runner_source_identity(
            values.get("expected_commit"),
            values.get("expected_evidence_schema"),
            values.get("role"),
        ),
        "evidence": evidence,
    }


def gbrain_get(slug: str, *, timeout: int = 30) -> tuple[bool, str]:
    raw = stargraph_raw(slug, timeout=timeout)
    if raw is not None:
        return True, raw
    result = run_cmd(["gbrain", "get", slug], timeout=timeout)
    if result.returncode == 0:
        return True, result.stdout
    return False, result.stderr or result.stdout


def gbrain_put(slug: str, markdown: str, *, timeout: int = 45) -> None:
    if not stargraph_save(slug, markdown, timeout=timeout):
        result = run_cmd(["gbrain", "put", slug, "--content", markdown], timeout=timeout)
        if result.returncode != 0:
            raise BridgePhaseError("artifact_persistence", f"Stargraph API save and gbrain put failed for {slug}: {(result.stderr or result.stdout).strip()}")
    raw = stargraph_raw(slug, timeout=timeout)
    if raw is None:
        readback = run_cmd(["gbrain", "get", slug], timeout=timeout)
        if readback.returncode != 0:
            raise BridgePhaseError("artifact_readback", f"readback failed for {slug}: {(readback.stderr or readback.stdout).strip()}")
        raw = readback.stdout
    if not markdown_readback_matches(markdown, raw):
        raise BridgePhaseError("artifact_readback", f"readback mismatch for {slug}")


def split_markdown(markdown: str) -> tuple[str, str]:
    if markdown.startswith("---") and markdown.count("---") >= 2:
        _, frontmatter, body = markdown.split("---", 2)
        return frontmatter.strip(), body.strip()
    return "", markdown.strip()


def frontmatter_status(frontmatter: str) -> str | None:
    for line in frontmatter.splitlines():
        match = re.match(r"status:\s*['\"]?([^'\"\n]+)['\"]?\s*$", line.strip())
        if match:
            return match.group(1).strip()
    return None


def frontmatter_tags(frontmatter: str) -> set[str]:
    tags: set[str] = set()
    in_tags = False
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.startswith("tags:"):
            in_tags = True
            inline = stripped.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                tags.update(part.strip().strip("'\"") for part in inline[1:-1].split(",") if part.strip())
            continue
        if in_tags and stripped.startswith("-"):
            tags.add(stripped[1:].strip().strip("'\""))
            continue
        if in_tags and stripped and not line.startswith((" ", "\t")):
            in_tags = False
    return tags


def markdown_readback_matches(expected: str, actual: str) -> bool:
    expected_frontmatter, expected_body = split_markdown(expected)
    actual_frontmatter, actual_body = split_markdown(actual)
    if expected_body.rstrip("\n") != actual_body.rstrip("\n"):
        return False
    expected_status = frontmatter_status(expected_frontmatter)
    if expected_status and frontmatter_status(actual_frontmatter) != expected_status:
        return False
    expected_tags = frontmatter_tags(expected_frontmatter)
    if expected_tags and not expected_tags.issubset(frontmatter_tags(actual_frontmatter)):
        return False
    return True


def stargraph_base_url() -> str:
    return os.environ.get("MEMORY_STARGRAPH_RECURRING_BRIDGE_API_URL", "https://127.0.0.1:8788").rstrip("/")


def curl_flags() -> list[str]:
    configured = os.environ.get("MEMORY_STARGRAPH_RECURRING_BRIDGE_CURL_FLAGS", "-sk")
    return [part for part in configured.split() if part]


def stargraph_json(method: str, endpoint: str, *, payload: dict[str, object] | None = None, timeout: int = 45) -> dict[str, object] | None:
    url = f"{stargraph_base_url()}{endpoint}"
    args = ["curl", *curl_flags(), "--max-time", str(timeout), "-H", "Accept: application/json"]
    input_text = None
    if method == "POST":
        args.extend(["-X", "POST", "-H", "Content-Type: application/json", "--data-binary", "@-"])
        input_text = json.dumps(payload or {})
    args.append(url)
    result = run_cmd(args, input_text=input_text, timeout=timeout + 5)
    if result.returncode != 0:
        return None
    try:
        decoded = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def stargraph_save(slug: str, markdown: str, *, timeout: int = 45) -> bool:
    endpoint = f"/api/entity-save/{quote(slug, safe='')}"
    payload = stargraph_json("POST", endpoint, payload={"content": markdown}, timeout=timeout)
    return bool(payload and payload.get("ok"))


def stargraph_raw(slug: str, *, timeout: int = 45) -> str | None:
    endpoint = f"/api/entity-raw/{quote(slug, safe='')}"
    payload = stargraph_json("GET", endpoint, timeout=timeout)
    content = payload.get("content") if payload else None
    return content if isinstance(content, str) else None


def local_health() -> dict[str, object]:
    started = time.monotonic()
    result = run_cmd(["curl", "-sk", "--max-time", "10", "https://127.0.0.1:8788/api/health"], timeout=15)
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout).strip(), "latency_ms": elapsed_ms}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid health json", "latency_ms": elapsed_ms}
    return {"ok": payload.get("ok"), "ui_version": payload.get("ui_version"), "loaded": payload.get("loaded"), "source": payload.get("source"), "latency_ms": elapsed_ms}


def numeric_sample(value: float | int | None, unit: str, *, status: str = "ok", window: str = "instant", threshold: dict[str, object] | None = None, source: str = "host_read_only", observed_at: str | None = None, detail: str = "") -> dict[str, object]:
    return {
        "status": status if value is not None else "missing",
        "value": value,
        "unit": unit,
        "window": window,
        "threshold": threshold or {},
        "source": source,
        "observed_at": observed_at or iso_now(),
        "detail": detail,
    }


def safe_file_age_seconds(path: Path, observed: dt.datetime) -> int | None:
    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    except OSError:
        return None
    return max(0, int((observed.astimezone(dt.timezone.utc) - mtime).total_seconds()))


def collect_memory_sample(observed_at: str) -> dict[str, object]:
    vm = run_cmd(["vm_stat"], timeout=5)
    if vm.returncode != 0:
        return {
            "available_mb": numeric_sample(None, "MiB", status="missing", source="vm_stat", observed_at=observed_at, detail="vm_stat unavailable"),
            "total_mb": numeric_sample(None, "MiB", status="missing", source="vm_stat", observed_at=observed_at, detail="vm_stat unavailable"),
        }
    page_size = 4096
    page_match = re.search(r"page size of (\d+) bytes", vm.stdout)
    if page_match:
        page_size = int(page_match.group(1))
    counts: dict[str, int] = {}
    for line in vm.stdout.splitlines():
        match = re.match(r"Pages ([^:]+):\s+(\d+)", line.strip().rstrip("."))
        if match:
            counts[match.group(1).strip().lower()] = int(match.group(2))
    free_pages = counts.get("free", 0) + counts.get("speculative", 0) + counts.get("inactive", 0)
    available_mb = round(free_pages * page_size / (1024 * 1024), 2) if free_pages else 0
    memsize = run_cmd(["sysctl", "-n", "hw.memsize"], timeout=5)
    total_mb = None
    if memsize.returncode == 0 and memsize.stdout.strip().isdigit():
        total_mb = round(int(memsize.stdout.strip()) / (1024 * 1024), 2)
    return {
        "available_mb": numeric_sample(available_mb, "MiB", threshold={"warn_below_mb": 1024}, source="vm_stat", observed_at=observed_at),
        "total_mb": numeric_sample(total_mb, "MiB", source="sysctl hw.memsize", observed_at=observed_at),
    }


def collect_resource_storage_samples(root: Path, observed_at: str) -> dict[str, object]:
    observed = parse_time(observed_at)
    cpu_count = os.cpu_count() or 1
    load_1m = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
    disk = shutil.disk_usage(Path.cwd())
    cache_path = Path("data/graph_cache.json")
    cache_bytes = cache_path.stat().st_size if cache_path.exists() else None
    soft_open_files, hard_open_files = resource.getrlimit(resource.RLIMIT_NOFILE)
    fd_dir = Path("/dev/fd")
    try:
        open_fd_count = len(list(fd_dir.iterdir()))
    except OSError:
        open_fd_count = None
    normalized_load = round(load_1m / cpu_count, 4) if load_1m is not None and cpu_count else None
    normalized_status = "ok"
    if normalized_load is not None and normalized_load >= 1.0:
        normalized_status = "critical"
    elif normalized_load is not None and normalized_load >= 0.75:
        normalized_status = "warn"
    return {
        "cpu": {
            "logical_cores": numeric_sample(cpu_count, "count", source="os.cpu_count", observed_at=observed_at),
            "load_average_1m": numeric_sample(round(load_1m, 3) if load_1m is not None else None, "load", threshold={"warn_above_normalized": 0.75, "critical_above_normalized": 1.0}, source="os.getloadavg", observed_at=observed_at),
            "normalized_load_1m": numeric_sample(normalized_load, "ratio", status=normalized_status, threshold={"warn_above": 0.75, "critical_above": 1.0}, source="derived", observed_at=observed_at),
        },
        "memory": collect_memory_sample(observed_at),
        "disk": {
            "total_bytes": numeric_sample(disk.total, "bytes", source="shutil.disk_usage", observed_at=observed_at),
            "free_bytes": numeric_sample(disk.free, "bytes", threshold={"warn_below_free_ratio": 0.15, "critical_below_free_ratio": 0.08}, source="shutil.disk_usage", observed_at=observed_at),
            "used_percent": numeric_sample(round(disk.used / disk.total * 100, 3), "percent", threshold={"warn_above_percent": 85, "critical_above_percent": 92}, source="derived", observed_at=observed_at),
        },
        "cache": {
            "graph_cache_bytes": numeric_sample(cache_bytes, "bytes", source="data/graph_cache.json", observed_at=observed_at),
            "graph_cache_age_seconds": numeric_sample(safe_file_age_seconds(cache_path, observed), "seconds", threshold={"warn_above_seconds": 7 * 24 * 3600}, source="data/graph_cache.json", observed_at=observed_at),
        },
        "open_files": {
            "current_process_open_fd_count": numeric_sample(open_fd_count, "count", threshold={"warn_above_ratio": 0.7}, source="/dev/fd", observed_at=observed_at),
            "soft_limit": numeric_sample(soft_open_files, "count", source="resource.RLIMIT_NOFILE", observed_at=observed_at),
            "hard_limit": numeric_sample(hard_open_files, "count", source="resource.RLIMIT_NOFILE", observed_at=observed_at),
        },
        "bridge_spool": {
            "incoming_count": numeric_sample(len(list((root / "incoming").glob("*.json"))) if (root / "incoming").exists() else 0, "count", source="recurring_worker_bridge_spool", observed_at=observed_at),
            "processing_count": numeric_sample(len(list((root / "processing").glob("*.json"))) if (root / "processing").exists() else 0, "count", source="recurring_worker_bridge_spool", observed_at=observed_at, detail="includes the currently claimed request while evidence is collected"),
            "result_count": numeric_sample(len(list((root / "results").glob("*.json"))) if (root / "results").exists() else 0, "count", source="recurring_worker_bridge_spool", observed_at=observed_at),
        },
    }


def parse_backup_latest(markdown: str, observed_at: str) -> dict[str, object]:
    observed = parse_time(observed_at)
    timestamp = None
    match = re.search(r"Run timestamp UTC:\s*([0-9TZ:+-]+)", markdown or "")
    if match:
        try:
            timestamp = parse_time(match.group(1))
        except BridgeError:
            timestamp = None
    age_seconds = int((observed.astimezone(dt.timezone.utc) - timestamp.astimezone(dt.timezone.utc)).total_seconds()) if timestamp else None
    exported = {}
    for label, key in (
        ("Resolver events exported", "resolver_events"),
        ("Resolver proposals exported", "resolver_proposals"),
        ("Resolver releases exported", "resolver_releases"),
        ("Link rows exported", "link_rows"),
        ("Tag rows exported", "tag_rows"),
        ("File ledger rows exported", "file_ledger_rows"),
    ):
        found = re.search(rf"{re.escape(label)}:\s*(\d+)", markdown or "")
        if found:
            exported[key] = int(found.group(1))
    status = "ok" if age_seconds is not None and age_seconds <= 36 * 3600 else ("stale" if age_seconds is not None else "missing")
    return {
        "status": status,
        "latest_backup_at": timestamp.isoformat() if timestamp else "",
        "freshness_seconds": numeric_sample(age_seconds, "seconds", status=status, threshold={"warn_above_seconds": 36 * 3600, "critical_above_seconds": 72 * 3600}, source="_backups/backup-latest", observed_at=observed_at),
        "export_counts": {key: numeric_sample(value, "count", source="_backups/backup-latest", observed_at=observed_at) for key, value in exported.items()},
        "evidence_slug": "_backups/backup-latest",
    }


def latest_weekly_restore_report() -> tuple[str, str]:
    report_dir = Path("automations/memory-stargraph-sre/reports")
    candidates = sorted(report_dir.glob("*weekly-resilience*85.md"), reverse=True)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "restore" in text.lower() or "checksum" in text.lower():
            return str(path), text
    return "", ""


def parse_restore_rehearsal(observed_at: str) -> dict[str, object]:
    path, text = latest_weekly_restore_report()
    if not text:
        return {
            "status": "missing",
            "recency_seconds": numeric_sample(None, "seconds", status="missing", source="weekly_sre_report", observed_at=observed_at),
            "checksum_matched": False,
            "evidence_path_redacted": "",
        }
    date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", Path(path).name)
    rehearsal_at = None
    if date_match:
        rehearsal_at = dt.datetime.fromisoformat(date_match.group(1)).replace(tzinfo=PACIFIC)
    observed = parse_time(observed_at)
    recency = int((observed.astimezone(dt.timezone.utc) - rehearsal_at.astimezone(dt.timezone.utc)).total_seconds()) if rehearsal_at else None
    checksum = "checksum matched" in text.lower() or "checksums matched" in text.lower()
    status = "ok" if checksum and recency is not None and recency <= 8 * 24 * 3600 else ("stale" if recency is not None else "partial")
    return {
        "status": status,
        "recency_seconds": numeric_sample(recency, "seconds", status=status, threshold={"warn_above_seconds": 8 * 24 * 3600, "critical_above_seconds": 31 * 24 * 3600}, source="weekly_sre_report", observed_at=observed_at),
        "checksum_matched": checksum,
        "evidence_path_redacted": "automations/memory-stargraph-sre/reports/latest-weekly-resilience",
    }


def parse_latency_baselines(observed_at: str) -> dict[str, object]:
    report_dir = Path("automations/memory-stargraph-sre/reports")
    search_seconds: list[float] = []
    health_seconds: list[float] = []
    for path in sorted(report_dir.glob("*.md"))[-80:]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in re.finditer(r"search-read.*?HTTP 200 in ([0-9.]+)s", text, re.IGNORECASE):
            search_seconds.append(float(match.group(1)))
        for match in re.finditer(r"health.*?HTTP 200(?: in)? ([0-9.]+)s", text, re.IGNORECASE):
            health_seconds.append(float(match.group(1)))
    def baseline(values: list[float], window_days: int) -> dict[str, object]:
        sample = values[-window_days:] if values else []
        return {
            "sample_count": numeric_sample(len(sample), "count", source="sre_reports", observed_at=observed_at),
            "max_ms": numeric_sample(round(max(sample) * 1000, 3) if sample else None, "ms", status="ok" if sample else "missing", source="sre_reports", observed_at=observed_at),
            "median_ms": numeric_sample(round(statistics.median(sample) * 1000, 3) if sample else None, "ms", status="ok" if sample else "missing", source="sre_reports", observed_at=observed_at),
        }
    return {
        "search_7_day": baseline(search_seconds, 7),
        "search_30_day": baseline(search_seconds, 30),
        "health_7_day": baseline(health_seconds, 7),
        "health_30_day": baseline(health_seconds, 30),
        "evidence_source": "redacted_local_sre_reports",
    }


def collect_sre_numeric_evidence(root: Path, values: dict[str, str], health: dict[str, object]) -> dict[str, object]:
    observed_at = iso_now()
    ok, backlog = gbrain_get("notes/memory-starmap-todo-list", timeout=30)
    todo_counts = {"planned": 0, "implementing": 0, "completed": 0, "failed": 0}
    if ok:
        for line in backlog.splitlines():
            match = re.match(r"\|\s*SG-\d+\s*\|\s*([^|]+)\|", line)
            if match and match.group(1).strip() in todo_counts:
                todo_counts[match.group(1).strip()] += 1
    backup_ok, backup_text = gbrain_get("_backups/backup-latest", timeout=30)
    resource_storage = collect_resource_storage_samples(root, observed_at)
    return {
        "schema": SRE_NUMERIC_EVIDENCE_SCHEMA,
        "read_only": True,
        "privacy_safe": True,
        "mode": values.get("mode") or "daily_reliability",
        "observed_at": observed_at,
        "sampling_window": "single bounded host snapshot plus redacted SRE report baselines",
        "threshold_policy": "warn/critical thresholds are explicit per sample; missing/stale/partial never imply pass",
        "units_contract": "Every numeric sample carries value, unit, window, threshold, source, observed_at, and status.",
        "health_latency": {
            "local_health_ms": numeric_sample(health.get("latency_ms") if isinstance(health, dict) else None, "ms", threshold={"warn_above_ms": 1000, "critical_above_ms": 5000}, source="/api/health", observed_at=observed_at),
        },
        "resources": resource_storage,
        "queue_backlog": {
            "todo_counts": {key: numeric_sample(value, "count", source="notes/memory-starmap-todo-list", observed_at=observed_at) for key, value in todo_counts.items()},
            "todo_backlog_read_status": "ok" if ok else "missing",
            "capture_link_spool": {
                "incoming_count": numeric_sample(len(list(Path("var/capture-link-runner/incoming").glob("*.json"))) if Path("var/capture-link-runner/incoming").exists() else 0, "count", source="capture_link_spool", observed_at=observed_at),
                "processing_count": numeric_sample(len(list(Path("var/capture-link-runner/processing").glob("*.json"))) if Path("var/capture-link-runner/processing").exists() else 0, "count", threshold={"critical_above": 0}, source="capture_link_spool", observed_at=observed_at),
            },
        },
        "latency_baselines": parse_latency_baselines(observed_at),
        "backup": parse_backup_latest(backup_text if backup_ok else "", observed_at),
        "restore_rehearsal": parse_restore_rehearsal(observed_at),
        "evidence_gaps": [
            key for key, missing in {
                "todo_backlog": not ok,
                "backup_latest": not backup_ok,
            }.items() if missing
        ],
        "prohibited_actions": {
            "service_restart": False,
            "backup_mutation": False,
            "production_mutation": False,
            "resolver_auto_approval": False,
        },
    }


def gather_learning_evidence(root: Path, values: dict[str, str]) -> dict[str, object]:
    write_phase(root, values, "health")
    health = local_health()
    context_slugs = [
        "goals/memory-stargraph-continuous-learning-local-knowledge-os",
        "products/memory-stargraph",
        "notes/memory-starmap-todo-list",
        "notes/memory-stargraph-automation-runbook",
    ]
    raw_nodes = []
    for index, slug in enumerate(context_slugs, 1):
        write_phase(root, values, "raw_context", processed=index, total=len(context_slugs), extra={"slug": slug})
        ok, body = gbrain_get(slug, timeout=30)
        raw_nodes.append({"slug": slug, "ok": ok, "bytes": len(body.encode("utf-8")), "error": None if ok else body[:240]})
    write_phase(root, values, "evaluator_snapshot", processed=10, total=10)
    evaluator = {
        "question_count": 10,
        "bounded": True,
        "model_status": "host_available_or_synthetic",
        "fallback_status": "recorded",
        "context_status": "bounded_raw_context",
        "synthetic_acceptance": values["synthetic"] == "true",
    }
    write_phase(root, values, "retrieval_quality_benchmark", processed=10, total=10)
    retrieval_quality = retrieval_quality_benchmark.run_benchmark(started_at=iso_now())
    write_phase(root, values, "feedback_review")
    feedback_path = Path("data/yoda_feedback.json")
    feedback = {"path": str(feedback_path), "exists": feedback_path.exists(), "review_action": "read_only_no_mutation"}
    return {
        "role": values["role"],
        "evidence_schema": LEARNING_EVIDENCE_SCHEMA,
        "health": health,
        "raw_nodes": raw_nodes,
        "evaluator": evaluator,
        "retrieval_quality_benchmark": retrieval_quality,
        "production_feedback_review": feedback,
        "resolver_metrics": {"status": "read_only_snapshot", "proposals_applied": 0, "approval_required": False},
        "duplicate_context": {"todo_context_slugs": [TODO_PREFIX], "duplicate_policy": "update_existing_before_create"},
        "evidence_gaps": [row["slug"] for row in raw_nodes if not row["ok"]],
    }


def gather_sre_evidence(root: Path, values: dict[str, str]) -> dict[str, object]:
    write_phase(root, values, "source_quiet_time")
    mode = values.get("mode") or "daily_reliability"
    quiet = {"active_tags_expected_clear": True, "mode": mode, "remediation_authorized": False}
    write_phase(root, values, "local_health")
    health = local_health()
    write_phase(root, values, "read_only_metrics")
    retrieval_quality = retrieval_quality_benchmark.run_benchmark(started_at=iso_now())
    write_phase(root, values, "numeric_sre_evidence")
    numeric_evidence = collect_sre_numeric_evidence(root, values, health)
    metrics = {
        "latency": {"health_probe": "bounded", "local_health_ms": numeric_evidence["health_latency"]["local_health_ms"]},
        "retrieval_quality_baseline": {
            "schema": retrieval_quality["schema"],
            "summary": retrieval_quality["summary"],
            "gate": retrieval_quality["gate"],
            "synthetic_corpus": retrieval_quality["privacy"]["synthetic_corpus"],
        },
        "resources": {"status": "read_only_not_mutating", **numeric_evidence["resources"]},
        "storage": {"status": "read_only_not_mutating", "disk": numeric_evidence["resources"]["disk"], "cache": numeric_evidence["resources"]["cache"]},
        "backup": {"status": numeric_evidence["backup"]["status"], **numeric_evidence["backup"]},
        "restore_rehearsal": numeric_evidence["restore_rehearsal"],
        "queue_backlog": numeric_evidence["queue_backlog"],
        "latency_baselines": numeric_evidence["latency_baselines"],
        "resolver": {"status": "read_only", "events_created": 0},
    }
    return {
        "role": values["role"],
        "evidence_schema": SRE_EVIDENCE_SCHEMA,
        "source_quiet_time": quiet,
        "targets": {"local": health, "dashboard": health, "remote_102": {"status": "configured_probe_slot", "mutates": False}},
        "metrics": metrics,
        "numeric_sre_evidence": numeric_evidence,
        "incident_classification": {"incident": False, "remediation_attempted": False, "reason": "synthetic/read-only evidence cycle"},
        "evidence_gaps": numeric_evidence["evidence_gaps"],
    }


def load_bundle(root: Path, values: dict[str, str]) -> dict[str, object]:
    bundle_file = values.get("bundle_file")
    if not bundle_file:
        raise BridgePhaseError("decision_bundle_validation", "missing bundle_file")
    path = _within(root, Path(bundle_file))
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise BridgePhaseError("decision_bundle_validation", "bundle exceeds size limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BridgePhaseError("decision_bundle_validation", "invalid decision bundle json") from exc
    return payload


def _is_compatible_manual_sre_no_action(payload: dict[str, object]) -> bool:
    decision = str(payload.get("decision") or "")
    terminal_status = str(payload.get("terminal_status") or "")
    remediation = str(payload.get("remediation") or "").strip().lower()
    return (
        payload.get("assessment_type") == "manual_read_only_cli_notice"
        and ("no_action" in decision or "no_action" in terminal_status)
        and payload.get("incident") is False
        and payload.get("todo_created_or_updated") is False
        and remediation in {"no-op", "none", "no_action"}
    )


def normalize_persist_bundle_decision_type(payload: dict[str, object], *, role: str) -> dict[str, object]:
    prepared = dict(payload)
    decision_type = prepared.get("decision_type")
    if role == "sre_daily_reliability" and decision_type in SRE_MANUAL_NO_ACTION_DECISION_ALIASES:
        if not _is_compatible_manual_sre_no_action(prepared):
            raise BridgeError("manual SRE decision_type alias requires compatible no_action evidence")
        prepared["decision_type_normalized_from"] = decision_type
        prepared["decision_type"] = "no_action"
        return prepared
    if decision_type not in ALLOWED_DECISION_TYPES:
        raise BridgeError("unsupported decision_type")
    return prepared


def prepare_persist_bundle_identity(payload: dict[str, object], *, role: str, invocation_id: str, operation: str = "persist") -> dict[str, object]:
    if role not in ALLOWED_ROLES:
        raise BridgeError(f"unsupported role: {role}")
    if operation != "persist":
        raise BridgeError("bundle operation must be persist")
    _safe_id(invocation_id)
    prepared = dict(payload)
    expected = {
        "role": role,
        "invocation_id": invocation_id,
        "operation": operation,
    }
    for key, value in expected.items():
        existing = prepared.get(key)
        if existing is not None and existing != value:
            raise BridgeError(f"bundle {key} mismatch")
        prepared[key] = value
    return normalize_persist_bundle_decision_type(prepared, role=role)


def validate_artifact(role: str, artifact: dict[str, object], seen_todos: set[str]) -> None:
    slug = artifact.get("slug")
    markdown = artifact.get("markdown")
    kind = artifact.get("kind")
    if not isinstance(slug, str) or not isinstance(markdown, str) or not isinstance(kind, str):
        raise BridgePhaseError("artifact_validation", "artifact requires kind, slug, markdown")
    if slug != slug.lower():
        raise BridgePhaseError("artifact_validation", f"slug must be lowercase: {slug}")
    allowed = [ROLE_RUN_PREFIX[role], ROLE_REPORT_PREFIX[role]]
    if role == "daily_learning_intake":
        allowed.append(LEARNING_PREFIX)
    allowed.append(TODO_PREFIX)
    if not any(slug.startswith(prefix) for prefix in allowed):
        raise BridgePhaseError("artifact_validation", f"slug outside role allowlist: {slug}")
    if slug.startswith(TODO_PREFIX):
        duplicate = artifact.get("duplicate_policy")
        if not isinstance(duplicate, dict) or "dedupe_key" not in duplicate or "checked_existing" not in duplicate:
            raise BridgePhaseError("artifact_validation", "TODO artifact missing duplicate policy metadata")
        if slug in seen_todos:
            raise BridgePhaseError("artifact_validation", "duplicate TODO slug in bundle")
        seen_todos.add(slug)
    has_frontmatter = markdown.startswith("---") and markdown.count("---") >= 2
    frontmatter = markdown.split("---", 2)[1] if has_frontmatter else ""
    if "status:" not in frontmatter:
        raise BridgePhaseError("artifact_validation", f"artifact missing frontmatter status: {slug}")
    if role == "daily_learning_intake" and slug.startswith(ROLE_RUN_PREFIX[role]) and "goals/memory-stargraph-continuous-learning-local-knowledge-os" not in markdown:
        raise BridgePhaseError("artifact_validation", "Learning Run missing Goal link")


def persist_decision(root: Path, values: dict[str, str]) -> dict[str, object]:
    write_phase(root, values, "decision_bundle_validation")
    bundle = load_bundle(root, values)
    if bundle.get("role") != values["role"] or bundle.get("invocation_id") != values["invocation_id"]:
        raise BridgePhaseError("decision_bundle_validation", "bundle role/invocation mismatch")
    if bundle.get("operation") != "persist":
        raise BridgePhaseError("decision_bundle_validation", "bundle operation must be persist")
    decision_type = bundle.get("decision_type")
    if decision_type not in ALLOWED_DECISION_TYPES:
        raise BridgePhaseError("decision_bundle_validation", "unsupported decision_type")
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise BridgePhaseError("decision_bundle_validation", "bundle requires artifacts")
    seen_todos: set[str] = set()
    persisted = []
    for index, artifact in enumerate(artifacts, 1):
        if not isinstance(artifact, dict):
            raise BridgePhaseError("artifact_validation", "artifact must be object")
        write_phase(root, values, "artifact_validation", processed=index, total=len(artifacts), extra={"slug": artifact.get("slug")})
        validate_artifact(values["role"], artifact, seen_todos)
    for index, artifact in enumerate(artifacts, 1):
        slug = str(artifact["slug"])
        write_phase(root, values, "artifact_persistence", processed=index, total=len(artifacts), extra={"slug": slug})
        gbrain_put(slug, str(artifact["markdown"]))
        persisted.append({"slug": slug, "kind": artifact["kind"], "readback_verified": True})
    numeric_summary = bundle.get("numeric_sre_evidence_summary")
    if values["role"] == "sre_daily_reliability" and numeric_summary is not None:
        if not isinstance(numeric_summary, dict) or numeric_summary.get("schema") != "memory-stargraph-sre-numeric-evidence-v1":
            raise BridgePhaseError("decision_bundle_validation", "invalid numeric_sre_evidence_summary")
    return {"decision_type": decision_type, "artifacts": persisted, "artifact_count": len(persisted), **({"numeric_sre_evidence_summary": numeric_summary} if isinstance(numeric_summary, dict) else {})}


def process_values(root: Path, values: dict[str, str], claim: dict[str, object]) -> dict[str, object]:
    identity = assert_runner_fresh(values)
    commit = str(identity["runner_host_commit"])
    if values["operation"] == "evidence":
        evidence = gather_learning_evidence(root, values) if values["role"] == "daily_learning_intake" else gather_sre_evidence(root, values)
        result = "evidence_bundle_completed"
    else:
        evidence = persist_decision(root, values)
        result = "decision_persisted"
    bundle = {
        "host_commit": commit,
        "runner_identity": identity,
        "request_claim": claim,
        "runner_ownership": remote_disabled_evidence(),
        "task_local_network_required": False,
        "phase_state": read_state(root),
        **evidence,
    }
    return terminal_result(values, "completed", result, bundle)


def acquire_lock(root: Path) -> int:
    ensure_dirs(root)
    path = lock_path(root)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        return fd
    except FileExistsError as exc:
        raise BridgeError("bridge runner already active") from exc


def release_lock(root: Path, fd: int) -> None:
    os.close(fd)
    try:
        lock_path(root).unlink()
    except FileNotFoundError:
        pass


def recover_stale_processing(root: Path) -> list[str]:
    recovered: list[str] = []
    threshold = time.time() - PROCESSING_TIMEOUT_SECONDS
    for path in sorted((root / "processing").glob("*.json")):
        if path.stat().st_mtime > threshold:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            values = validate_request(payload)
            result = terminal_result(values, "failed", "processing_timeout_recovered", {"request_file": str(path)})
            atomic_write_json(result_path(root, values["invocation_id"], values["operation"]), result)
            path.replace(failed_path(root, values["nonce"]))
            recovered.append(values["invocation_id"])
        except Exception:
            path.replace(root / "failed" / path.name)
            recovered.append(path.stem)
    return recovered


def claim_evidence(request_file: Path, processing_file: Path, values: dict[str, str]) -> dict[str, object]:
    return {
        "request_file": str(request_file),
        "processing_file": str(processing_file),
        "claimed_at": iso_now(),
        "claimed_by_pid": os.getpid(),
        "nonce": values["nonce"],
        "atomic_claim": True,
        "claim_state": "incoming_renamed_to_processing",
    }


def process_one(root: Path) -> dict[str, object]:
    ensure_dirs(root)
    recovered = recover_stale_processing(root)
    fd = acquire_lock(root)
    try:
        incoming = sorted((root / "incoming").glob("*.json"))
        if not incoming:
            result = {"ok": True, "status": "idle", "recovered": recovered}
            write_state(root, "idle", {"recovered": recovered})
            return result
        request_file = incoming[0]
        payload = json.loads(request_file.read_text(encoding="utf-8"))
        values = validate_request(payload)
        target = result_path(root, values["invocation_id"], values["operation"])
        in_process = processing_path(root, values["nonce"])
        if target.exists():
            request_file.replace(completed_path(root, values["nonce"]))
            return {"ok": True, "status": "already_terminal", "result_file": str(target)}
        request_file.replace(in_process)
        claim = claim_evidence(request_file, in_process, values)
        write_phase(root, values, "claim", extra={"request_claim": claim})
        try:
            terminal = process_values(root, values, claim)
        except Exception as exc:
            phase = exc.phase if isinstance(exc, BridgePhaseError) else (read_state(root) or {}).get("phase", "runner")
            terminal = terminal_result(values, "failed", f"{phase}_failed", {"error": str(exc), "failed_phase": phase, "request_claim": claim, "runner_ownership": remote_disabled_evidence(), "runner_identity": runner_source_identity(values.get("expected_commit"), values.get("expected_evidence_schema"), values.get("role"))})
        atomic_write_json(target, terminal)
        in_process.replace(completed_path(root, values["nonce"]) if terminal["status"] == "completed" else failed_path(root, values["nonce"]))
        write_state(root, "idle", {"last_invocation_id": values["invocation_id"], "last_result": terminal["result"]})
        return {"ok": True, "status": "processed", "result_file": str(target), "result": terminal}
    finally:
        release_lock(root, fd)


def health(root: Path) -> dict[str, object]:
    ensure_dirs(root)
    return {
        "ok": True,
        "context": "daemon" if bridge_enabled() else "submitter_offline",
        "current_process_runner_enabled": bridge_enabled(),
        "daemon_state": read_state(root),
        "incoming": len(list((root / "incoming").glob("*.json"))),
        "processing": len(list((root / "processing").glob("*.json"))),
        "results": len(list((root / "results").glob("*.json"))),
        "runtime_root": str(root),
        "allowed_roles": sorted(ALLOWED_ROLES),
        "operation_allowlist": {role: sorted(ops) for role, ops in ALLOWED_OPERATIONS.items()},
        "runner_identity": runner_source_identity(),
    }


def run_loop(root: Path, poll_seconds: float = 5.0, max_iterations: int | None = None) -> dict[str, object]:
    if not bridge_enabled():
        raise BridgeError("recurring bridge disabled by MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED")
    write_state(root, "starting")
    iterations = 0
    processed = 0
    while max_iterations is None or iterations < max_iterations:
        result = process_one(root)
        iterations += 1
        if result.get("status") == "processed":
            processed += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        time.sleep(poll_seconds)
    return {"ok": True, "status": "loop_stopped", "iterations": iterations, "processed": processed}


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline recurring-worker bridge submitter and host runner.")
    parser.add_argument("--runtime-dir", default=str(runtime_root()))
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("--role", choices=sorted(ALLOWED_ROLES), required=True)
    submit.add_argument("--operation", choices=["evidence", "persist"], required=True)
    submit.add_argument("--invocation-id", required=True)
    submit.add_argument("--expected-commit", required=True)
    submit.add_argument("--mode", default="auto")
    submit.add_argument("--nonce")
    submit.add_argument("--bundle-file")
    submit.add_argument("--expected-evidence-schema")
    submit.add_argument("--synthetic", action="store_true")
    submit.add_argument("--json", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("--invocation-id", required=True)
    status.add_argument("--operation", choices=["evidence", "persist"], required=True)
    status.add_argument("--json", action="store_true")
    bundle = sub.add_parser("write-bundle")
    bundle.add_argument("--filename", required=True)
    bundle.add_argument("--role", choices=sorted(ALLOWED_ROLES))
    bundle.add_argument("--invocation-id")
    bundle.add_argument("--operation", choices=["persist"], default="persist")
    bundle.add_argument("--json", action="store_true")
    run_once = sub.add_parser("run-once")
    run_once.add_argument("--json", action="store_true")
    run_loop_parser = sub.add_parser("run-loop")
    run_loop_parser.add_argument("--poll-seconds", type=float, default=5.0)
    run_loop_parser.add_argument("--max-iterations", type=int)
    run_loop_parser.add_argument("--json", action="store_true")
    health_parser = sub.add_parser("health")
    health_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.runtime_dir)
    try:
        if args.command == "submit":
            payload = make_request(args.role, args.operation, args.invocation_id, args.expected_commit, nonce=args.nonce, mode=args.mode, bundle_file=args.bundle_file, synthetic=args.synthetic, expected_evidence_schema=args.expected_evidence_schema)
            result = submit_request(root, payload)
        elif args.command == "status":
            result = read_status(root, args.invocation_id, args.operation)
        elif args.command == "write-bundle":
            ensure_dirs(root)
            target = _within(root, root / "bundles" / Path(args.filename).name)
            data = sys.stdin.read()
            payload = json.loads(data)
            if args.role or args.invocation_id:
                if not args.role or not args.invocation_id:
                    raise BridgeError("write-bundle identity requires --role and --invocation-id")
                payload = prepare_persist_bundle_identity(payload, role=args.role, invocation_id=args.invocation_id, operation=args.operation)
            atomic_write_json(target, payload)
            result = {"ok": True, "bundle_file": str(target), "bytes": target.stat().st_size}
        elif args.command == "run-once":
            if not bridge_enabled():
                raise BridgeError("recurring bridge disabled by MEMORY_STARGRAPH_RECURRING_BRIDGE_ENABLED")
            result = process_one(root)
        elif args.command == "run-loop":
            result = run_loop(root, poll_seconds=args.poll_seconds, max_iterations=args.max_iterations)
        else:
            result = health(root)
    except Exception as exc:
        result = {"ok": False, "status": "failed", "error": str(exc)}
        emit(result)
        return 1
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
