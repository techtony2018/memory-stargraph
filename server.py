#!/usr/bin/env python3
import argparse
import email
import email.policy
import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.parse import parse_qs
from urllib.request import Request, urlopen


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
    "yoda_backend": "openclaw",
    "yoda_agent": "",
    "yoda_model": "",
    "yoda_base_url": "",
    "yoda_api_key_env": "OPENAI_API_KEY",
    "yoda_timeout_seconds": 45,
    "yoda_graph_query_timeout_seconds": 30,
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


def read_local_config_file():
    path = config_path()
    if not path.exists():
        return {}
    with path.open() as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"Config must be a JSON object: {path}")
    return loaded


def write_local_config_file(config):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


CONFIG = load_config()
PUBLIC_DIR = resolve_project_path(CONFIG["public_dir"])
DATA_DIR = resolve_project_path(CONFIG["data_dir"])
CACHE_PATH = DATA_DIR / "graph_cache.json"
DELETED_PATH = DATA_DIR / "deleted_entities.json"
HIDDEN_PATH = DATA_DIR / "hidden_entities.json"
YODA_LOG_PATH = DATA_DIR / "yoda_logs.json"
YODA_CHAT_PATH = DATA_DIR / "yoda_chats.json"
YODA_SETTINGS_PATH = DATA_DIR / "yoda_settings.json"
RESOLVER_EVENTS_PATH = DATA_DIR / "resolver_dispatch_events.json"
RESOLVER_PROPOSALS_PATH = DATA_DIR / "resolver_proposals.json"
RESOLVER_DREAM_LOG_PATH = DATA_DIR / "resolver_dream_runs.json"
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
YODA_BACKENDS = {"openclaw", "openai", "openai_compatible", "ollama", "gbrain_think"}
VIEW_SCHEMA_VERSION = 5
UI_VERSION = "V1.0.138"
TAKE_REVIEW_ACTOR = "memory-stargraph-ui"
TAKE_REVIEW_MAX_LIMIT = 100
TAKES_VIEW_FETCH_LIMIT = 500
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
    {"action": "take-review", "method": "GET", "endpoint": "/api/take-proposals", "mutates_gbrain": False},
    {"action": "take-review-accept", "method": "POST", "endpoint": "/api/take-proposals/<id>/accept", "mutates_gbrain": True},
    {"action": "take-review-reject", "method": "POST", "endpoint": "/api/take-proposals/<id>/reject", "mutates_gbrain": True},
    {"action": "take-review-defer", "method": "POST", "endpoint": "/api/take-proposals/<id>/defer", "mutates_gbrain": True},
    {"action": "take-review-bulk", "method": "POST", "endpoint": "/api/take-proposals/bulk", "mutates_gbrain": True},
    {"action": "takes", "method": "GET", "endpoint": "/api/takes", "mutates_gbrain": False},
    {"action": "yoda-system-prompt", "method": "GET", "endpoint": "/api/yoda-system-prompt", "mutates_gbrain": False},
    {"action": "yoda-system-prompt-save", "method": "POST", "endpoint": "/api/yoda-system-prompt", "mutates_gbrain": False},
    {"action": "yoda-logs", "method": "GET", "endpoint": "/api/yoda-logs", "mutates_gbrain": False},
    {"action": "resolver-events", "method": "GET", "endpoint": "/api/resolver/events", "mutates_gbrain": False},
    {"action": "resolver-event-log", "method": "POST", "endpoint": "/api/resolver/events", "mutates_gbrain": False},
    {"action": "resolver-proposals", "method": "GET", "endpoint": "/api/resolver/proposals", "mutates_gbrain": False},
    {"action": "resolver-proposal-generate", "method": "POST", "endpoint": "/api/resolver/proposals/generate", "mutates_gbrain": False},
    {"action": "resolver-proposal-accept", "method": "POST", "endpoint": "/api/resolver/proposals/<id>/accept", "mutates_gbrain": False},
    {"action": "resolver-proposal-reject", "method": "POST", "endpoint": "/api/resolver/proposals/<id>/reject", "mutates_gbrain": False},
    {"action": "resolver-proposal-apply", "method": "POST", "endpoint": "/api/resolver/proposals/<id>/apply", "mutates_gbrain": False},
    {"action": "resolver-dream", "method": "POST", "endpoint": "/api/resolver/dream", "mutates_gbrain": False},
]

DEFAULT_YODA_SYSTEM_PROMPT = """You are Ask Yoda inside Memory Stargraph.
Answer from GBrain evidence. Start with the selected node when useful, then use graph expansion, backlinks, targeted search, and direct source-node reads.
Be concise, cite relevant slugs or source node names, and say when the graph does not contain enough evidence.

Before traversing the graph, classify the question intent. For writing, post, note, article, or publication questions, prefer typed/container enumeration over broad expansion. Enumerate publication, platform, collection, or feed nodes through has_member/member_of, has_post/has_entry, authored_by, and similar typed edges. Verify candidate writing evidence with author or holder relationships and container membership before treating a title/content hit as relevant.

avoid unconstrained graph-query --depth 4 --direction both from high-degree hub nodes. If broad traversal times out or the selected node has large fanout, explain the hub fanout and retry with constrained typed traversals such as --type authored_by --direction in --depth 1, has_member/member_of, has_post/has_entry, or topic-filtered container scans.

Cite evidence from backlinks and relationships. Distinguish direct content/title matches from noisy metadata or frontmatter matches."""

MAX_YODA_LOGS = 200
MAX_YODA_LOGS_PER_SLUG = 20
MAX_YODA_CHAT_MESSAGES = 80
MAX_YODA_CHAT_SLUGS = 80
MAX_RESOLVER_EVENTS = 500
MAX_RESOLVER_PROPOSALS = 200

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


def read_json_file(path, default):
    try:
        if not path.exists():
            return default
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if data is not None else default
    except (OSError, json.JSONDecodeError):
        return default


def write_json_file(path, data):
    ensure_data_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temp_path.replace(path)


SECRET_RE = re.compile(r"(?i)(\bsk-[a-z0-9_-]+|token[=:]\s*\S+|api[_-]?key[=:]\s*\S+|password[=:]\s*\S+)")


def sanitize_text_summary(value, limit=220):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = SECRET_RE.sub("[redacted]", text)
    text = text.rstrip("?!")
    return text[:limit]


def yoda_system_prompt_state():
    data = read_json_file(YODA_SETTINGS_PATH, {})
    prompt = str(data.get("system_prompt") or "").strip() if isinstance(data, dict) else ""
    if prompt:
        return {"prompt": prompt, "default_prompt": DEFAULT_YODA_SYSTEM_PROMPT, "override": True}
    return {"prompt": DEFAULT_YODA_SYSTEM_PROMPT, "default_prompt": DEFAULT_YODA_SYSTEM_PROMPT, "override": False}


