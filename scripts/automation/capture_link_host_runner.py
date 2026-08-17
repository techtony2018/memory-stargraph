#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.automation import manage_capture_backlog as capture
from scripts.automation.worker_persistence import _raw_readback_matches


PACIFIC = ZoneInfo("America/Los_Angeles")
SCHEMA_VERSION = 1
OPERATION = "capture_link_drain"
AUTOMATION_ID = "memory-stargraph-capture-link-drain"
MAX_REQUEST_BYTES = 8192
MAX_AGE_SECONDS = 6 * 60 * 60
PROCESSING_TIMEOUT_SECONDS = 45 * 60
STALE_LOCK_SECONDS = 60
MAX_LOG_BYTES = 512 * 1024
DEFAULT_MODE = "auto"
ALLOWED_MODES = {"auto", "capture_drain", "empty_queue_enrichment"}
ENRICHMENT_SELECTION_VERSION = "empty-queue-enrichment-v1"
MAX_ENRICHMENT_CANDIDATES = 500
MAX_ENRICHMENT_ATTEMPTS = 2
MAX_ENRICHMENT_INSPECTIONS = 20
MAX_ENRICHMENT_EVIDENCE_ITEMS = 20
ENRICHMENT_ENTITY_READ_TIMEOUT = 15
CURATOR_POLL_MAX_SECONDS = 10 * 60
RUNNER_HEARTBEAT_STALE_SECONDS = 2 * 60
MAX_CAPTURE_FETCH_BYTES = 180_000
MAX_CAPTURE_TEXT_CHARS = 6_000
MAX_CAPTURE_INSTRUCTION_CHARS = 2_000
MAX_CAPTURE_FETCH_SECONDS = 30
TERMINAL_LIFECYCLE_TAGS = ("active", "implementing")
TERMINAL_LIFECYCLE_READBACK_ATTEMPTS = 5
TERMINAL_LIFECYCLE_READBACK_DELAY_SECONDS = 1
GLOBAL_ACTIVE_TAG_READBACK_SOURCE = "gbrain list --tag active"


class RunnerError(RuntimeError):
    pass


class RunnerPhaseError(RunnerError):
    def __init__(self, phase: str, message: str):
        super().__init__(message)
        self.phase = phase


def pacific_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(PACIFIC).replace(microsecond=0)


def iso_now() -> str:
    return pacific_now().isoformat()


RUNNER_STARTED_AT = iso_now()
RUNNER_INSTANCE_ID = os.environ.get("MEMORY_STARGRAPH_CAPTURE_RUNNER_INSTANCE_ID", uuid.uuid4().hex)


def runtime_root() -> Path:
    configured = os.environ.get("MEMORY_STARGRAPH_CAPTURE_RUNNER_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path("var") / "capture-link-runner"


def _safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", value):
        raise RunnerError(f"unsafe identifier: {value!r}")
    return value


def _safe_nonce(value: str | None = None) -> str:
    nonce = value or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,127}", nonce):
        raise RunnerError("nonce must be 8-128 safe filename characters")
    return nonce


def _within(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise RunnerError(f"path escapes runtime root: {path}")
    return resolved


def ensure_dirs(root: Path) -> None:
    for name in ("incoming", "processing", "results", "completed", "failed", "locks", "logs"):
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except PermissionError:
            pass


def result_path(root: Path, invocation_id: str) -> Path:
    return _within(root, root / "results" / f"{_safe_id(invocation_id)}.json")


def incoming_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "incoming" / f"{_safe_nonce(nonce)}.json")


def processing_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "processing" / f"{_safe_nonce(nonce)}.json")


def completed_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "completed" / f"{_safe_nonce(nonce)}.json")


def failed_path(root: Path, nonce: str) -> Path:
    return _within(root, root / "failed" / f"{_safe_nonce(nonce)}.json")


def lock_path(root: Path) -> Path:
    return _within(root, root / "locks" / "capture_link_drain.lock")


def log_path(root: Path) -> Path:
    return _within(root, root / "logs" / "runner.jsonl")


def state_path(root: Path) -> Path:
    return _within(root, root / "runner-state.json")


def parse_time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunnerError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise RunnerError("timestamp must be timezone-aware")
    return parsed


def current_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerPhaseError("source_validation", f"git rev-parse failed: {exc}") from exc
    if result.returncode != 0:
        raise RunnerError((result.stderr or result.stdout).strip() or "git rev-parse failed")
    return result.stdout.strip()


def run_gbrain(args: list[str], input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gbrain", *args],
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["gbrain", *args], 124, "", str(exc))


def result_error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout).strip()


def put_entity(slug: str, markdown: str) -> None:
    result = run_gbrain(["put", slug], input_text=markdown, timeout=180)
    if result.returncode != 0:
        raise RunnerError(f"gbrain put failed for {slug}: {result_error(result)}")
    readback = run_gbrain(["get", slug], timeout=120)
    if readback.returncode != 0:
        raise RunnerError(f"gbrain get failed for {slug}: {result_error(readback)}")
    if not _raw_readback_matches(markdown, readback.stdout):
        raise RunnerError(f"gbrain readback mismatch for {slug}")


def mutate_tag(slug: str, tag: str, action: str) -> None:
    command = "tag" if action == "add" else "untag"
    result = run_gbrain([command, slug, tag], timeout=60)
    if result.returncode != 0 and not (action == "remove" and "not found" in result_error(result).lower()):
        raise RunnerError(f"gbrain {command} failed for {slug}: {result_error(result)}")


def read_tags(slug: str) -> list[str]:
    result = run_gbrain(["tags", slug], timeout=60)
    if result.returncode != 0:
        raise RunnerError(f"gbrain tags failed for {slug}: {result_error(result)}")
    tags: list[str] = []
    for line in result.stdout.splitlines():
        cleaned = line.strip().lstrip("-").strip()
        for item in cleaned.split(","):
            tag = item.strip()
            if tag:
                tags.append(tag)
    return tags


def list_active_tag_pages() -> list[dict[str, str]]:
    result = run_gbrain(["list", "--tag", "active"], timeout=60)
    if result.returncode != 0:
        raise RunnerError(f"gbrain active tag list failed: {result_error(result)}")
    pages: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "No pages found.":
            continue
        parts = stripped.split("\t")
        pages.append(
            {
                "slug": parts[0],
                "type": parts[1] if len(parts) > 1 else "",
                "updated": parts[2] if len(parts) > 2 else "",
                "title": parts[3] if len(parts) > 3 else parts[0],
            }
        )
    return pages


def global_active_tag_readback() -> dict[str, object]:
    last: dict[str, object] = {}
    for attempt in range(1, TERMINAL_LIFECYCLE_READBACK_ATTEMPTS + 1):
        readback_at = iso_now()
        pages = list_active_tag_pages()
        last = {
            "source": GLOBAL_ACTIVE_TAG_READBACK_SOURCE,
            "readback_at": readback_at,
            "attempt": attempt,
            "active_tag_count": len(pages),
            "active_tag_pages": pages,
            "active_tags_clear": len(pages) == 0,
        }
        if not pages:
            return last
        if attempt < TERMINAL_LIFECYCLE_READBACK_ATTEMPTS:
            time.sleep(TERMINAL_LIFECYCLE_READBACK_DELAY_SECONDS)
    raise RunnerError(f"global active tag readback not clear: {last}")


