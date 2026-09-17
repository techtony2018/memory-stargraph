#!/usr/bin/env python3
"""Prepare and verify worker Run/report persistence API operations.

The recurring workers run in environments where direct loopback access to
GBrain/PostgreSQL and nested network clients can be intermittently refused. This
module is offline-only: it prepares payload files, slug encodings, deterministic
top-level curl command lines, and semantic readback checks, but it never spawns
network clients.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


DEFAULT_WORKER_API_BASE_URL = "http://127.0.0.1:8788"
DEFAULT_RETRIES = 3
DEFAULT_OUTPUT_DIR = Path(".worker-persistence")


class WorkerPersistenceError(RuntimeError):
    """Raised when bounded worker persistence cannot be verified."""


def entity_save_response_persistence(payload: object) -> dict[str, object] | None:
    """Return normalized durable-save evidence, including no-embed pending state."""
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    if payload.get("persisted", True) is not True:
        return None
    raw = payload.get("persistence")
    if raw is None:
        return {
            "persisted": True,
            "readback_verified": False,
            "mode": "legacy_api",
            "indexing_status": "unknown",
            "degraded": False,
        }
    if not isinstance(raw, dict) or raw.get("persisted") is not True:
        return None
    indexing_status = str(raw.get("indexing_status") or "")
    if indexing_status not in {"ready", "pending"}:
        return None
    return {
        "persisted": True,
        "readback_verified": raw.get("readback_verified") is True,
        "mode": str(raw.get("mode") or "unknown"),
        "indexing_status": indexing_status,
        "degraded": raw.get("degraded") is True,
    }


@dataclass(frozen=True)
class WorkerRoute:
    base_url: str
    curl_flags: tuple[str, ...]
    source: str


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            parsed = [raw_value.strip().strip("'\"")]
        values[key] = parsed[0] if parsed else ""
    return values


def default_config_path() -> Path:
    configured = os.environ.get("MEMORY_STARGRAPH_AUTOMATION_CONFIG")
    if configured:
        return Path(configured).expanduser()
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return codex_home / "automations" / "memory-stargraph-wish-to-reallity" / "deployment-targets.env"


def _is_loopback_url(url: str) -> bool:
    return bool(re.search(r"^https?://(127(?:\.\d+){3}|localhost)(?::|/|$)", url, flags=re.IGNORECASE))


def _candidate_routes(config: dict[str, str], config_source: str) -> list[WorkerRoute]:
    routes: list[WorkerRoute] = []
    dashboard_url = config.get("MEMORY_STARGRAPH_DASHBOARD_URL", "").strip()
    if dashboard_url:
        routes.append(
            WorkerRoute(
                dashboard_url.rstrip("/"),
                tuple(shlex.split(config.get("MEMORY_STARGRAPH_DASHBOARD_CURL_FLAGS", ""))),
                f"{config_source}:MEMORY_STARGRAPH_DASHBOARD_URL",
            )
        )
    local_url = config.get("MEMORY_STARGRAPH_LOCAL_URL", "").strip()
    if local_url:
        routes.append(
            WorkerRoute(
                local_url.rstrip("/"),
                tuple(shlex.split(config.get("MEMORY_STARGRAPH_LOCAL_CURL_FLAGS", ""))),
                f"{config_source}:MEMORY_STARGRAPH_LOCAL_URL",
            )
        )
    routes.append(WorkerRoute(DEFAULT_WORKER_API_BASE_URL, (), "default_loopback"))
    seen: set[tuple[str, tuple[str, ...]]] = set()
    deduped: list[WorkerRoute] = []
    for route in routes:
        identity = (route.base_url, route.curl_flags)
        if identity not in seen:
            seen.add(identity)
            deduped.append(route)
    return deduped


def resolve_worker_route(config_path: Path | None = None) -> WorkerRoute:
    path = config_path or default_config_path()
    config = _parse_env_file(path)
    env_url = os.environ.get("MEMORY_STARGRAPH_WORKER_API_URL", "").strip()
    if env_url:
        return WorkerRoute(
            env_url.rstrip("/"),
            tuple(shlex.split(os.environ.get("MEMORY_STARGRAPH_WORKER_API_CURL_FLAGS", ""))),
            "MEMORY_STARGRAPH_WORKER_API_URL",
        )
    candidates = _candidate_routes(config, str(path))
    non_loopback = [route for route in candidates if not _is_loopback_url(route.base_url)]
    loopback = [route for route in candidates if _is_loopback_url(route.base_url)]
    if non_loopback:
        return non_loopback[0]
    if loopback:
        return loopback[0]
    raise WorkerPersistenceError("no healthy worker API route available")


def route_records(config_path: Path | None = None) -> list[dict[str, object]]:
    path = config_path or default_config_path()
    env_url = os.environ.get("MEMORY_STARGRAPH_WORKER_API_URL", "").strip()
    if env_url:
        candidates = [
            WorkerRoute(
                env_url.rstrip("/"),
                tuple(shlex.split(os.environ.get("MEMORY_STARGRAPH_WORKER_API_CURL_FLAGS", ""))),
                "MEMORY_STARGRAPH_WORKER_API_URL",
            )
        ]
    else:
        candidates = _candidate_routes(_parse_env_file(path), str(path))
        non_loopback = [route for route in candidates if not _is_loopback_url(route.base_url)]
        loopback = [route for route in candidates if _is_loopback_url(route.base_url)]
        candidates = [*non_loopback, *loopback]
    return [
        {
            "base_url": route.base_url,
            "curl_flags": list(route.curl_flags),
            "curl_flags_shell": shlex.join(route.curl_flags),
            "source": route.source,
            "loopback": _is_loopback_url(route.base_url),
        }
        for route in candidates
    ]


def content_from_raw_payload(raw_payload: dict[str, object]) -> str:
    content = raw_payload.get("content")
    if not isinstance(content, str):
        raise WorkerPersistenceError("raw readback missing content")
    return content


def _safe_slug_filename(slug: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    return cleaned[:120] or "entity"


def _preferred_non_loopback_route(config_path: Path | None = None) -> WorkerRoute:
    records = route_records(config_path)
    for record in records:
        if not record["loopback"]:
            return WorkerRoute(
                str(record["base_url"]),
                tuple(str(flag) for flag in record["curl_flags"]),
                str(record["source"]),
            )
    raise WorkerPersistenceError("no configured non-loopback worker API route available")


def _curl_argv(route: WorkerRoute, *args: str) -> list[str]:
    return ["curl", "-sS", "--fail", *route.curl_flags, *args]


def _shell(argv: list[str]) -> str:
    return shlex.join(argv)


def prepare_request(
    action: str,
    slug: str | None = None,
    source_file: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    config_path: Path | None = None,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, object]:
    route = _preferred_non_loopback_route(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_payload: dict[str, object] = {
        "ok": True,
        "action": action,
        "route": {
            "base_url": route.base_url,
            "curl_flags": list(route.curl_flags),
            "source": route.source,
            "loopback": False,
        },
        "transport_contract": "run each curl command explicitly as a top-level worker command; do not run this helper, Python, or a shell wrapper to perform network transport",
        "retries": retries,
    }
    if action == "health":
        argv = _curl_argv(route, "--max-time", "8", f"{route.base_url}/api/health")
        return {
            **base_payload,
            "commands": [{"step": "health", "argv": argv, "shell": _shell(argv), "timeout_seconds": 8}],
        }
    if not slug:
        raise WorkerPersistenceError(f"{action} requires a slug")
    encoded = quote(slug, safe="")
    safe = _safe_slug_filename(slug)
    raw_output = output_dir / f"{safe}.raw.json"
    read_argv = _curl_argv(route, "--max-time", "45", f"{route.base_url}/api/entity-raw/{encoded}", "-o", str(raw_output))
    if action == "read":
        return {
            **base_payload,
            "slug": slug,
            "encoded_slug": encoded,
            "raw_output_file": str(raw_output),
            "commands": [{"step": "read_raw", "argv": read_argv, "shell": _shell(read_argv), "timeout_seconds": 45}],
            "offline_next": {
                "extract_content": _shell([sys.executable, "scripts/automation/worker_persistence.py", "content-from-raw", "--raw-json-file", str(raw_output)])
            },
        }
    if action == "save":
        if source_file is None:
            raise WorkerPersistenceError("save requires --file")
        payload_file = output_dir / f"{safe}.save-payload.json"
        payload_file.write_text(json.dumps(save_payload(source_file), ensure_ascii=False), encoding="utf-8")
        save_argv = _curl_argv(
            route,
            "--max-time",
            "120",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            f"@{payload_file}",
            f"{route.base_url}/api/entity-save/{encoded}",
        )
        verify_argv = [
            sys.executable,
            "scripts/automation/worker_persistence.py",
            "verify-save",
            "--expected-file",
            str(source_file),
            "--raw-json-file",
            str(raw_output),
            "--json",
        ]
        return {
            **base_payload,
            "slug": slug,
            "encoded_slug": encoded,
            "payload_file": str(payload_file),
            "raw_output_file": str(raw_output),
            "commands": [
                {"step": "save", "argv": save_argv, "shell": _shell(save_argv), "timeout_seconds": 120},
                {"step": "readback", "argv": read_argv, "shell": _shell(read_argv), "timeout_seconds": 45},
            ],
            "offline_verify": {"argv": verify_argv, "shell": _shell(verify_argv)},
            "body_policy": "exact_except_one_optional_final_newline",
        }
    if action == "tags":
        payload_file = output_dir / f"{safe}.tags-payload.json"
        payload_file.write_text(json.dumps(tag_payload(add or [], remove or []), ensure_ascii=False), encoding="utf-8")
        tags_argv = _curl_argv(
            route,
            "--max-time",
            "90",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            f"@{payload_file}",
            f"{route.base_url}/api/entity-tags/{encoded}",
        )
        verify_argv = [
            sys.executable,
            "scripts/automation/worker_persistence.py",
            "verify-tags",
            "--raw-json-file",
            str(raw_output),
            *sum((["--add", tag] for tag in add or []), []),
            *sum((["--remove", tag] for tag in remove or []), []),
            "--json",
        ]
        return {
            **base_payload,
            "slug": slug,
            "encoded_slug": encoded,
            "payload_file": str(payload_file),
            "raw_output_file": str(raw_output),
            "commands": [
                {"step": "tags", "argv": tags_argv, "shell": _shell(tags_argv), "timeout_seconds": 90},
                {"step": "readback", "argv": read_argv, "shell": _shell(read_argv), "timeout_seconds": 45},
            ],
            "offline_verify": {"argv": verify_argv, "shell": _shell(verify_argv)},
        }
    raise WorkerPersistenceError(f"unsupported prepare action: {action}")


def _frontmatter_tags(markdown: str) -> set[str]:
    tags = _frontmatter_values(markdown).get("tags", [])
    if isinstance(tags, list):
        return {str(tag) for tag in tags if str(tag)}
    if isinstance(tags, str):
        return {tag.strip() for tag in tags.split(",") if tag.strip()}
    return set()


def _split_frontmatter(markdown: str) -> tuple[str, str]:
    if not markdown.startswith("---\n"):
        return "", markdown
    end = markdown.find("\n---", 4)
    if end < 0:
        return "", markdown
    body_start = end + len("\n---")
    if markdown[body_start : body_start + 1] == "\n":
        body_start += 1
    return markdown[4:end], markdown[body_start:]


def _frontmatter_scalars(markdown: str) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in _frontmatter_values(markdown).items()
        if not isinstance(value, list)
    }


def _strip_yaml_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _parse_inline_list(value: str) -> list[str]:
    inside = value.strip()[1:-1]
    if not inside.strip():
        return []
    return [_normalize_scalar(item) for item in inside.split(",")]


def _fold_block(lines: list[str], style: str) -> str:
    cleaned = [line[2:] if line.startswith("  ") else line.lstrip() for line in lines]
    if style.startswith("|"):
        value = "\n".join(cleaned)
    else:
        paragraphs: list[str] = []
        current: list[str] = []
        for line in cleaned:
            if line == "":
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append("")
            else:
                current.append(line)
        if current:
            paragraphs.append(" ".join(current))
        value = "\n".join(paragraphs)
    if not style.endswith("-"):
        value += "\n"
    return value


def _normalize_timestamp(value: str) -> str | None:
    candidate = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ][0-9:.+-]+|Z)?", candidate):
        return None
    try:
        parsed = dt.datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        try:
            return dt.date.fromisoformat(candidate).isoformat()
        except ValueError:
            return None
    if parsed.microsecond:
        return parsed.isoformat()
    return parsed.replace(microsecond=0).isoformat()


def _normalize_scalar(value: object) -> str:
    text = _strip_yaml_quotes(str(value))
    lowered = text.lower()
    if lowered in {"true", "false", "null"}:
        return lowered
    timestamp = _normalize_timestamp(text)
    if timestamp:
        return timestamp
    return text


def _frontmatter_values(markdown: str) -> dict[str, object]:
    frontmatter, _ = _split_frontmatter(markdown)
    values: dict[str, object] = {}
    lines = frontmatter.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith((" ", "-")) or ":" not in line:
            index += 1
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        index += 1
        if value in {">", ">-", "|", "|-"}:
            block: list[str] = []
            while index < len(lines) and (lines[index].startswith(" ") or not lines[index]):
                block.append(lines[index])
                index += 1
            values[key] = _normalize_scalar(_fold_block(block, value))
            continue
        if value == "":
            items: list[str] = []
            while index < len(lines) and lines[index].startswith(" "):
                match = re.match(r"^\s*-\s*(.+?)\s*$", lines[index])
                if match:
                    items.append(_normalize_scalar(match.group(1)))
                index += 1
            values[key] = items
            continue
        if value.startswith("[") and value.endswith("]"):
            values[key] = _parse_inline_list(value)
            continue
        values[key] = _normalize_scalar(value)
    return values


def _body_matches(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    expected_without_final = expected[:-1] if expected.endswith("\n") else expected
    actual_without_final = actual[:-1] if actual.endswith("\n") else actual
    return expected_without_final == actual_without_final


def _raw_readback_matches(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    expected_frontmatter, expected_body = _split_frontmatter(expected)
    actual_frontmatter, actual_body = _split_frontmatter(actual)
    if not expected_frontmatter or not actual_frontmatter or not _body_matches(expected_body, actual_body):
        return False
    expected_values = _frontmatter_values(expected)
    actual_values = _frontmatter_values(actual)
    for key, value in expected_values.items():
        if key == "tags":
            continue
        if actual_values.get(key) != value:
            return False
    return _frontmatter_tags(expected).issubset(_frontmatter_tags(actual))


def save_payload(path: Path) -> dict[str, str]:
    return {"content": path.read_text(encoding="utf-8")}


def tag_payload(add: list[str], remove: list[str]) -> dict[str, list[str]]:
    add_tags = sorted({tag.strip() for tag in add if tag.strip()})
    remove_tags = sorted({tag.strip() for tag in remove if tag.strip()})
    if not add_tags and not remove_tags:
        raise WorkerPersistenceError("at least one tag mutation is required")
    return {"add": add_tags, "remove": remove_tags}


def verify_save_payload(expected_path: Path, raw_payload_path: Path) -> dict[str, object]:
    expected = expected_path.read_text(encoding="utf-8")
    raw_payload = json.loads(raw_payload_path.read_text(encoding="utf-8"))
    actual = content_from_raw_payload(raw_payload)
    ok = _raw_readback_matches(expected, actual)
    return {"ok": ok, "body_policy": "exact_except_one_optional_final_newline"}


def verify_tags_payload(raw_payload_path: Path, add: list[str], remove: list[str]) -> dict[str, object]:
    raw_payload = json.loads(raw_payload_path.read_text(encoding="utf-8"))
    content = content_from_raw_payload(raw_payload)
    tags = _frontmatter_tags(content)
    missing = sorted({tag.strip() for tag in add if tag.strip() and tag.strip() not in tags})
    present = sorted({tag.strip() for tag in remove if tag.strip() and tag.strip() in tags})
    return {"ok": not missing and not present, "missing": missing, "present": present, "tags": sorted(tags)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist worker Run/report entities through the worker API.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--config", help="Deployment env file used for route resolution.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    routes_parser = subparsers.add_parser("routes", help="List unprobed route candidates for shell curl.")
    routes_parser.add_argument("--json", action="store_true", dest="command_json")
    routes_parser.add_argument("--shell", action="store_true", help="Emit tab-separated kind/base/flags/source rows.")

    encode_parser = subparsers.add_parser("encode-slug")
    encode_parser.add_argument("slug")

    save_payload_parser = subparsers.add_parser("save-payload")
    save_payload_parser.add_argument("--file", required=True)
    save_payload_parser.add_argument("--json", action="store_true", dest="command_json")

    tag_payload_parser = subparsers.add_parser("tag-payload")
    tag_payload_parser.add_argument("--add", action="append", default=[])
    tag_payload_parser.add_argument("--remove", action="append", default=[])
    tag_payload_parser.add_argument("--json", action="store_true", dest="command_json")

    content_parser = subparsers.add_parser("content-from-raw")
    content_parser.add_argument("--raw-json-file", required=True)

    verify_save_parser = subparsers.add_parser("verify-save")
    verify_save_parser.add_argument("--expected-file", required=True)
    verify_save_parser.add_argument("--raw-json-file", required=True)
    verify_save_parser.add_argument("--json", action="store_true", dest="command_json")

    verify_tags_parser = subparsers.add_parser("verify-tags")
    verify_tags_parser.add_argument("--raw-json-file", required=True)
    verify_tags_parser.add_argument("--add", action="append", default=[])
    verify_tags_parser.add_argument("--remove", action="append", default=[])
    verify_tags_parser.add_argument("--json", action="store_true", dest="command_json")

    prepare_parser = subparsers.add_parser("prepare", help="Prepare top-level curl command materials without network I/O.")
    prepare_parser.add_argument("action", choices=("health", "read", "save", "tags"))
    prepare_parser.add_argument("slug", nargs="?")
    prepare_parser.add_argument("--file")
    prepare_parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    prepare_parser.add_argument("--add", action="append", default=[])
    prepare_parser.add_argument("--remove", action="append", default=[])
    prepare_parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    prepare_parser.add_argument("--json", action="store_true", dest="command_json")

    args = parser.parse_args(argv)
    emit_json = bool(args.json or getattr(args, "command_json", False))
    try:
        if args.command == "routes":
            records = route_records(Path(args.config).expanduser() if args.config else None)
            if args.shell:
                for record in records:
                    kind = "loopback" if record["loopback"] else "non_loopback"
                    print(f"{kind}\t{record['base_url']}\t{record['curl_flags_shell']}\t{record['source']}")
                return 0
            payload: object = {"routes": records}
        elif args.command == "encode-slug":
            print(quote(args.slug, safe=""))
            return 0
        elif args.command == "save-payload":
            payload = save_payload(Path(args.file))
        elif args.command == "tag-payload":
            payload = tag_payload(args.add, args.remove)
        elif args.command == "content-from-raw":
            print(content_from_raw_payload(json.loads(Path(args.raw_json_file).read_text(encoding="utf-8"))))
            return 0
        elif args.command == "verify-save":
            payload = verify_save_payload(Path(args.expected_file), Path(args.raw_json_file))
        elif args.command == "verify-tags":
            payload = verify_tags_payload(Path(args.raw_json_file), args.add, args.remove)
        elif args.command == "prepare":
            payload = prepare_request(
                args.action,
                slug=args.slug,
                source_file=Path(args.file) if args.file else None,
                output_dir=Path(args.output_dir),
                add=args.add,
                remove=args.remove,
                config_path=Path(args.config).expanduser() if args.config else None,
                retries=args.retries,
            )
        else:
            raise AssertionError(args.command)
    except WorkerPersistenceError as exc:
        if emit_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"worker persistence failed: {exc}", file=sys.stderr)
        return 1

    if emit_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if isinstance(payload, dict) and "content" in payload:
            print(payload["content"])
        else:
            print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