def save_yoda_system_prompt(prompt):
    clean = str(prompt or "").strip()
    if not clean:
        return reset_yoda_system_prompt()
    if len(clean) > 20000:
        raise ValueError("system prompt must be 20000 characters or less")
    data = read_json_file(YODA_SETTINGS_PATH, {})
    if not isinstance(data, dict):
        data = {}
    data["system_prompt"] = clean
    data["updated_at"] = iso_now()
    write_json_file(YODA_SETTINGS_PATH, data)
    return yoda_system_prompt_state()


def reset_yoda_system_prompt():
    data = read_json_file(YODA_SETTINGS_PATH, {})
    if not isinstance(data, dict):
        data = {}
    data.pop("system_prompt", None)
    data["updated_at"] = iso_now()
    write_json_file(YODA_SETTINGS_PATH, data)
    return yoda_system_prompt_state()


def yoda_log_entries(slug=None, limit=20):
    rows = read_json_file(YODA_LOG_PATH, [])
    if not isinstance(rows, list):
        rows = []
    if slug:
        rows = [row for row in rows if row.get("slug") == slug]
    try:
        bounded_limit = max(1, min(100, int(limit)))
    except (TypeError, ValueError):
        bounded_limit = 20
    return rows[:bounded_limit]


def append_yoda_log(slug, entry):
    if not slug or not isinstance(entry, dict):
        return None
    rows = read_json_file(YODA_LOG_PATH, [])
    if not isinstance(rows, list):
        rows = []
    safe_entry = {
        "slug": str(slug),
        "captured_at": entry.get("captured_at") or iso_now(),
        "request_id": str(entry.get("request_id") or ""),
        "source": sanitize_text_summary(entry.get("source"), 80),
        "timings": entry.get("timings") if isinstance(entry.get("timings"), dict) else {},
        "diagnostics": sanitize_diagnostics(entry.get("diagnostics") if isinstance(entry.get("diagnostics"), dict) else {}),
    }
    rows.insert(0, safe_entry)
    per_slug_seen = defaultdict(int)
    bounded = []
    for row in rows:
        row_slug = row.get("slug")
        if per_slug_seen[row_slug] >= MAX_YODA_LOGS_PER_SLUG:
            continue
        per_slug_seen[row_slug] += 1
        bounded.append(row)
        if len(bounded) >= MAX_YODA_LOGS:
            break
    write_json_file(YODA_LOG_PATH, bounded)
    return safe_entry


def sanitize_chat_message(message):
    if not isinstance(message, dict):
        return None
    if message.get("pending"):
        return None
    role = str(message.get("role") or "").strip().lower()
    if role not in {"system", "user", "assistant"}:
        return None
    content = SECRET_RE.sub("[redacted]", str(message.get("content") or "").strip())[:5000]
    if not content:
        return None
    safe = {
        "role": role,
        "content": sanitize_text_summary(content, 5000),
        "timestamp": sanitize_text_summary(message.get("timestamp") or iso_now(), 80),
    }
    fallback_output = str(message.get("fallbackOutput") or message.get("fallback_output") or "").strip()
    if fallback_output:
        safe["fallbackOutput"] = SECRET_RE.sub("[redacted]", fallback_output)[:12000]
    return safe


def yoda_chat_rows():
    rows = read_json_file(YODA_CHAT_PATH, {})
    return rows if isinstance(rows, dict) else {}


def yoda_chat_history(slug):
    rows = yoda_chat_rows()
    history = rows.get(str(slug), [])
    if not isinstance(history, list):
        history = []
    return [item for item in (sanitize_chat_message(message) for message in history) if item]


def save_yoda_chat_history(slug, messages):
    clean_slug = str(slug or "").strip()
    if not clean_slug:
        raise ValueError("slug is required")
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    rows = yoda_chat_rows()
    sanitized = [item for item in (sanitize_chat_message(message) for message in messages) if item]
    rows[clean_slug] = sanitized[-MAX_YODA_CHAT_MESSAGES:]
    if len(rows) > MAX_YODA_CHAT_SLUGS:
        ordered = sorted(
            rows.items(),
            key=lambda item: str((item[1][-1] if isinstance(item[1], list) and item[1] else {}).get("timestamp") or ""),
            reverse=True,
        )
        rows = dict(ordered[:MAX_YODA_CHAT_SLUGS])
    write_json_file(YODA_CHAT_PATH, rows)
    return rows[clean_slug]


def clear_yoda_chat_history(slug):
    rows = yoda_chat_rows()
    rows.pop(str(slug or "").strip(), None)
    write_json_file(YODA_CHAT_PATH, rows)


def sanitize_diagnostics(diagnostics):
    allowed = {
        "request_id",
        "selected_slug",
        "depth",
        "source",
        "fallback_used",
        "model_status",
        "openclaw_status",
        "model_backend",
        "model_name",
        "error_summary",
        "stdout_preview",
        "stderr_preview",
        "timings",
    }
    safe = {}
    for key, value in diagnostics.items():
        if key not in allowed:
            continue
        if isinstance(value, dict):
            safe[key] = {str(k): v for k, v in value.items() if isinstance(v, (int, float, str, bool)) or v is None}
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[key] = value
        else:
            safe[key] = sanitize_text_summary(value, 600)
    return safe


def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def resolver_event_id(payload):
    seed = json.dumps(payload, sort_keys=True, default=str)
    return "re-" + hashlib.sha1(f"{time.time()}:{seed}".encode("utf-8")).hexdigest()[:14]


def normalize_resolver_status(value, fallback_used=False):
    status = str(value or "").strip().lower()
    if status in {"success", "ok", "answered", "passed"}:
        return "success"
    if status in {"timeout", "timed_out"}:
        return "timeout"
    if status in {"no_match", "missing", "not_found"}:
        return "no_match"
    if status in {"error", "failed", "api_error"}:
        return "error"
    return "fallback" if fallback_used else (status or "unknown")


def resolver_cluster_key(intent_summary):
    words = re.findall(r"[a-z0-9]+", str(intent_summary or "").lower())
    stop = {"the", "and", "for", "with", "that", "this", "from", "about", "find", "show", "what", "which"}
    useful = [word for word in words if word not in stop][:8]
    return "-".join(useful) or "general"