def terminal_lifecycle_tag_evidence(
    slug: str,
    *,
    expected_status: str,
    expected_result: str,
    expect_curator_lease: bool = True,
) -> dict[str, object]:
    last: dict[str, object] = {}
    for attempt in range(1, TERMINAL_LIFECYCLE_READBACK_ATTEMPTS + 1):
        tags = read_tags(slug)
        markdown = get_entity(slug)
        frontmatter = {
            "status": frontmatter_value(markdown, "status"),
            "result": frontmatter_value(markdown, "result"),
            "active_change": frontmatter_value(markdown, "active_change"),
        }
        if expect_curator_lease:
            frontmatter["curator_lease"] = frontmatter_value(markdown, "curator_lease")
        stale_tags = [tag for tag in TERMINAL_LIFECYCLE_TAGS if tag in tags]
        lease_ok = True
        if frontmatter.get("active_change") not in {False, "false", "False", None}:
            lease_ok = False
        if expect_curator_lease and frontmatter.get("curator_lease") not in {False, "false", "False"}:
            lease_ok = False
        status_ok = str(frontmatter.get("status") or "") == expected_status
        result_ok = str(frontmatter.get("result") or "") == expected_result
        last = {
            "slug": slug,
            "attempt": attempt,
            "tags": tags,
            "stale_lifecycle_tags": stale_tags,
            "frontmatter": frontmatter,
            "terminal_status_verified": status_ok,
            "terminal_result_verified": result_ok,
            "terminal_lease_fields_verified": lease_ok,
        }
        if not stale_tags and status_ok and result_ok and lease_ok:
            return last
        if attempt < TERMINAL_LIFECYCLE_READBACK_ATTEMPTS:
            time.sleep(TERMINAL_LIFECYCLE_READBACK_DELAY_SECONDS)
    raise RunnerError(f"terminal lifecycle readback failed for {slug}: {last}")


def clear_terminal_lifecycle_tags(slugs: list[tuple[str, bool]], status: str, result: str) -> dict[str, object]:
    evidence: dict[str, object] = {"removed_tags": list(TERMINAL_LIFECYCLE_TAGS), "entities": {}}
    for slug, expect_curator_lease in slugs:
        for tag in TERMINAL_LIFECYCLE_TAGS:
            mutate_tag(slug, tag, "remove")
        evidence["entities"][slug] = terminal_lifecycle_tag_evidence(
            slug,
            expected_status=status,
            expected_result=result,
            expect_curator_lease=expect_curator_lease,
        )
    evidence["global_active_tag_readback"] = global_active_tag_readback()
    evidence["lifecycle_tags_released"] = True
    return evidence


def get_entity(slug: str, timeout: int = 120) -> str:
    result = run_gbrain(["get", slug], timeout=timeout)
    if result.returncode != 0:
        raise RunnerError(f"gbrain get failed for {slug}: {result_error(result)}")
    return result.stdout


def list_entities(entity_type: str, limit: int = MAX_ENRICHMENT_CANDIDATES) -> list[dict[str, str]]:
    result = run_gbrain(["list", "--type", entity_type, "-n", str(limit)], timeout=30)
    if result.returncode != 0:
        raise RunnerError(f"gbrain list failed for type {entity_type}: {result_error(result)}")
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append({"slug": parts[0], "type": parts[1], "updated": parts[2], "title": parts[3]})
        elif parts and parts[0].strip():
            rows.append({"slug": parts[0].strip(), "type": entity_type, "updated": "", "title": parts[0].strip()})
    return sorted(rows, key=lambda item: item["slug"])


def lifecycle_slugs(values: dict[str, str]) -> tuple[str, str]:
    date = pacific_now().strftime("%Y-%m-%d")
    suffix = _safe_id(values["invocation_id"])
    return (
        f"runs/memory-stargraph-capture-link-drain-{suffix}",
        f"reports/memory-stargraph-capture-link-drain-{date}-{suffix}",
    )


def markdown_list(items: list[str]) -> str:
    return "\n".join(f"  - {item}" for item in items) if items else "  []"


def build_run_markdown(
    values: dict[str, str],
    run_slug: str,
    report_slug: str,
    *,
    status: str,
    result: str,
    evidence: dict[str, object] | None = None,
) -> str:
    active = status == "running"
    tags = ["capture-link", "curator", "host-runner"]
    if active:
        tags.append("active")
    else:
        tags.append(status)
    evidence_block = json.dumps(evidence or {}, ensure_ascii=False, indent=2, sort_keys=True)
    return f"""---
type: run
title: Capture Link host drain {values["invocation_id"]}
status: {status}
result: {result}
automation_id: {AUTOMATION_ID}
invocation_id: {values["invocation_id"]}
operation: {OPERATION}
expected_commit: {values["expected_commit"]}
curator_lease: {str(active).lower()}
active_change: false
started_at: '{values["created_at"]}'
completed_at: '{iso_now() if not active else ""}'
report_slug: {report_slug}
tags:
{markdown_list(tags)}
---

# Capture Link host drain {values["invocation_id"]}

Report: [[{report_slug}]]

## Evidence

```json
{evidence_block}
```
"""


def build_report_markdown(
    values: dict[str, str],
    run_slug: str,
    report_slug: str,
    *,
    status: str,
    result: str,
    evidence: dict[str, object],
) -> str:
    evidence_block = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)
    return f"""---
type: report
title: Capture Link host runner report {values["invocation_id"]}
status: {status}
result: {result}
automation_id: {AUTOMATION_ID}
invocation_id: {values["invocation_id"]}
operation: {OPERATION}
run_slug: {run_slug}
created_at: '{iso_now()}'
tags:
- capture-link
- curator
- host-runner
- {status}
---

# Capture Link host runner report {values["invocation_id"]}

Run: [[{run_slug}]]

## Evidence

```json
{evidence_block}
```
"""


def create_active_lifecycle(values: dict[str, str]) -> tuple[str, str]:
    run_slug, report_slug = lifecycle_slugs(values)
    put_entity(
        run_slug,
        build_run_markdown(
            values,
            run_slug,
            report_slug,
            status="running",
            result="active",
            evidence={"request": values, "runner": "host-managed-spool"},
        ),
    )
    mutate_tag(run_slug, "active", "add")
    return run_slug, report_slug


def update_active_lifecycle(values: dict[str, str], run_slug: str, report_slug: str, evidence: dict[str, object]) -> None:
    put_entity(
        run_slug,
        build_run_markdown(values, run_slug, report_slug, status="running", result="active", evidence=evidence),
    )


def terminalize_lifecycle(
    values: dict[str, str],
    run_slug: str,
    report_slug: str,
    status: str,
    result: str,
    evidence: dict[str, object],
) -> dict[str, object]:
    lifecycle = {
        **evidence,
        "run_slug": run_slug,
        "report_slug": report_slug,
    }
    put_entity(
        run_slug,
        build_run_markdown(values, run_slug, report_slug, status=status, result=result, evidence=lifecycle),
    )
    put_entity(
        report_slug,
        build_report_markdown(values, run_slug, report_slug, status=status, result=result, evidence=lifecycle),
    )
    lifecycle_readback = clear_terminal_lifecycle_tags(
        [(run_slug, True), (report_slug, False)],
        status,
        result,
    )
    final_lifecycle = {
        **lifecycle,
        **lifecycle_readback,
    }
    put_entity(
        run_slug,
        build_run_markdown(values, run_slug, report_slug, status=status, result=result, evidence=final_lifecycle),
    )
    put_entity(
        report_slug,
        build_report_markdown(values, run_slug, report_slug, status=status, result=result, evidence=final_lifecycle),
    )
    final_readback = clear_terminal_lifecycle_tags(
        [(run_slug, True), (report_slug, False)],
        status,
        result,
    )
    return {
        **final_lifecycle,
        "final_terminal_readback": final_readback,
        "global_active_tag_readback": final_readback["global_active_tag_readback"],
    }


