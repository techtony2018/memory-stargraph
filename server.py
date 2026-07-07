#!/usr/bin/env python3
import argparse
import email
import email.policy
import json
import math
import mimetypes
import os
import re
import shutil
import ssl
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.parse import parse_qs
from urllib.request import urlopen


APP_NAME = "Memory Stargraph"
ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8788,
    "public_dir": "public",
    "data_dir": "data",
    "gbrain_path": "/opt/homebrew/bin/gbrain",
    "max_list_pages": 140,
    "graph_depth": 1,
    "graph_stale_seconds": 300,
    "graph_command_limit": 140,
    "graph_command_pause_seconds": 0.2,
    "media_roots": ["media", "data/media"],
    "media_discovery_roots": ["media", "data/media", "data/uploads"],
    "remote_media_base_urls": [],
    "gbrain_file_base_urls": [],
    "gbrain_file_store_roots": [],
    "media_fetch_timeout_seconds": 8,
    "max_upload_bytes": 25 * 1024 * 1024,
}


def config_path():
    return Path(os.environ.get("MEMORY_STARGRAPH_CONFIG", ROOT / "config" / "local.json")).expanduser()


def resolve_project_path(value):
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else ROOT / path


def load_config():
    config = dict(DEFAULT_CONFIG)
    path = config_path()
    if path.exists():
        with path.open() as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise RuntimeError(f"Config must be a JSON object: {path}")
        config.update({key: value for key, value in loaded.items() if value is not None})
    return config


CONFIG = load_config()
PUBLIC_DIR = resolve_project_path(CONFIG["public_dir"])
DATA_DIR = resolve_project_path(CONFIG["data_dir"])
CACHE_PATH = DATA_DIR / "graph_cache.json"
DELETED_PATH = DATA_DIR / "deleted_entities.json"
HIDDEN_PATH = DATA_DIR / "hidden_entities.json"
GBRAIN = Path(str(CONFIG["gbrain_path"])).expanduser()
MAX_LIST_PAGES = int(CONFIG["max_list_pages"])
GRAPH_DEPTH = int(CONFIG["graph_depth"])
GRAPH_STALE_SECONDS = int(CONFIG["graph_stale_seconds"])
GRAPH_COMMAND_LIMIT = int(os.environ.get("MEMORY_STARGRAPH_GRAPH_COMMAND_LIMIT", str(CONFIG["graph_command_limit"])))
GRAPH_COMMAND_PAUSE_SECONDS = float(os.environ.get("MEMORY_STARGRAPH_GRAPH_COMMAND_PAUSE_SECONDS", str(CONFIG["graph_command_pause_seconds"])))
BACKLINK_SUPPLEMENT_MAX_EDGES = 200
BACKLINK_SUPPLEMENT_GRAPH_EDGE_THRESHOLD = 10
MEDIA_ROOTS = [
    resolve_project_path(root)
    for root in str(os.environ.get("MEMORY_STARGRAPH_MEDIA_ROOTS", "")).split(",")
    if root.strip()
] or [resolve_project_path(root) for root in CONFIG.get("media_roots", [])]
MEDIA_DISCOVERY_ROOTS = [
    resolve_project_path(root)
    for root in str(os.environ.get("MEMORY_STARGRAPH_MEDIA_DISCOVERY_ROOTS", "")).split(",")
    if root.strip()
] or [resolve_project_path(root) for root in CONFIG.get("media_discovery_roots", [])]
REMOTE_MEDIA_BASE_URLS = [
    url.rstrip("/") + "/"
    for url in (
        [value.strip() for value in str(os.environ.get("MEMORY_STARGRAPH_REMOTE_MEDIA_BASE_URLS", "")).split(",") if value.strip()]
        or CONFIG.get("remote_media_base_urls", [])
    )
    if str(url).strip()
]
GBRAIN_FILE_BASE_URLS = [
    url.rstrip("/") + "/"
    for url in (
        [value.strip() for value in str(os.environ.get("MEMORY_STARGRAPH_GBRAIN_FILE_BASE_URLS", "")).split(",") if value.strip()]
        or CONFIG.get("gbrain_file_base_urls", [])
    )
    if str(url).strip()
]
GBRAIN_FILE_STORE_ROOTS = [
    resolve_project_path(root)
    for root in str(os.environ.get("MEMORY_STARGRAPH_GBRAIN_FILE_STORE_ROOTS", "")).split(",")
    if root.strip()
] or [resolve_project_path(root) for root in CONFIG.get("gbrain_file_store_roots", [])]
MEDIA_FETCH_TIMEOUT_SECONDS = float(CONFIG.get("media_fetch_timeout_seconds", 8))
MAX_UPLOAD_BYTES = int(CONFIG.get("max_upload_bytes", 25 * 1024 * 1024))
VIEW_SCHEMA_VERSION = 5
UI_VERSION = "V1.0.92"
MAX_DISPLAY_LABEL_CHARS = int(CONFIG.get("max_display_label_chars", 20))
ROOT_INDEX_SLUG = "index"
PART_SLUG_RE = re.compile(r"^(?P<base>.+?)/part-\d{1,3}$", re.IGNORECASE)
PART_LABEL_RE = re.compile(r"^(?P<base>.+?)\s*[-–]\s*Part\s+\d{1,3}$", re.IGNORECASE)
GBRAIN_USAGE_RE = re.compile(r"^agent/reports/gbrain-usage-\d{4}-\d{2}-\d{2}$", re.IGNORECASE)
BLOCKED_SLUGS = {"people/darsha-krana", "people/tony-gu"}
BLOCKED_LABELS = {
    "people/darsha krana",
    "people/darsha-krana",
    "darsha krana",
    "people/tony gu",
    "people/tony-gu",
    "tony gu",
}
NODE_OPERATION_ENDPOINTS = [
    {"action": "create", "method": "POST", "endpoint": "/api/entity-create", "mutates_gbrain": True},
    {"action": "ask-yoda", "method": "POST", "endpoint": "/api/entity-ask-yoda/<slug>", "mutates_gbrain": False},
    {"action": "media", "method": "GET", "endpoint": "/api/entity-media/<slug>", "mutates_gbrain": False},
    {"action": "backlinks", "method": "POST", "endpoint": "/api/entity-backlinks/<slug>", "mutates_gbrain": False},
    {"action": "graph-query", "method": "POST", "endpoint": "/api/entity-graph-query/<slug>", "mutates_gbrain": False},
    {"action": "history", "method": "POST", "endpoint": "/api/entity-history/<slug>", "mutates_gbrain": False},
    {"action": "add-link", "method": "POST", "endpoint": "/api/entity-link/<slug>", "mutates_gbrain": True},
    {"action": "remove-link", "method": "POST", "endpoint": "/api/entity-unlink/<slug>", "mutates_gbrain": True},
    {"action": "tags", "method": "POST", "endpoint": "/api/entity-tags/<slug>", "mutates_gbrain": True},
    {"action": "timeline-view", "method": "GET", "endpoint": "/api/entity-timeline-view/<slug>", "mutates_gbrain": False},
    {"action": "timeline", "method": "POST", "endpoint": "/api/entity-timeline/<slug>", "mutates_gbrain": True},
    {"action": "attach-file", "method": "POST", "endpoint": "/api/entity-attach-file/<slug>", "mutates_gbrain": True},
    {"action": "embed", "method": "POST", "endpoint": "/api/entity-embed/<slug>", "mutates_gbrain": True},
]

MEDIA_EXTENSIONS = {
    "image": {".apng", ".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"},
    "video": {".m4v", ".mov", ".mp4", ".mpeg", ".mpg", ".ogv", ".webm"},
    "audio": {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".wav", ".webm"},
    "document": {".doc", ".docx", ".odt", ".pdf", ".rtf", ".rtfd", ".zip"},
}


DEMO_GRAPH = {
    "title": "Memory Stargraph",
    "source": {
        "mode": "demo",
        "status": "fallback",
        "message": "Using bundled demo data because gbrain was unavailable.",
        "updated_at": None,
    },
    "nodes": [
        {
            "id": "tony-codex",
            "slug": "tony-codex",
            "label": "Tony Codex",
            "type": "persona",
            "summary": "Operator node for Codex workstreams, automations, and repo sessions.",
            "tags": ["codex", "operator"],
            "links": ["collective-knowledge-system", "gbrain", "all-things-codex-dashboard", "resume-tailor"],
            "updated_at": "2026-06-27T08:00:00",
        },
        {
            "id": "collective-knowledge-system",
            "slug": "collective-knowledge-system",
            "label": "Collective Knowledge System",
            "type": "project",
            "summary": "Workspace for visualizing and navigating entity relationships from gbrain.",
            "tags": ["graph", "service"],
            "links": ["tony-codex", "tg-entity-graph", "gbrain", "all-things-codex-dashboard"],
            "updated_at": "2026-06-27T08:10:00",
        },
        {
            "id": "gbrain",
            "slug": "gbrain",
            "label": "gbrain",
            "type": "tool",
            "summary": "Personal knowledge brain CLI exposing pages, backlinks, and graph traversals.",
            "tags": ["cli", "knowledge"],
            "links": ["tony-codex", "collective-knowledge-system", "entity-links", "remote-brain", "tg-entity-graph"],
            "updated_at": "2026-06-27T08:15:00",
        },
        {
            "id": "tg-entity-graph",
            "slug": "tg-entity-graph",
            "label": "Memory Stargraph",
            "type": "feature",
            "summary": "Star-cloud entity visualization with search, focus, and relationship detail views.",
            "tags": ["ui", "graph"],
            "links": ["collective-knowledge-system", "gbrain", "starfield-ui", "all-things-codex-dashboard"],
            "updated_at": "2026-06-27T08:20:00",
        },
        {
            "id": "starfield-ui",
            "slug": "starfield-ui",
            "label": "Starfield UI",
            "type": "design",
            "summary": "Nebula and constellation-inspired presentation for browsing knowledge clusters.",
            "tags": ["design", "visual"],
            "links": ["tg-entity-graph", "entity-links", "all-things-codex-dashboard"],
            "updated_at": "2026-06-27T08:30:00",
        },
        {
            "id": "entity-links",
            "slug": "entity-links",
            "label": "Entity Links",
            "type": "data",
            "summary": "Direct connection counts determine node mass, radius, and neighborhood emphasis.",
            "tags": ["edges", "metrics"],
            "links": ["gbrain", "tg-entity-graph", "starfield-ui", "remote-brain"],
            "updated_at": "2026-06-27T08:35:00",
        },
        {
            "id": "all-things-codex-dashboard",
            "slug": "all-things-codex-dashboard",
            "label": "All Things Codex Dashboard",
            "type": "dashboard",
            "summary": "External dashboard that can embed or launch the Memory Stargraph graph service.",
            "tags": ["dashboard", "integration"],
            "links": ["tony-codex", "collective-knowledge-system", "tg-entity-graph", "starfield-ui"],
            "updated_at": "2026-06-27T08:40:00",
        },
        {
            "id": "resume-tailor",
            "slug": "resume-tailor",
            "label": "Resume Tailor",
            "type": "project",
            "summary": "Daily role-finding automation that feeds Tony's manager-level job search.",
            "tags": ["automation", "resume"],
            "links": ["tony-codex", "remote-brain", "knowledge-daily-loop"],
            "updated_at": "2026-06-27T08:50:00",
        },
        {
            "id": "remote-brain",
            "slug": "remote-brain",
            "label": "Remote Brain",
            "type": "infrastructure",
            "summary": "Thin-client gbrain setup that may be unreachable and trigger local fallback mode.",
            "tags": ["remote", "health"],
            "links": ["gbrain", "entity-links", "resume-tailor", "knowledge-daily-loop"],
            "updated_at": "2026-06-27T09:00:00",
        },
        {
            "id": "knowledge-daily-loop",
            "slug": "knowledge-daily-loop",
            "label": "Knowledge Daily Loop",
            "type": "workflow",
            "summary": "Morning reports, syncs, and graph refreshes that keep entities current.",
            "tags": ["workflow", "daily"],
            "links": ["resume-tailor", "remote-brain", "graph-cache"],
            "updated_at": "2026-06-27T09:05:00",
        },
        {
            "id": "graph-cache",
            "slug": "graph-cache",
            "label": "Graph Cache",
            "type": "storage",
            "summary": "Latest successful graph snapshot persisted locally for faster warm starts.",
            "tags": ["cache", "json"],
            "links": ["knowledge-daily-loop", "service-health"],
            "updated_at": "2026-06-27T09:08:00",
        },
        {
            "id": "service-health",
            "slug": "service-health",
            "label": "Service Health",
            "type": "ops",
            "summary": "Health endpoint describing whether the graph came from live gbrain, cache, or demo data.",
            "tags": ["ops", "health"],
            "links": ["graph-cache", "collective-knowledge-system"],
            "updated_at": "2026-06-27T09:10:00",
        },
    ],
}


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def normalize_slug(value):
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "entity"