def append_resolver_event(payload):
    event = {
        "id": resolver_event_id(payload),
        "created_at": iso_now(),
        "surface": sanitize_text_summary(payload.get("surface") or payload.get("source") or "Stargraph UI", 80),
        "intent_summary": sanitize_text_summary(payload.get("intent_summary") or payload.get("user_intent"), 180),
        "selected_skill": sanitize_text_summary(payload.get("selected_skill"), 120),
        "selected_context": sanitize_text_summary(payload.get("selected_context") or payload.get("related_slug"), 180),
        "candidate_skills": [sanitize_text_summary(item, 120) for item in payload.get("candidate_skills", [])[:10]] if isinstance(payload.get("candidate_skills"), list) else [],
        "candidate_contexts": [sanitize_text_summary(item, 180) for item in payload.get("candidate_contexts", [])[:10]] if isinstance(payload.get("candidate_contexts"), list) else [],
        "confidence": payload.get("confidence") if isinstance(payload.get("confidence"), (int, float)) else None,
        "fallback_used": bool(payload.get("fallback_used")),
        "operation": sanitize_text_summary(payload.get("operation") or payload.get("tool_path"), 160),
        "result_status": normalize_resolver_status(payload.get("result_status"), bool(payload.get("fallback_used"))),
        "error_class": sanitize_text_summary(payload.get("error_class") or payload.get("error_timeout_class"), 120),
        "correction_signal": sanitize_text_summary(payload.get("correction_signal"), 160),
        "related_node_slug": sanitize_text_summary(payload.get("related_node_slug") or payload.get("related_slug"), 180),
    }
    events = read_json_file(RESOLVER_EVENTS_PATH, [])
    if not isinstance(events, list):
        events = []
    events.insert(0, event)
    write_json_file(RESOLVER_EVENTS_PATH, events[:MAX_RESOLVER_EVENTS])
    return event


def resolver_events(limit=50):
    try:
        bounded_limit = max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        bounded_limit = 50
    rows = read_json_file(RESOLVER_EVENTS_PATH, [])
    return rows[:bounded_limit] if isinstance(rows, list) else []


def resolver_proposals():
    rows = read_json_file(RESOLVER_PROPOSALS_PATH, [])
    return rows if isinstance(rows, list) else []


def write_resolver_proposals(rows):
    write_json_file(RESOLVER_PROPOSALS_PATH, rows[:MAX_RESOLVER_PROPOSALS])


def proposal_id_for(cluster_key, kind):
    return "rp-" + hashlib.sha1(f"{kind}:{cluster_key}".encode("utf-8")).hexdigest()[:14]


def proposal_impact(events):
    statuses = [normalize_resolver_status(event.get("result_status"), event.get("fallback_used")) for event in events]
    return {
        "event_count": len(events),
        "fallback_count": sum(1 for event in events if event.get("fallback_used")),
        "timeout_count": statuses.count("timeout"),
        "no_match_count": statuses.count("no_match"),
        "success_count": statuses.count("success"),
    }


def generate_resolver_proposals():
    events = resolver_events(MAX_RESOLVER_EVENTS)
    groups = defaultdict(list)
    for event in events:
        status = normalize_resolver_status(event.get("result_status"), event.get("fallback_used"))
        if status not in {"timeout", "no_match", "fallback", "error"} and not event.get("correction_signal"):
            continue
        groups[resolver_cluster_key(event.get("intent_summary"))].append(event)
    existing = resolver_proposals()
    existing_ids = {row.get("id") for row in existing}
    created = []
    for cluster_key, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        statuses = {normalize_resolver_status(event.get("result_status"), event.get("fallback_used")) for event in group}
        kind = "add_trigger" if statuses & {"no_match", "fallback", "timeout"} else "add_routing_eval"
        proposal_id = proposal_id_for(cluster_key, kind)
        if proposal_id in existing_ids:
            continue
        examples = [event.get("intent_summary") for event in group[:5] if event.get("intent_summary")]
        proposal = {
            "id": proposal_id,
            "kind": kind,
            "status": "pending",
            "cluster_key": cluster_key,
            "confidence": min(0.9, 0.45 + (0.1 * len(group))),
            "target": "resolver/routing-eval",
            "created_at": iso_now(),
            "event_ids": [event.get("id") for event in group[:20] if event.get("id")],
            "example_intents": examples,
            "proposed_change": f"Add resolver routing coverage for repeated intents matching `{cluster_key}`.",
            "proposed_markdown_diff": f"- Add trigger/eval for `{cluster_key}` based on {len(group)} resolver events.",
            "evidence": [{"event_id": event.get("id"), "intent_summary": event.get("intent_summary"), "result_status": event.get("result_status")} for event in group[:5]],
            "impact": {"before": proposal_impact(group), "after": {}, "follow_up_status": "pending"},
        }
        existing.insert(0, proposal)
        existing_ids.add(proposal_id)
        created.append(proposal)
    write_resolver_proposals(existing)
    return {"created": len(created), "proposals": created, "events_scanned": len(events), "clusters_found": len(groups)}


def update_resolver_proposal(proposal_id, updater):
    rows = resolver_proposals()
    for index, row in enumerate(rows):
        if row.get("id") != proposal_id:
            continue
        updated = updater(dict(row))
        rows[index] = updated
        write_resolver_proposals(rows)
        return updated
    raise ValueError(f"Unknown resolver proposal: {proposal_id}")


def validate_resolver_release(proposal, approved_route):
    cluster_key = sanitize_text_summary(proposal.get("cluster_key"), 200).strip()
    route = sanitize_text_summary(approved_route, 160).strip()
    if not cluster_key or not route:
        raise ValueError("Resolver release requires a cluster key and approved route")
    trigger = re.sub(r"[|`\r\n]+", " ", cluster_key).strip()
    with tempfile.TemporaryDirectory(prefix="stargraph-resolver-validation-") as temp_dir:
        skills_dir = Path(temp_dir) / "skills"
        skill_dir = skills_dir / "approved-resolver-route"
        skill_dir.mkdir(parents=True)
        write_json_file(skills_dir / "manifest.json", {
            "skills": [{"name": "approved-resolver-route", "path": "approved-resolver-route/SKILL.md"}],
        })
        (skills_dir / "RESOLVER.md").write_text(
            "\n".join([
                "# Resolver release validation",
                "",
                "| Trigger | Skill |",
                "|---------|-------|",
                f'| "{trigger}" | `skills/approved-resolver-route/SKILL.md` |',
                "",
            ]),
            encoding="utf-8",
        )
        (skill_dir / "SKILL.md").write_text(
            "---\nname: approved-resolver-route\ntriggers:\n"
            f"  - {json.dumps(trigger)}\n---\n\n"
            f"Approved route: {route}\n",
            encoding="utf-8",
        )
        (skill_dir / "routing-eval.jsonl").write_text(
            json.dumps({
                "intent": f"Please handle this {trigger} request now",
                "expected_skill": "approved-resolver-route",
            }) + "\n",
            encoding="utf-8",
        )
        run_gbrain("check-resolvable", "--strict", "--skills-dir", str(skills_dir), timeout=30)
        run_gbrain("routing-eval", "--skills-dir", str(skills_dir), timeout=30)
    return {
        "check_resolvable": "passed",
        "routing_tests": "passed",
        "checked_at": iso_now(),
        "cluster_key": cluster_key,
        "approved_route": route,
    }