def make_request(invocation_id: str, expected_commit: str, mode: str, nonce: str | None = None) -> dict[str, object]:
    if mode not in ALLOWED_MODES:
        raise RunnerError(f"unsupported mode: {mode}")
    return {
        "version": SCHEMA_VERSION,
        "operation": OPERATION,
        "invocation_id": _safe_id(invocation_id),
        "automation_id": AUTOMATION_ID,
        "expected_commit": expected_commit,
        "mode": mode,
        "created_at": iso_now(),
        "nonce": _safe_nonce(nonce),
    }


def validate_request(payload: dict[str, object], *, now: dt.datetime | None = None) -> dict[str, str]:
    values = {
        "version": payload.get("version"),
        "operation": payload.get("operation"),
        "invocation_id": payload.get("invocation_id"),
        "automation_id": payload.get("automation_id"),
        "expected_commit": payload.get("expected_commit"),
        "mode": payload.get("mode", DEFAULT_MODE),
        "created_at": payload.get("created_at"),
        "nonce": payload.get("nonce"),
    }
    if values["version"] != SCHEMA_VERSION:
        raise RunnerError("unsupported request version")
    if values["operation"] != OPERATION:
        raise RunnerError("unsupported operation")
    if values["automation_id"] != AUTOMATION_ID:
        raise RunnerError("unsupported automation_id")
    for key in ("invocation_id", "expected_commit", "mode", "created_at", "nonce"):
        if not isinstance(values[key], str) or not values[key]:
            raise RunnerError(f"missing {key}")
    if str(values["mode"]) not in ALLOWED_MODES:
        raise RunnerError("unsupported mode")
    created = parse_time(str(values["created_at"]))
    age = (now or pacific_now()).astimezone(dt.timezone.utc) - created.astimezone(dt.timezone.utc)
    if age.total_seconds() < -300 or age.total_seconds() > MAX_AGE_SECONDS:
        raise RunnerError("request is outside freshness window")
    return {
        "invocation_id": _safe_id(str(values["invocation_id"])),
        "expected_commit": str(values["expected_commit"]),
        "mode": str(values["mode"]),
        "created_at": str(values["created_at"]),
        "nonce": _safe_nonce(str(values["nonce"])),
    }


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(data.encode("utf-8")) > MAX_REQUEST_BYTES and path.parent.name == "incoming":
        raise RunnerError("request exceeds size limit")
    temp.write_text(data, encoding="utf-8")
    try:
        temp.chmod(0o600)
    except PermissionError:
        pass
    temp.replace(path)


def submit_request(root: Path, request: dict[str, object]) -> dict[str, object]:
    ensure_dirs(root)
    values = validate_request(request)
    destination = incoming_path(root, values["nonce"])
    existing_result = result_path(root, values["invocation_id"])
    if existing_result.exists():
        return {"ok": True, "status": "already_terminal", "result_file": str(existing_result)}
    for existing in (destination, processing_path(root, values["nonce"]), completed_path(root, values["nonce"])):
        if existing.exists():
            existing_payload = json.loads(existing.read_text(encoding="utf-8"))
            if existing_payload != request:
                raise RunnerError("nonce replay with different payload")
            return {
                "ok": True,
                "status": "already_submitted",
                "request_file": str(existing),
                "result_file": str(existing_result),
            }
    atomic_write_json(destination, request)
    return {"ok": True, "status": "submitted", "request_file": str(destination), "result_file": str(existing_result)}


def read_status(root: Path, invocation_id: str) -> dict[str, object]:
    ensure_dirs(root)
    target = result_path(root, invocation_id)
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload.setdefault("result_file", str(target))
        return payload
    daemon_state = read_runner_state(root)
    return {
        "ok": True,
        "status": "pending",
        "result_file": str(target),
        "polling_guidance": {
            "max_seconds": CURATOR_POLL_MAX_SECONDS,
            "heartbeat_stale_seconds": RUNNER_HEARTBEAT_STALE_SECONDS,
            "continue_while": "daemon heartbeat fresh and runner ownership stable",
        },
        "submitter_context": {
            "network_required": False,
            "current_process_runner_enabled": current_process_enabled(),
        },
        "daemon_state": daemon_state,
    }


def curator_poll_decision(
    status_payload: dict[str, object],
    *,
    started_at: dt.datetime,
    now: dt.datetime | None = None,
    expected_runner_instance_id: str | None = None,
    max_seconds: int = CURATOR_POLL_MAX_SECONDS,
    heartbeat_stale_seconds: int = RUNNER_HEARTBEAT_STALE_SECONDS,
) -> dict[str, object]:
    current = now or pacific_now()
    elapsed = (current.astimezone(dt.timezone.utc) - started_at.astimezone(dt.timezone.utc)).total_seconds()
    status = status_payload.get("status")
    if status in {"completed", "failed"}:
        return {"decision": "terminal", "reason": str(status), "elapsed_seconds": elapsed}
    if elapsed > max_seconds:
        return {"decision": "fail", "reason": "overall_deadline_exceeded", "elapsed_seconds": elapsed}
    daemon_state = status_payload.get("daemon_state")
    if not isinstance(daemon_state, dict):
        return {"decision": "continue", "reason": "not_claimed_yet", "elapsed_seconds": elapsed}
    if expected_runner_instance_id and daemon_state.get("runner_instance_id") != expected_runner_instance_id:
        return {"decision": "fail", "reason": "runner_ownership_changed", "elapsed_seconds": elapsed}
    heartbeat = daemon_state.get("heartbeat_at") or daemon_state.get("phase_updated_at") or daemon_state.get("updated_at")
    if not isinstance(heartbeat, str):
        return {"decision": "fail", "reason": "missing_daemon_heartbeat", "elapsed_seconds": elapsed}
    try:
        heartbeat_at = parse_time(heartbeat)
    except RunnerError:
        return {"decision": "fail", "reason": "invalid_daemon_heartbeat", "elapsed_seconds": elapsed}
    heartbeat_age = (current.astimezone(dt.timezone.utc) - heartbeat_at.astimezone(dt.timezone.utc)).total_seconds()
    if heartbeat_age > heartbeat_stale_seconds:
        return {
            "decision": "fail",
            "reason": "stale_daemon_heartbeat",
            "elapsed_seconds": elapsed,
            "heartbeat_age_seconds": heartbeat_age,
        }
    return {
        "decision": "continue",
        "reason": "fresh_daemon_progress",
        "elapsed_seconds": elapsed,
        "heartbeat_age_seconds": heartbeat_age,
        "phase": daemon_state.get("phase"),
        "progress": daemon_state.get("progress"),
    }


def acquire_lock(root: Path) -> int:
    ensure_dirs(root)
    path = lock_path(root)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        return fd
    except FileExistsError as exc:
        if stale_lock_recovered(path):
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            return fd
        raise RunnerError("runner already active") from exc


def stale_lock_recovered(path: Path) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return True
    if content.isdigit():
        try:
            os.kill(int(content), 0)
            return False
        except ProcessLookupError:
            path.unlink(missing_ok=True)
            return True
        except PermissionError:
            return False
    if age > STALE_LOCK_SECONDS:
        path.unlink(missing_ok=True)
        return True
    return False


def release_lock(root: Path, fd: int) -> None:
    os.close(fd)
    try:
        lock_path(root).unlink()
    except FileNotFoundError:
        pass