def entity_slug_from_name(name, category):
    category_slug = normalize_slug(category or "entities")
    name_slug = normalize_slug(name)
    return f"{category_slug}/{name_slug}"


def yaml_scalar(value):
    text = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def create_entity_markdown(name, description, category):
    clean_name = str(name or "").strip()
    clean_category = normalize_slug(category or "entities")
    clean_description = str(description or "").strip()
    body = clean_description or f"{clean_name}."
    return "\n".join(
        [
            "---",
            f"type: {yaml_scalar(clean_category)}",
            f"title: {yaml_scalar(clean_name)}",
            "source: \"memory-stargraph\"",
            "---",
            "",
            f"# {clean_name}",
            "",
            body,
            "",
        ]
    )


def decode_process_output(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_gbrain(*args, input_text=None, timeout=20):
    if not GBRAIN.exists():
        raise FileNotFoundError(f"gbrain not found at {GBRAIN}")
    command = [str(GBRAIN), *args]
    env = os.environ.copy()
    bun_bin = Path.home() / ".bun" / "bin"
    env["PATH"] = f"{bun_bin}:/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=env,
        input=input_text.encode("utf-8") if isinstance(input_text, str) else input_text,
    )
    if result.returncode != 0:
        stderr = decode_process_output(result.stderr).strip()
        stdout = decode_process_output(result.stdout).strip()
        message = stderr or stdout or f"gbrain exited with status {result.returncode}"
        raise RuntimeError(message)
    return decode_process_output(result.stdout)