def run_resolver_dream_phase(enabled=True):
    if not enabled:
        summary = {"enabled": False, "events_scanned": 0, "clusters_found": 0, "proposals_created": 0, "duplicates_skipped": 0, "applied": 0, "errors": []}
    else:
        before = len(resolver_proposals())
        generated = generate_resolver_proposals()
        after = len(resolver_proposals())
        summary = {
            "enabled": True,
            "events_scanned": generated["events_scanned"],
            "clusters_found": generated["clusters_found"],
            "proposals_created": generated["created"],
            "duplicates_skipped": max(0, before + generated["created"] - after),
            "applied": 0,
            "errors": [],
        }
    runs = read_json_file(RESOLVER_DREAM_LOG_PATH, [])
    if not isinstance(runs, list):
        runs = []
    runs.insert(0, {"created_at": iso_now(), "summary": summary})
    write_json_file(RESOLVER_DREAM_LOG_PATH, runs[:100])
    return summary


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


def gbrain_call_tool(tool_name, payload=None, timeout=30):
    try:
        output = run_gbrain("call", tool_name, json.dumps(payload or {}), timeout=timeout)
    except RuntimeError as exc:
        message = str(exc)
        for line in reversed(message.splitlines()):
            cleaned = line.strip()
            if cleaned.startswith("Unknown tool:"):
                raise RuntimeError(f"GBrain backend does not expose {tool_name}: {cleaned}") from exc
        raise
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, (dict, list)):
        return parsed
    parsed_object = extract_json_object(output)
    if parsed_object is not None:
        return parsed_object
    parsed_list = extract_json_list(output)
    if parsed_list is not None:
        return parsed_list
    return {"output": output}


def resolver_submit_event(payload):
    event_payload = {
        "event_id": str(payload.get("event_id") or f"stargraph-{int(time.time() * 1000)}"),
        "producer": str(payload.get("producer") or "stargraph"),
        "resolver_version": str(payload.get("resolver_version") or UI_VERSION),
        "intent_summary": sanitize_text_summary(payload.get("intent_summary") or payload.get("user_intent"), 500),
        "candidate_resolvers": payload.get("candidate_resolvers") or payload.get("candidate_skills") or [],
        "selected_route": sanitize_text_summary(payload.get("selected_route") or payload.get("selected_skill"), 160),
        "confidence": payload.get("confidence"),
        "related_node_slug": sanitize_text_summary(payload.get("related_node_slug") or payload.get("related_slug") or payload.get("selected_context"), 220),
        "outcome": normalize_resolver_status(payload.get("outcome") or payload.get("result_status"), bool(payload.get("fallback_used"))),
        "correction_signal": sanitize_text_summary(payload.get("correction_signal"), 160),
        "operation_path": sanitize_text_summary(payload.get("operation_path") or payload.get("operation"), 160),
        "client_timestamp": iso_now(),
    }
    return gbrain_call_tool("resolver_events_submit", event_payload, timeout=20)


def resolver_list_events(limit=50, producer=None, outcome=None):
    payload = {"limit": limit}
    if producer:
        payload["producer"] = producer
    if outcome:
        payload["outcome"] = outcome
    return gbrain_call_tool("resolver_events_list", payload, timeout=20)


def resolver_list_proposals(status_filter="", limit=100):
    payload = {"limit": limit}
    if status_filter:
        payload["status"] = status_filter
    return gbrain_call_tool("resolver_proposals_list", payload, timeout=30)


def resolver_generate_proposals(payload=None):
    request_payload = dict(payload or {})
    request_payload.setdefault("min_evidence", 2)
    request_payload.setdefault("run_source", "memory-stargraph")
    return gbrain_call_tool("resolver_proposals_generate", request_payload, timeout=60)


def resolver_update_proposal(proposal_id, action, payload=None):
    request_payload = dict(payload or {})
    request_payload["proposal_id"] = proposal_id
    request_payload["action"] = action
    return gbrain_call_tool("resolver_proposals_update", request_payload, timeout=30)


def resolver_apply_proposal(proposal_id, payload=None):
    request_payload = dict(payload or {})
    listed = resolver_list_proposals("accepted", 200)
    proposals = listed.get("proposals", []) if isinstance(listed, dict) else []
    proposal = next((row for row in proposals if row.get("id") == proposal_id), None)
    if not proposal:
        raise ValueError(f"Accepted resolver proposal not found: {proposal_id}")
    approved_route = str(request_payload.get("approved_route") or "gbrain-hybrid-search")
    request_payload["proposal_id"] = proposal_id
    request_payload.setdefault("approved_by", "memory-stargraph")
    request_payload["approved_route"] = approved_route
    request_payload.setdefault("environments", ["codex", "openclaw"])
    request_payload["validation"] = validate_resolver_release(proposal, approved_route)
    return gbrain_call_tool("resolver_releases_apply", request_payload, timeout=60)


def resolver_measure_impact(proposal_id, payload=None):
    request_payload = dict(payload or {})
    request_payload["proposal_id"] = proposal_id
    return gbrain_call_tool("resolver_impact_measure", request_payload, timeout=30)


def resolver_feedback_health():
    return gbrain_call_tool("resolver_feedback_health", {}, timeout=20)


def clamp_take_review_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 20
    return max(1, min(TAKE_REVIEW_MAX_LIMIT, limit))


def first_query_value(query, key, default=""):
    values = query.get(key)
    if not values:
        return default
    return str(values[0] or "").strip()


def parse_nonnegative_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def holder_filter_is_wildcard(value):
    text = str(value or "").strip()
    return text == "*" or "*" in text


def wildcard_to_regex(value):
    text = str(value or "").strip().lower()
    escaped = re.escape(text).replace(r"\*", ".*")
    return re.compile(f"^{escaped}$")


def holder_matches_filter(holder, holder_filter):
    text = str(holder or "").strip().lower()
    pattern = str(holder_filter or "").strip().lower()
    if not pattern or pattern == "*":
        return True
    matcher = wildcard_to_regex(pattern)
    basename = text.rsplit("/", 1)[-1]
    labelish = basename.replace("-", " ")
    first = labelish.split(" ", 1)[0]
    return any(matcher.match(candidate) for candidate in (text, basename, labelish, first))


def collection_row_holder(row):
    if not isinstance(row, dict):
        return ""
    return row.get("holder") or row.get("who") or row.get("subject") or ""