def recover_stale_processing(root: Path, now: dt.datetime | None = None) -> list[str]:
    ensure_dirs(root)
    recovered: list[str] = []
    threshold = (now or pacific_now()).timestamp() - PROCESSING_TIMEOUT_SECONDS
    for path in sorted((root / "processing").glob("*.json")):
        if path.stat().st_mtime > threshold:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            values = validate_request(payload, now=now)
            terminal = terminal_result(values, "failed", "processing_timeout_recovered", {"request_file": str(path)})
            atomic_write_json(result_path(root, values["invocation_id"]), terminal)
            path.replace(failed_path(root, values["nonce"]))
            recovered.append(values["invocation_id"])
        except Exception:
            path.replace(root / "failed" / path.name)
            recovered.append(path.stem)
    return recovered


def terminal_result(values: dict[str, str], status: str, result: str, evidence: dict[str, object]) -> dict[str, object]:
    return {
        "ok": status == "completed",
        "status": status,
        "result": result,
        "version": SCHEMA_VERSION,
        "operation": OPERATION,
        "automation_id": AUTOMATION_ID,
        "invocation_id": values["invocation_id"],
        "nonce": values["nonce"],
        "completed_at": iso_now(),
        "evidence": evidence,
    }


def current_process_enabled() -> bool:
    return os.environ.get("MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED", "0") in {"1", "true", "yes"}


def remote_runner_disabled_evidence() -> dict[str, object]:
    configured = os.environ.get("MEMORY_STARGRAPH_CAPTURE_REMOTE_DISABLED_JSON")
    if configured:
        try:
            payload = json.loads(configured)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return {
        "configured_remote_runner_disabled": True,
        "remote_role": ".102",
        "method": "disabled_by_default_without_launchd_enablement",
        "verification": os.environ.get(
            "MEMORY_STARGRAPH_CAPTURE_REMOTE_DISABLED_EVIDENCE",
            ".102 code deployed; MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED is not set by default",
        ),
    }


def runner_identity(root: Path) -> dict[str, object]:
    remote = remote_runner_disabled_evidence()
    return {
        "runner_host_role": os.environ.get("MEMORY_STARGRAPH_CAPTURE_RUNNER_HOST_ROLE", ".85-authoritative"),
        "runner_enabled": current_process_enabled(),
        "runner_instance_id": RUNNER_INSTANCE_ID,
        "runner_pid": os.getpid(),
        "runner_started_at": RUNNER_STARTED_AT,
        "runner_state_file": str(state_path(root)),
        **remote,
    }


def write_runner_state(root: Path, status: str, extra: dict[str, object] | None = None) -> dict[str, object]:
    ensure_dirs(root)
    payload = {
        "ok": True,
        "status": status,
        "updated_at": iso_now(),
        "operation": OPERATION,
        **runner_identity(root),
        **(extra or {}),
    }
    atomic_write_json(state_path(root), payload)
    return payload


def write_phase_state(
    root: Path,
    values: dict[str, str],
    phase: str,
    *,
    processed: int | None = None,
    total: int | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    previous = read_runner_state(root) or {}
    now = iso_now()
    phase_started_at = previous.get("phase_started_at") if previous.get("phase") == phase else None
    progress: dict[str, object] = {}
    if processed is not None:
        progress["processed"] = processed
    if total is not None:
        progress["total"] = total
    return write_runner_state(
        root,
        "processing",
        {
            "active_invocation_id": values["invocation_id"],
            "phase": phase,
            "phase_started_at": phase_started_at or now,
            "phase_updated_at": now,
            "heartbeat_at": now,
            "curator_poll_contract": {
                "max_seconds": CURATOR_POLL_MAX_SECONDS,
                "heartbeat_stale_seconds": RUNNER_HEARTBEAT_STALE_SECONDS,
                "continue_while": "daemon heartbeat fresh and runner ownership stable",
                "fail_early_on": [
                    "terminal_failure",
                    "stale_heartbeat",
                    "runner_ownership_change",
                    "hard_overall_deadline",
                ],
            },
            **({"progress": progress} if progress else {}),
            **(extra or {}),
        },
    )


def read_runner_state(root: Path) -> dict[str, object] | None:
    path = state_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"ok": False, "status": "invalid_daemon_state", "runner_state_file": str(path)}
    return payload if isinstance(payload, dict) else {"ok": False, "status": "invalid_daemon_state", "runner_state_file": str(path)}


def claim_evidence(root: Path, request_file: Path, processing_file: Path, values: dict[str, str]) -> dict[str, object]:
    return {
        "request_file": str(request_file),
        "processing_file": str(processing_file),
        "claimed_at": iso_now(),
        "claimed_by_pid": os.getpid(),
        "nonce": values["nonce"],
        "atomic_claim": True,
        "claim_state": "incoming_renamed_to_processing",
    }


def frontmatter_value(markdown: str, key: str) -> object | None:
    from scripts.automation.worker_persistence import _frontmatter_values

    return _frontmatter_values(markdown).get(key)


def source_urls(markdown: str) -> list[str]:
    return sorted(set(re.findall(r"https?://[^\\s)\\]>\"']+", markdown)))


def recent_enrichment_review(markdown: str, now: dt.datetime | None = None) -> str | None:
    values = re.findall(r"(?m)^capture_link_enrichment_reviewed_at:\s*['\"]?([^'\"\n]+)['\"]?\s*$", markdown)
    values.extend(re.findall(r"<!-- capture-link-enrichment-reviewed-at:\s*([^>]+) -->", markdown))
    current = (now or pacific_now()).astimezone(dt.timezone.utc)
    newest: tuple[dt.datetime, str] | None = None
    for raw in values:
        value = raw.strip()
        try:
            reviewed = parse_time(value).astimezone(dt.timezone.utc)
        except RunnerError:
            continue
        if newest is None or reviewed > newest[0]:
            newest = (reviewed, value)
    if newest is None:
        return None
    age_days = (current - newest[0]).days
    return newest[1] if age_days < 30 else None


def candidate_deficiencies(markdown: str) -> list[str]:
    deficiencies: list[str] = []
    if not re.search(r"(?im)^##\\s+(Biography|Bio|Summary|Description)\\s*$", markdown):
        deficiencies.append("missing_biography_or_summary")
    if not source_urls(markdown):
        deficiencies.append("missing_authoritative_public_source")
    if not re.search(r"(?im)^##\\s+(Roles|Current Roles|Work|Projects)\\s*$", markdown):
        deficiencies.append("missing_roles_or_projects")
    if "![" not in markdown and "profile_image" not in markdown:
        deficiencies.append("missing_profile_media")
    return deficiencies


def entity_is_public(markdown: str) -> bool:
    public_value = frontmatter_value(markdown, "public")
    visibility = str(frontmatter_value(markdown, "visibility") or "").lower()
    tags = frontmatter_value(markdown, "tags") or []
    tag_values = {str(tag).lower() for tag in tags} if isinstance(tags, list) else {str(tags).lower()}
    if public_value is True or str(public_value).lower() == "true" or visibility == "public" or "public" in tag_values:
        return True
    return bool(source_urls(markdown))