def extract_json_object(text):
    source = str(text or "")
    decoder = json.JSONDecoder()
    for index, char in enumerate(source):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(source[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def extract_json_list(text):
    source = str(text or "")
    decoder = json.JSONDecoder()
    for index, char in enumerate(source):
        if char != "[":
            continue
        try:
            payload, _ = decoder.raw_decode(source[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            return payload
    return None


def extract_openclaw_answer(output):
    payload = extract_json_object(output)
    if not payload:
        return ""
    for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    payloads = payload.get("payloads")
    if isinstance(payloads, list):
        parts = []
        for item in payloads:
            if isinstance(item, dict) and str(item.get("text") or "").strip():
                parts.append(str(item["text"]).strip())
        if parts:
            return "\n\n".join(parts)
    return ""


def safe_preview(value, limit=600):
    text = decode_process_output(value).strip()
    text = re.sub(r"(?i)(api[_-]?key|token|authorization|password)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    return text[:limit]


def run_openclaw_agent(prompt, timeout=45, return_details=False):
    agent_ref = str(CONFIG.get("yoda_agent") or os.environ.get("MEMORY_STARGRAPH_YODA_AGENT") or "").strip()
    command = [
        "openclaw",
        "agent",
        "--local",
        "--json",
        "--timeout",
        str(max(5, int(timeout) - 5)),
        "--session-key",
        "agent:memory-stargraph-ask-yoda:web",
        "--message",
        prompt,
    ]
    if agent_ref:
        command.extend(["--agent", agent_ref])
    env = os.environ.copy()
    bun_bin = Path.home() / ".bun" / "bin"
    env["PATH"] = f"{bun_bin}:/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
    details = {
        "openclaw_status": "unknown",
        "model_status": "unknown",
        "fallback_used": False,
        "stdout_preview": "",
        "stderr_preview": "",
        "error_summary": "",
    }
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        details.update({"openclaw_status": "unavailable", "model_status": "unavailable", "error_summary": str(exc)})
        return {"output": None, **details} if return_details else None
    except subprocess.TimeoutExpired as exc:
        details.update({
            "openclaw_status": "timeout",
            "model_status": "timeout",
            "error_summary": f"OpenClaw agent timed out after {timeout}s",
            "stdout_preview": safe_preview(exc.stdout),
            "stderr_preview": safe_preview(exc.stderr),
        })
        return {"output": None, **details} if return_details else None
    details["stdout_preview"] = safe_preview(result.stdout)
    details["stderr_preview"] = safe_preview(result.stderr)
    if result.returncode != 0:
        details.update({
            "openclaw_status": f"exit_{result.returncode}",
            "model_status": "nonzero_exit",
            "error_summary": details["stderr_preview"] or details["stdout_preview"] or f"OpenClaw exited with status {result.returncode}",
        })
        return {"output": None, **details} if return_details else None
    output = "\n".join(
        value
        for value in (
            decode_process_output(result.stdout),
            decode_process_output(result.stderr),
        )
        if value
    )
    answer = extract_openclaw_answer(output) or None
    details.update({
        "openclaw_status": "ok",
        "model_status": "answered" if answer else "empty_output",
    })
    return {"output": answer, **details} if return_details else answer


def sanitize_yoda_result(result):
    payload = dict(result or {})
    output = str(payload.get("output") or "").strip()
    raw_markers = [
        "Question-specific gbrain retrieval:",
        "Direct relationship context:",
        "Selected node content:",
        "OpenClaw agent unavailable; using deterministic GBrain retrieval fallback.",
    ]
    if any(marker in output for marker in raw_markers):
        output = re.split(
            r"(?:Question-specific gbrain retrieval:|Direct relationship context:|Selected node content:)",
            output,
            maxsplit=1,
        )[0]
        output = output.replace("OpenClaw agent unavailable; using deterministic GBrain retrieval fallback.", "").strip()
        if not output:
            output = "I found graph context for this node, but the answer model is unavailable right now. Try again after the Ask Yoda agent is reachable."
    payload["output"] = output
    payload.pop("prompt", None)
    diagnostics = dict(payload.get("diagnostics") or {})
    timings = payload.get("timings") or diagnostics.get("timings") or {}
    diagnostics["timings"] = timings
    diagnostics.setdefault("request_id", payload.get("request_id") or f"yoda-{int(time.time() * 1000)}")
    diagnostics.setdefault("source", payload.get("source") or "unknown")
    diagnostics.setdefault("fallback_used", payload.get("source") == "fallback")
    diagnostics.setdefault("model_status", "unknown")
    payload["diagnostics"] = diagnostics
    payload["request_id"] = diagnostics["request_id"]
    return payload


def clamp_yoda_depth(value):
    try:
        depth = int(value)
    except (TypeError, ValueError):
        depth = 4
    return max(1, min(6, depth))


def parse_slugs(raw_text):
    slugs = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("Usage:"):
            continue
        match = re.search(r"\[\[([^\]]+)\]\]", line)
        if match:
            slugs.append(match.group(1).strip())
            continue
        if line.startswith("- "):
            token = line[2:].split()[0]
            slugs.append(token.strip())
            continue
        token = line.split()[0]
        if re.fullmatch(r"[A-Za-z0-9._:/-]+", token):
            slugs.append(token.strip())
    seen = set()
    ordered = []
    for slug in slugs:
        normalized = slug.strip().strip(",")
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def parse_page_list(output):
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        if len(parts) == 4:
            rows.append(
                {
                    "slug": parts[0],
                    "type": parts[1],
                    "date": parts[2],
                    "title": parts[3],
                }
            )
    return rows


def parse_search_results(output):
    results = []
    for line in output.splitlines():
        match = re.match(r"^\[(?P<score>[0-9.]+)\]\s+(?P<slug>\S+)\s+--\s*(?P<preview>.*)$", line)
        if not match:
            continue
        preview = match.group("preview").strip()
        label = re.sub(r"^#+\s*", "", preview).strip() or make_label(match.group("slug"))
        results.append(
            {
                "slug": match.group("slug"),
                "score": float(match.group("score")),
                "label": label[:120],
                "preview": preview,
            }
        )
    return results


def safe_upload_filename(filename):
    name = Path(str(filename or "upload.bin")).name.strip()
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "upload.bin"


def parse_multipart_form(content_type, body):
    if "boundary=" not in str(content_type or ""):
        raise ValueError("multipart boundary is missing")
    message = email.message_from_bytes(
        b"Content-Type: " + str(content_type).encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body,
        policy=email.policy.default,
    )
    fields = {}
    files = {}
    if not message.is_multipart():
        return fields, files
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if "form-data" not in disposition:
            continue
        name = part.get_param("name", header="Content-Disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = {
                "filename": safe_upload_filename(filename),
                "content_type": part.get_content_type(),
                "data": payload,
            }
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return fields, files


def save_uploaded_file(slug, upload):
    filename = safe_upload_filename(upload.get("filename"))
    target_dir = DATA_DIR / "uploads" / re.sub(r"[^A-Za-z0-9._-]+", "_", slug.strip("/") or "root")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_bytes(upload.get("data") or b"")
    return target


def parse_frontmatter(markdown):
    if not markdown.startswith("---"):
        return {}, markdown
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", markdown, flags=re.DOTALL)
    if not match:
        return {}, markdown
    raw_meta, body = match.groups()
    meta = {}
    current_key = None
    for line in raw_meta.splitlines():
        if line.startswith("  - ") and current_key:
            meta.setdefault(current_key, []).append(line[4:].strip().strip("'\""))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            meta[key] = []
            current_key = key
        else:
            meta[key] = value.strip("'\"")
            current_key = key
    return meta, body


def media_kind_for_url(url):
    clean_url = str(url or "").strip().split("?", 1)[0].split("#", 1)[0].lower()
    suffix = Path(clean_url).suffix
    for media_kind, extensions in MEDIA_EXTENSIONS.items():
        if suffix in extensions:
            return media_kind
    if clean_url.startswith("data:image/"):
        return "image"
    if clean_url.startswith("data:video/"):
        return "video"
    if clean_url.startswith("data:audio/"):
        return "audio"
    return "link"


def is_embeddable_media_url(url):
    text = str(url or "").strip()
    return text.startswith(("http://", "https://", "data:"))


def is_supported_media_path(path):
    return media_kind_for_url(path) != "link"


GBRAIN_FILE_SCHEME = "gbrain:files/"


def normalize_media_reference(value):
    text = str(value or "").strip()
    if text.startswith(GBRAIN_FILE_SCHEME):
        return text[len(GBRAIN_FILE_SCHEME) :]
    return text


def safe_media_relative_path(value):
    text = normalize_media_reference(value)
    if text.startswith("/media/"):
        text = text.split("/media/", 1)[1]
    if not text or urlparse(text).scheme or text.startswith(("/", "\\")):
        return None
    parts = Path(unquote(text)).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    if not is_supported_media_path(text):
        return None
    return Path(*parts)


def serve_url_for_media_reference(value):
    relative_path = safe_media_relative_path(value)
    if not relative_path:
        return None
    return media_served_url_for_relative_path(relative_path)


def media_served_url_for_relative_path(relative_path):
    if isinstance(relative_path, Path):
        safe_path = relative_path
    else:
        safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return None
    return "/media/" + "/".join(quote(part) for part in safe_path.parts)


def resolve_media_file_path(request_path):
    if not str(request_path or "").startswith("/media/"):
        return None
    relative_path = safe_media_relative_path(str(request_path).split("/media/", 1)[1])
    if not relative_path:
        return None
    for root in MEDIA_ROOTS:
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def media_destination_for_relative_path(relative_path):
    if not MEDIA_ROOTS:
        return None
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return None
    return MEDIA_ROOTS[0] / safe_path


def find_media_source_file(relative_path):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return None
    for root in MEDIA_DISCOVERY_ROOTS:
        expanded_root = root.expanduser()
        exact = (expanded_root / safe_path).resolve()
        try:
            exact.relative_to(expanded_root.resolve())
        except ValueError:
            continue
        if exact.is_file():
            return exact
        by_name = (expanded_root / safe_path.name).resolve()
        try:
            by_name.relative_to(expanded_root.resolve())
        except ValueError:
            continue
        if by_name.is_file():
            return by_name
    for root in MEDIA_DISCOVERY_ROOTS:
        expanded_root = root.expanduser()
        if not expanded_root.is_dir():
            continue
        checked = 0
        for dirpath, dirnames, filenames in os.walk(expanded_root):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")][:20]
            checked += len(filenames)
            if checked > 5000:
                break
            if safe_path.name in filenames:
                return Path(dirpath) / safe_path.name
    return None


def find_gbrain_stored_file(relative_path):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return None
    for root in GBRAIN_FILE_STORE_ROOTS:
        expanded_root = root.expanduser()
        candidate = (expanded_root / safe_path).resolve()
        try:
            candidate.relative_to(expanded_root.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def copy_media_source_to_root(source_path, relative_path):
    destination = media_destination_for_relative_path(relative_path)
    if not destination:
        return None
    source = Path(source_path).expanduser()
    if not source.is_file() or not is_supported_media_path(source.name):
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    served_url = media_served_url_for_relative_path(relative_path)
    return {
        "path": str(destination),
        "served_url": served_url,
        "served_available": bool(resolve_media_file_path(served_url)),
        "source": str(source),
    }


def copy_file_to_gbrain_store(source_path, relative_path):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path or not GBRAIN_FILE_STORE_ROOTS:
        return None
    source = Path(source_path).expanduser()
    if not source.is_file() or not is_supported_media_path(source.name):
        return None
    for root in GBRAIN_FILE_STORE_ROOTS:
        destination = root.expanduser() / safe_path
        try:
            destination.resolve().relative_to(root.expanduser().resolve())
        except ValueError:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination
    return None


def extract_first_http_url(text):
    match = re.search(r"https?://[^\s\"'<>]+", str(text or ""))
    return match.group(0) if match else None


def download_media_url_to_root(url, relative_path):
    destination = media_destination_for_relative_path(relative_path)
    if not destination:
        return None
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"}:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=MEDIA_FETCH_TIMEOUT_SECONDS) as response:
        destination.write_bytes(response.read())
    served_url = media_served_url_for_relative_path(relative_path)
    return {
        "path": str(destination),
        "served_url": served_url,
        "served_available": bool(resolve_media_file_path(served_url)),
        "source": url,
    }


def remote_media_url_for_relative_path(base_url, relative_path):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return None
    parsed = urlparse(str(base_url or ""))
    if parsed.scheme not in {"http", "https"}:
        return None
    return str(base_url).rstrip("/") + "/" + "/".join(quote(part) for part in safe_path.parts)


def gbrain_file_url_for_relative_path(base_url, relative_path):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return None
    parsed = urlparse(str(base_url or ""))
    if parsed.scheme not in {"http", "https"}:
        return None
    return str(base_url).rstrip("/") + "/" + "/".join(quote(part) for part in safe_path.parts)


def try_gbrain_signed_media_url(relative_path):
    try:
        output = run_gbrain("files", "signed-url", str(relative_path))
    except Exception:  # noqa: BLE001
        return None
    return extract_first_http_url(output)


def ensure_media_reference_available(item):
    served_url = item.get("served_url")
    if not served_url or item.get("served_available"):
        return item
    relative_path = safe_media_relative_path(str(served_url).split("/media/", 1)[1] if "/media/" in served_url else item.get("url"))
    if not relative_path:
        return item
    result = None
    source_file = find_media_source_file(relative_path)
    if source_file:
        result = copy_media_source_to_root(source_file, relative_path)
    if not result and str(item.get("url") or "").strip().startswith(GBRAIN_FILE_SCHEME):
        for base_url in GBRAIN_FILE_BASE_URLS:
            gbrain_file_url = gbrain_file_url_for_relative_path(base_url, relative_path)
            if not gbrain_file_url:
                continue
            try:
                result = download_media_url_to_root(gbrain_file_url, relative_path)
            except Exception:  # noqa: BLE001
                result = None
            if result:
                break
    if not result:
        for base_url in REMOTE_MEDIA_BASE_URLS:
            remote_url = remote_media_url_for_relative_path(base_url, relative_path)
            if not remote_url:
                continue
            try:
                result = download_media_url_to_root(remote_url, relative_path)
            except Exception:  # noqa: BLE001
                result = None
            if result:
                break
    if not result:
        signed_url = try_gbrain_signed_media_url(relative_path)
        if signed_url:
            try:
                result = download_media_url_to_root(signed_url, relative_path)
            except Exception:  # noqa: BLE001
                result = None
    if result:
        item = dict(item)
        item["served_available"] = result["served_available"]
        item["materialized_from"] = result["source"]
    return item


def ensure_media_references_available(items):
    return [ensure_media_reference_available(dict(item)) for item in items]


def materialize_gbrain_file_reference(relative_path):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return None
    served_url = media_served_url_for_relative_path(safe_path)
    if served_url and resolve_media_file_path(served_url):
        return {
            "served_available": True,
            "source": "media-cache",
            "served_url": served_url,
        }
    stored_file = find_gbrain_stored_file(safe_path)
    if stored_file:
        return copy_media_source_to_root(stored_file, safe_path)
    source_file = find_media_source_file(safe_path)
    if source_file:
        return copy_media_source_to_root(source_file, safe_path)
    for base_url in REMOTE_MEDIA_BASE_URLS:
        remote_url = remote_media_url_for_relative_path(base_url, safe_path)
        if not remote_url:
            continue
        try:
            result = download_media_url_to_root(remote_url, safe_path)
        except Exception:  # noqa: BLE001
            result = None
        if result:
            return result
    signed_url = try_gbrain_signed_media_url(safe_path)
    if signed_url:
        try:
            return download_media_url_to_root(signed_url, safe_path)
        except Exception:  # noqa: BLE001
            return None
    return None


def local_media_destination_for_slug(slug, file_path, raw_markdown=""):
    source = Path(str(file_path or "")).expanduser()
    if not source.is_file() or not is_supported_media_path(source.name):
        return None
    candidates = []
    referenced_paths = []
    if raw_markdown:
        for item in parse_media_references(raw_markdown):
            relative_path = safe_media_relative_path(item.get("url"))
            if relative_path:
                referenced_paths.append(relative_path)
                if relative_path.name == source.name:
                    candidates.append(relative_path)
    fallback_path = safe_media_relative_path(f"{slug.strip('/')}/{source.name}")
    if fallback_path:
        candidates.append(fallback_path)
    if not candidates or not MEDIA_ROOTS:
        return None
    return MEDIA_ROOTS[0] / candidates[0]


def materialize_local_media_for_slug(slug, file_path, raw_markdown=""):
    destination = local_media_destination_for_slug(slug, file_path, raw_markdown)
    if not destination:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(str(file_path)).expanduser(), destination)
    try:
        relative_path = destination.resolve().relative_to(MEDIA_ROOTS[0].resolve())
    except ValueError:
        return None
    served_url = media_served_url_for_relative_path(relative_path)
    return {
        "path": str(destination),
        "served_url": served_url,
        "served_available": bool(resolve_media_file_path(served_url)),
    }


def relative_path_for_local_media(local_media):
    if not local_media:
        return None
    served_url = str(local_media.get("served_url") or "")
    if served_url.startswith("/media/"):
        return safe_media_relative_path(served_url.split("/media/", 1)[1])
    media_path = local_media.get("path")
    if media_path:
        path = Path(media_path).expanduser()
        for root in MEDIA_ROOTS:
            try:
                return path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
    return None


def markdown_link_label(relative_path):
    stem = Path(str(relative_path or "attachment")).stem.replace("-", " ").replace("_", " ").strip()
    return stem or "Attachment"


def escape_markdown_label(label):
    return str(label or "Attachment").replace("[", "\\[").replace("]", "\\]")


def attachment_markdown_line(relative_path, description=""):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return ""
    label = escape_markdown_label(str(description or "").strip() or markdown_link_label(safe_path))
    url = "/".join(safe_path.parts)
    if media_kind_for_url(url) == "image":
        return f"![{label}]({url})"
    return f"[{label}]({url})"


def append_attachment_reference(markdown, relative_path, description=""):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return markdown
    url = "/".join(safe_path.parts)
    text = str(markdown or "")
    if url in text or f"/media/{url}" in text:
        return text
    line = attachment_markdown_line(safe_path, description)
    if not line:
        return text
    trimmed = text.rstrip()
    if re.search(r"^##\s+Attachments\s*$", trimmed, flags=re.MULTILINE):
        return f"{trimmed}\n\n{line}\n"
    return f"{trimmed}\n\n## Attachments\n\n{line}\n" if trimmed else f"## Attachments\n\n{line}\n"


def looks_like_media_key(key):
    normalized = str(key or "").lower()
    return any(
        token in normalized
        for token in ("image", "photo", "picture", "avatar", "thumbnail", "media", "attachment", "file")
    )


def looks_like_media_location(value):
    text = str(value or "").strip()
    return bool(re.search(r"^(https?://|data:|/|\./|\.\./)", text) or re.search(r"[\\/].+\.[A-Za-z0-9]{2,6}$", text))


def iter_frontmatter_media_values(value):
    if isinstance(value, str):
        yield value, ""
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item, ""
            elif isinstance(item, dict):
                url = item.get("url") or item.get("path") or item.get("src") or item.get("href")
                label = item.get("label") or item.get("title") or item.get("name") or ""
                if url:
                    yield url, label
    elif isinstance(value, dict):
        url = value.get("url") or value.get("path") or value.get("src") or value.get("href")
        label = value.get("label") or value.get("title") or value.get("name") or ""
        if url:
            yield url, label


def parse_media_references(markdown):
    items = []
    seen = set()

    def markdown_destination(value):
        text = str(value or "").strip()
        title_match = re.match(r'^(?P<url>.+?)\s+"[^"]*"\s*$', text)
        return (title_match.group("url") if title_match else text).strip()

    def add_item(kind, url, label="", source="markdown"):
        clean_url = str(url or "").strip()
        if not clean_url or clean_url in seen:
            return
        seen.add(clean_url)
        detected_kind = kind if kind != "link" else media_kind_for_url(clean_url)
        served_url = serve_url_for_media_reference(clean_url)
        items.append(
            {
                "kind": detected_kind,
                "url": clean_url,
                "label": str(label or "").strip() or Path(clean_url.split("?", 1)[0]).name or clean_url,
                "source": source,
                "embeddable": is_embeddable_media_url(clean_url),
                "served_url": served_url,
                "served_available": bool(resolve_media_file_path(served_url)) if served_url else False,
            }
        )

    text = str(markdown or "")
    meta, body = parse_frontmatter(text)
    for key, value in meta.items():
        for url, label in iter_frontmatter_media_values(value):
            kind = media_kind_for_url(url)
            if kind != "link" or (looks_like_media_key(key) and looks_like_media_location(url)):
                add_item(kind, url, label or key.replace("_", " "), f"frontmatter:{key}")

    text = body
    for match in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", text):
        add_item("image", markdown_destination(match.group(2)), match.group(1), "markdown_image")
    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        url = markdown_destination(match.group(2))
        kind = media_kind_for_url(url)
        if kind != "link":
            add_item(kind, url, match.group(1), "markdown_link")
    for match in re.finditer(r"""<(img|video|audio|source)\b[^>]*\bsrc=["']([^"']+)["'][^>]*>""", text, flags=re.IGNORECASE):
        tag = match.group(1).lower()
        kind = "image" if tag == "img" else "video" if tag in {"video", "source"} else "audio"
        add_item(kind, match.group(2), "", f"html_{tag}")
    return items


def parse_neighbors(raw_text, center_slug):
    graph_nodes = extract_json_list(raw_text)
    if isinstance(graph_nodes, list):
        edges = set()
        for graph_node in graph_nodes:
            if not isinstance(graph_node, dict):
                continue
            source = str(graph_node.get("slug") or "")
            if not source:
                continue
            for link in graph_node.get("links") or []:
                if not isinstance(link, dict):
                    continue
                target = str(link.get("to_slug") or "")
                if not target or target == source:
                    continue
                if source == center_slug or target == center_slug:
                    edges.add(tuple(sorted((source, target))))
        return edges

    edges = set()
    slugs = parse_slugs(raw_text)
    for slug in slugs:
        if slug != center_slug:
            edges.add(tuple(sorted((center_slug, slug))))
    for line in raw_text.splitlines():
        hits = re.findall(r"([A-Za-z0-9._:/-]{3,})", line)
        if center_slug not in line or len(hits) < 2:
            continue
        for slug in hits:
            if slug != center_slug:
                edges.add(tuple(sorted((center_slug, slug))))
    return edges


def edge_key(left, right):
    return tuple(sorted((left, right)))


def parse_link_types(raw_text, center_slug):
    edge_types = defaultdict(set)
    graph_nodes = extract_json_list(raw_text)
    if not isinstance(graph_nodes, list):
        return edge_types

    for graph_node in graph_nodes:
        if not isinstance(graph_node, dict):
            continue
        source = str(graph_node.get("slug") or "").strip()
        if not source:
            continue
        for link in graph_node.get("links") or []:
            if not isinstance(link, dict):
                continue
            target = str(link.get("to_slug") or "").strip()
            link_type = str(link.get("link_type") or "").strip()
            if source and target and source != target and link_type and (source == center_slug or target == center_slug):
                edge_types[edge_key(source, target)].add(link_type)
    return edge_types


def parse_backlinks(raw_text, center_slug):
    edges = set()
    backlinks = extract_json_list(raw_text)

    if isinstance(backlinks, list):
        for backlink in backlinks:
            if not isinstance(backlink, dict):
                continue
            source = str(backlink.get("from_slug") or "").strip()
            target = str(backlink.get("to_slug") or center_slug).strip()
            if source and target and source != target:
                edges.add(tuple(sorted((source, target))))
        return edges

    for slug in parse_slugs(raw_text):
        if slug != center_slug:
            edges.add(tuple(sorted((center_slug, slug))))
    return edges


def parse_backlink_types(raw_text, center_slug):
    edge_types = defaultdict(set)
    backlinks = extract_json_list(raw_text)
    if not isinstance(backlinks, list):
        return edge_types

    for backlink in backlinks:
        if not isinstance(backlink, dict):
            continue
        source = str(backlink.get("from_slug") or "").strip()
        target = str(backlink.get("to_slug") or center_slug).strip()
        link_type = str(backlink.get("link_type") or "").strip()
        if source and target and source != target and link_type:
            edge_types[edge_key(source, target)].add(link_type)
    return edge_types


def merge_edge_types(target, source):
    for key, values in source.items():
        target[key].update(values)


def edge_types_payload(edge_types):
    return [
        {"source": left, "target": right, "types": sorted(types)}
        for (left, right), types in sorted(edge_types.items())
        if types
    ]


def choose_backlink_supplement_edges(graph_edges, backlink_edges, backlink_types):
    explicit_neighbor_edges = {
        edge for edge in backlink_edges
        if any(str(value).strip().lower() == "neighbor" for value in backlink_types.get(edge, set()))
    }
    if len(graph_edges) < BACKLINK_SUPPLEMENT_GRAPH_EDGE_THRESHOLD or len(backlink_edges) <= BACKLINK_SUPPLEMENT_MAX_EDGES:
        return set(backlink_edges)
    return explicit_neighbor_edges


def filter_edge_types(edge_types, allowed_edges):
    return {key: values for key, values in edge_types.items() if key in allowed_edges}


def is_wechat_category(slug):
    slug_text = str(slug or "").strip().lower()
    segments = [segment for segment in slug_text.split("/") if segment]
    return any(segment.startswith("wechat") for segment in segments)


def strip_wechat_identity_suffix(value):
    text = str(value or "").strip()
    cleaned = re.sub(
        r"[-_\s]+(?:\d{6,}|(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{8,})$",
        "",
        text,
    ).strip()
    return cleaned or text


def is_people_category(slug):
    slug_text = str(slug or "").strip().lower()
    category = slug_text.split("/", 1)[0] if "/" in slug_text else slug_text
    return category == "people"


def strip_people_identity_suffix(value):
    text = str(value or "").strip()
    cleaned = re.sub(
        r"[-_\s]+(?:\d{5,}|(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{8,})$",
        "",
        text,
    ).strip()
    return cleaned or text


def limit_display_label(value, fallback=""):
    text = str(value or "").strip() or str(fallback or "").strip()
    if len(text) <= MAX_DISPLAY_LABEL_CHARS:
        return text
    if MAX_DISPLAY_LABEL_CHARS <= 3:
        return text[:MAX_DISPLAY_LABEL_CHARS]
    return f"{text[:MAX_DISPLAY_LABEL_CHARS - 3].rstrip()}..."


def make_label(slug):
    slug_text = str(slug or "").strip().rstrip("/")
    leaf = slug_text.split("/")[-1] if "/" in slug_text else slug_text
    if is_wechat_category(slug_text):
        leaf = strip_wechat_identity_suffix(leaf)
    elif is_people_category(slug_text):
        leaf = strip_people_identity_suffix(leaf)
    cleaned = leaf.replace("-", " ").replace("_", " ").strip()
    words = [word.capitalize() for word in cleaned.split()]
    return limit_display_label(" ".join(words) if words else slug_text)


def friendly_label(slug, label=None):
    slug_text = str(slug or "").strip()
    label_text = str(label or "").strip()
    if not label_text:
        return make_label(slug_text)
    category = slug_text.split("/", 1)[0].lower() if "/" in slug_text else ""
    if category and label_text.lower().startswith(f"{category}/"):
        return make_label(slug_text)
    if is_wechat_category(slug_text):
        cleaned = strip_wechat_identity_suffix(label_text)
        return limit_display_label(cleaned, make_label(slug_text))
    if is_people_category(slug_text):
        cleaned = strip_people_identity_suffix(label_text)
        return limit_display_label(cleaned, make_label(slug_text))
    return limit_display_label(label_text, make_label(slug_text))


def is_placeholder_entity_summary(summary):
    text = str(summary or "").strip().lower()
    return (
        not text
        or text in {"summary", "metadata", "no summary available."}
        or text.startswith("metadata\n")
        or text.startswith("discovered by lazy")
    )


def markdown_sections(body):
    text = str(body or "")
    sections = []
    current_heading = ""
    current_lines = []
    for line in text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            if current_heading or current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = heading.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_heading or current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return sections


def clean_summary_candidate(block, label=""):
    cleaned = re.sub(r"(?m)^#+\s*", "", str(block or "").strip()).strip()
    cleaned = re.sub(r"(?m)^[-*]\s*(Source file|Source|Author|Published|Collection|Date|Tags?):.*$", "", cleaned).strip()
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", cleaned).strip()
    cleaned = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", cleaned)
    cleaned = re.sub(r"\[\[([^\]]+)\]\]", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    label_text = str(label or "").strip()
    if not cleaned or cleaned == label_text:
        return ""
    if cleaned.lower() in {"summary", "metadata", "attachments", "media", "comments"}:
        return ""
    if cleaned.startswith("[["):
        return ""
    return cleaned


def extract_summary_from_markdown_body(body, label="", entity_type=""):
    sections = markdown_sections(body)
    entity_type_text = str(entity_type or "").lower()
    skip_headings = {"metadata", "attachments", "attached photo", "media", "comments", "links", "timeline"}
    profile_headings = ["summary", "about", "profile", "bio", "biography", "description", "overview"]
    article_headings = ["content", "body", "article", "post"]
    preferred_headings = article_headings if any(token in entity_type_text for token in ("post", "blog", "article")) else profile_headings + article_headings
    candidates = []
    for wanted in preferred_headings:
        for heading, content in sections:
            if heading.strip().lower() == wanted:
                candidates.extend(re.split(r"\n\s*\n", content))
    for heading, content in sections:
        heading_key = heading.strip().lower()
        if heading_key in skip_headings:
            continue
        candidates.extend(re.split(r"\n\s*\n", content))
    for block in candidates:
        cleaned = clean_summary_candidate(block, label)
        if cleaned:
            return cleaned[:1000]
    return ""


def is_placeholder_wechat_member_label(slug, label=None):
    slug_text = str(slug or "").strip().lower()
    label_text = str(label or "").strip().lower()
    leaf = slug_text.rsplit("/", 1)[-1]
    return leaf.startswith("wechat-member") or label_text in {"wechat member", "wechat-member"}


def wechat_identity_token(slug):
    leaf = str(slug or "").strip().lower().rsplit("/", 1)[-1]
    match = re.search(r"wechat-(?:member|friend)-(.+)$", leaf)
    return match.group(1) if match else ""


def alias_label_for_wechat_member(slug, node_map):
    token = wechat_identity_token(slug)
    if not token or not node_map:
        return ""
    for candidate_slug, candidate in node_map.items():
        if candidate_slug == slug or wechat_identity_token(candidate_slug) != token:
            continue
        label = str(candidate.get("label") or "").strip()
        if label and not is_placeholder_wechat_member_label(candidate_slug, label):
            return friendly_label(slug, label)
    return ""


def collapse_part_identity(slug, label=None):
    slug_text = str(slug or "").strip()
    label_text = str(label or "").strip()
    slug_match = PART_SLUG_RE.match(slug_text)
    label_match = PART_LABEL_RE.match(label_text)
    if not slug_match and not label_match:
        return slug_text, label_text or make_label(slug_text), False

    base_slug = slug_match.group("base") if slug_match else normalize_slug(label_match.group("base"))
    base_label = label_match.group("base").strip() if label_match else make_label(base_slug)
    return base_slug, base_label, True


def collapse_report_identity(slug, label=None):
    slug_text = str(slug or "").strip()
    label_text = str(label or "").strip()
    if not GBRAIN_USAGE_RE.match(slug_text):
        return slug_text, label_text or make_label(slug_text), False
    return "agent/reports/gbrain-usage", "Agent/reports/gbrain Usage", True


def graph_identity(slug, label=None):
    report_slug, report_label, report_collapsed = collapse_report_identity(slug, label)
    if report_collapsed:
        return report_slug, report_label, True, "report"
    part_slug, part_label, part_collapsed = collapse_part_identity(slug, label)
    return part_slug, part_label, part_collapsed, "part" if part_collapsed else None


def is_blocked_entity(slug, label=None):
    slug_text = str(slug or "").strip().lower()
    label_text = str(label or "").strip().lower()
    return slug_text in BLOCKED_SLUGS or label_text in BLOCKED_LABELS


def category_for_slug(slug, node_type):
    if "/" in slug:
        return slug.split("/", 1)[0]
    return node_type or "entity"


def collect_seed_graph():
    raw_list = run_gbrain("list", "-n", str(MAX_LIST_PAGES))
    page_rows = parse_page_list(raw_list)
    slugs = [row["slug"] for row in page_rows] or parse_slugs(raw_list)
    if not slugs:
        raise RuntimeError("gbrain list returned no detectable slugs")
    if ROOT_INDEX_SLUG not in slugs:
        slugs.insert(0, ROOT_INDEX_SLUG)

    row_by_slug = {row["slug"]: row for row in page_rows}
    nodes = []
    for slug in slugs:
        normalized = slug.strip()
        if not normalized:
            continue
        page_row = row_by_slug.get(normalized, {})
        nodes.append({
            "id": normalize_slug(normalized),
            "slug": normalized,
            "label": friendly_label(normalized, page_row.get("title")),
            "type": page_row.get("type") or "entity",
            "summary": "",
            "tags": [],
            "links": [],
            "updated_at": page_row.get("date"),
            "expanded": False,
        })

    seed_graph = {
        "title": "Memory Stargraph",
        "source": {
            "mode": "gbrain",
            "status": "lazy",
            "message": "Seed graph loaded from gbrain list. Root index is loaded eagerly; other relationships load when nodes are selected.",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "warnings": [],
            "lazy": True,
            "coverage": {
                "listed_nodes": len(nodes),
                "graph_commands_attempted": 0,
                "graph_command_limit": GRAPH_COMMAND_LIMIT,
                "expanded_slugs": [],
                "root_index_slug": ROOT_INDEX_SLUG,
            },
        },
        "nodes": sorted(nodes, key=lambda item: item["slug"]),
    }
    try:
        root_graph = expand_raw_graph(seed_graph, ROOT_INDEX_SLUG)
        source = dict(root_graph.get("source") or {})
        coverage = dict(source.get("coverage") or {})
        coverage["root_index_loaded"] = True
        source["coverage"] = coverage
        source["status"] = "lazy-root"
        source["message"] = "Seed graph loaded with the root index expanded eagerly. Other relationships load lazily."
        root_graph["source"] = source
        return root_graph
    except Exception as exc:  # noqa: BLE001
        seed_graph["source"]["warnings"].append(f"root index expansion failed: {exc}")
        seed_graph["source"]["coverage"]["root_index_loaded"] = False
        return seed_graph


def collect_live_graph():
    seed_graph = collect_seed_graph()
    nodes = {node["slug"]: dict(node) for node in seed_graph["nodes"]}
    edge_set = set()
    edge_types = defaultdict(set)
    failures = []
    graph_slugs = list(nodes)[:GRAPH_COMMAND_LIMIT]
    for index, slug in enumerate(graph_slugs):
        try:
            graph_output = run_gbrain("graph", slug, "--depth", str(GRAPH_DEPTH))
            edge_set.update(parse_neighbors(graph_output, slug))
            merge_edge_types(edge_types, parse_link_types(graph_output, slug))
            backlinks_output = run_gbrain("backlinks", slug)
            edge_set.update(parse_backlinks(backlinks_output, slug))
            merge_edge_types(edge_types, parse_backlink_types(backlinks_output, slug))
            nodes[slug]["expanded"] = True
        except Exception as exc:  # noqa: BLE001
            failures.append(f"graph {slug}: {exc}")
        if GRAPH_COMMAND_PAUSE_SECONDS and index < len(graph_slugs) - 1:
            time.sleep(GRAPH_COMMAND_PAUSE_SECONDS)

    adjacency = defaultdict(set)
    for left, right in edge_set:
        adjacency[left].add(right)
        adjacency[right].add(left)

    live_nodes = []
    for slug, node in nodes.items():
        node["links"] = sorted(adjacency.get(slug, set()))
        live_nodes.append(node)

    return {
        "title": "Memory Stargraph",
        "source": {
            "mode": "gbrain",
            "status": "live" if not failures else "partial",
            "message": "Live graph loaded from gbrain." if not failures else "Live graph loaded with some command failures.",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "warnings": failures[:30],
            "lazy": False,
            "coverage": {
                "listed_nodes": len(nodes),
                "graph_commands_attempted": len(graph_slugs),
                "graph_command_limit": GRAPH_COMMAND_LIMIT,
                "expanded_slugs": graph_slugs,
            },
        },
        "nodes": sorted(live_nodes, key=lambda item: item["slug"]),
        "edge_types": edge_types_payload(edge_types),
    }


def graph_to_raw_payload(graph):
    return {
        "title": graph.get("title") or "Memory Stargraph",
        "source": dict(graph.get("source") or {}),
        "nodes": [
            {
                "id": node.get("id") or normalize_slug(node.get("slug", "")),
                "slug": node.get("slug"),
                "label": node.get("label"),
                "type": node.get("type") or "entity",
                "summary": node.get("summary") or "",
                "tags": list(node.get("tags") or []),
                "links": list(node.get("links") or []),
                "updated_at": node.get("updated_at"),
                "expanded": bool(node.get("expanded")),
            }
            for node in graph.get("nodes", [])
        ],
        "edge_types": [
            {"source": edge.get("source"), "target": edge.get("target"), "types": list(edge.get("types") or [])}
            for edge in graph.get("edges", [])
            if edge.get("types")
        ],
    }


def expand_raw_graph(raw_graph, center_slug):
    nodes = {}
    edge_set = set()
    edge_types = defaultdict(set)
    for edge in raw_graph.get("edge_types") or []:
        left = str(edge.get("source") or "").strip()
        right = str(edge.get("target") or "").strip()
        if left and right and left != right:
            for link_type in edge.get("types") or []:
                value = str(link_type).strip()
                if value:
                    edge_types[edge_key(left, right)].add(value)
    for node in raw_graph.get("nodes", []):
        slug = str(node.get("slug") or "").strip()
        if not slug:
            continue
        nodes[slug] = dict(node)
        for linked in node.get("links") or []:
            linked_slug = str(linked).strip()
            if linked_slug:
                edge_set.add(tuple(sorted((slug, linked_slug))))

    if center_slug not in nodes:
        nodes[center_slug] = {
            "id": normalize_slug(center_slug),
            "slug": center_slug,
            "label": make_label(center_slug),
            "type": "entity",
            "summary": "",
            "tags": [],
            "links": [],
            "updated_at": None,
            "expanded": False,
        }

    graph_output = run_gbrain("graph", center_slug, "--depth", str(GRAPH_DEPTH))
    graph_edges = parse_neighbors(graph_output, center_slug)
    discovered_edges = set(graph_edges)
    merge_edge_types(edge_types, parse_link_types(graph_output, center_slug))
    backlinks_output = run_gbrain("backlinks", center_slug)
    backlink_edges = parse_backlinks(backlinks_output, center_slug)
    backlink_types = parse_backlink_types(backlinks_output, center_slug)
    supplement_edges = choose_backlink_supplement_edges(graph_edges, backlink_edges, backlink_types)
    discovered_edges.update(supplement_edges)
    merge_edge_types(edge_types, filter_edge_types(backlink_types, supplement_edges))
    edge_set.update(discovered_edges)
    for left, right in discovered_edges:
        for slug in (left, right):
            if slug not in nodes:
                nodes[slug] = {
                    "id": normalize_slug(slug),
                    "slug": slug,
                    "label": make_label(slug),
                    "type": "entity",
                    "summary": "Discovered by lazy graph expansion.",
                    "tags": [],
                    "links": [],
                    "updated_at": None,
                    "expanded": False,
                }

    adjacency = defaultdict(set)
    for left, right in edge_set:
        adjacency[left].add(right)
        adjacency[right].add(left)

    for slug, node in nodes.items():
        node["links"] = sorted(adjacency.get(slug, set()))
    nodes[center_slug]["expanded"] = True

    source = dict(raw_graph.get("source") or {})
    coverage = dict(source.get("coverage") or {})
    expanded_slugs = sorted(set(coverage.get("expanded_slugs") or []) | {center_slug})
    coverage["listed_nodes"] = max(int(coverage.get("listed_nodes") or 0), len(nodes))
    coverage["graph_commands_attempted"] = len(expanded_slugs)
    coverage["graph_command_limit"] = GRAPH_COMMAND_LIMIT
    coverage["expanded_slugs"] = expanded_slugs
    source.update(
        {
            "mode": "gbrain",
            "status": "lazy-expanded",
            "message": "Seed graph loaded. Selected-node relationships are being expanded lazily.",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "lazy": True,
            "coverage": coverage,
        }
    )
    return {
        "title": raw_graph.get("title") or "Memory Stargraph",
        "source": source,
        "nodes": sorted(nodes.values(), key=lambda item: item["slug"]),
        "edge_types": edge_types_payload(edge_types),
    }


def search_raw_graph(raw_graph, query):
    search_output = run_gbrain("search", query)
    results = parse_search_results(search_output)
    nodes = {str(node.get("slug")): dict(node) for node in raw_graph.get("nodes", []) if node.get("slug")}
    for result in results:
        slug = result["slug"]
        nodes.setdefault(
            slug,
            {
                "id": normalize_slug(slug),
                "slug": slug,
                "label": friendly_label(slug, result.get("label")),
                "type": "entity",
                "summary": result.get("preview") or "Discovered by lazy search.",
                "tags": ["lazy-search"],
                "links": [],
                "updated_at": None,
                "expanded": False,
            },
        )
    source = dict(raw_graph.get("source") or {})
    coverage = dict(source.get("coverage") or {})
    coverage["search_results"] = len(results)
    coverage["last_search_query"] = query
    coverage["search_slugs"] = [result["slug"] for result in results]
    source.update(
        {
            "mode": "gbrain",
            "status": "lazy-search",
            "message": "Seed graph loaded. Search results and selected-node relationships are loaded lazily.",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "lazy": True,
            "coverage": coverage,
        }
    )
    return {
        "title": raw_graph.get("title") or "Memory Stargraph",
        "source": source,
        "nodes": sorted(nodes.values(), key=lambda item: item["slug"]),
        "edge_types": list(raw_graph.get("edge_types") or []),
    }


def read_cache():
    if not CACHE_PATH.exists():
        return None
    try:
        payload = json.loads(CACHE_PATH.read_text())
    except Exception:  # noqa: BLE001
        return None
    if int(payload.get("view_schema_version") or 0) < VIEW_SCHEMA_VERSION:
        return None
    return finalize_graph(payload)


def cached_startup_graph():
    cached = read_cache()
    if not cached:
        return None
    cached = dict(cached)
    cached["ui_version"] = UI_VERSION
    cached["view_schema_version"] = VIEW_SCHEMA_VERSION
    cached_source = dict(cached.get("source") or {})
    cached_source["mode"] = "cache"
    cached_source["status"] = "cached-startup"
    cached_source["message"] = "Using cached graph for fast startup. Refresh Graph reloads live gbrain data."
    cached["source"] = cached_source
    return cached


def write_cache(payload):
    ensure_data_dir()
    CACHE_PATH.write_text(json.dumps(payload, indent=2))


def read_deleted_slugs():
    try:
        payload = json.loads(DELETED_PATH.read_text())
    except Exception:  # noqa: BLE001
        return set()
    if isinstance(payload, list):
        return {str(item).strip() for item in payload if str(item).strip()}
    return {str(item).strip() for item in payload.get("slugs", []) if str(item).strip()}


def add_deleted_slug(slug):
    ensure_data_dir()
    slugs = sorted(read_deleted_slugs() | {slug})
    DELETED_PATH.write_text(json.dumps({"slugs": slugs}, indent=2))


def read_hidden_slugs():
    try:
        payload = json.loads(HIDDEN_PATH.read_text())
    except Exception:  # noqa: BLE001
        return set()
    if isinstance(payload, list):
        return {str(item).strip() for item in payload if str(item).strip()}
    return {str(item).strip() for item in payload.get("slugs", []) if str(item).strip()}


def write_hidden_slugs(slugs):
    ensure_data_dir()
    HIDDEN_PATH.write_text(json.dumps({"slugs": sorted(slugs)}, indent=2))


def add_hidden_slug(slug):
    write_hidden_slugs(read_hidden_slugs() | {slug})


def remove_hidden_slug(slug):
    write_hidden_slugs(read_hidden_slugs() - {slug})


def finalize_graph(raw_graph):
    node_map = {}
    adjacency = defaultdict(set)
    edge_type_map = defaultdict(set)
    raw_to_group = {}
    deleted_slugs = read_deleted_slugs()

    for item in raw_graph.get("nodes", []):
        slug = item.get("slug") or item.get("id") or item.get("label")
        if not slug:
            continue
        normalized_slug = normalize_slug(slug) if " " in slug else slug
        raw_item_label = str(item.get("label") or "").strip()
        item_label = friendly_label(normalized_slug, raw_item_label)
        if normalized_slug in deleted_slugs or is_blocked_entity(normalized_slug, item_label):
            continue
        group_slug, raw_group_label, collapsed, collapse_kind = graph_identity(normalized_slug, raw_item_label or item_label)
        group_label = friendly_label(group_slug, raw_group_label)
        raw_to_group[normalized_slug] = group_slug
        incoming_tags = set(item.get("tags") or [])
        node = node_map.setdefault(
            group_slug,
            {
                "id": normalize_slug(group_slug),
                "slug": group_slug,
                "label": group_label or item_label or make_label(group_slug),
                "type": item.get("type") or "entity",
                "summary": item.get("summary") or "No summary available.",
                "tags": [],
                "updated_at": item.get("updated_at"),
                "parts_count": 0,
                "report_count": 0,
                "collapsed_children": [],
                "collapsed_aliases": [],
                "expanded": False,
            },
        )
        node["tags"] = sorted(set(node.get("tags") or []) | incoming_tags)
        if collapsed:
            if collapse_kind == "report":
                node["report_count"] = int(node.get("report_count") or 0) + 1
            else:
                node["parts_count"] = int(node.get("parts_count") or 0) + 1
            node["collapsed_children"].append(normalized_slug)
            if item.get("label"):
                node["collapsed_aliases"].append(str(item["label"]))
        if node.get("summary") == "No summary available." and item.get("summary"):
            node["summary"] = item["summary"]
        if not node.get("updated_at") and item.get("updated_at"):
            node["updated_at"] = item["updated_at"]
        if item.get("expanded"):
            node["expanded"] = True

    for item in raw_graph.get("nodes", []):
        slug = item.get("slug") or item.get("id") or item.get("label")
        if not slug:
            continue
        normalized_slug = normalize_slug(slug) if " " in slug else slug
        if normalized_slug in deleted_slugs or is_blocked_entity(normalized_slug, item.get("label")):
            continue
        source_slug = raw_to_group.get(normalized_slug, normalized_slug)
        if source_slug not in node_map:
            continue
        for linked in item.get("links", []):
            neighbor_slug = normalize_slug(linked) if " " in str(linked) else str(linked)
            if neighbor_slug in deleted_slugs or is_blocked_entity(neighbor_slug):
                continue
            neighbor_slug, neighbor_label, _, _ = graph_identity(neighbor_slug)
            if neighbor_slug in deleted_slugs:
                continue
            if neighbor_slug == source_slug:
                continue
            if neighbor_slug not in node_map:
                node_map[neighbor_slug] = {
                    "id": normalize_slug(neighbor_slug),
                    "slug": neighbor_slug,
                    "label": neighbor_label or make_label(neighbor_slug),
                    "type": "entity",
                    "summary": "Discovered by graph traversal.",
                    "tags": [],
                    "updated_at": None,
                    "parts_count": 0,
                    "report_count": 0,
                    "collapsed_children": [],
                    "collapsed_aliases": [],
                    "expanded": False,
                }
            adjacency[source_slug].add(neighbor_slug)
            adjacency[neighbor_slug].add(source_slug)

    for edge in raw_graph.get("edge_types") or []:
        left = str(edge.get("source") or "").strip()
        right = str(edge.get("target") or "").strip()
        if not left or not right:
            continue
        left = raw_to_group.get(left, graph_identity(left)[0])
        right = raw_to_group.get(right, graph_identity(right)[0])
        if left == right or left not in node_map or right not in node_map:
            continue
        key = edge_key(left, right)
        for link_type in edge.get("types") or []:
            value = str(link_type).strip()
            if value:
                edge_type_map[key].add(value)

    nodes = []
    degrees = []
    for slug, node in sorted(node_map.items()):
        links = sorted(adjacency.get(slug, set()))
        degree = len(links)
        node["links"] = links
        node["degree"] = degree
        node["category"] = category_for_slug(slug, node.get("type"))
        node["importance"] = degree + math.log2(max(1, int(node.get("parts_count") or 0)))
        node["collapsed_children"] = sorted(set(node.get("collapsed_children") or []))
        node["collapsed_aliases"] = sorted(set(node.get("collapsed_aliases") or []))
        nodes.append(node)
        degrees.append(degree)

    max_degree = max(degrees or [1])
    for node in nodes:
        ratio = node["degree"] / max_degree if max_degree else 0
        node["size"] = round(6 + 18 * math.sqrt(ratio), 2)

    edges = []
    for slug, neighbors in adjacency.items():
        for neighbor in neighbors:
            if slug < neighbor:
                edges.append({"source": slug, "target": neighbor, "types": sorted(edge_type_map.get(edge_key(slug, neighbor), set()))})

    return {
        "title": raw_graph.get("title") or "Memory Stargraph",
        "ui_version": UI_VERSION,
        "view_schema_version": VIEW_SCHEMA_VERSION,
        "source": raw_graph.get("source") or {"mode": "unknown", "status": "unknown", "message": ""},
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "max_degree": max_degree,
            "collapsed_parts": sum(int(node.get("parts_count") or 0) for node in nodes),
            "collapsed_reports": sum(int(node.get("report_count") or 0) for node in nodes),
            "expanded_nodes": sum(1 for node in nodes if node.get("expanded")),
        },
        "nodes": nodes,
        "edges": sorted(edges, key=lambda edge: (edge["source"], edge["target"])),
    }


class GraphStore:
    def __init__(self):
        self.graph = None
        self.loaded_at = 0.0
        self.refreshing = False
        self.condition = threading.Condition()

    def get_graph(self, force=False):
        now = time.time()
        if self.graph and not force and now - self.loaded_at < GRAPH_STALE_SECONDS:
            return self.graph
        if not self.graph and not force:
            cached = cached_startup_graph()
            if cached:
                with self.condition:
                    self.graph = cached
                    self.loaded_at = time.time()
                    return self.graph

        with self.condition:
            if self.refreshing:
                self.condition.wait(timeout=180)
                if self.graph:
                    return self.graph
            self.refreshing = True

        payload = None
        errors = []
        try:
            payload = finalize_graph(collect_live_graph())
            write_cache(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            cached = read_cache()
            if cached:
                cached = dict(cached)
                cached_source = dict(cached.get("source") or {})
                cached_source["mode"] = "cache"
                cached_source["status"] = "cached"
                cached_source["message"] = f"Using cached graph because live gbrain load failed: {exc}"
                cached["source"] = cached_source
                payload = cached
            else:
                demo = finalize_graph(DEMO_GRAPH)
                demo_source = dict(demo.get("source") or {})
                demo_source["message"] = f"Using demo graph because live gbrain load failed: {exc}"
                demo["source"] = demo_source
                payload = demo
        if errors and payload:
            payload["source"]["errors"] = errors
        with self.condition:
            self.graph = payload
            self.loaded_at = time.time()
            self.refreshing = False
            self.condition.notify_all()
            return self.graph

    def get_seed_graph(self, force=False):
        now = time.time()
        if self.graph and not force and now - self.loaded_at < GRAPH_STALE_SECONDS:
            return self.graph
        if not self.graph and not force:
            cached = cached_startup_graph()
            if cached:
                with self.condition:
                    self.graph = cached
                    self.loaded_at = time.time()
                    return self.graph

        with self.condition:
            if self.refreshing:
                self.condition.wait(timeout=60)
                if self.graph:
                    return self.graph
            self.refreshing = True

        payload = None
        errors = []
        try:
            payload = finalize_graph(collect_seed_graph())
            write_cache(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            cached = read_cache()
            if cached:
                cached = dict(cached)
                cached_source = dict(cached.get("source") or {})
                cached_source["mode"] = "cache"
                cached_source["status"] = "cached"
                cached_source["message"] = f"Using cached graph because seed gbrain load failed: {exc}"
                cached["source"] = cached_source
                payload = cached
            else:
                demo = finalize_graph(DEMO_GRAPH)
                demo_source = dict(demo.get("source") or {})
                demo_source["message"] = f"Using demo graph because seed gbrain load failed: {exc}"
                demo["source"] = demo_source
                payload = demo
        if errors and payload:
            payload["source"]["errors"] = errors
        with self.condition:
            self.graph = payload
            self.loaded_at = time.time()
            self.refreshing = False
            self.condition.notify_all()
            return self.graph

    def expand_entity(self, slug):
        graph = self.get_seed_graph()
        node_map = {node["slug"]: node for node in graph["nodes"]}
        if node_map.get(slug, {}).get("expanded"):
            return graph
        raw_graph = graph_to_raw_payload(graph)
        payload = finalize_graph(expand_raw_graph(raw_graph, slug))
        write_cache(payload)
        with self.condition:
            self.graph = payload
            self.loaded_at = time.time()
            return self.graph

    def search(self, query):
        graph = self.get_seed_graph()
        raw_graph = graph_to_raw_payload(graph)
        payload = finalize_graph(search_raw_graph(raw_graph, query))
        with self.condition:
            self.graph = payload
            self.loaded_at = time.time()
            return self.graph

    def invalidate(self):
        with self.condition:
            self.graph = None
            self.loaded_at = 0.0

    def hydrate_node_details(self, node, node_map=None, allow_fetch=True, fetch_timeout=6):
        slug = node.get("slug")
        if not slug:
            return node
        if is_placeholder_wechat_member_label(slug, node.get("label")):
            alias_label = alias_label_for_wechat_member(slug, node_map)
            if alias_label:
                node["label"] = alias_label
                if is_placeholder_entity_summary(node.get("summary")):
                    node["summary"] = node.get("summary") or "Cached WeChat Profile"
                return node
        if not allow_fetch:
            return node
        should_fetch = is_placeholder_entity_summary(node.get("summary")) or is_placeholder_wechat_member_label(slug, node.get("label"))
        if not should_fetch:
            return node
        try:
            page_output = run_gbrain("get", slug, timeout=fetch_timeout)
            meta, body = parse_frontmatter(page_output)
            if meta.get("title"):
                node["label"] = friendly_label(slug, str(meta["title"]))
            if meta.get("type"):
                node["type"] = str(meta["type"])
            summary = extract_summary_from_markdown_body(body, node.get("label"), node.get("type") or node.get("category"))
            if summary:
                node["summary"] = summary[:720]
            elif is_placeholder_entity_summary(node.get("summary")):
                node["summary"] = node.get("summary") or "No summary available."
        except Exception as exc:  # noqa: BLE001
            if is_placeholder_entity_summary(node.get("summary")):
                node["summary"] = f"{node.get('summary') or 'No summary available.'} Detail refresh failed: {exc}"
        return node

    def hydrate_wechat_neighbor_labels(self, neighbors, node_map):
        pending = []
        for neighbor in neighbors:
            slug = neighbor.get("slug")
            if not is_placeholder_wechat_member_label(slug, neighbor.get("label")):
                continue
            alias_label = alias_label_for_wechat_member(slug, node_map)
            if alias_label:
                neighbor["label"] = alias_label
                continue
            pending.append(neighbor)

        if not pending:
            return

        workers = min(8, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self.hydrate_node_details, neighbor, node_map, True, 8)
                for neighbor in pending[:40]
            ]
            for future in futures:
                try:
                    future.result()
                except Exception:  # noqa: BLE001
                    pass

    def direct_relationship_types(self, slug):
        edge_types = defaultdict(set)
        try:
            graph_output = run_gbrain("graph", slug, "--depth", str(GRAPH_DEPTH))
            merge_edge_types(edge_types, parse_link_types(graph_output, slug))
        except Exception:  # noqa: BLE001
            pass
        try:
            backlinks_output = run_gbrain("backlinks", slug)
            merge_edge_types(edge_types, parse_backlink_types(backlinks_output, slug))
        except Exception:  # noqa: BLE001
            pass
        return edge_types

    def get_entity(self, slug):
        graph = self.get_seed_graph()
        node_map = {node["slug"]: node for node in graph["nodes"]}
        if slug not in node_map:
            return None
        node = node_map[slug]
        self.hydrate_node_details(node, node_map=node_map, allow_fetch=True)
        edge_types = {edge_key(edge["source"], edge["target"]): edge.get("types") or [] for edge in graph.get("edges", [])}
        for key, types in self.direct_relationship_types(slug).items():
            merged = set(edge_types.get(key) or [])
            merged.update(types)
            edge_types[key] = sorted(merged)
        direct_slugs = set(node.get("links") or [])
        for edge in graph.get("edges", []):
            if not edge.get("types"):
                continue
            source_slug = edge.get("source")
            target_slug = edge.get("target")
            if source_slug == slug and target_slug:
                direct_slugs.add(target_slug)
            elif target_slug == slug and source_slug:
                direct_slugs.add(source_slug)
        direct_slugs = {item for item in direct_slugs if item in node_map and item != slug}
        node["links"] = sorted(direct_slugs)
        node["degree"] = len(direct_slugs)
        neighbors = []
        for item in node["links"]:
            if item not in node_map:
                continue
            neighbor = dict(node_map[item])
            self.hydrate_node_details(neighbor, node_map=node_map, allow_fetch=False)
            neighbor["link_types"] = sorted(edge_types.get(edge_key(slug, item), []))
            neighbors.append(neighbor)
        self.hydrate_wechat_neighbor_labels(neighbors, node_map)
        second_ring = []
        seen = {slug, *node["links"]}
        for neighbor in neighbors:
            for linked in neighbor["links"]:
                if linked not in seen and linked in node_map:
                    second_ring.append(node_map[linked])
                    seen.add(linked)
        return {
            "entity": node,
            "neighbors": neighbors,
            "second_ring": sorted(second_ring, key=lambda item: (-item["degree"], item["label"]))[:20],
            "source": graph["source"],
        }

    def get_entity_raw(self, slug):
        try:
            return run_gbrain("get", slug)
        except Exception:  # noqa: BLE001
            return None

    def get_entity_media(self, slug):
        raw = self.get_entity_raw(slug)
        if raw is None:
            return None
        return ensure_media_references_available(parse_media_references(raw))

    def save_entity_raw(self, slug, content):
        run_gbrain("put", slug, input_text=content)
        self.invalidate()

    def create_entity(self, name, description="", category="entities"):
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("name is required")
        slug = entity_slug_from_name(clean_name, category)
        markdown = create_entity_markdown(clean_name, description, category)
        run_gbrain("put", slug, input_text=markdown)
        self.invalidate()
        return slug

    def delete_entity(self, slug):
        graph = self.get_seed_graph()
        node_map = {node["slug"]: node for node in graph["nodes"]}
        if slug not in node_map:
            add_deleted_slug(slug)
            self.invalidate()
            return
        try:
            run_gbrain("delete", slug)
        except RuntimeError as exc:
            message = str(exc)
            if "page_not_found" not in message and "Page not found" not in message:
                raise
        add_deleted_slug(slug)
        self.invalidate()

    def add_relationship(self, source_slug, target_slug, link_type, context=""):
        command = ["link", source_slug, target_slug, "--link-type", link_type]
        if context:
            command.extend(["--context", context])
        run_gbrain(*command)
        self.invalidate()

    def remove_relationship(self, source_slug, target_slug, link_type=""):
        command = ["unlink", source_slug, target_slug]
        if link_type:
            command.extend(["--link-type", link_type])
        run_gbrain(*command)
        self.invalidate()

    def update_tags(self, slug, add_tags=None, remove_tags=None):
        for tag in add_tags or []:
            run_gbrain("tag", slug, tag)
        for tag in remove_tags or []:
            run_gbrain("untag", slug, tag)
        self.invalidate()

    def add_timeline_event(self, slug, date, summary, detail="", source=""):
        command = ["timeline-add", slug, date, summary]
        if detail:
            command.extend(["--detail", detail])
        if source:
            command.extend(["--source", source])
        run_gbrain(*command)
        self.invalidate()

    def ask_gbrain(self, slug, question):
        sections = [f"Question: {question}", f"Selected node: {slug}"]
        normalized_question = question.lower()

        if any(token in normalized_question for token in ("media", "image", "images", "photo", "picture", "attachment", "file")):
            media_items = self.get_entity_media(slug) or []
            if media_items:
                media_lines = []
                for item in media_items[:12]:
                    url = item.get("served_url") or item.get("url") or ""
                    label = item.get("label") or item.get("url") or "media"
                    kind = item.get("kind") or "media"
                    media_lines.append(f"- {label} ({kind}): {url}")
                sections.append("Detected media:\n" + "\n".join(media_lines))
            else:
                sections.append("Detected media:\nNo media references were found on this node.")

        try:
            graph_output = run_gbrain("graph-query", slug, "--direction", "both", "--depth", "1")
            sections.append("Direct relationship context:\n" + str(graph_output or ""))
        except Exception as exc:  # noqa: BLE001
            sections.append(f"Direct relationship context unavailable: {exc}")

        query_text = f"{question} {slug}"
        search_output = run_gbrain(
            "query",
            query_text,
            "--adaptive-return",
            "true",
            "--limit",
            "8",
            "--relational",
            "true",
        )
        sections.append("Question-specific gbrain retrieval:\n" + str(search_output or ""))
        return "\n\n".join(sections)

    def build_yoda_prompt(self, slug, question, history=None, depth="4"):
        history = history or []
        yoda_depth = clamp_yoda_depth(depth)
        lines = [
            "You are Ask Yoda inside Memory Stargraph.",
            "Answer from GBrain evidence. Start with the selected node when useful, then use graph expansion, backlinks, targeted search, and direct source-node reads.",
            "Be concise, cite relevant slugs or source node names, and say when the graph does not contain enough evidence.",
            "",
            f"Selected node: {slug}",
            f"Question: {question}",
            f"Retrieval depth: {yoda_depth}",
        ]
        if history:
            lines.extend(["", "Recent chat:"])
            for item in history[-8:]:
                role = str(item.get("role") or "user").strip()[:20]
                content = str(item.get("content") or "").strip()
                if content:
                    lines.append(f"- {role}: {content}")
        raw = self.get_entity_raw(slug) or ""
        if raw:
            lines.extend(["", "Selected node content:", raw[:6000]])
        try:
            graph_output = run_gbrain("graph-query", slug, "--direction", "both", "--depth", str(yoda_depth))
        except Exception as exc:  # noqa: BLE001
            graph_output = f"Direct relationship context unavailable: {exc}"
        lines.extend(["", "Direct relationship context:", str(graph_output or "")[:6000]])
        try:
            backlink_output = run_gbrain("backlinks", slug)
        except Exception as exc:  # noqa: BLE001
            backlink_output = f"Backlink context unavailable: {exc}"
        lines.extend(["", "Backlink context:", str(backlink_output or "")[:4000]])
        try:
            search_output = run_gbrain(
                "query",
                f"{question} {slug}",
                "--adaptive-return",
                "true",
                "--limit",
                "10",
                "--relational",
                "true",
            )
        except Exception as exc:  # noqa: BLE001
            search_output = f"Broader retrieval unavailable: {exc}"
        lines.extend(["", "Broader retrieval context:", str(search_output or "")[:6000]])
        search_slugs = [item["slug"] for item in parse_search_results(str(search_output or ""))]
        if not search_slugs:
            search_slugs = parse_slugs(str(search_output or ""))
        likely_slugs = [candidate for candidate in search_slugs if candidate != slug and "/" in candidate][:min(4, yoda_depth)]
        if likely_slugs:
            lines.append("")
            lines.append("Direct reads from likely source nodes:")
            for candidate in likely_slugs:
                try:
                    candidate_raw = run_gbrain("get", candidate)
                except Exception as exc:  # noqa: BLE001
                    candidate_raw = f"Unable to read {candidate}: {exc}"
                lines.extend([f"## {candidate}", str(candidate_raw or "")[:2200]])
        return "\n".join(lines)

    def ask_yoda(self, slug, question, history=None, depth="4"):
        request_id = f"yoda-{int(time.time() * 1000)}"
        started_at = time.perf_counter()
        prompt_started_at = time.perf_counter()
        yoda_depth = clamp_yoda_depth(depth)
        prompt = self.build_yoda_prompt(slug, question, history, yoda_depth)
        prompt_ms = int((time.perf_counter() - prompt_started_at) * 1000)
        model_started_at = time.perf_counter()
        agent_result = run_openclaw_agent(prompt, return_details=True)
        agent_output = agent_result.get("output") if isinstance(agent_result, dict) else agent_result
        model_ms = int((time.perf_counter() - model_started_at) * 1000)
        timings = {
            "prompt_ms": prompt_ms,
            "model_ms": model_ms,
            "total_ms": int((time.perf_counter() - started_at) * 1000),
        }
        diagnostics = {
            "request_id": request_id,
            "selected_slug": slug,
            "depth": yoda_depth,
            "timings": timings,
            "source": "openclaw-agent" if agent_output else "fallback",
            "fallback_used": not bool(agent_output),
            "model_status": agent_result.get("model_status", "unknown") if isinstance(agent_result, dict) else "unknown",
            "openclaw_status": agent_result.get("openclaw_status", "unknown") if isinstance(agent_result, dict) else "unknown",
            "error_summary": agent_result.get("error_summary", "") if isinstance(agent_result, dict) else "",
            "stdout_preview": agent_result.get("stdout_preview", "") if isinstance(agent_result, dict) else "",
            "stderr_preview": agent_result.get("stderr_preview", "") if isinstance(agent_result, dict) else "",
        }
        if agent_output:
            return {"output": agent_output, "source": "openclaw-agent", "timings": timings, "request_id": request_id, "diagnostics": diagnostics}
        fallback_text = f"Question: {question}\nSelected node: {slug}\n\nI gathered selected-node, graph, backlink, search, and source-node context, but the Ask Yoda model is unavailable right now."
        return {
            "output": fallback_text or "I found no concise answer in the graph context for this question yet.",
            "source": "fallback",
            "timings": timings,
            "request_id": request_id,
            "diagnostics": diagnostics,
        }

    def backlinks(self, slug):
        return run_gbrain("backlinks", slug)

    def graph_query(self, slug, link_type="", direction="both", depth="1"):
        command = ["graph-query", slug]
        if link_type:
            command.extend(["--type", link_type])
        if direction:
            command.extend(["--direction", direction])
        if depth:
            command.extend(["--depth", str(depth)])
        try:
            return run_gbrain(*command)
        except RuntimeError as exc:
            message = str(exc)
            if "database_url is missing" not in message and "No database URL" not in message:
                raise
            return self.graph_query_from_loaded_graph(slug, link_type, direction, depth, message)

    def graph_query_from_loaded_graph(self, slug, link_type="", direction="both", depth="1", reason=""):
        try:
            max_depth = max(1, min(3, int(depth)))
        except (TypeError, ValueError):
            max_depth = 1

        graph = self.expand_entity(slug)
        node_map = {node["slug"]: node for node in graph.get("nodes", [])}
        if slug not in node_map:
            return f"Remote-safe fallback used because native gbrain graph-query is unavailable here.\n\nNo loaded node found for {slug}."

        wanted_type = str(link_type or "").strip().lower()
        adjacency = defaultdict(list)
        for edge in graph.get("edges", []):
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if not source or not target or source == target:
                continue
            types = [str(item).strip() for item in edge.get("types") or [] if str(item).strip()]
            if wanted_type and wanted_type not in {item.lower() for item in types}:
                continue
            relation = ", ".join(types) if types else "related to"
            if direction in {"both", "outgoing"}:
                adjacency[source].append((target, relation))
            if direction in {"both", "incoming"}:
                adjacency[target].append((source, relation))

        lines = [
            "Remote-safe fallback used because native gbrain graph-query requires local database configuration on this host.",
        ]
        if reason:
            lines.append(f"Native error: {reason.splitlines()[0]}")
        lines.append("")
        lines.append(f"# Graph query: {node_map[slug].get('label') or slug}")
        if link_type:
            lines.append(f"Relationship filter: {link_type}")
        lines.append(f"Direction: {direction or 'both'}")
        lines.append(f"Depth: {max_depth}")
        lines.append("")

        queue = deque([(slug, 0)])
        visited = {slug}
        found = []
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= max_depth:
                continue
            for neighbor, relation in sorted(adjacency.get(current, []), key=lambda item: item[0]):
                if neighbor not in node_map:
                    continue
                next_depth = current_depth + 1
                neighbor_label = node_map[neighbor].get("label") or make_label(neighbor)
                found.append((current, relation, neighbor, neighbor_label, next_depth))
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, next_depth))

        if not found:
            lines.append("No matching relationships were found in the currently loaded graph. Try selecting the node first or refreshing the graph.")
            return "\n".join(lines)

        for source, relation, target, target_label, item_depth in found:
            lines.append(f"- depth {item_depth}: {source} --{relation}-> {target} ({target_label})")
        return "\n".join(lines)

    def attach_file(self, slug, file_path, description=""):
        raw = ""
        try:
            raw_output = run_gbrain("get", slug)
            raw = raw_output if isinstance(raw_output, str) else ""
        except Exception:  # noqa: BLE001
            raw = ""
        local_media = materialize_local_media_for_slug(slug, file_path, raw)
        try:
            run_gbrain("files", "upload", file_path, "--page", slug)
        except RuntimeError:
            if not local_media:
                raise
        markdown_updated = False
        relative_path = relative_path_for_local_media(local_media)
        if relative_path:
            copy_file_to_gbrain_store(file_path, relative_path)
        if raw and relative_path:
            updated_raw = append_attachment_reference(raw, relative_path, description)
            if updated_raw != raw:
                run_gbrain("put", slug, input_text=updated_raw)
                markdown_updated = True
        self.invalidate()
        if local_media:
            local_media["markdown_updated"] = markdown_updated
        return local_media

    def history(self, slug):
        return run_gbrain("history", slug)

    def timeline(self, slug):
        return run_gbrain("timeline", slug)

    def refresh_embedding(self, slug):
        run_gbrain("embed", slug)
        self.invalidate()


STORE = GraphStore()


class MemoryStargraphHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def end_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body or "{}")

    def read_multipart_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}, {}
        if length > MAX_UPLOAD_BYTES:
            raise ValueError(f"Upload is too large. Limit is {MAX_UPLOAD_BYTES} bytes.")
        body = self.rfile.read(length)
        return parse_multipart_form(self.headers.get("Content-Type") or "", body)

    def serve_media_file(self, request_path, head_only=False):
        file_path = resolve_media_file_path(request_path)
        if not file_path:
            self.send_error(HTTPStatus.NOT_FOUND, "Media file not found")
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        content_length = file_path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        if not head_only:
            self.wfile.write(file_path.read_bytes())

    def serve_gbrain_file(self, request_path, head_only=False):
        relative_text = unquote(str(request_path or "").split("/gbrain-files/", 1)[1] if "/gbrain-files/" in str(request_path or "") else "")
        relative_path = safe_media_relative_path(relative_text)
        if not relative_path:
            self.send_error(HTTPStatus.NOT_FOUND, "GBrain file not found")
            return
        result = materialize_gbrain_file_reference(relative_path)
        served_url = result.get("served_url") if result else media_served_url_for_relative_path(relative_path)
        if not served_url:
            self.send_error(HTTPStatus.NOT_FOUND, "GBrain file not found")
            return
        return self.serve_media_file(served_url, head_only=head_only)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            return self.serve_media_file(parsed.path, head_only=True)
        if parsed.path.startswith("/gbrain-files/"):
            return self.serve_gbrain_file(parsed.path, head_only=True)
        return super().do_HEAD()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            return self.serve_media_file(parsed.path)
        if parsed.path.startswith("/gbrain-files/"):
            return self.serve_gbrain_file(parsed.path)
        if parsed.path == "/api/health":
            return self.end_json(
                {
                    "ok": True,
                    "title": APP_NAME,
                    "ui_version": UI_VERSION,
                    "loaded": bool(STORE.graph),
                    "source": STORE.graph.get("source") if STORE.graph else None,
                    "stats": STORE.graph.get("stats") if STORE.graph else None,
                }
            )
        if parsed.path == "/api/graph":
            graph = STORE.get_seed_graph()
            return self.end_json(graph)
        if parsed.path == "/api/hidden":
            return self.end_json({"slugs": sorted(read_hidden_slugs())})
        if parsed.path == "/api/node-operations":
            return self.end_json({"operations": NODE_OPERATION_ENDPOINTS})
        if parsed.path == "/api/search":
            query = (parse_qs(parsed.query).get("q") or [""])[0].strip()
            if len(query) < 2:
                return self.end_json({"error": "q must be at least 2 characters"}, status=HTTPStatus.BAD_REQUEST)
            try:
                graph = STORE.search(query)
                return self.end_json({"ok": True, "query": query, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/refresh":
            graph = STORE.get_seed_graph(force=True)
            return self.end_json(graph)
        if parsed.path.startswith("/api/entity-raw/"):
            slug = unquote(parsed.path.split("/api/entity-raw/", 1)[1]).strip("/")
            try:
                raw = STORE.get_entity_raw(slug)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
            if raw is None:
                return self.end_json({"error": f"Unknown entity: {slug}"}, status=HTTPStatus.NOT_FOUND)
            return self.end_json({"slug": slug, "content": raw})
        if parsed.path.startswith("/api/entity-media/"):
            slug = unquote(parsed.path.split("/api/entity-media/", 1)[1]).strip("/")
            try:
                media = STORE.get_entity_media(slug)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
            if media is None:
                return self.end_json({"error": f"Unknown entity: {slug}"}, status=HTTPStatus.NOT_FOUND)
            return self.end_json({"slug": slug, "media": media})
        if parsed.path.startswith("/api/entity-timeline-view/"):
            slug = unquote(parsed.path.split("/api/entity-timeline-view/", 1)[1]).strip("/")
            try:
                output = STORE.timeline(slug)
                return self.end_json({"ok": True, "slug": slug, "output": output})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity/"):
            slug = unquote(parsed.path.split("/api/entity/", 1)[1]).strip("/")
            entity = STORE.get_entity(slug)
            if not entity:
                return self.end_json({"error": f"Unknown entity: {slug}"}, status=HTTPStatus.NOT_FOUND)
            return self.end_json(entity)
        if parsed.path in ("/", "/index.html"):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/refresh":
            graph = STORE.get_seed_graph(force=True)
            return self.end_json(graph)
        if parsed.path == "/api/entity-create":
            try:
                payload = self.read_json_body()
                name = str(payload.get("name") or "").strip()
                description = str(payload.get("description") or "").strip()
                category = str(payload.get("category") or "").strip()
                if not name:
                    return self.end_json({"error": "name is required"}, status=HTTPStatus.BAD_REQUEST)
                slug = STORE.create_entity(name, description, category)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-expand/"):
            slug = unquote(parsed.path.split("/api/entity-expand/", 1)[1]).strip("/")
            try:
                graph = STORE.expand_entity(slug)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-save/"):
            slug = unquote(parsed.path.split("/api/entity-save/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                content = payload.get("content")
                if not isinstance(content, str):
                    return self.end_json({"error": "content must be a string"}, status=HTTPStatus.BAD_REQUEST)
                STORE.save_entity_raw(slug, content)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-delete/"):
            slug = unquote(parsed.path.split("/api/entity-delete/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                graph = STORE.get_seed_graph()
                node_map = {node["slug"]: node for node in graph["nodes"]}
                expected_label = node_map.get(slug, {}).get("label") or slug
                if payload.get("confirm_label") != expected_label:
                    return self.end_json(
                        {
                            "error": f"Type the full node name exactly before deleting: {expected_label}",
                            "expected_label": expected_label,
                        },
                        status=HTTPStatus.BAD_REQUEST,
                    )
                STORE.delete_entity(slug)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-link/"):
            slug = unquote(parsed.path.split("/api/entity-link/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                target = str(payload.get("target") or "").strip()
                link_type = str(payload.get("link_type") or "").strip()
                context = str(payload.get("context") or "").strip()
                if not target or not link_type:
                    return self.end_json({"error": "target and link_type are required"}, status=HTTPStatus.BAD_REQUEST)
                STORE.add_relationship(slug, target, link_type, context)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "target": target, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-unlink/"):
            slug = unquote(parsed.path.split("/api/entity-unlink/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                target = str(payload.get("target") or "").strip()
                link_type = str(payload.get("link_type") or "").strip()
                if not target:
                    return self.end_json({"error": "target is required"}, status=HTTPStatus.BAD_REQUEST)
                STORE.remove_relationship(slug, target, link_type)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "target": target, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-tags/"):
            slug = unquote(parsed.path.split("/api/entity-tags/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                add_tags = [str(tag).strip() for tag in payload.get("add") or [] if str(tag).strip()]
                remove_tags = [str(tag).strip() for tag in payload.get("remove") or [] if str(tag).strip()]
                if not add_tags and not remove_tags:
                    return self.end_json({"error": "At least one tag to add or remove is required"}, status=HTTPStatus.BAD_REQUEST)
                STORE.update_tags(slug, add_tags, remove_tags)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-timeline/"):
            slug = unquote(parsed.path.split("/api/entity-timeline/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                date = str(payload.get("date") or "").strip()
                summary = str(payload.get("summary") or "").strip()
                detail = str(payload.get("detail") or "").strip()
                source = str(payload.get("source") or "").strip()
                if not date or not summary:
                    return self.end_json({"error": "date and summary are required"}, status=HTTPStatus.BAD_REQUEST)
                STORE.add_timeline_event(slug, date, summary, detail, source)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-ask-yoda/"):
            slug = unquote(parsed.path.split("/api/entity-ask-yoda/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                question = str(payload.get("question") or "").strip()
                history = payload.get("history") if isinstance(payload.get("history"), list) else []
                depth = clamp_yoda_depth(payload.get("depth"))
                if not question:
                    return self.end_json({"error": "question is required"}, status=HTTPStatus.BAD_REQUEST)
                result = sanitize_yoda_result(STORE.ask_yoda(slug, question, history, depth))
                return self.end_json({"ok": True, "slug": slug, **result})
            except Exception as exc:  # noqa: BLE001
                request_id = f"yoda-{int(time.time() * 1000)}"
                return self.end_json({
                    "error": str(exc),
                    "request_id": request_id,
                    "diagnostics": {
                        "request_id": request_id,
                        "selected_slug": slug,
                        "depth": locals().get("depth", 4),
                        "source": "api-error",
                        "fallback_used": False,
                        "model_status": "api_error",
                        "openclaw_status": "not_started",
                        "error_summary": str(exc)[:600],
                        "timings": {},
                    },
                }, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-backlinks/"):
            slug = unquote(parsed.path.split("/api/entity-backlinks/", 1)[1]).strip("/")
            try:
                output = STORE.backlinks(slug)
                return self.end_json({"ok": True, "slug": slug, "output": output})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-graph-query/"):
            slug = unquote(parsed.path.split("/api/entity-graph-query/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                direction = str(payload.get("direction") or "both").strip()
                depth = str(payload.get("depth") or "1").strip()
                if direction not in {"both", "outgoing", "incoming"}:
                    return self.end_json({"error": "direction must be one of: both, outgoing, incoming"}, status=HTTPStatus.BAD_REQUEST)
                if depth not in {"1", "2", "3"}:
                    return self.end_json({"error": "depth must be one of: 1, 2, 3"}, status=HTTPStatus.BAD_REQUEST)
                output = STORE.graph_query(
                    slug,
                    str(payload.get("link_type") or "").strip(),
                    direction,
                    depth,
                )
                return self.end_json({"ok": True, "slug": slug, "output": output})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-attach-file/"):
            slug = unquote(parsed.path.split("/api/entity-attach-file/", 1)[1]).strip("/")
            try:
                content_type = getattr(self, "headers", {}).get("Content-Type") or ""
                uploaded_path = None
                description = ""
                if content_type.startswith("multipart/form-data"):
                    fields, files = self.read_multipart_body()
                    description = str(fields.get("description") or "").strip()
                    upload = files.get("file")
                    if not upload:
                        return self.end_json({"error": "file is required"}, status=HTTPStatus.BAD_REQUEST)
                    uploaded_path = save_uploaded_file(slug, upload)
                    file_path = str(uploaded_path)
                else:
                    payload = self.read_json_body()
                    file_path = str(payload.get("file_path") or "").strip()
                    description = str(payload.get("description") or "").strip()
                if not file_path:
                    return self.end_json({"error": "file_path is required"}, status=HTTPStatus.BAD_REQUEST)
                local_media = STORE.attach_file(slug, file_path, description)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json(
                    {
                        "ok": True,
                        "slug": slug,
                        "graph": graph,
                        "local_media": local_media,
                        "uploaded_path": str(uploaded_path) if uploaded_path else None,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-history/"):
            slug = unquote(parsed.path.split("/api/entity-history/", 1)[1]).strip("/")
            try:
                output = STORE.history(slug)
                return self.end_json({"ok": True, "slug": slug, "output": output})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-embed/"):
            slug = unquote(parsed.path.split("/api/entity-embed/", 1)[1]).strip("/")
            try:
                STORE.refresh_embedding(slug)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-hide/"):
            slug = unquote(parsed.path.split("/api/entity-hide/", 1)[1]).strip("/")
            if not slug:
                return self.end_json({"error": "slug is required"}, status=HTTPStatus.BAD_REQUEST)
            add_hidden_slug(slug)
            return self.end_json({"ok": True, "slug": slug, "hidden": sorted(read_hidden_slugs())})
        if parsed.path.startswith("/api/entity-show/"):
            slug = unquote(parsed.path.split("/api/entity-show/", 1)[1]).strip("/")
            if not slug:
                return self.end_json({"error": "slug is required"}, status=HTTPStatus.BAD_REQUEST)
            remove_hidden_slug(slug)
            return self.end_json({"ok": True, "slug": slug, "hidden": sorted(read_hidden_slugs())})
        return self.end_json({"error": f"Unknown endpoint: {parsed.path}"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))


def main():
    parser = argparse.ArgumentParser(description=f"Serve the {APP_NAME} graph locally.")
    parser.add_argument("--host", default=str(CONFIG["host"]), help=f"Bind host (default: {CONFIG['host']})")
    parser.add_argument("--port", type=int, default=int(CONFIG["port"]), help=f"Bind port (default: {CONFIG['port']})")
    parser.add_argument("--certfile", help="TLS certificate chain file. When set with --keyfile, serve HTTPS.")
    parser.add_argument("--keyfile", help="TLS private key file. When set with --certfile, serve HTTPS.")
    args = parser.parse_args()

    ensure_data_dir()
    server = ThreadingHTTPServer((args.host, args.port), MemoryStargraphHandler)
    scheme = "http"
    if args.certfile or args.keyfile:
        if not args.certfile or not args.keyfile:
            parser.error("--certfile and --keyfile must be provided together")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=args.certfile, keyfile=args.keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    print(f"{APP_NAME} serving on {scheme}://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