def paginate_rows(rows, limit, offset):
    bounded_limit = max(1, min(TAKE_REVIEW_MAX_LIMIT, int(limit or 20)))
    bounded_offset = max(0, int(offset or 0))
    total = len(rows)
    page = rows[bounded_offset:bounded_offset + bounded_limit]
    next_offset = bounded_offset + bounded_limit if bounded_offset + bounded_limit < total else None
    previous_offset = max(0, bounded_offset - bounded_limit) if bounded_offset > 0 else None
    return page, {
        "limit": bounded_limit,
        "offset": bounded_offset,
        "total": total,
        "next_offset": next_offset,
        "previous_offset": previous_offset,
    }


def normalize_take_collection(payload, collection_key):
    if isinstance(payload, list):
        return {collection_key: payload}
    if not isinstance(payload, dict):
        return {collection_key: [], "backend_message": str(payload or "")}
    normalized = dict(payload)
    rows = normalized.get(collection_key)
    if rows is None:
        for key in ("items", "rows", "results", "data"):
            if isinstance(normalized.get(key), list):
                rows = normalized[key]
                break
    if (rows is None or rows == []) and ("claim" in normalized or "page_slug" in normalized):
        rows = [dict(normalized)]
    normalized[collection_key] = rows if isinstance(rows, list) else []
    return normalized


def take_review_filters_from_query(query):
    limit = clamp_take_review_limit(first_query_value(query, "limit", "20"))
    cursor = first_query_value(query, "cursor")
    offset = first_query_value(query, "offset")
    payload = {
        "status": first_query_value(query, "status", "pending") or "pending",
        "holder": first_query_value(query, "holder"),
        "source_slug": first_query_value(query, "source_slug") or first_query_value(query, "source"),
        "query": first_query_value(query, "q") or first_query_value(query, "query"),
        "limit": limit,
    }
    if cursor:
        payload["cursor"] = cursor
    if offset:
        try:
            payload["offset"] = max(0, int(offset))
        except ValueError:
            payload["offset"] = 0
    return payload


def takes_filters_from_query(query):
    holder = first_query_value(query, "holder")
    limit = clamp_take_review_limit(first_query_value(query, "limit", "20"))
    offset = parse_nonnegative_int(first_query_value(query, "offset"), 0)
    payload = {
        "page_slug": first_query_value(query, "page_slug") or first_query_value(query, "slug"),
        "holder": holder,
        "kind": first_query_value(query, "kind"),
        "limit": TAKES_VIEW_FETCH_LIMIT,
        "offset": 0,
    }
    if holder_filter_is_wildcard(holder):
        payload.pop("holder", None)
    for key in ("page_slug", "holder", "kind"):
        if not payload.get(key):
            payload.pop(key, None)
    if first_query_value(query, "active"):
        payload["active"] = first_query_value(query, "active").lower() == "true"
    if first_query_value(query, "resolved"):
        payload["resolved"] = first_query_value(query, "resolved").lower() == "true"
    return payload, holder, limit, offset


def take_review_action_payload(proposal_id, action, payload):
    raw_payload = payload if isinstance(payload, dict) else {}
    idempotency_key = str(raw_payload.get("idempotency_key") or "").strip()
    if not idempotency_key:
        idempotency_key = f"{TAKE_REVIEW_ACTOR}:{action}:{proposal_id}"
    return {
        "id": str(proposal_id),
        "proposal_id": str(proposal_id),
        "acted_by": str(raw_payload.get("acted_by") or TAKE_REVIEW_ACTOR).strip() or TAKE_REVIEW_ACTOR,
        "idempotency_key": idempotency_key,
        "reason": str(raw_payload.get("reason") or "").strip(),
        "source": "memory-stargraph",
        "provenance": {
            "surface": "memory-stargraph-ui",
            "ui_version": UI_VERSION,
        },
    }


def take_review_bulk_payload(payload):
    raw_payload = payload if isinstance(payload, dict) else {}
    action = str(raw_payload.get("action") or "").strip().lower()
    ids = [str(item).strip() for item in raw_payload.get("ids") or [] if str(item).strip()]
    if action not in {"accept", "reject", "defer"}:
        raise ValueError("action must be accept, reject, or defer")
    if not ids:
        raise ValueError("ids are required for bulk review")
    idempotency_key = str(raw_payload.get("idempotency_key") or "").strip() or f"{TAKE_REVIEW_ACTOR}:bulk:{action}:{','.join(ids)}"
    return {
        "action": action,
        "ids": ids[:TAKE_REVIEW_MAX_LIMIT],
        "acted_by": str(raw_payload.get("acted_by") or TAKE_REVIEW_ACTOR).strip() or TAKE_REVIEW_ACTOR,
        "idempotency_key": idempotency_key,
        "reason": str(raw_payload.get("reason") or "").strip(),
        "source": "memory-stargraph",
        "provenance": {
            "surface": "memory-stargraph-ui",
            "ui_version": UI_VERSION,
        },
    }


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


def yoda_runtime_config():
    config = load_config()
    backend = str(os.environ.get("MEMORY_STARGRAPH_YODA_BACKEND") or config.get("yoda_backend") or "openclaw").strip().lower()
    if backend not in YODA_BACKENDS:
        backend = "openclaw"
    model = str(os.environ.get("MEMORY_STARGRAPH_YODA_MODEL") or config.get("yoda_model") or "").strip()
    base_url = str(os.environ.get("MEMORY_STARGRAPH_YODA_BASE_URL") or config.get("yoda_base_url") or "").strip()
    api_key_env = str(os.environ.get("MEMORY_STARGRAPH_YODA_API_KEY_ENV") or config.get("yoda_api_key_env") or "OPENAI_API_KEY").strip()
    agent_ref = str(config.get("yoda_agent") or os.environ.get("MEMORY_STARGRAPH_YODA_AGENT") or "").strip()
    try:
        timeout = max(5, int(os.environ.get("MEMORY_STARGRAPH_YODA_TIMEOUT_SECONDS") or config.get("yoda_timeout_seconds") or 45))
    except (TypeError, ValueError):
        timeout = 45
    try:
        graph_query_timeout = max(5, min(300, int(os.environ.get("MEMORY_STARGRAPH_YODA_GRAPH_QUERY_TIMEOUT_SECONDS") or config.get("yoda_graph_query_timeout_seconds") or 30)))
    except (TypeError, ValueError):
        graph_query_timeout = 30
    return {
        "backend": backend,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "agent": agent_ref,
        "timeout": timeout,
        "graph_query_timeout": graph_query_timeout,
    }


def public_yoda_model_config():
    config = yoda_runtime_config()
    return {
        "backend": config["backend"],
        "model": config["model"],
        "base_url": config["base_url"],
        "api_key_env": config["api_key_env"],
        "agent": config["agent"],
        "timeout_seconds": config["timeout"],
        "graph_query_timeout_seconds": config["graph_query_timeout"],
        "api_key_available": bool(os.environ.get(config["api_key_env"])) if config["api_key_env"] else False,
        "backends": sorted(YODA_BACKENDS),
    }