def inspect_enrichment_candidates(
    now: dt.datetime | None = None,
    *,
    root: Path | None = None,
    values: dict[str, str] | None = None,
    max_inspections: int | None = None,
) -> dict[str, object]:
    inspected_scope = [
        {"type": "person", "limit": MAX_ENRICHMENT_CANDIDATES},
        {"type": "organization", "limit": MAX_ENRICHMENT_CANDIDATES},
        {"type": "company", "limit": MAX_ENRICHMENT_CANDIDATES},
        {"type": "team", "limit": MAX_ENRICHMENT_CANDIDATES},
        {"type": "project", "limit": MAX_ENRICHMENT_CANDIDATES},
        {"type": "product", "limit": MAX_ENRICHMENT_CANDIDATES},
        {"type": "technology", "limit": MAX_ENRICHMENT_CANDIDATES},
    ]
    rows_by_scope: list[tuple[int, dict[str, object], list[dict[str, str]]]] = []
    total_scope_count = 0
    for type_rank, scope in enumerate(inspected_scope):
        if root is not None and values is not None:
            write_phase_state(root, values, "candidate_listing", processed=type_rank, total=len(inspected_scope), extra={"current_type": scope["type"]})
        rows = list_entities(str(scope["type"]), int(scope["limit"]))
        rows_by_scope.append((type_rank, scope, rows))
        scope["listed_count"] = len(rows)
        total_scope_count += len(rows)

    exclusions: dict[str, int] = {}
    candidates: list[dict[str, object]] = []
    inspected_count = 0
    selection_truncated = False
    stop_reason = "scope_exhausted"
    for type_rank, scope, rows in rows_by_scope:
        for row in rows:
            if max_inspections is not None and inspected_count >= max_inspections:
                selection_truncated = True
                stop_reason = "inspection_limit_reached"
                break
            inspected_count += 1
            slug = row["slug"]
            if root is not None and values is not None:
                write_phase_state(root, values, "entity_reads", processed=inspected_count, total=total_scope_count, extra={"current_slug": slug})
            try:
                markdown = get_entity(slug, timeout=ENRICHMENT_ENTITY_READ_TIMEOUT)
            except RunnerError:
                exclusions["read_failed"] = exclusions.get("read_failed", 0) + 1
                continue
            reasons: list[str] = []
            if not entity_is_public(markdown):
                reasons.append("not_public_or_no_reliable_public_source")
            recent_review = recent_enrichment_review(markdown, now)
            if recent_review:
                reasons.append("reviewed_within_30_days")
            deficiencies = candidate_deficiencies(markdown)
            if reasons:
                for reason in reasons:
                    exclusions[reason] = exclusions.get(reason, 0) + 1
                continue
            candidates.append({
                "slug": slug,
                "type": row["type"],
                "title": row["title"],
                "type_rank": type_rank,
                "deficiencies": deficiencies,
                "deficiency_count": len(deficiencies),
                "source_count": len(source_urls(markdown)),
                "order_key": [type_rank, -len(deficiencies), slug],
            })
            if len(candidates) >= MAX_ENRICHMENT_ATTEMPTS:
                selection_truncated = inspected_count < total_scope_count
                stop_reason = "eligible_attempt_limit_reached" if selection_truncated else "scope_exhausted"
                break
        if selection_truncated:
            break
    candidates.sort(key=lambda item: (int(item["type_rank"]), -int(item["deficiency_count"]), str(item["slug"])))
    for index, candidate in enumerate(candidates, 1):
        candidate["selection_order"] = index
        candidate.pop("order_key", None)
    scope_complete = inspected_count >= total_scope_count and not selection_truncated
    uninspected_count = max(total_scope_count - inspected_count, 0)
    no_eligible_candidate = len(candidates) == 0 and scope_complete
    no_eligible_within_inspected = len(candidates) == 0 and not scope_complete
    evidence_display_truncated = len(candidates) > MAX_ENRICHMENT_EVIDENCE_ITEMS
    return {
        "selection_version": ENRICHMENT_SELECTION_VERSION,
        "inspected_scope": inspected_scope,
        "scope_complete": scope_complete,
        "total_scope_count": total_scope_count,
        "inspected_count": inspected_count,
        "uninspected_count": uninspected_count,
        "inspection_limit": max_inspections,
        "selection_truncated": selection_truncated,
        "inspection_truncated": selection_truncated,
        "evidence_display_truncated": evidence_display_truncated,
        "stop_reason": stop_reason,
        "candidate_count": len(candidates),
        "exclusion_counts": exclusions,
        "ordered_candidates": candidates[:MAX_ENRICHMENT_EVIDENCE_ITEMS],
        "selected_candidates": candidates[:MAX_ENRICHMENT_ATTEMPTS],
        "no_eligible_candidate": no_eligible_candidate,
        "no_eligible_candidate_within_inspected_scope": no_eligible_within_inspected,
    }


def reserve_candidate(
    values: dict[str, str],
    run_slug: str,
    report_slug: str,
    candidate: dict[str, object],
    reservations: list[dict[str, object]],
    base_evidence: dict[str, object],
    *,
    root: Path | None = None,
    processed: int | None = None,
    total: int | None = None,
) -> dict[str, object]:
    if root is not None:
        write_phase_state(root, values, "reservation_persistence", processed=processed, total=total, extra={"current_slug": candidate["slug"]})
    reservation = {
        "slug": candidate["slug"],
        "type": candidate["type"],
        "reserved_at": iso_now(),
        "invocation_id": values["invocation_id"],
        "reservation_status": "persisted_before_mutation",
    }
    reservations.append(reservation)
    update_active_lifecycle(
        values,
        run_slug,
        report_slug,
        {**base_evidence, "reservations": reservations, "reservation_readback_required": True},
    )
    readback = get_entity(run_slug)
    if str(candidate["slug"]) not in readback or values["invocation_id"] not in readback:
        raise RunnerError(f"reservation readback failed for {candidate['slug']}")
    return {**reservation, "readback_verified": True}


def apply_entity_enrichment(values: dict[str, str], candidate: dict[str, object], *, root: Path | None = None, processed: int | None = None, total: int | None = None) -> dict[str, object]:
    slug = str(candidate["slug"])
    if root is not None:
        write_phase_state(root, values, "enrichment", processed=processed, total=total, extra={"current_slug": slug})
    before = get_entity(slug)
    stamp = iso_now()
    urls = source_urls(before)
    deficiencies = list(candidate.get("deficiencies", []))
    review_marker = f"<!-- capture-link-enrichment-reviewed-at: {stamp} -->"
    review_section = (
        f"\n\n## Capture Link Enrichment Review\n\n"
        f"{review_marker}\n\n"
        f"- Reviewed at: {stamp}\n"
        f"- Invocation: {values['invocation_id']}\n"
        f"- Selection version: {ENRICHMENT_SELECTION_VERSION}\n"
        f"- Source URLs checked: {len(urls)}\n"
        f"- Deficiencies: {', '.join(deficiencies) if deficiencies else 'none'}\n"
    )
    if "## Capture Link Enrichment Review" in before:
        outcome = "already_sufficient"
        receipt_section = (
            f"\n\n## Capture Link Already-Sufficient Review Receipt\n\n"
            f"{review_marker}\n\n"
            f"- Reviewed at: {stamp}\n"
            f"- Invocation: {values['invocation_id']}\n"
            f"- Selection version: {ENRICHMENT_SELECTION_VERSION}\n"
            f"- Reason: already_sufficient_existing_enrichment_review\n"
            f"- Source URLs checked: {len(urls)}\n"
            f"- Deficiencies: {', '.join(deficiencies) if deficiencies else 'none'}\n"
            f"- Expires when: source entity content changes materially, new authoritative public sources appear, or the review window lapses\n"
        )
        after = before.rstrip() + receipt_section + "\n"
        put_entity(slug, after)
    else:
        outcome = "enriched_review_metadata"
        after = before.rstrip() + review_section + "\n"
        put_entity(slug, after)
    readback = get_entity(slug)
    if review_marker not in readback:
        raise RunnerError(f"enrichment readback failed for {slug}")
    return {
        "slug": slug,
        "result": outcome,
        "source_count": len(urls),
        "deficiencies": deficiencies,
        "receipt_recorded": True,
        "content_mutation": outcome != "already_sufficient",
        "verification": {
            "readback_verified": True,
            "review_marker_present": review_marker in readback,
            "body_changed": before != after,
        },
    }