def save_yoda_model_config(payload):
    backend = str(payload.get("backend") or "openclaw").strip().lower()
    if backend not in YODA_BACKENDS:
        raise ValueError(f"backend must be one of: {', '.join(sorted(YODA_BACKENDS))}")
    model = str(payload.get("model") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    api_key_env = str(payload.get("api_key_env") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY"
    agent = str(payload.get("agent") or "").strip()
    try:
        timeout_seconds = max(5, min(300, int(payload.get("timeout_seconds") or 45)))
    except (TypeError, ValueError):
        timeout_seconds = 45
    try:
        graph_query_timeout_seconds = max(5, min(300, int(payload.get("graph_query_timeout_seconds") or 30)))
    except (TypeError, ValueError):
        graph_query_timeout_seconds = 30
    if backend in {"openai", "openai_compatible", "ollama", "gbrain_think"} and not model:
        raise ValueError("model is required for the selected Yoda backend")
    if backend == "openai_compatible" and not base_url:
        raise ValueError("base_url is required for openai_compatible")

    config = read_local_config_file()
    config.update({
        "yoda_backend": backend,
        "yoda_model": model,
        "yoda_base_url": base_url,
        "yoda_api_key_env": api_key_env,
        "yoda_agent": agent,
        "yoda_timeout_seconds": timeout_seconds,
        "yoda_graph_query_timeout_seconds": graph_query_timeout_seconds,
    })
    write_local_config_file(config)
    return public_yoda_model_config()


def yoda_details(backend, model="", timeout=45):
    return {
        "backend": backend,
        "model": model,
        "openclaw_status": "not_used" if backend != "openclaw" else "unknown",
        "model_status": "unknown",
        "fallback_used": False,
        "stdout_preview": "",
        "stderr_preview": "",
        "error_summary": "",
        "timeout_seconds": timeout,
    }


def chat_completion_url(base_url):
    base = (base_url or "https://api.openai.com/v1").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def run_openai_compatible_yoda(prompt, config, return_details=False):
    backend = config["backend"]
    model = config["model"] or ("gpt-5.2" if backend == "openai" else "")
    details = yoda_details(backend, model, config["timeout"])
    if not model:
        details.update({"model_status": "unavailable", "error_summary": "Yoda model is not configured"})
        return {"output": None, **details} if return_details else None
    api_key = os.environ.get(config["api_key_env"] or "")
    if not api_key:
        details.update({"model_status": "unavailable", "error_summary": f"{config['api_key_env']} is not set in the service environment"})
        return {"output": None, **details} if return_details else None
    base_url = config["base_url"] or "https://api.openai.com/v1"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        chat_completion_url(base_url),
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=config["timeout"]) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
    except Exception as exc:  # noqa: BLE001
        details.update({"model_status": "api_error", "error_summary": str(exc)})
        return {"output": None, **details} if return_details else None
    answer = ""
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        answer = str(message.get("content") or "").strip() if isinstance(message, dict) else ""
    if not answer and isinstance(data, dict):
        answer = str(data.get("output_text") or data.get("text") or "").strip()
    details["model_status"] = "answered" if answer else "empty_output"
    return {"output": answer or None, **details} if return_details else (answer or None)


def run_ollama_yoda(prompt, config, return_details=False):
    model = config["model"]
    details = yoda_details("ollama", model, config["timeout"])
    if not model:
        details.update({"model_status": "unavailable", "error_summary": "Yoda model is not configured"})
        return {"output": None, **details} if return_details else None
    base_url = (config["base_url"] or "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=config["timeout"]) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
    except Exception as exc:  # noqa: BLE001
        details.update({"model_status": "api_error", "error_summary": str(exc)})
        return {"output": None, **details} if return_details else None
    message = data.get("message") if isinstance(data, dict) else {}
    answer = str(message.get("content") or data.get("response") or "").strip() if isinstance(message, dict) else ""
    details["model_status"] = "answered" if answer else "empty_output"
    return {"output": answer or None, **details} if return_details else (answer or None)


def run_gbrain_think_yoda(prompt, config, return_details=False):
    model = config["model"]
    details = yoda_details("gbrain_think", model, config["timeout"])
    command = ["think", prompt]
    if model:
        command.extend(["--model", model])
    try:
        answer = run_gbrain(*command, timeout=config["timeout"])
    except Exception as exc:  # noqa: BLE001
        details.update({"model_status": "api_error", "error_summary": str(exc)})
        return {"output": None, **details} if return_details else None
    details["model_status"] = "answered" if answer else "empty_output"
    return {"output": answer or None, **details} if return_details else (answer or None)


def run_yoda_model(prompt, return_details=False):
    config = yoda_runtime_config()
    if config["backend"] == "openclaw":
        return run_openclaw_agent(prompt, config=config, return_details=return_details)
    if config["backend"] in {"openai", "openai_compatible"}:
        return run_openai_compatible_yoda(prompt, config, return_details=return_details)
    if config["backend"] == "ollama":
        return run_ollama_yoda(prompt, config, return_details=return_details)
    if config["backend"] == "gbrain_think":
        return run_gbrain_think_yoda(prompt, config, return_details=return_details)
    details = yoda_details(config["backend"], config["model"], config["timeout"])
    details.update({"model_status": "unavailable", "error_summary": f"Unsupported Yoda backend: {config['backend']}"})
    return {"output": None, **details} if return_details else None


def run_openclaw_agent(prompt, timeout=45, return_details=False, config=None):
    config = config or yoda_runtime_config()
    timeout = int(config.get("timeout") or timeout or 45)
    agent_ref = str(config.get("agent") or "").strip()
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
    if str(config.get("model") or "").strip():
        command.extend(["--model", str(config.get("model")).strip()])
    env = os.environ.copy()
    bun_bin = Path.home() / ".bun" / "bin"
    env["PATH"] = f"{bun_bin}:/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
    details = yoda_details("openclaw", str(config.get("model") or ""), timeout)
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
    original_output = output
    raw_markers = [
        "Question-specific gbrain retrieval:",
        "Direct relationship context:",
        "Selected node content:",
        "OpenClaw agent unavailable; using deterministic GBrain retrieval fallback.",
    ]
    had_raw_fallback = any(marker in output for marker in raw_markers)
    if had_raw_fallback:
        output = re.split(
            r"(?:Question-specific gbrain retrieval:|Direct relationship context:|Selected node content:)",
            output,
            maxsplit=1,
        )[0]
        output = output.replace("OpenClaw agent unavailable; using deterministic GBrain retrieval fallback.", "").strip()
        if not output:
            output = "I found graph context for this node, but the answer model is unavailable right now. Try again after the Ask Yoda agent is reachable."
    payload["output"] = output
    if payload.get("source") == "fallback" and original_output:
        payload["fallback_output"] = str(payload.get("fallback_output") or original_output).strip()
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


def gbrain_file_ledger_has_relative_path(slug, relative_path):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return False
    try:
        output = run_gbrain("files", "list", slug)
    except Exception:  # noqa: BLE001
        return False
    filename = safe_path.name
    page = str(slug or "").strip("/")
    for line in str(output or "").splitlines():
        if filename not in line:
            continue
        if page and page not in line:
            continue
        return True
    return False


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


def ensure_media_reference_available(item):
    served_url = item.get("served_url")
    if not served_url or item.get("served_available"):
        return item
    relative_path = safe_media_relative_path(str(served_url).split("/media/", 1)[1] if "/media/" in served_url else item.get("url"))
    if not relative_path:
        return item
    result = None
    is_gbrain_file_reference = str(item.get("url") or "").strip().startswith(GBRAIN_FILE_SCHEME)
    source_file = find_media_source_file(relative_path)
    if source_file:
        result = copy_media_source_to_root(source_file, relative_path)
    if not result and is_gbrain_file_reference:
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
    if not result and not is_gbrain_file_reference:
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
    for base_url in GBRAIN_FILE_BASE_URLS:
        gbrain_file_url = gbrain_file_url_for_relative_path(base_url, safe_path)
        if not gbrain_file_url:
            continue
        try:
            result = download_media_url_to_root(gbrain_file_url, safe_path)
        except Exception:  # noqa: BLE001
            result = None
        if result:
            return result
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
            graph_output = run_gbrain("graph-query", slug, "--direction", "both", "--depth", "1", timeout=yoda_runtime_config()["graph_query_timeout"])
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
        prompt_state = yoda_system_prompt_state()
        lines = [
            prompt_state["prompt"],
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
            graph_output = run_gbrain(
                "graph-query",
                slug,
                "--direction",
                "both",
                "--depth",
                str(yoda_depth),
                timeout=yoda_runtime_config()["graph_query_timeout"],
            )
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
        agent_result = run_yoda_model(prompt, return_details=True)
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
            "source": agent_result.get("backend", "model") if isinstance(agent_result, dict) and agent_output else ("openclaw-agent" if agent_output else "fallback"),
            "fallback_used": not bool(agent_output),
            "model_status": agent_result.get("model_status", "unknown") if isinstance(agent_result, dict) else "unknown",
            "openclaw_status": agent_result.get("openclaw_status", "unknown") if isinstance(agent_result, dict) else "unknown",
            "model_backend": agent_result.get("backend", "unknown") if isinstance(agent_result, dict) else "unknown",
            "model_name": agent_result.get("model", "") if isinstance(agent_result, dict) else "",
            "error_summary": agent_result.get("error_summary", "") if isinstance(agent_result, dict) else "",
            "stdout_preview": agent_result.get("stdout_preview", "") if isinstance(agent_result, dict) else "",
            "stderr_preview": agent_result.get("stderr_preview", "") if isinstance(agent_result, dict) else "",
        }
        if agent_output:
            return {"output": agent_output, "source": diagnostics["source"], "timings": timings, "request_id": request_id, "diagnostics": diagnostics}
        fallback_text = f"Question: {question}\nSelected node: {slug}\n\nI gathered selected-node, graph, backlink, search, and source-node context, but the Ask Yoda model is unavailable right now."
        try:
            fallback_output = self.ask_gbrain(slug, question)
        except Exception as exc:  # noqa: BLE001
            fallback_output = f"Ask GBrain fallback unavailable: {exc}"
        return {
            "output": fallback_text or "I found no concise answer in the graph context for this question yet.",
            "fallback_output": fallback_output,
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
        relative_path = relative_path_for_local_media(local_media)
        if not relative_path:
            raise RuntimeError("Could not create a safe relative media path for this attachment.")
        try:
            run_gbrain("files", "upload", file_path, "--page", slug)
        except RuntimeError as exc:
            raise RuntimeError(
                "Attachment upload did not reach GBrain files; markdown was not updated. "
                "Fix the GBrain file upload path and try again."
            ) from exc
        if not gbrain_file_ledger_has_relative_path(slug, relative_path):
            raise RuntimeError(
                f"Attachment upload was not visible in GBrain files for {slug}; markdown was not updated."
            )
        markdown_updated = False
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

    def list_take_proposals(self, filters=None):
        payload = dict(filters or {})
        payload["limit"] = clamp_take_review_limit(payload.get("limit"))
        result = gbrain_call_tool("take_proposals_list", payload, timeout=30)
        normalized = normalize_take_collection(result, "proposals")
        normalized.setdefault("filters", payload)
        normalized.setdefault("counts", {})
        return normalized

    def review_take_proposal(self, proposal_id, action, payload=None):
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"accept", "reject", "defer"}:
            raise ValueError("action must be accept, reject, or defer")
        review_payload = take_review_action_payload(proposal_id, normalized_action, payload or {})
        result = gbrain_call_tool(f"take_proposals_{normalized_action}", review_payload, timeout=45)
        if isinstance(result, dict):
            return {"ok": True, "action": normalized_action, "proposal_id": str(proposal_id), **result}
        return {"ok": True, "action": normalized_action, "proposal_id": str(proposal_id), "result": result}

    def bulk_review_take_proposals(self, payload=None):
        review_payload = take_review_bulk_payload(payload or {})
        result = gbrain_call_tool("take_proposals_bulk", review_payload, timeout=60)
        if isinstance(result, dict):
            return {"ok": True, **result}
        return {"ok": True, "results": result}

    def list_takes(self, filters=None):
        payload = dict(filters or {})
        payload["limit"] = max(1, min(TAKES_VIEW_FETCH_LIMIT, int(payload.get("limit") or TAKES_VIEW_FETCH_LIMIT)))
        result = gbrain_call_tool("takes_list", payload, timeout=30)
        normalized = normalize_take_collection(result, "takes")
        normalized.setdefault("filters", payload)
        return normalized


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
            relative_path = safe_media_relative_path(str(request_path or "").split("/media/", 1)[1] if "/media/" in str(request_path or "") else "")
            if relative_path:
                materialize_gbrain_file_reference(relative_path)
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
        if parsed.path == "/api/yoda-model-config":
            try:
                return self.end_json({"ok": True, **public_yoda_model_config()})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/yoda-system-prompt":
            try:
                return self.end_json({"ok": True, **yoda_system_prompt_state()})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/yoda-logs":
            query = parse_qs(parsed.query)
            slug = (query.get("slug") or [""])[0].strip()
            limit = (query.get("limit") or ["20"])[0]
            return self.end_json({"ok": True, "slug": slug, "entries": yoda_log_entries(slug or None, limit)})
        if parsed.path.startswith("/api/yoda-chat/"):
            slug = unquote(parsed.path.split("/api/yoda-chat/", 1)[1]).strip("/")
            return self.end_json({"ok": True, "slug": slug, "messages": yoda_chat_history(slug)})
        if parsed.path == "/api/resolver/events":
            query = parse_qs(parsed.query)
            limit = (query.get("limit") or ["50"])[0]
            producer = (query.get("producer") or [""])[0].strip()
            outcome = (query.get("outcome") or [""])[0].strip()
            try:
                data = resolver_list_events(limit, producer or None, outcome or None)
                return self.end_json({"ok": True, **data})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/resolver/health":
            try:
                return self.end_json({"ok": True, **resolver_feedback_health()})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/resolver/proposals":
            query = parse_qs(parsed.query)
            status_filter = (query.get("status") or [""])[0].strip()
            limit = parse_nonnegative_int((query.get("limit") or ["100"])[0], 100)
            try:
                return self.end_json({"ok": True, **resolver_list_proposals(status_filter, limit)})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path in ("/api/take-proposals", "/api/hosting/take-proposals"):
            filters = take_review_filters_from_query(parse_qs(parsed.query))
            requested_holder = filters.get("holder", "")
            requested_limit = filters.get("limit", 20)
            requested_offset = parse_nonnegative_int(filters.get("offset"), 0)
            if holder_filter_is_wildcard(requested_holder):
                filters = dict(filters)
                filters.pop("holder", None)
                filters["limit"] = TAKE_REVIEW_MAX_LIMIT
                filters["offset"] = 0
            try:
                data = STORE.list_take_proposals(filters)
                if holder_filter_is_wildcard(requested_holder):
                    proposals = data.get("proposals") if isinstance(data, dict) else []
                    if not isinstance(proposals, list):
                        proposals = []
                    proposals = [row for row in proposals if holder_matches_filter(collection_row_holder(row), requested_holder)]
                    page, metadata = paginate_rows(proposals, requested_limit, requested_offset)
                    data = dict(data)
                    data["proposals"] = page
                    data.update(metadata)
                    data["holder_filter"] = requested_holder
                return self.end_json({"ok": True, **data})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path in ("/api/takes", "/api/hosting/takes"):
            filters, holder_filter, limit, offset = takes_filters_from_query(parse_qs(parsed.query))
            try:
                data = normalize_take_collection(STORE.list_takes(filters), "takes")
                rows = data.get("takes") if isinstance(data, dict) else []
                if not isinstance(rows, list):
                    rows = []
                if holder_filter_is_wildcard(holder_filter):
                    rows = [row for row in rows if holder_matches_filter(collection_row_holder(row), holder_filter)]
                page, metadata = paginate_rows(rows, limit, offset)
                data = dict(data)
                data["takes"] = page
                data.update(metadata)
                data.setdefault("filters", filters)
                data["holder_filter"] = holder_filter
                return self.end_json({"ok": True, **data})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
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
        if parsed.path == "/api/yoda-model-config":
            try:
                payload = self.read_json_body()
                return self.end_json({"ok": True, **save_yoda_model_config(payload)})
            except ValueError as exc:
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/yoda-system-prompt":
            try:
                payload = self.read_json_body()
                if payload.get("reset"):
                    return self.end_json({"ok": True, **reset_yoda_system_prompt()})
                return self.end_json({"ok": True, **save_yoda_system_prompt(payload.get("prompt"))})
            except ValueError as exc:
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/yoda-chat/"):
            slug = unquote(parsed.path.split("/api/yoda-chat/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                if payload.get("clear"):
                    clear_yoda_chat_history(slug)
                    return self.end_json({"ok": True, "slug": slug, "messages": []})
                messages = save_yoda_chat_history(slug, payload.get("messages") or [])
                return self.end_json({"ok": True, "slug": slug, "messages": messages})
            except ValueError as exc:
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/resolver/events":
            try:
                payload = self.read_json_body()
                data = resolver_submit_event(payload)
                return self.end_json({"ok": True, **data})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/resolver/proposals/generate":
            try:
                payload = self.read_json_body()
                return self.end_json({"ok": True, **resolver_generate_proposals(payload)})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path == "/api/resolver/dream":
            try:
                payload = self.read_json_body()
                if payload.get("enabled") is False:
                    return self.end_json({"ok": True, "summary": {"enabled": False, "auto_applied": 0}})
                data = resolver_generate_proposals({"run_source": "memory-stargraph-dream", "min_evidence": payload.get("min_evidence", 2)})
                return self.end_json({"ok": True, "summary": data.get("dream_run", data)})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        resolver_action_match = re.match(r"^/api/resolver/proposals/([^/]+)/(accept|reject|apply|impact)$", parsed.path)
        if resolver_action_match:
            proposal_id = unquote(resolver_action_match.group(1)).strip()
            action = resolver_action_match.group(2)
            try:
                payload = self.read_json_body()
                if action == "apply":
                    data = resolver_apply_proposal(proposal_id, payload)
                    return self.end_json({"ok": True, **data})
                if action == "impact":
                    data = resolver_measure_impact(proposal_id, payload)
                    return self.end_json({"ok": True, **data})
                data = resolver_update_proposal(proposal_id, action, payload)
                return self.end_json({"ok": True, **data})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        take_action_match = re.match(r"^/api/(?:hosting/)?take-proposals/([^/]+)/(accept|reject|defer)$", parsed.path)
        if take_action_match:
            proposal_id = unquote(take_action_match.group(1)).strip()
            action = take_action_match.group(2)
            try:
                payload = self.read_json_body()
                data = STORE.review_take_proposal(proposal_id, action, payload)
                return self.end_json(data)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path in ("/api/take-proposals/bulk", "/api/hosting/take-proposals/bulk"):
            try:
                payload = self.read_json_body()
                take_review_bulk_payload(payload)
                data = STORE.bulk_review_take_proposals(payload)
                return self.end_json(data)
            except ValueError as exc:
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
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
                append_yoda_log(slug, {
                    "request_id": result.get("request_id"),
                    "source": result.get("source"),
                    "timings": result.get("timings"),
                    "diagnostics": result.get("diagnostics"),
                })
                try:
                    resolver_submit_event({
                        "event_id": result.get("request_id") or f"ask-yoda:{slug}:{hashlib.sha1(question.encode('utf-8')).hexdigest()[:12]}",
                        "producer": "stargraph",
                        "resolver_version": UI_VERSION,
                        "user_intent": question,
                        "selected_skill": "Ask Yoda",
                        "selected_context": slug,
                        "operation": "/api/entity-ask-yoda",
                        "result_status": result.get("diagnostics", {}).get("model_status") or result.get("source"),
                        "fallback_used": result.get("diagnostics", {}).get("fallback_used") or result.get("source") == "fallback",
                        "related_slug": slug,
                        "error_class": result.get("diagnostics", {}).get("error_summary"),
                    })
                except Exception:
                    pass
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