def _plain_cell(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_wikilink(value: str) -> str:
    match = re.search(r"\[\[([^\]]+)\]\]", value or "")
    return match.group(1).strip() if match else ""


def _slug_tail(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:90].strip("-") or "source"


def _capture_title(row: dict[str, str], child_markdown: str, fetched: dict[str, object]) -> str:
    title = _plain_cell(fetched.get("title"))
    if title:
        return title
    match = re.search(r"(?m)^#\s+(.+?)\s*$", child_markdown)
    if match:
        return _plain_cell(match.group(1))
    source = _plain_cell(row.get("source"))
    return source.rstrip("/").rsplit("/", 1)[-1] or _plain_cell(row.get("id")) or "Captured source"


def _target_slug(row: dict[str, str], title: str) -> str:
    configured = _extract_wikilink(_plain_cell(row.get("target")))
    if configured:
        return configured
    capture_id = _plain_cell(row.get("id")).lower() or "capture"
    return f"notes/memory-stargraph-captures/{_slug_tail(capture_id)}-{_slug_tail(title)}"


def _extract_capture_instructions(child_markdown: str, row: dict[str, str]) -> str:
    match = re.search(r"(?ms)^## Capture Instructions\s*\n(.*?)(?=^## |\Z)", child_markdown)
    instructions = match.group(1).strip() if match else ""
    if not instructions:
        instructions = _plain_cell(row.get("notes"))
    return instructions[:MAX_CAPTURE_INSTRUCTION_CHARS]


def _html_to_text(raw: str) -> tuple[str, str]:
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""
    body = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    body = re.sub(r"(?s)<!--.*?-->", " ", body)
    body = re.sub(r"(?is)<br\s*/?>", "\n", body)
    body = re.sub(r"(?is)</(p|div|section|article|header|footer|li|h[1-6])>", "\n", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    text = html.unescape(body)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


def fetch_capture_source(source_url: str) -> dict[str, object]:
    if not source_url or not re.match(r"^https?://", source_url):
        raise RunnerError("capture source URL is missing or unsupported")
    try:
        result = subprocess.run(
            ["curl", "-L", "-sS", "--fail", "--max-time", str(MAX_CAPTURE_FETCH_SECONDS), source_url],
            capture_output=True,
            check=False,
            timeout=MAX_CAPTURE_FETCH_SECONDS + 10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"source fetch failed: {exc}") from exc
    if result.returncode != 0:
        error = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace")
        raise RunnerError(f"source fetch failed: {error.strip()[:500]}")
    raw_bytes = result.stdout[:MAX_CAPTURE_FETCH_BYTES]
    raw = raw_bytes.decode("utf-8", errors="replace")
    title, text = _html_to_text(raw)
    return {
        "status": "fetched",
        "source_url": source_url,
        "bytes_read": len(raw_bytes),
        "bytes_truncated": len(result.stdout) > MAX_CAPTURE_FETCH_BYTES,
        "title": title,
        "text_excerpt": text[:MAX_CAPTURE_TEXT_CHARS],
        "text_truncated": len(text) > MAX_CAPTURE_TEXT_CHARS,
    }


def build_capture_artifact(row: dict[str, str], child_markdown: str, fetched: dict[str, object], values: dict[str, str]) -> tuple[str, str]:
    capture_id = _plain_cell(row.get("id"))
    source_url = _plain_cell(row.get("source"))
    source_kind = _plain_cell(row.get("source kind")) or "url"
    title = _capture_title(row, child_markdown, fetched)
    target_slug = _target_slug(row, title)
    instructions = _extract_capture_instructions(child_markdown, row)
    text_excerpt = str(fetched.get("text_excerpt") or "").strip()
    artifact = f"""---
type: captured-source
title: {json.dumps(title, ensure_ascii=False)}
status: captured
capture_id: {capture_id}
source_url: {json.dumps(source_url, ensure_ascii=False)}
source_kind: {json.dumps(source_kind, ensure_ascii=False)}
captured_at: '{iso_now()}'
capture_invocation_id: {json.dumps(values["invocation_id"], ensure_ascii=False)}
tags:
- capture-link
- memory-stargraph
- source
---

# {title}

Source: {source_url}
Capture request: [[{capture.node_slug(row) or ''}]]
Invocation: {values["invocation_id"]}

## Capture Instructions

{instructions or "No extra instructions were provided."}

## Host Runner Evidence

- Fetch status: {fetched.get("status")}
- Bytes read: {fetched.get("bytes_read")}
- Bytes truncated: {str(fetched.get("bytes_truncated")).lower()}
- Text truncated: {str(fetched.get("text_truncated")).lower()}
- Artifact policy: bounded source excerpt only; no private snippets, secrets, raw prompts, or task-local fallback.

## Bounded Source Excerpt

{text_excerpt or "No readable source text was extracted from the bounded fetch."}
"""
    return target_slug, artifact


def drain_frozen_capture_rows(
    root: Path,
    values: dict[str, str],
    run_slug: str,
    report_slug: str,
    snapshot: dict[str, object],
    base_evidence: dict[str, object],
) -> dict[str, object]:
    raw_rows = snapshot.get("rows", [])
    if not isinstance(raw_rows, list):
        raise RunnerPhaseError("capture_drain", "snapshot rows malformed")
    rows = sorted(raw_rows, key=capture.item_number)
    outcomes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    reservations: list[dict[str, object]] = []
    frozen_ids: list[str] = []
    total = len(rows)
    for index, row_obj in enumerate(rows, 1):
        if not isinstance(row_obj, dict):
            raise RunnerPhaseError("capture_drain", f"snapshot row {index} malformed")
        row = {str(key): str(value) for key, value in row_obj.items()}
        capture_id = _plain_cell(row.get("id"))
        frozen_ids.append(capture_id or f"row-{index}")
        if not capture_id:
            raise RunnerPhaseError("capture_drain", f"snapshot row {index} missing id")
        if row.get("status") != "planned":
            raise RunnerPhaseError("capture_drain", f"{capture_id} snapshot status {row.get('status')!r} is not planned")
        child_slug = capture.node_slug(row)
        if not child_slug:
            raise RunnerPhaseError("capture_drain", f"{capture_id} missing child node")
        source_url = _plain_cell(row.get("source"))
        if not source_url:
            raise RunnerPhaseError("capture_drain", f"{capture_id} missing source URL")
        reserved = False
        reservation: dict[str, object] | None = None
        try:
            write_phase_state(root, values, "capture_reservation", processed=index, total=total, extra={"capture_id": capture_id, "child_slug": child_slug})
            reservation_transition = capture.apply_transition(
                capture_id,
                "planned",
                "capturing",
                f"host runner reserved frozen snapshot row {capture_id} for invocation {values['invocation_id']}",
                pacific_now(),
            )
            reservation = {
                **reservation_transition,
                "capture_id": capture_id,
                "reservation_status": "persisted_before_mutation",
                "readback_verified": True,
            }
            reservations.append(reservation)
            reserved = True
            update_active_lifecycle(
                values,
                run_slug,
                report_slug,
                {**base_evidence, "capture_reservations": reservations, "capture_drain_frozen_ids": frozen_ids},
            )

            write_phase_state(root, values, "capture_source_fetch", processed=index, total=total, extra={"capture_id": capture_id, "source_url": source_url})
            child_markdown = get_entity(child_slug, timeout=60)
            fetched = fetch_capture_source(source_url)
            target_slug, artifact = build_capture_artifact(row, child_markdown, fetched, values)

            write_phase_state(root, values, "capture_artifact_persistence", processed=index, total=total, extra={"capture_id": capture_id, "target_slug": target_slug})
            put_entity(target_slug, artifact)
            capture.link(child_slug, target_slug, "captured_as")
            capture.link(target_slug, child_slug, "capture_result_for")

            write_phase_state(root, values, "capture_terminal_transition", processed=index, total=total, extra={"capture_id": capture_id, "target_slug": target_slug})
            completed_transition = capture.apply_transition(
                capture_id,
                "capturing",
                "completed",
                f"host runner captured frozen snapshot row into [[{target_slug}]] for invocation {values['invocation_id']}",
                pacific_now(),
            )
            outcomes.append({
                "capture_id": capture_id,
                "child_slug": child_slug,
                "target_slug": target_slug,
                "source_url": source_url,
                "result": "completed",
                "reservation": reservation,
                "transition": completed_transition,
                "fetch": {
                    "status": fetched.get("status"),
                    "bytes_read": fetched.get("bytes_read"),
                    "bytes_truncated": fetched.get("bytes_truncated"),
                    "text_truncated": fetched.get("text_truncated"),
                    "title": fetched.get("title"),
                },
                "readback_verified": True,
            })
        except Exception as exc:
            failure: dict[str, object] = {
                "capture_id": capture_id,
                "child_slug": child_slug,
                "result": "failed",
                "error": str(exc),
                "reserved_before_failure": reserved,
                "readback_verified": False,
            }
            if reserved:
                try:
                    failed_transition = capture.apply_transition(
                        capture_id,
                        "capturing",
                        "failed",
                        f"host runner failed frozen snapshot row {capture_id}: {str(exc)[:300]}",
                        pacific_now(),
                    )
                    failure["terminal_transition"] = failed_transition
                    failure["readback_verified"] = True
                except Exception as transition_exc:
                    failure["terminal_transition_error"] = str(transition_exc)
                    failures.append(failure)
                    raise RunnerPhaseError("capture_drain", f"{capture_id} failed and terminal transition failed: {transition_exc}") from transition_exc
            else:
                raise RunnerPhaseError("capture_drain", f"{capture_id} reservation failed: {exc}") from exc
            failures.append(failure)
    all_frozen_terminal = len(outcomes) + len(failures) == total and all(bool(item.get("readback_verified")) for item in [*outcomes, *failures])
    result = "completed_non_empty_snapshot_drain" if not failures else "completed_non_empty_snapshot_drain_with_failures"
    return {
        "mode": "capture_drain",
        "result": result,
        "snapshot_row_count": total,
        "frozen_ids": frozen_ids,
        "deterministic_ordering": "capture_id_numeric_ascending",
        "reservations": reservations,
        "outcomes": outcomes,
        "failures": failures,
        "metrics": {
            "frozen_rows": total,
            "completed_items": len(outcomes),
            "failed_items": len(failures),
            "terminal_items": len(outcomes) + len(failures),
        },
        "all_frozen_terminal": all_frozen_terminal,
        "task_local_network_required": False,
        "mutated_only_frozen_snapshot": True,
    }


def run_empty_queue_enrichment(root: Path, values: dict[str, str], run_slug: str, report_slug: str, base_evidence: dict[str, object]) -> dict[str, object]:
    write_phase_state(root, values, "candidate_listing", processed=0, total=7)
    selection = inspect_enrichment_candidates(root=root, values=values)
    reservations: list[dict[str, object]] = []
    outcomes: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    if selection["no_eligible_candidate"]:
        return {
            "mode": "empty_queue_enrichment",
            "result": "completed_empty_snapshot_no_eligible_candidates",
            "selection": selection,
            "reservations": reservations,
            "outcomes": outcomes,
            "failures": failures,
            "metrics": {
                "eligible_candidate_count": 0,
                "attempted_enrichments": 0,
                "successful_enrichments": 0,
                "failed_enrichments": 0,
            },
            "no_eligible_candidate": True,
            "no_eligible_candidate_within_inspected_scope": False,
        }
    if selection.get("no_eligible_candidate_within_inspected_scope"):
        return {
            "mode": "empty_queue_enrichment",
            "result": "completed_empty_snapshot_no_eligible_candidates_within_inspected_scope",
            "selection": selection,
            "reservations": reservations,
            "outcomes": outcomes,
            "failures": failures,
            "metrics": {
                "eligible_candidate_count": 0,
                "attempted_enrichments": 0,
                "successful_enrichments": 0,
                "failed_enrichments": 0,
            },
            "no_eligible_candidate": False,
            "no_eligible_candidate_within_inspected_scope": True,
        }
    selected = list(selection["selected_candidates"])
    for index, candidate in enumerate(selected, 1):
        try:
            reservation = reserve_candidate(
                values,
                run_slug,
                report_slug,
                candidate,
                reservations,
                {**base_evidence, "enrichment_selection": selection},
                root=root,
                processed=index,
                total=len(selected),
            )
            outcome = apply_entity_enrichment(values, candidate, root=root, processed=index, total=len(selected))
            outcomes.append({**outcome, "reservation": reservation})
        except Exception as exc:
            failures.append({"slug": candidate.get("slug"), "error": str(exc), "result": "failed"})
    return {
        "mode": "empty_queue_enrichment",
        "result": "completed_empty_snapshot_enrichment",
        "selection": selection,
        "reservations": reservations,
        "outcomes": outcomes,
        "failures": failures,
        "metrics": {
            "eligible_candidate_count": selection["candidate_count"],
            "attempted_enrichments": len(outcomes) + len(failures),
            "successful_enrichments": len(outcomes),
            "failed_enrichments": len(failures),
        },
        "no_eligible_candidate": False,
        "no_eligible_candidate_within_inspected_scope": False,
    }


def log_event(root: Path, event: dict[str, object]) -> None:
    ensure_dirs(root)
    path = log_path(root)
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        archive = path.with_suffix(".jsonl.1")
        path.replace(archive)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": iso_now(), **event}, ensure_ascii=False, sort_keys=True) + "\n")


def run_capture_link_drain(root: Path, values: dict[str, str], claim: dict[str, object]) -> dict[str, object]:
    run_slug = ""
    report_slug = ""
    commit = ""
    ownership = runner_identity(root)
    first_compaction: dict[str, object] | None = None
    snapshot: dict[str, object] | None = None
    capture_drain: dict[str, object] | None = None
    enrichment: dict[str, object] | None = None
    phase = "source_validation"
    try:
        write_phase_state(root, values, phase, extra={"request_claim": claim})
        commit = current_commit()
        if commit != values["expected_commit"]:
            raise RunnerPhaseError(phase, f"expected commit {values['expected_commit']} but host is {commit}")

        phase = "run_persistence"
        write_phase_state(root, values, phase, extra={"host_commit": commit, "request_claim": claim})
        run_slug, report_slug = create_active_lifecycle(values)

        phase = "compaction_before_snapshot"
        write_phase_state(root, values, phase, extra={"run_slug": run_slug, "report_slug": report_slug})
        first_compaction = capture.apply_compaction()

        phase = "snapshot"
        write_phase_state(root, values, phase, extra={"first_compaction": first_compaction})
        snapshot = capture.create_snapshot(invocation_id=values["invocation_id"])
        rows = snapshot.get("rows", [])
        if not isinstance(rows, list):
            raise RunnerPhaseError(phase, "snapshot rows malformed")
        mode = values["mode"]
        if mode == "capture_drain" and not rows:
            raise RunnerPhaseError(phase, "mode capture_drain requested but snapshot is empty")
        if mode == "empty_queue_enrichment" and rows:
            raise RunnerPhaseError(phase, "mode empty_queue_enrichment requested but snapshot is non-empty")
        base = {
            "host_commit": commit,
            "runner": "host-managed-spool",
            "task_local_network_required": False,
            "runner_ownership": ownership,
            "request_claim": claim,
            "snapshot": snapshot,
        }
        if rows:
            phase = "capture_drain"
            write_phase_state(root, values, phase, processed=0, total=len(rows), extra={"snapshot": snapshot})
            capture_drain = drain_frozen_capture_rows(root, values, run_slug, report_slug, snapshot, base)
            result = str(capture_drain["result"])
            status = "completed" if capture_drain.get("all_frozen_terminal") else "failed"
        else:
            enrichment = run_empty_queue_enrichment(root, values, run_slug, report_slug, base)
            result = str(enrichment["result"])
            status = "completed"

        phase = "final_compaction"
        write_phase_state(root, values, phase, extra={"result": result, "snapshot": snapshot})
        final_compaction = capture.apply_compaction()
        evidence = {
            "host_commit": commit,
            "first_compaction": first_compaction,
            "snapshot": snapshot,
            "final_compaction": final_compaction,
            "runner": "host-managed-spool",
            "task_local_network_required": False,
            "runner_ownership": ownership,
            "request_claim": claim,
            "capture_drain": capture_drain,
            "enrichment": enrichment,
            "progress": read_runner_state(root),
        }

        phase = "terminal_persistence"
        write_phase_state(root, values, phase, extra={"result": result, "status": status})
        evidence = terminalize_lifecycle(values, run_slug, report_slug, status, result, evidence)
        write_phase_state(root, values, "tag_release", extra={"result": result, "status": status, "run_slug": run_slug, "report_slug": report_slug})
        return terminal_result(values, status, result, evidence)
    except Exception as exc:
        failed_phase = exc.phase if isinstance(exc, RunnerPhaseError) else phase
        error_result = f"{failed_phase}_failed"
        evidence = {
            "error": str(exc),
            "failed_phase": failed_phase,
            "host_commit": commit or None,
            "first_compaction": first_compaction,
            "snapshot": snapshot,
            "runner": "host-managed-spool",
            "task_local_network_required": False,
            "runner_ownership": ownership,
            "request_claim": claim,
            "capture_drain": capture_drain,
            "enrichment": enrichment,
            "progress": read_runner_state(root),
        }
        if run_slug and report_slug:
            try:
                write_phase_state(root, values, "terminal_persistence", extra={"result": error_result, "status": "failed"})
                evidence = terminalize_lifecycle(values, run_slug, report_slug, "failed", error_result, evidence)
                write_phase_state(root, values, "tag_release", extra={"result": error_result, "status": "failed", "run_slug": run_slug, "report_slug": report_slug})
            except Exception as terminal_exc:
                evidence["terminalize_error"] = str(terminal_exc)
        return terminal_result(values, "failed", error_result, evidence)


def process_one(root: Path) -> dict[str, object]:
    ensure_dirs(root)
    recovered = recover_stale_processing(root)
    fd = acquire_lock(root)
    try:
        incoming = sorted((root / "incoming").glob("*.json"))
        if not incoming:
            write_runner_state(root, "idle", {"recovered": recovered})
            result = {"ok": True, "status": "idle", "recovered": recovered}
            log_event(root, result)
            return result
        request_file = incoming[0]
        if request_file.stat().st_size > MAX_REQUEST_BYTES:
            request_file.replace(root / "failed" / request_file.name)
            raise RunnerError("request exceeds size limit")
        payload = json.loads(request_file.read_text(encoding="utf-8"))
        values = validate_request(payload)
        target_result = result_path(root, values["invocation_id"])
        in_process = processing_path(root, values["nonce"])
        if target_result.exists():
            request_file.replace(completed_path(root, values["nonce"]))
            result = {"ok": True, "status": "already_terminal", "result_file": str(target_result), "recovered": recovered}
            log_event(root, result)
            return result
        request_file.replace(in_process)
        try:
            claim = claim_evidence(root, request_file, in_process, values)
            write_runner_state(root, "processing", {"active_invocation_id": values["invocation_id"], "request_claim": claim})
            result = run_capture_link_drain(root, values, claim)
        except Exception as exc:
            result = terminal_result(values, "failed", "runner_error", {"error": str(exc)})
        atomic_write_json(target_result, result)
        in_process.replace(completed_path(root, values["nonce"]) if result.get("status") == "completed" else failed_path(root, values["nonce"]))
        processed = {"ok": True, "status": "processed", "result_file": str(target_result), "result": result, "recovered": recovered}
        log_event(root, {"status": "processed", "result_file": str(target_result), "terminal_status": result.get("status"), "terminal_result": result.get("result")})
        return processed
    finally:
        release_lock(root, fd)


def run_loop(root: Path, poll_seconds: float = 5.0, max_iterations: int | None = None) -> dict[str, object]:
    if os.environ.get("MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED", "0") not in {"1", "true", "yes"}:
        raise RunnerError("host runner disabled by MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED")
    write_runner_state(root, "starting")
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


def health(root: Path) -> dict[str, object]:
    ensure_dirs(root)
    return {
        "ok": True,
        "context": "daemon" if current_process_enabled() else "submitter_offline",
        "current_process_runner_enabled": current_process_enabled(),
        "daemon_state": read_runner_state(root),
        "runtime_root": str(root),
        "incoming": len(list((root / "incoming").glob("*.json"))),
        "processing": len(list((root / "processing").glob("*.json"))),
        "results": len(list((root / "results").glob("*.json"))),
        "log_file": str(log_path(root)),
        "operation": OPERATION,
    }


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline submitter and host runner for Capture Link jobs.")
    parser.add_argument("--runtime-dir", default=str(runtime_root()))
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit", help="Submit an atomic local request file without network access.")
    submit.add_argument("--invocation-id", required=True)
    submit.add_argument("--expected-commit", required=True)
    submit.add_argument("--mode", choices=sorted(ALLOWED_MODES), default=DEFAULT_MODE)
    submit.add_argument("--nonce")
    submit.add_argument("--json", action="store_true")
    status = sub.add_parser("status", help="Read local terminal result.")
    status.add_argument("--invocation-id", required=True)
    status.add_argument("--json", action="store_true")
    run_once = sub.add_parser("run-once", help="Host-side runner processes one request.")
    run_once.add_argument("--json", action="store_true")
    run_loop_parser = sub.add_parser("run-loop", help="Host-side runner loop for launchd/dashboard management.")
    run_loop_parser.add_argument("--poll-seconds", type=float, default=5.0)
    run_loop_parser.add_argument("--max-iterations", type=int)
    run_loop_parser.add_argument("--json", action="store_true")
    health_parser = sub.add_parser("health", help="Report local spool readiness.")
    health_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.runtime_dir)
    try:
        if args.command == "submit":
            payload = make_request(args.invocation_id, args.expected_commit, args.mode, args.nonce)
            result = submit_request(root, payload)
        elif args.command == "status":
            result = read_status(root, args.invocation_id)
        elif args.command == "run-once":
            if os.environ.get("MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED", "0") not in {"1", "true", "yes"}:
                raise RunnerError("host runner disabled by MEMORY_STARGRAPH_CAPTURE_RUNNER_ENABLED")
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
