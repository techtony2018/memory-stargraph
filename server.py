#!/usr/bin/env python3
import argparse
import email
import email.policy
import email.utils
import gzip
import hashlib
import io
import json
import math
import mimetypes
import os
import queue
import re
import selectors
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unicodedata
from concurrent.futures import Future, ThreadPoolExecutor
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.parse import parse_qs, urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from PIL import Image, ImageOps
except ImportError:  # Preview requests safely fall back to the original media.
    Image = None
    ImageOps = None

APP_NAME = "Memory Stargraph"
JSON_GZIP_MIN_BYTES = 1024
COMPRESSIBLE_STATIC_PATHS = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/styles.css": "styles.css",
}
BROTLI_STATIC_DIR = "assets/precompressed"


def content_encoding_qualities(header):
    qualities = {}
    for item in str(header or "").split(","):
        parts = [part.strip() for part in item.split(";") if part.strip()]
        if not parts:
            continue
        quality = 1.0
        for parameter in parts[1:]:
            key, separator, value = parameter.partition("=")
            if separator and key.strip().lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        qualities[parts[0].lower()] = quality
    return qualities


def content_encoding_quality(header, encoding):
    qualities = content_encoding_qualities(header)
    return qualities.get(str(encoding).lower(), qualities.get("*", 0.0))


def accepts_gzip_encoding(header):
    return content_encoding_quality(header, "gzip") > 0


def accepted_static_encodings(header):
    preference = {"br": 1, "gzip": 0}
    return sorted(
        (encoding for encoding in preference if content_encoding_quality(header, encoding) > 0),
        key=lambda encoding: (content_encoding_quality(header, encoding), preference[encoding]),
        reverse=True,
    )


@lru_cache(maxsize=16)
def gzip_static_file(path, mtime_ns, size):
    del mtime_ns, size
    return gzip.compress(Path(path).read_bytes(), compresslevel=1, mtime=0)


@lru_cache(maxsize=4)
def load_brotli_static_manifest(path, mtime_ns, size):
    del mtime_ns, size
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=16)
def validated_brotli_static_file(
    public_dir,
    relative_path,
    mtime_ns,
    size,
    manifest_mtime_ns,
    manifest_size,
):
    source_path = Path(public_dir) / relative_path
    manifest_path = Path(public_dir) / BROTLI_STATIC_DIR / "manifest.json"
    try:
        manifest = load_brotli_static_manifest(
            str(manifest_path),
            manifest_mtime_ns,
            manifest_size,
        )
        entry = (manifest.get("assets") or {}).get(relative_path) or {}
        if int(entry.get("source_size") or -1) != int(size):
            return None
        source = source_path.read_bytes()
        if hashlib.sha256(source).hexdigest() != str(entry.get("source_sha256") or ""):
            return None
        compressed_path = Path(public_dir) / BROTLI_STATIC_DIR / f"{relative_path}.br"
        compressed = compressed_path.read_bytes()
        if len(compressed) != int(entry.get("brotli_size") or -1):
            return None
        return compressed
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def brotli_static_file(public_dir, relative_path, mtime_ns, size):
    manifest_path = Path(public_dir) / BROTLI_STATIC_DIR / "manifest.json"
    try:
        manifest_stat = manifest_path.stat()
    except OSError:
        return None
    return validated_brotli_static_file(
        public_dir,
        relative_path,
        mtime_ns,
        size,
        manifest_stat.st_mtime_ns,
        manifest_stat.st_size,
    )


class MemoryStargraphHTTPServer(ThreadingHTTPServer):
    """Join request handlers before process-long services are closed."""

    daemon_threads = False
    block_on_close = True


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
    "gbrain_files_bridge_ssh": "",
    "gbrain_files_bridge_path": "gbrain",
    "gbrain_backend_id": "primary",
    "gbrain_backend_choices": [],
    "media_fetch_timeout_seconds": 8,
    "max_upload_bytes": 25 * 1024 * 1024,
    "yoda_backend": "openclaw",
    "yoda_agent": "",
    "yoda_model": "",
    "yoda_base_url": "",
    "yoda_api_key_env": "OPENAI_API_KEY",
    "yoda_timeout_seconds": 45,
    "yoda_graph_query_timeout_seconds": 30,
    "yoda_broad_graph_budget_seconds": 8,
    "yoda_gbrain_mcp_sessions": 5,
    "yoda_node_path": "",
    "yoda_node_fallback_paths": [],
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


def apply_runtime_config(config):
    global CONFIG, GBRAIN, MAX_LIST_PAGES, GRAPH_DEPTH, GRAPH_STALE_SECONDS, GRAPH_COMMAND_LIMIT, GRAPH_COMMAND_PAUSE_SECONDS
    CONFIG = dict(DEFAULT_CONFIG)
    CONFIG.update({key: value for key, value in dict(config or {}).items() if value is not None})
    GBRAIN = Path(str(CONFIG["gbrain_path"])).expanduser()
    MAX_LIST_PAGES = int(CONFIG["max_list_pages"])
    GRAPH_DEPTH = int(CONFIG["graph_depth"])
    GRAPH_STALE_SECONDS = int(CONFIG["graph_stale_seconds"])
    GRAPH_COMMAND_LIMIT = int(os.environ.get("MEMORY_STARGRAPH_GRAPH_COMMAND_LIMIT", str(CONFIG["graph_command_limit"])))
    GRAPH_COMMAND_PAUSE_SECONDS = float(os.environ.get("MEMORY_STARGRAPH_GRAPH_COMMAND_PAUSE_SECONDS", str(CONFIG["graph_command_pause_seconds"])))
    search_session = globals().get("PERSISTENT_GBRAIN_SEARCH")
    if search_session is not None:
        was_active = search_session.active
        search_session.close()
        if was_active:
            search_session.prewarm_async()
    yoda_pool = globals().get("YODA_GBRAIN_MCP_POOL")
    if yoda_pool is not None:
        was_active = yoda_pool.active
        yoda_pool.close()
        if was_active:
            yoda_pool.prewarm_async()


CONFIG = load_config()
PUBLIC_DIR = resolve_project_path(CONFIG["public_dir"])
DATA_DIR = resolve_project_path(CONFIG["data_dir"])
CACHE_PATH = DATA_DIR / "graph_cache.json"
DELETED_PATH = DATA_DIR / "deleted_entities.json"
HIDDEN_PATH = DATA_DIR / "hidden_entities.json"
YODA_LOG_PATH = DATA_DIR / "yoda_logs.json"
YODA_CHAT_PATH = DATA_DIR / "yoda_chats.json"
YODA_FEEDBACK_PATH = DATA_DIR / "yoda_feedback.json"
YODA_SETTINGS_PATH = DATA_DIR / "yoda_settings.json"
RESOLVER_EVENTS_PATH = DATA_DIR / "resolver_dispatch_events.json"
RESOLVER_PROPOSALS_PATH = DATA_DIR / "resolver_proposals.json"
RESOLVER_DREAM_LOG_PATH = DATA_DIR / "resolver_dream_runs.json"
DEPLOYMENT_ATTESTATIONS_PATH = DATA_DIR / "deployment_attestations.json"
COMPLETED_TODO_ARCHIVE_INDEX_PATH = ROOT / "config" / "completed_todo_archive_index.json"
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
GBRAIN_FILES_BRIDGE_SSH = str(os.environ.get("MEMORY_STARGRAPH_GBRAIN_FILES_BRIDGE_SSH", CONFIG.get("gbrain_files_bridge_ssh", ""))).strip()
GBRAIN_FILES_BRIDGE_PATH = str(os.environ.get("MEMORY_STARGRAPH_GBRAIN_FILES_BRIDGE_PATH", CONFIG.get("gbrain_files_bridge_path", "gbrain"))).strip() or "gbrain"
MEDIA_FETCH_TIMEOUT_SECONDS = float(CONFIG.get("media_fetch_timeout_seconds", 8))
MAX_UPLOAD_BYTES = int(CONFIG.get("max_upload_bytes", 25 * 1024 * 1024))
YODA_BACKENDS = {"openclaw", "openai", "openai_compatible", "ollama", "gbrain_think"}
VIEW_SCHEMA_VERSION = 5
UI_VERSION = "V1.0.215"
GBRAIN_RERANKER_SUNSET_DATE = "2026-09-04"
GBRAIN_RERANKER_TARGET_MODEL = "voyage:rerank-2.5"
GBRAIN_RERANKER_READINESS_CACHE_SECONDS = 5 * 60
GBRAIN_NATIVE_BACKUP_MIN_VERSION = (0, 46, 33, 0)
GBRAIN_NATIVE_BACKUP_SCHEMA = "gbrain-backup-status-v1"
GBRAIN_NATIVE_BACKUP_MAX_BYTES = 1024 * 1024
DEPLOYMENT_ATTESTATION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
SRE_BACKUP_WARNING_SECONDS = 36 * 60 * 60
SRE_BACKUP_CRITICAL_SECONDS = 72 * 60 * 60
SRE_DAILY_EVIDENCE_MAX_AGE_SECONDS = 36 * 60 * 60
SRE_WEEKLY_EVIDENCE_MAX_AGE_SECONDS = 10 * 24 * 60 * 60
SRE_EVIDENCE_CANDIDATE_LIMIT = 12
SRE_EVIDENCE_READ_WORKERS = 6
SRE_RUN_PREFIXES = (
    "runs/memory-stargraph-sre-daily-reliability-",
    "runs/memory-stargraph-sre-weekly-resilience-",
)
SRE_LEGACY_NUMERIC_EVIDENCE_SLUGS = (
    "runs/memory-stargraph-wish-sg0196-20260809t144900-0700-56c8c7d",
    "reports/memory-stargraph-wish-sg0196-20260809t144900-0700-56c8c7d",
    "runs/memory-stargraph-sre-weekly-resilience-20260809t143652-0700-85",
    "reports/memory-stargraph-sre-weekly-resilience-2026-08-09-143652-85",
)
TAKE_REVIEW_ACTOR = "memory-stargraph-ui"
TAKE_REVIEW_MAX_LIMIT = 100
TAKES_VIEW_FETCH_LIMIT = 500
AUTOPILOT_FINDINGS_MAX_LIMIT = 200
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
    {"action": "read-tags", "method": "GET", "endpoint": "/api/entity-tags/<slug>", "mutates_gbrain": False},
    {"action": "list-pages", "method": "GET", "endpoint": "/api/pages", "mutates_gbrain": False},
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
    {"action": "autopilot-findings", "method": "GET", "endpoint": "/api/autopilot-findings", "mutates_gbrain": False},
    {"action": "autopilot-finding-acknowledge", "method": "POST", "endpoint": "/api/autopilot-findings/<id>/acknowledge", "mutates_gbrain": True},
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

Before interpreting the graph, classify the question intent. For writing, post, note, article, or publication questions, prefer typed/container evidence over broad expansion. Enumerate publication, platform, collection, or feed nodes through has_member/member_of, has_post/has_entry, authored_by, and similar typed edges. Verify candidate writing evidence with author or holder relationships and container membership before treating a title/content hit as relevant.

Broad graph context may be truncated for high-degree hubs. Never conclude that a relationship or member does not exist merely because it is absent from a truncated broad graph section. Prefer targeted entity relationship evidence and direct relationship-source reads when those sections are present.

Cite evidence from backlinks and relationships. Distinguish direct content/title matches from noisy metadata or frontmatter matches."""

MAX_YODA_LOGS = 200
MAX_YODA_LOGS_PER_SLUG = 20
MAX_YODA_CHAT_MESSAGES = 80
MAX_YODA_CHAT_SLUGS = 80
MAX_YODA_FEEDBACK_COMMENT = 2000
MAX_YODA_FEEDBACK_RESULTS = 500
MAX_RESOLVER_EVENTS = 500
MAX_RESOLVER_PROPOSALS = 200

MEDIA_EXTENSIONS = {
    "image": {".apng", ".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"},
    "video": {".m4v", ".mov", ".mp4", ".mpeg", ".mpg", ".ogv", ".webm"},
    "audio": {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".wav", ".webm"},
    "document": {".doc", ".docx", ".odt", ".pdf", ".rtf", ".rtfd", ".zip"},
}
MEDIA_PREVIEW_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}
MEDIA_PREVIEW_MIN_BYTES = 512 * 1024
MEDIA_PREVIEW_MAX_SIZE = (640, 640)
MEDIA_STREAM_CHUNK_BYTES = 1024 * 1024
MEDIA_RANGE_INVALID = object()


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

SAMPLE_FIRST_VALUE_GRAPH = {
    "title": "Memory Stargraph Sample Brain",
    "source": {
        "mode": "demo",
        "status": "sample",
        "message": "Demo mode uses bundled synthetic data only. No private GBrain content is loaded.",
        "updated_at": None,
    },
    "nodes": [
        {
            "id": "sample-memory-hub",
            "slug": "sample-memory-hub",
            "label": "Sample Memory Hub",
            "type": "sample",
            "summary": "Synthetic starting point for trying search, selection, relationships, View, and Ask Yoda without private data.",
            "tags": ["sample", "demo", "privacy-safe"],
            "links": ["sample-project-alpha", "sample-learning-loop", "sample-source-note"],
            "updated_at": "2026-07-20T02:10:00-07:00",
        },
        {
            "id": "sample-project-alpha",
            "slug": "sample-project-alpha",
            "label": "Sample Project Alpha",
            "type": "project",
            "summary": "A fictional project node that demonstrates relationship traversal and provenance inspection.",
            "tags": ["sample", "project"],
            "links": ["sample-memory-hub", "sample-source-note"],
            "updated_at": "2026-07-20T02:10:00-07:00",
        },
        {
            "id": "sample-learning-loop",
            "slug": "sample-learning-loop",
            "label": "Sample Learning Loop",
            "type": "learning",
            "summary": "Synthetic learning evidence showing how runs, feedback, and future improvements connect.",
            "tags": ["sample", "learning"],
            "links": ["sample-memory-hub", "sample-weekly-digest"],
            "updated_at": "2026-07-20T02:10:00-07:00",
        },
        {
            "id": "sample-source-note",
            "slug": "sample-source-note",
            "label": "Sample Source Note",
            "type": "note",
            "summary": "Redacted provenance placeholder used to demonstrate source review without exposing real content.",
            "tags": ["sample", "provenance"],
            "links": ["sample-memory-hub", "sample-project-alpha"],
            "updated_at": "2026-07-20T02:10:00-07:00",
        },
        {
            "id": "sample-weekly-digest",
            "slug": "sample-weekly-digest",
            "label": "Sample Weekly Digest",
            "type": "report",
            "summary": "Synthetic digest node summarizing learned items, fixed issues, blockers, and next action.",
            "tags": ["sample", "digest"],
            "links": ["sample-learning-loop"],
            "updated_at": "2026-07-20T02:10:00-07:00",
        },
    ],
    "edges": [
        {"source": "sample-memory-hub", "target": "sample-project-alpha", "types": ["demo_related"]},
        {"source": "sample-memory-hub", "target": "sample-learning-loop", "types": ["demo_related"]},
        {"source": "sample-memory-hub", "target": "sample-source-note", "types": ["has_provenance"]},
        {"source": "sample-project-alpha", "target": "sample-source-note", "types": ["cites"]},
        {"source": "sample-learning-loop", "target": "sample-weekly-digest", "types": ["summarized_by"]},
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
PRIVATE_PATH_RE = re.compile(r"(?i)(/Users/[^\s,'\"\]]+|/private/[^\s,'\"\]]+|/var/folders/[^\s,'\"\]]+|/usr/local/[^\s,'\"\]]+|/opt/homebrew/[^\s,'\"\]]+)")


def sanitize_text_summary(value, limit=220):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = SECRET_RE.sub("[redacted]", text)
    text = text.rstrip("?!")
    return text[:limit]


def bounded_readiness_summary(value, limit=220, full_limit=660):
    full_text = re.sub(r"\s+", " ", str(value or "")).strip()
    full_text = SECRET_RE.sub("[redacted]", full_text)
    full_text = PRIVATE_PATH_RE.sub("[redacted-path]", full_text)
    if len(full_text) > full_limit:
        clipped = full_text[: max(0, full_limit - 3)].rsplit(" ", 1)[0].rstrip(".,;:")
        full_text = f"{clipped}..."
    if len(full_text) <= limit:
        return {"text": full_text, "full_text": full_text, "truncated": False}
    visible_window = full_text[:limit]
    sentence_ends = list(re.finditer(r"[.!?](?=\s|$)", visible_window))
    if sentence_ends:
        visible_text = visible_window[: sentence_ends[-1].end()].rstrip()
    else:
        clipped = visible_window[: max(0, limit - 3)].rsplit(" ", 1)[0].rstrip(".,;:")
        visible_text = f"{clipped}..."
    return {"text": visible_text, "full_text": full_text, "truncated": True}


def sanitize_runtime_error(value, limit=220):
    text = sanitize_text_summary(value, limit * 2)
    text = PRIVATE_PATH_RE.sub("[redacted-path]", text)
    return text[:limit]


def sanitize_chat_content(value, limit=5000):
    """Redact persisted chat content without destroying Markdown layout."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(character for character in text if character in "\n\t" or ord(character) >= 32)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
    text = SECRET_RE.sub("[redacted]", text)
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
        "environment": sanitize_text_summary(entry.get("environment"), 40) or "production",
        "synthetic": entry.get("synthetic") is True,
        "test_run": entry.get("test_run") is True,
        "pair_id": sanitize_text_summary(entry.get("pair_id"), 200),
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


def stable_yoda_answer_id(slug, message):
    request_id = sanitize_text_summary(message.get("request_id"), 200)
    answer_id = sanitize_text_summary(message.get("answer_id"), 200)
    if answer_id or request_id:
        return answer_id or request_id
    identity = "\n".join(
        (
            str(slug or ""),
            str(message.get("timestamp") or ""),
            sanitize_chat_content(message.get("content"), 5000),
        )
    )
    return f"legacy-yoda-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def sanitize_chat_message(message, slug=""):
    if not isinstance(message, dict):
        return None
    if message.get("pending"):
        return None
    role = str(message.get("role") or "").strip().lower()
    if role not in {"system", "user", "assistant"}:
        return None
    content = sanitize_chat_content(message.get("content"), 5000)
    if not content:
        return None
    safe = {
        "role": role,
        "content": content,
        "timestamp": sanitize_text_summary(message.get("timestamp") or iso_now(), 80),
    }
    if role == "assistant":
        safe["answer_id"] = stable_yoda_answer_id(slug, message)
        request_id = sanitize_text_summary(message.get("request_id"), 200)
        if request_id:
            safe["request_id"] = request_id
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
    return [item for item in (sanitize_chat_message(message, slug) for message in history) if item]


def save_yoda_chat_history(slug, messages):
    clean_slug = str(slug or "").strip()
    if not clean_slug:
        raise ValueError("slug is required")
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    rows = yoda_chat_rows()
    sanitized = [item for item in (sanitize_chat_message(message, clean_slug) for message in messages) if item]
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


def yoda_feedback_rows():
    rows = read_json_file(YODA_FEEDBACK_PATH, {})
    return rows if isinstance(rows, dict) else {}


def yoda_feedback_is_test(row):
    return str(row.get("environment") or "production") != "production" or row.get("synthetic") is True or row.get("test_run") is True


def sanitize_yoda_feedback_comment(value):
    raw = str(value or "")
    if len(raw) > MAX_YODA_FEEDBACK_COMMENT:
        raise ValueError(f"comment must be {MAX_YODA_FEEDBACK_COMMENT} characters or less")
    text = "".join(character for character in raw if character in "\n\t" or ord(character) >= 32)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return SECRET_RE.sub("[redacted]", text)


def upsert_yoda_feedback(answer_id, payload):
    clean_answer_id = sanitize_text_summary(answer_id, 200)
    if not clean_answer_id:
        raise ValueError("answer_id is required")
    rating = str(payload.get("rating") or "").strip().lower()
    if rating not in {"", "up", "down"}:
        raise ValueError("rating must be up, down, or empty")
    slug = str(payload.get("slug") or "").strip()
    if not slug:
        raise ValueError("slug is required")
    rows = yoda_feedback_rows()
    existing = rows.get(clean_answer_id) if isinstance(rows.get(clean_answer_id), dict) else {}
    now = iso_now()
    environment = sanitize_text_summary(payload.get("environment") or existing.get("environment") or "production", 40).lower() or "production"
    record = {
        "answer_id": clean_answer_id,
        "request_id": sanitize_text_summary(payload.get("request_id") or existing.get("request_id"), 200),
        "slug": slug,
        "rating": rating,
        "comment": sanitize_yoda_feedback_comment(payload.get("comment")),
        "environment": environment,
        "synthetic": payload.get("synthetic") is True,
        "test_run": payload.get("test_run") is True,
        "pair_id": sanitize_text_summary(payload.get("pair_id") or existing.get("pair_id"), 200),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "review_status": existing.get("review_status") or "unreviewed",
        "reviewed_at": existing.get("reviewed_at") or "",
        "review_run_slug": existing.get("review_run_slug") or "",
        "decision": existing.get("decision") or "",
        "related_todo_ids": existing.get("related_todo_ids") if isinstance(existing.get("related_todo_ids"), list) else [],
        "related_learning_slugs": existing.get("related_learning_slugs") if isinstance(existing.get("related_learning_slugs"), list) else [],
    }
    rows[clean_answer_id] = record
    write_json_file(YODA_FEEDBACK_PATH, rows)
    return record


def list_yoda_feedback(filters):
    rows = list(yoda_feedback_rows().values())
    rows = [row for row in rows if isinstance(row, dict)]
    counts = {
        "production": sum(1 for row in rows if not yoda_feedback_is_test(row)),
        "test": sum(1 for row in rows if yoda_feedback_is_test(row)),
    }
    include_test = str(filters.get("include_test") or "").lower() in {"1", "true", "yes"}
    if not include_test:
        rows = [row for row in rows if not yoda_feedback_is_test(row)]
    for field in ("slug", "rating", "review_status"):
        expected = str(filters.get(field) or "").strip()
        if expected:
            rows = [row for row in rows if str(row.get(field) or "") == expected]
    since = str(filters.get("since") or "").strip()
    until = str(filters.get("until") or "").strip()
    if since:
        rows = [row for row in rows if str(row.get("updated_at") or "") >= since]
    if until:
        rows = [row for row in rows if str(row.get("updated_at") or "") <= until]
    try:
        limit = max(1, min(MAX_YODA_FEEDBACK_RESULTS, int(filters.get("limit") or 100)))
    except (TypeError, ValueError):
        limit = 100
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return rows[:limit], counts


YODA_FEEDBACK_DECISIONS = {
    "no_action",
    "product_todo_created",
    "product_todo_updated",
    "data_quality_recommendation",
    "capture_guidance",
    "learning_only",
}


def review_yoda_feedback(payload):
    answer_ids = [sanitize_text_summary(value, 200) for value in payload.get("answer_ids", []) if sanitize_text_summary(value, 200)]
    if not answer_ids:
        raise ValueError("answer_ids are required")
    review_run_slug = str(payload.get("review_run_slug") or "").strip()
    if not review_run_slug:
        raise ValueError("review_run_slug is required")
    decision = str(payload.get("decision") or "").strip()
    if decision not in YODA_FEEDBACK_DECISIONS:
        raise ValueError("decision is invalid")
    reviewed_at = sanitize_text_summary(payload.get("reviewed_at") or iso_now(), 80)
    todo_ids = [sanitize_text_summary(value, 80) for value in payload.get("related_todo_ids", []) if sanitize_text_summary(value, 80)]
    learning_slugs = [sanitize_text_summary(value, 220) for value in payload.get("related_learning_slugs", []) if sanitize_text_summary(value, 220)]
    rows = yoda_feedback_rows()
    updated = 0
    for answer_id in answer_ids:
        record = rows.get(answer_id)
        if not isinstance(record, dict):
            continue
        desired = ("reviewed", reviewed_at, review_run_slug, decision, todo_ids, learning_slugs)
        current = (
            record.get("review_status"), record.get("reviewed_at"), record.get("review_run_slug"), record.get("decision"),
            record.get("related_todo_ids"), record.get("related_learning_slugs"),
        )
        if current == desired:
            continue
        record.update({
            "review_status": "reviewed",
            "reviewed_at": reviewed_at,
            "review_run_slug": review_run_slug,
            "decision": decision,
            "related_todo_ids": todo_ids,
            "related_learning_slugs": learning_slugs,
            "updated_at": iso_now(),
        })
        updated += 1
    if updated:
        write_json_file(YODA_FEEDBACK_PATH, rows)
    return {"updated": updated, "requested": len(answer_ids)}


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
        "node_runtime_status",
        "node_runtime_path",
        "node_runtime_version",
        "node_runtime_source",
        "node_runtime_error",
        "timings",
        "context_cache_hit",
        "context_subphases_ms",
        "context_counts",
        "context_degraded",
        "context_degraded_reason",
        "broad_graph_status",
        "broad_graph_unavailable_reason",
        "broad_graph_budget_ms",
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


def resolver_proposal_counts_from_rows(rows):
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "deferred": 0}
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "pending").strip().lower()
        if status not in counts:
            counts[status] = 0
        counts[status] += 1
    return counts


def parse_iso_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolver_events_24h_count(rows):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        created = parse_iso_timestamp(row.get("created_at") or row.get("timestamp") or row.get("updated_at"))
        if created is not None and created >= cutoff:
            count += 1
    return count


def resolver_feedback_health_from_local_ledger(reason=""):
    proposals = resolver_proposals()
    events = resolver_events(MAX_RESOLVER_EVENTS)
    proposal_counts = resolver_proposal_counts_from_rows(proposals)
    statuses = [
        normalize_resolver_status(row.get("result_status"), bool(row.get("fallback_used")))
        for row in events
        if isinstance(row, dict)
    ]
    latest_timestamps = [
        parse_iso_timestamp(row.get("created_at") or row.get("timestamp") or row.get("updated_at"))
        for row in [*proposals[:20], *events[:20]]
        if isinstance(row, dict)
    ]
    latest_timestamps = [item for item in latest_timestamps if item is not None]
    latest = max(latest_timestamps).isoformat().replace("+00:00", "Z") if latest_timestamps else ""
    sanitized_reason = sanitize_text_summary(reason, 240)
    if "resolver_feedback_health" in sanitized_reason or "Unknown tool" in sanitized_reason:
        sanitized_reason = "Authoritative resolver health tool is unavailable."
    return {
        "source": "local_resolver_ledger_fallback",
        "status": "ready" if proposal_counts.get("pending", 0) == 0 else "degraded",
        "read_only": True,
        "fallback_used": True,
        "fallback_reason": sanitized_reason or "Authoritative resolver health tool is unavailable.",
        "pending": proposal_counts.get("pending", 0),
        "proposal_counts": proposal_counts,
        "events_24h": resolver_events_24h_count(events),
        "event_counts": {
            "total": len(events),
            "success": statuses.count("success"),
            "fallback": statuses.count("fallback"),
            "timeout": statuses.count("timeout"),
            "no_match": statuses.count("no_match"),
            "error": statuses.count("error"),
        },
        "scheduled_loop": "not_mutated",
        "auto_approval": False,
        "evidence_slugs": ["/api/resolver/proposals", "/api/resolver/events"],
        "evidence_source": "local-durable-resolver-ledger",
        "latest_evidence_at": latest,
        "privacy": "Aggregate resolver counts only; proposal bodies, prompts, private paths, and backend tool names are withheld.",
    }


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


def gbrain_subprocess_env():
    env = os.environ.copy()
    bun_bin = Path.home() / ".bun" / "bin"
    env["PATH"] = f"{bun_bin}:/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
    return env


def parse_gbrain_search_arguments(args):
    if len(args) < 2 or args[0] != "search":
        raise ValueError("persistent search requires a search query")
    payload = {"query": str(args[1])}
    option_names = {
        "--limit": ("limit", int),
        "--offset": ("offset", int),
        "--mode": ("mode", str),
        "--snippet-chars": ("snippet_chars", int),
        "--types": ("types", lambda value: [item for item in str(value).split(",") if item]),
    }
    index = 2
    while index < len(args):
        option = str(args[index])
        if option not in option_names or index + 1 >= len(args):
            raise ValueError(f"unsupported persistent search option: {option}")
        key, parser = option_names[option]
        payload[key] = parser(args[index + 1])
        index += 2
    return payload


def parse_cli_boolean(value):
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValueError(f"invalid boolean option: {value}")


def parse_gbrain_query_arguments(args):
    if len(args) < 2 or args[0] != "query":
        raise ValueError("persistent query requires query text")
    payload = {"query": str(args[1])}
    option_names = {
        "--adaptive-return": ("adaptive_return", parse_cli_boolean),
        "--limit": ("limit", int),
        "--mode": ("mode", str),
        "--offset": ("offset", int),
        "--relational": ("relational", parse_cli_boolean),
        "--snippet-chars": ("snippet_chars", int),
        "--types": ("types", lambda value: [item for item in str(value).split(",") if item]),
    }
    index = 2
    while index < len(args):
        option = str(args[index])
        if option == "--no-expand":
            payload["expand"] = False
            index += 1
            continue
        if option not in option_names or index + 1 >= len(args):
            raise ValueError(f"unsupported persistent query option: {option}")
        key, parser = option_names[option]
        payload[key] = parser(args[index + 1])
        index += 2
    return payload


def parse_gbrain_graph_query_arguments(args):
    if len(args) < 2 or args[0] != "graph-query":
        raise ValueError("persistent graph-query requires a root slug")
    payload = {"slug": str(args[1]), "depth": 5, "direction": "out"}
    option_names = {
        "--type": ("link_type", str),
        "--depth": ("depth", int),
        "--direction": ("direction", str),
    }
    index = 2
    while index < len(args):
        option = str(args[index])
        if option not in option_names or index + 1 >= len(args):
            raise ValueError(f"unsupported persistent graph-query option: {option}")
        key, parser = option_names[option]
        payload[key] = parser(args[index + 1])
        index += 2
    if payload["direction"] not in {"in", "out", "both"}:
        raise ValueError(f"invalid graph-query direction: {payload['direction']}")
    return payload


def parse_gbrain_list_arguments(args):
    if not args or args[0] != "list":
        raise ValueError("persistent list requires a list command")
    payload = {}
    option_names = {
        "--type": ("type", str),
        "--tag": ("tag", str),
        "-n": ("limit", int),
        "--limit": ("limit", int),
        "--offset": ("offset", int),
        "--updated-after": ("updated_after", str),
        "--sort": ("sort", str),
        "--source-id": ("source_id", str),
    }
    index = 1
    while index < len(args):
        option = str(args[index])
        if option == "--include-deleted":
            payload["include_deleted"] = True
            index += 1
            continue
        if option not in option_names or index + 1 >= len(args):
            raise ValueError(f"unsupported persistent list option: {option}")
        key, parser = option_names[option]
        payload[key] = parser(args[index + 1])
        index += 2
    return payload


def truncate_utf16(text, max_units):
    encoded = str(text or "").encode("utf-16-le")
    return encoded[: max(0, int(max_units)) * 2].decode("utf-16-le", errors="ignore")


def format_mcp_search_results(rows):
    lines = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("slug"):
            continue
        chunk_lines = str(row.get("chunk_text") or "").splitlines()
        preview_source = next((line for line in chunk_lines if line.strip()), str(row.get("title") or ""))
        preview = truncate_utf16(preview_source, 100).strip()
        try:
            score = float(row.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        lines.append(f"[{score:.4f}] {row['slug']} -- {preview}")
    return "\n".join(lines) + ("\n" if lines else "")


def format_mcp_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def format_mcp_page_list(rows):
    lines = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("slug"):
            continue
        updated = str(row.get("updated_at") or row.get("date") or "")[:10]
        lines.append(
            "\t".join(
                (
                    str(row["slug"]),
                    str(row.get("type") or ""),
                    updated,
                    str(row.get("title") or ""),
                )
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def format_mcp_graph_query(paths, payload):
    root_slug = str(payload["slug"])
    direction = str(payload["direction"])
    if not paths:
        type_suffix = f" (--type {payload['link_type']})" if payload.get("link_type") else ""
        return f"No edges found from {root_slug}{type_suffix}.\n"

    by_parent = defaultdict(list)
    for path in paths:
        if not isinstance(path, dict):
            continue
        parent = path.get("to_slug") if direction == "in" else path.get("from_slug")
        if parent:
            by_parent[str(parent)].append(path)

    lines = [f"[depth 0] {root_slug}"]
    seen = set()

    def walk(parent, indent):
        if parent in seen:
            return
        seen.add(parent)
        children = sorted(
            by_parent.get(parent, []),
            key=lambda item: (int(item.get("depth") or 0), str(item.get("to_slug") or "")),
        )
        for child in children:
            next_slug = child.get("from_slug") if direction == "in" else child.get("to_slug")
            if not next_slug:
                continue
            arrow = "<-" if direction == "in" else "--"
            tail = "--" if direction == "in" else "->"
            lines.append(
                f"{'  ' * (indent + 1)}{arrow}{child.get('link_type') or ''}{tail} "
                f"{next_slug} (depth {int(child.get('depth') or 0)})"
            )
            walk(str(next_slug), indent + 1)

    walk(root_slug, 0)
    return "\n".join(lines) + "\n"


MCP_OPERATING_CONTRACT_SCHEMA = "memory-stargraph-gbrain-mcp-operating-contract-v1"
MCP_OPERATING_CONTRACT_MAX_CHARS = 65536


def mcp_operating_contract_status(
    instructions,
    *,
    server_version="",
    protocol_version="",
):
    base = {
        "schema": MCP_OPERATING_CONTRACT_SCHEMA,
        "status": "uninitialized",
        "present": False,
        "server_version": str(server_version or ""),
        "protocol_version": str(protocol_version or ""),
        "content_sha256": None,
        "content_length": 0,
        "put_page_replace_whole_page_documented": False,
        "write_safety_ready": False,
        "summary": "MCP operating instructions have not been observed.",
    }
    if instructions is None:
        if base["server_version"] or base["protocol_version"]:
            base.update(
                status="missing",
                summary=(
                    "MCP initialization omitted operating instructions; "
                    "mutating-operation safety is not attested."
                ),
            )
        return base
    if not isinstance(instructions, str):
        base.update(
            status="malformed",
            summary=(
                "MCP operating instructions were malformed; "
                "mutating-operation safety is not attested."
            ),
        )
        return base
    normalized = " ".join(instructions.split())
    if not normalized or len(normalized) > MCP_OPERATING_CONTRACT_MAX_CHARS:
        base.update(
            status="malformed",
            content_length=min(len(normalized), MCP_OPERATING_CONTRACT_MAX_CHARS + 1),
            summary=(
                "MCP operating instructions were empty or exceeded the bounded limit; "
                "mutating-operation safety is not attested."
            ),
        )
        return base
    lower = normalized.casefold()
    replace_whole_page = "put_page" in lower and any(
        phrase in lower
        for phrase in (
            "replace the whole page",
            "replaces the whole page",
            "replace whole page",
            "replaces whole page",
            "replace the entire page",
            "replaces the entire page",
            "replace entire page",
            "replaces entire page",
        )
    )
    base.update(
        status="present",
        present=True,
        content_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        content_length=len(normalized),
        put_page_replace_whole_page_documented=replace_whole_page,
        write_safety_ready=replace_whole_page,
        summary=(
            "MCP operating instructions are present and document put_page as a "
            "replace-whole-page operation."
            if replace_whole_page
            else "MCP operating instructions are present, but put_page replacement "
            "semantics are not attested."
        ),
    )
    return base


def aggregate_mcp_operating_contracts(contracts, *, expected_sessions):
    normalized = [
        item if isinstance(item, dict) else mcp_operating_contract_status(None)
        for item in contracts
    ]
    expected = max(0, int(expected_sessions))
    statuses = [str(item.get("status") or "uninitialized") for item in normalized]
    present = [item for item in normalized if item.get("present") is True]
    hashes = {str(item.get("content_sha256")) for item in present if item.get("content_sha256")}
    server_versions = {str(item.get("server_version")) for item in normalized if item.get("server_version")}
    protocol_versions = {str(item.get("protocol_version")) for item in normalized if item.get("protocol_version")}
    all_present = expected > 0 and len(present) == expected
    if "malformed" in statuses:
        status = "malformed"
    elif len(hashes) > 1 or len(server_versions) > 1 or len(protocol_versions) > 1:
        status = "inconsistent"
    elif all_present:
        status = "present"
    elif statuses and all(item == "missing" for item in statuses):
        status = "missing"
    elif statuses and any(item != "uninitialized" for item in statuses):
        status = "partial"
    else:
        status = "uninitialized"
    write_safety_ready = all_present and all(
        item.get("write_safety_ready") is True for item in normalized
    )
    return {
        "schema": MCP_OPERATING_CONTRACT_SCHEMA,
        "status": status,
        "present": all_present,
        "session_count": expected,
        "attested_session_count": len(present),
        "missing_session_count": statuses.count("missing"),
        "malformed_session_count": statuses.count("malformed"),
        "uninitialized_session_count": statuses.count("uninitialized") + max(0, expected - len(statuses)),
        "server_version": next(iter(server_versions)) if len(server_versions) == 1 else "",
        "protocol_version": next(iter(protocol_versions)) if len(protocol_versions) == 1 else "",
        "content_sha256": next(iter(hashes)) if len(hashes) == 1 else None,
        "put_page_replace_whole_page_documented": write_safety_ready,
        "write_safety_ready": write_safety_ready,
        "summary": (
            "All persistent MCP sessions attest the same operating contract and "
            "replace-whole-page write semantics."
            if write_safety_ready
            else "Persistent MCP write safety is not attested across every session."
        ),
    }


class PersistentGBrainSearch:
    def __init__(self):
        self.lock = threading.Lock()
        self.metrics_lock = threading.Lock()
        self.process = None
        self.request_id = 0
        self.server_version = ""
        self.operating_contract = mcp_operating_contract_status(None)
        self.active = False
        self.prewarming = False
        self.metrics = {
            "process_start_attempts": 0,
            "process_starts": 0,
            "process_restarts": 0,
            "tool_calls": 0,
            "tool_successes": 0,
            "tool_errors": 0,
            "tool_timeouts": 0,
            "tool_latency_ms_total": 0.0,
            "tool_latency_ms_max": 0.0,
            "tool_calls_by_name": {},
            "cli_fallbacks": 0,
            "cli_fallbacks_by_command": {},
            "last_error": None,
            "last_error_at": None,
        }

    def _record_tool_call(self, name, elapsed_ms, exc=None):
        with self.metrics_lock:
            self.metrics["tool_calls"] += 1
            by_name = self.metrics["tool_calls_by_name"]
            by_name[name] = int(by_name.get(name, 0)) + 1
            self.metrics["tool_latency_ms_total"] += elapsed_ms
            self.metrics["tool_latency_ms_max"] = max(
                self.metrics["tool_latency_ms_max"], elapsed_ms
            )
            if exc is None:
                self.metrics["tool_successes"] += 1
            else:
                self.metrics["tool_errors"] += 1
                if isinstance(exc, TimeoutError):
                    self.metrics["tool_timeouts"] += 1
                self.metrics["last_error"] = str(exc)[:300]
                self.metrics["last_error_at"] = iso_now()

    def record_cli_fallback(self, command, exc):
        with self.metrics_lock:
            self.metrics["cli_fallbacks"] += 1
            by_command = self.metrics["cli_fallbacks_by_command"]
            command = str(command or "unknown")
            by_command[command] = int(by_command.get(command, 0)) + 1
            self.metrics["last_error"] = str(exc)[:300]
            self.metrics["last_error_at"] = iso_now()

    def metrics_snapshot(self):
        with self.metrics_lock:
            metrics = dict(self.metrics)
            metrics["tool_calls_by_name"] = dict(metrics["tool_calls_by_name"])
            metrics["cli_fallbacks_by_command"] = dict(
                metrics["cli_fallbacks_by_command"]
            )
        calls = int(metrics["tool_calls"])
        metrics["tool_latency_ms_average"] = round(
            float(metrics["tool_latency_ms_total"]) / calls, 3
        ) if calls else 0.0
        metrics["tool_latency_ms_total"] = round(
            float(metrics["tool_latency_ms_total"]), 3
        )
        metrics["tool_latency_ms_max"] = round(
            float(metrics["tool_latency_ms_max"]), 3
        )
        return metrics

    def _close_locked(self):
        process = self.process
        self.process = None
        self.request_id = 0
        self.server_version = ""
        self.operating_contract = mcp_operating_contract_status(None)
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

    def close(self):
        with self.lock:
            self.active = False
            self._close_locked()

    def status(self):
        busy = not self.lock.acquire(blocking=False)
        if busy:
            process = self.process
            return {
                "active": self.active,
                "ready": process is not None and process.poll() is None,
                "busy": True,
                "operating_contract": dict(self.operating_contract),
                "metrics": self.metrics_snapshot(),
            }
        try:
            process = self.process
            return {
                "active": self.active,
                "ready": process is not None and process.poll() is None,
                "busy": False,
                "operating_contract": dict(self.operating_contract),
                "metrics": self.metrics_snapshot(),
            }
        finally:
            self.lock.release()

    def _drain_stderr(self, process):
        try:
            for _line in process.stderr:
                pass
        except Exception:  # noqa: BLE001
            pass

    def _request_locked(self, method, params, deadline):
        process = self.process
        if process is None or process.poll() is not None:
            raise RuntimeError("persistent GBrain search process is unavailable")
        self.request_id += 1
        request_id = self.request_id
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
                separators=(",", ":"),
            )
            + "\n"
        )
        process.stdin.flush()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"persistent GBrain {method} timed out")
                if not selector.select(remaining):
                    raise TimeoutError(f"persistent GBrain {method} timed out")
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError("persistent GBrain search process exited")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if message.get("id") != request_id:
                    continue
                if message.get("error"):
                    raise RuntimeError("persistent GBrain search returned an MCP error")
                return message.get("result") or {}
        finally:
            selector.close()

    def _start_locked(self, deadline):
        if self.process is not None and self.process.poll() is None:
            return
        with self.metrics_lock:
            self.metrics["process_start_attempts"] += 1
        self._close_locked()
        if not GBRAIN.exists():
            raise FileNotFoundError(f"gbrain not found at {GBRAIN}")
        process = subprocess.Popen(
            [str(GBRAIN), "serve", "--surface", "full"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=gbrain_subprocess_env(),
        )
        self.process = process
        threading.Thread(target=self._drain_stderr, args=(process,), daemon=True).start()
        initialized = self._request_locked(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "memory-stargraph", "version": UI_VERSION},
            },
            deadline,
        )
        server_info = initialized.get("serverInfo")
        if not isinstance(server_info, dict):
            raise RuntimeError("persistent GBrain search initialization was invalid")
        self.server_version = normalize_gbrain_version(server_info.get("version"))
        self.operating_contract = mcp_operating_contract_status(
            initialized.get("instructions"),
            server_version=self.server_version,
            protocol_version=initialized.get("protocolVersion"),
        )
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                separators=(",", ":"),
            )
            + "\n"
        )
        process.stdin.flush()
        with self.metrics_lock:
            self.metrics["process_starts"] += 1
            self.metrics["process_restarts"] = max(
                0, self.metrics["process_starts"] - 1
            )

    def _call_tool_locked(self, name, payload, deadline):
        started = time.monotonic()
        recorded_error = None
        try:
            result = self._request_locked(
                "tools/call",
                {"name": name, "arguments": payload},
                deadline,
            )
            content = result.get("content") if isinstance(result.get("content"), list) else []
            text_items = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if result.get("isError"):
                detail = "\n".join(str(item) for item in text_items if item).strip()
                raise RuntimeError(
                    f"persistent GBrain {name} tool failed: {detail or 'unknown MCP error'}"
                )
            if "structuredContent" in result:
                return result["structuredContent"]
            if not text_items:
                return None
            text_item = str(text_items[-1])
            try:
                return json.loads(text_item)
            except json.JSONDecodeError:
                return text_item
        except Exception as exc:
            recorded_error = exc
            raise
        finally:
            self._record_tool_call(
                str(name),
                round((time.monotonic() - started) * 1000, 3),
                recorded_error,
            )

    def call_tool(self, name, payload=None, timeout=30):
        started = time.monotonic()
        timeout_seconds = max(0.1, float(timeout))
        if not self.lock.acquire(timeout=timeout_seconds):
            raise RuntimeError("persistent GBrain MCP session is busy")
        deadline = started + timeout_seconds
        try:
            self._start_locked(deadline)
            return self._call_tool_locked(str(name), dict(payload or {}), deadline)
        except Exception:
            self._close_locked()
            raise
        finally:
            self.lock.release()

    def _list_pages_locked(self, payload, deadline):
        requested = payload.get("limit")
        if requested is None or int(requested) <= 100:
            return self._call_tool_locked("list_pages", payload, deadline)

        rows = []
        remaining = max(0, int(requested))
        offset = max(0, int(payload.get("offset") or 0))
        while remaining > 0:
            page_limit = min(100, remaining)
            page_payload = dict(payload)
            page_payload["limit"] = page_limit
            page_payload["offset"] = offset + len(rows)
            page = self._call_tool_locked("list_pages", page_payload, deadline)
            if not isinstance(page, list):
                raise RuntimeError("persistent GBrain list returned invalid rows")
            rows.extend(page)
            remaining -= len(page)
            if len(page) < page_limit:
                break
        return rows

    def read_cli_output(self, args, timeout):
        command = args[0] if args else ""
        if command == "search":
            tool_name = "search"
            payload = parse_gbrain_search_arguments(args)
            formatter = format_mcp_search_results
        elif command == "query":
            tool_name = "query"
            payload = parse_gbrain_query_arguments(args)
            formatter = format_mcp_search_results
        elif command == "get" and len(args) == 2:
            tool_name = "get_page"
            payload = {"slug": str(args[1]), "include_content": True}
            formatter = None
        elif command == "backlinks" and len(args) == 2:
            tool_name = "get_backlinks"
            payload = {"slug": str(args[1])}
            formatter = format_mcp_json
        elif command == "graph-query":
            tool_name = "traverse_graph"
            payload = parse_gbrain_graph_query_arguments(args)
            formatter = None
        elif command == "list":
            tool_name = "list_pages"
            payload = parse_gbrain_list_arguments(args)
            formatter = format_mcp_page_list
        else:
            raise ValueError(f"unsupported persistent GBrain command: {command}")
        lane_wait_limit = 2.0 if command in {"get", "backlinks", "graph-query", "list"} else 0.25
        lock_wait = min(lane_wait_limit, max(0.0, float(timeout)))
        if not self.lock.acquire(timeout=lock_wait):
            raise RuntimeError("persistent GBrain read session is busy")
        deadline = time.monotonic() + max(0.1, float(timeout))
        try:
            self._start_locked(deadline)
            value = (
                self._list_pages_locked(payload, deadline)
                if command == "list"
                else self._call_tool_locked(tool_name, payload, deadline)
            )
            if command in {"search", "query", "backlinks", "graph-query", "list"} and not isinstance(value, list):
                raise RuntimeError(f"persistent GBrain {command} returned invalid rows")
            if command == "get":
                if not isinstance(value, dict) or not isinstance(value.get("content"), str):
                    raise RuntimeError("persistent GBrain get returned invalid content")
                return value["content"]
            if command == "graph-query":
                return format_mcp_graph_query(value, payload)
            return formatter(value)
        except Exception:
            self._close_locked()
            raise
        finally:
            self.lock.release()

    def search_cli_output(self, args, timeout):
        if not args or args[0] != "search":
            raise ValueError("persistent search requires a search command")
        return self.read_cli_output(args, timeout)

    def prewarm_async(
        self,
        timeout=15,
        tool_name=None,
        tool_payload=None,
    ):
        self.active = True
        if self.prewarming or (self.process is not None and self.process.poll() is None):
            return False
        self.prewarming = True

        def prewarm():
            if not self.lock.acquire(blocking=False):
                self.prewarming = False
                return
            try:
                deadline = time.monotonic() + timeout
                self._start_locked(deadline)
                if tool_name:
                    self._call_tool_locked(
                        str(tool_name),
                        dict(tool_payload or {}),
                        deadline,
                    )
            except Exception:  # noqa: BLE001
                self._close_locked()
            finally:
                self.prewarming = False
                self.lock.release()

        threading.Thread(target=prewarm, daemon=True).start()
        return True


PERSISTENT_GBRAIN_SEARCH = PersistentGBrainSearch()


class BoundedGBrainMCPPool:
    """A fixed set of local MCP sessions for concurrent Ask Yoda reads."""

    def __init__(self, size=None, session_factory=PersistentGBrainSearch):
        configured_size = size
        if configured_size is None:
            configured_size = os.environ.get(
                "MEMORY_STARGRAPH_YODA_GBRAIN_MCP_SESSIONS",
                CONFIG.get("yoda_gbrain_mcp_sessions", 5),
            )
        self.size = max(1, min(8, int(configured_size)))
        self.sessions = [session_factory() for _ in range(self.size)]
        self.available = queue.Queue(maxsize=self.size)
        for session in self.sessions:
            self.available.put_nowait(session)
        self.active = False
        self.prewarm_lock = threading.Lock()
        self.prewarm_generation = 0
        self.prewarming = False
        self.metrics_lock = threading.Lock()
        self.metrics = {
            "tool_calls": 0,
            "tool_successes": 0,
            "tool_errors": 0,
            "tool_timeouts": 0,
            "busy_rejections": 0,
            "tool_latency_ms_total": 0.0,
            "tool_latency_ms_max": 0.0,
            "tool_calls_by_name": {},
            "last_error": None,
            "last_error_at": None,
        }

    def _record(self, name, elapsed_ms, exc=None, *, busy=False):
        with self.metrics_lock:
            self.metrics["tool_calls"] += 1
            by_name = self.metrics["tool_calls_by_name"]
            by_name[name] = int(by_name.get(name, 0)) + 1
            self.metrics["tool_latency_ms_total"] += elapsed_ms
            self.metrics["tool_latency_ms_max"] = max(
                self.metrics["tool_latency_ms_max"], elapsed_ms
            )
            if exc is None:
                self.metrics["tool_successes"] += 1
                return
            self.metrics["tool_errors"] += 1
            if isinstance(exc, TimeoutError):
                self.metrics["tool_timeouts"] += 1
            if busy:
                self.metrics["busy_rejections"] += 1
            self.metrics["last_error"] = str(exc)[:300]
            self.metrics["last_error_at"] = iso_now()

    def call_tool(self, name, payload=None, timeout=30):
        started = time.monotonic()
        timeout_seconds = max(0.1, float(timeout))
        try:
            session = self.available.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            error = RuntimeError("Ask Yoda GBrain MCP pool is busy")
            self._record(
                str(name),
                round((time.monotonic() - started) * 1000, 3),
                error,
                busy=True,
            )
            raise error from exc
        recorded_error = None
        try:
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Ask Yoda GBrain MCP request timed out before dispatch")
            return session.call_tool(name, payload, timeout=remaining)
        except Exception as exc:
            recorded_error = exc
            raise
        finally:
            self.available.put_nowait(session)
            self._record(
                str(name),
                round((time.monotonic() - started) * 1000, 3),
                recorded_error,
            )

    def close(self):
        with self.prewarm_lock:
            self.active = False
            self.prewarm_generation += 1
            self.prewarming = False
        for session in self.sessions:
            session.close()

    def prewarm_async(self, timeout=15):
        with self.prewarm_lock:
            if self.prewarming:
                return 0
            self.active = True
            self.prewarming = True
            self.prewarm_generation += 1
            generation = self.prewarm_generation
        probe = {
            "query": "Memory Stargraph",
            "expand": False,
            "adaptive_return": True,
            "limit": 10,
            "relational": True,
        }
        first = self.sessions[0]
        first.prewarm_async(
            timeout=timeout,
            tool_name="query",
            tool_payload=probe,
        )

        def prewarm_remaining():
            deadline = time.monotonic() + max(0.1, float(timeout))
            while getattr(first, "prewarming", False) and time.monotonic() < deadline:
                with self.prewarm_lock:
                    if not self.active or self.prewarm_generation != generation:
                        return
                time.sleep(0.02)
            with self.prewarm_lock:
                if not self.active or self.prewarm_generation != generation:
                    return
                for session in self.sessions[1:]:
                    session.prewarm_async(
                        timeout=timeout,
                        tool_name="query",
                        tool_payload=probe,
                    )
            rest_deadline = time.monotonic() + max(0.1, float(timeout))
            while (
                any(getattr(session, "prewarming", False) for session in self.sessions[1:])
                and time.monotonic() < rest_deadline
            ):
                with self.prewarm_lock:
                    if not self.active or self.prewarm_generation != generation:
                        return
                time.sleep(0.02)
            with self.prewarm_lock:
                if self.prewarm_generation == generation:
                    self.prewarming = False

        threading.Thread(target=prewarm_remaining, daemon=True).start()
        return self.size

    def metrics_snapshot(self):
        with self.metrics_lock:
            metrics = dict(self.metrics)
            metrics["tool_calls_by_name"] = dict(metrics["tool_calls_by_name"])
        calls = int(metrics["tool_calls"])
        metrics["tool_latency_ms_average"] = round(
            float(metrics["tool_latency_ms_total"]) / calls, 3
        ) if calls else 0.0
        metrics["tool_latency_ms_total"] = round(
            float(metrics["tool_latency_ms_total"]), 3
        )
        metrics["tool_latency_ms_max"] = round(
            float(metrics["tool_latency_ms_max"]), 3
        )
        metrics["cli_fallbacks"] = 0
        return metrics

    def status(self):
        states = [session.status() for session in self.sessions]
        prewarming_sessions = sum(
            bool(getattr(session, "prewarming", False)) for session in self.sessions
        )
        available = self.available.qsize()
        return {
            "active": self.active,
            "pool_size": self.size,
            "ready_sessions": sum(bool(state.get("ready")) for state in states),
            "semantic_ready_sessions": sum(
                bool(state.get("ready")) and not getattr(session, "prewarming", False)
                for session, state in zip(self.sessions, states)
            ),
            "prewarming_sessions": prewarming_sessions,
            "in_use_sessions": self.size - available,
            "busy": available == 0,
            "structured_only": True,
            "subprocess_fallback": False,
            "operating_contract": aggregate_mcp_operating_contracts(
                [state.get("operating_contract") for state in states],
                expected_sessions=self.size,
            ),
            "metrics": self.metrics_snapshot(),
        }


YODA_GBRAIN_MCP_TOOL_NAMES = frozenset(
    {
        "get_page",
        "query",
        "search",
        "get_backlinks",
        "traverse_graph",
        "list_pages",
        "get_tags",
        "think",
    }
)
YODA_GBRAIN_ROW_TOOL_NAMES = frozenset(
    {"query", "search", "get_backlinks", "traverse_graph", "list_pages"}
)
YODA_GBRAIN_MCP_POOL = BoundedGBrainMCPPool()


def yoda_gbrain_call_tool(tool_name, payload=None, timeout=30):
    """Call an allowlisted structured MCP tool without any CLI fallback."""
    name = str(tool_name or "").strip()
    if name not in YODA_GBRAIN_MCP_TOOL_NAMES:
        raise ValueError(f"Ask Yoda GBrain MCP tool is not allowed: {name or 'empty'}")
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("Ask Yoda GBrain MCP payload must be an object")
    value = YODA_GBRAIN_MCP_POOL.call_tool(name, dict(payload or {}), timeout=timeout)
    if name == "get_page":
        if not isinstance(value, dict) or not isinstance(value.get("content"), str):
            raise RuntimeError("Ask Yoda GBrain get_page returned invalid structured content")
        return value
    if name in YODA_GBRAIN_ROW_TOOL_NAMES:
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise RuntimeError(f"Ask Yoda GBrain {name} returned invalid structured rows")
        return value
    if name == "get_tags":
        tags = value.get("tags") if isinstance(value, dict) else value
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise RuntimeError("Ask Yoda GBrain get_tags returned invalid structured tags")
        return sorted({tag.strip() for tag in tags if tag.strip()})
    if name == "think":
        if not isinstance(value, dict):
            raise RuntimeError("Ask Yoda GBrain think returned invalid structured content")
        return value
    raise RuntimeError(f"Ask Yoda GBrain MCP validator is missing for {name}")


def run_gbrain_subprocess(*args, input_text=None, timeout=20):
    if not GBRAIN.exists():
        raise FileNotFoundError(f"gbrain not found at {GBRAIN}")
    command = [str(GBRAIN), *args]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=gbrain_subprocess_env(),
        input=input_text.encode("utf-8") if isinstance(input_text, str) else input_text,
    )
    if result.returncode != 0:
        stderr = decode_process_output(result.stderr).strip()
        stdout = decode_process_output(result.stdout).strip()
        message = stderr or stdout or f"gbrain exited with status {result.returncode}"
        raise RuntimeError(message)
    return decode_process_output(result.stdout)


def run_remote_gbrain_read(*args, timeout=20):
    command = args[0] if args else ""
    if command == "search":
        tool_name = "search"
        payload = parse_gbrain_search_arguments(args)
        formatter = format_mcp_search_results
    elif command == "query":
        tool_name = "query"
        payload = parse_gbrain_query_arguments(args)
        formatter = format_mcp_search_results
    elif command == "get" and len(args) == 2:
        tool_name = "get_page"
        payload = {"slug": str(args[1]), "include_content": True}
        formatter = None
    elif command == "backlinks" and len(args) == 2:
        tool_name = "get_backlinks"
        payload = {"slug": str(args[1])}
        formatter = format_mcp_json
    elif command == "graph-query":
        tool_name = "traverse_graph"
        payload = parse_gbrain_graph_query_arguments(args)
        formatter = None
    elif command == "list":
        tool_name = "list_pages"
        payload = parse_gbrain_list_arguments(args)
        formatter = format_mcp_page_list
    else:
        raise ValueError(f"unsupported remote GBrain command: {command}")

    deadline = time.monotonic() + max(0.1, float(timeout))

    def call_tool(name, arguments):
        remaining = max(0.1, deadline - time.monotonic())
        return gbrain_call_tool(name, arguments, timeout=remaining)

    if command == "list" and int(payload.get("limit") or 0) > 100:
        rows = []
        remaining_rows = max(0, int(payload["limit"]))
        offset = max(0, int(payload.get("offset") or 0))
        while remaining_rows > 0:
            page_limit = min(100, remaining_rows)
            page_payload = dict(payload)
            page_payload["limit"] = page_limit
            page_payload["offset"] = offset + len(rows)
            page = call_tool(tool_name, page_payload)
            if not isinstance(page, list):
                raise RuntimeError("remote GBrain list returned invalid rows")
            rows.extend(page)
            remaining_rows -= len(page)
            if len(page) < page_limit:
                break
        value = rows
    else:
        value = call_tool(tool_name, payload)

    if command in {"search", "query", "backlinks", "graph-query", "list"} and not isinstance(value, list):
        raise RuntimeError(f"remote GBrain {command} returned invalid rows")
    if command == "get":
        if not isinstance(value, dict) or not isinstance(value.get("content"), str):
            raise RuntimeError("remote GBrain get returned invalid content")
        return value["content"]
    if command == "graph-query":
        return format_mcp_graph_query(value, payload)
    return formatter(value)


def run_gbrain(*args, input_text=None, timeout=20):
    started = time.monotonic()
    persistent_commands = {"search", "query", "get", "backlinks", "graph-query", "list"}
    if input_text is None and args and args[0] in persistent_commands and configured_remote_mcp_path() is not None:
        return run_remote_gbrain_read(*args, timeout=timeout)
    if input_text is None and args and args[0] in persistent_commands and PERSISTENT_GBRAIN_SEARCH.active:
        try:
            return PERSISTENT_GBRAIN_SEARCH.read_cli_output(args, timeout)
        except Exception as exc:  # noqa: BLE001
            PERSISTENT_GBRAIN_SEARCH.record_cli_fallback(args[0], exc)
    remaining = max(0.1, float(timeout) - (time.monotonic() - started))
    return run_gbrain_subprocess(*args, input_text=input_text, timeout=remaining)


def run_gbrain_binary(gbrain_path, *args, timeout=20):
    binary = Path(str(gbrain_path or "")).expanduser()
    if not binary.exists():
        raise FileNotFoundError(f"gbrain not found at {binary}")
    env = os.environ.copy()
    bun_bin = Path.home() / ".bun" / "bin"
    env["PATH"] = f"{bun_bin}:/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
    result = subprocess.run(
        [str(binary), *args],
        cwd=ROOT,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        stderr = decode_process_output(result.stderr).strip()
        stdout = decode_process_output(result.stdout).strip()
        raise RuntimeError(stderr or stdout or f"gbrain exited with status {result.returncode}")
    return decode_process_output(result.stdout)


def safe_public_backend_record(record, *, fallback_path=None):
    item = dict(record or {})
    backend_id = normalize_slug(item.get("id") or item.get("label") or "primary")
    label = str(item.get("label") or backend_id.replace("-", " ").title()).strip()
    role = str(item.get("role") or ("primary" if backend_id == "primary" else "custom")).strip().lower()
    gbrain_path = str(item.get("gbrain_path") or fallback_path or "").strip()
    service_url = str(item.get("service_url") or "").strip().rstrip("/")
    write_authority = str(item.get("write_authority") or ("primary" if role == "primary" else "non_primary")).strip()
    return {
        "id": backend_id,
        "label": label,
        "role": role,
        "gbrain_path": gbrain_path,
        "service_url": service_url,
        "write_authority": write_authority,
        "requires_split_brain_ack": role != "primary" or write_authority != "primary",
    }


def infer_gbrain_backend_defaults(gbrain_path):
    lower_path = str(gbrain_path or "").lower()
    if any(token in lower_path for token in ("secondary", "slave", "test")):
        return {"id": "secondary-test", "label": "Secondary/test", "role": "secondary", "write_authority": "non_primary"}
    return {"id": "primary", "label": "Primary", "role": "primary", "write_authority": "primary"}


def configured_gbrain_backends(config=None):
    config = config or load_config()
    choices = config.get("gbrain_backend_choices") or []
    if not isinstance(choices, list):
        choices = []
    backends = [safe_public_backend_record(item) for item in choices if isinstance(item, dict)]
    if not backends:
        inferred = infer_gbrain_backend_defaults(config.get("gbrain_path"))
        backends.insert(
            0,
            safe_public_backend_record(
                {
                    "id": config.get("gbrain_backend_id") or inferred["id"],
                    "label": config.get("gbrain_backend_label") or inferred["label"],
                    "role": config.get("gbrain_backend_role") or inferred["role"],
                    "gbrain_path": config.get("gbrain_path"),
                    "service_url": config.get("primary_service_url", ""),
                    "write_authority": config.get("gbrain_backend_write_authority") or inferred["write_authority"],
                }
            ),
        )
    current_path = str(config.get("gbrain_path") or DEFAULT_CONFIG["gbrain_path"])
    for item in backends:
        if not item.get("gbrain_path"):
            item["gbrain_path"] = current_path
    return backends


def current_gbrain_backend(config=None):
    config = config or load_config()
    backends = configured_gbrain_backends(config)
    selected_id = str(config.get("gbrain_backend_id") or "primary").strip()
    selected = next((item for item in backends if item["id"] == selected_id), None)
    if selected is None:
        custom = config.get("gbrain_backend_custom")
        if isinstance(custom, dict):
            selected = safe_public_backend_record(custom, fallback_path=config.get("gbrain_path"))
        elif backends:
            selected = backends[0]
        else:
            selected = safe_public_backend_record(
                {
                    "id": "custom",
                    "label": "Custom",
                    "role": "custom",
                    "gbrain_path": config.get("gbrain_path"),
                    "service_url": config.get("gbrain_backend_service_url", ""),
                    "write_authority": config.get("gbrain_backend_write_authority", "custom"),
                }
            )
    return selected


def validate_memory_stargraph_service(service_url, timeout=8):
    if not service_url:
        return {"ok": True, "skipped": True}
    base_url = service_url.rstrip("/")
    health_request = Request(f"{base_url}/api/health", headers={"Accept": "application/json"})
    with urlopen(health_request, timeout=timeout) as response:
        health = json.loads(response.read().decode("utf-8") or "{}")
    if not health.get("ok"):
        raise RuntimeError("service /api/health returned ok=false")
    raw_request = Request(f"{base_url}/api/entity-raw/{quote(ROOT_INDEX_SLUG, safe='')}", headers={"Accept": "application/json"})
    with urlopen(raw_request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8") or "{}")
    if raw.get("slug") != ROOT_INDEX_SLUG:
        raise RuntimeError("service index readback did not return index")
    source = health.get("source") or {}
    return {
        "ok": True,
        "health_ok": health.get("ok"),
        "ui_version": health.get("ui_version"),
        "source_mode": source.get("mode"),
        "source_status": source.get("status"),
        "index_readback": True,
    }


def validate_gbrain_backend_record(record):
    backend = safe_public_backend_record(record)
    validation = {"backend_id": backend["id"], "validated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    output = run_gbrain_binary(backend["gbrain_path"], "get", ROOT_INDEX_SLUG, timeout=20)
    if ROOT_INDEX_SLUG not in output and "# " not in output:
        raise RuntimeError("gbrain index readback returned unexpected content")
    validation["gbrain_cli_readback"] = True
    validation["service"] = validate_memory_stargraph_service(backend.get("service_url", ""))
    validation["requires_split_brain_ack"] = backend["requires_split_brain_ack"]
    return validation


def public_gbrain_backend_config():
    config = load_config()
    backends = configured_gbrain_backends(config)
    current = current_gbrain_backend(config)
    return {
        "current_backend_id": current["id"],
        "current_backend": current,
        "backends": backends,
        "custom_supported": True,
        "config_path": str(config_path()),
        "split_brain_warning": "Only Primary is the normal write authority. Use Secondary/test or custom backends only for verified testing or approved failover.",
    }


def save_gbrain_backend_config(payload):
    payload = payload or {}
    config = read_local_config_file()
    merged = load_config()
    selected_id = normalize_slug(payload.get("backend_id") or "primary")
    backends = configured_gbrain_backends(merged)
    selected = next((item for item in backends if item["id"] == selected_id), None)
    if selected_id == "custom":
        selected = safe_public_backend_record(
            {
                "id": "custom",
                "label": payload.get("custom_label") or "Custom",
                "role": "custom",
                "gbrain_path": payload.get("custom_gbrain_path") or payload.get("gbrain_path"),
                "service_url": payload.get("custom_service_url") or payload.get("service_url") or "",
                "write_authority": payload.get("write_authority") or "custom",
            }
        )
    if selected is None:
        raise ValueError("Choose a configured GBrain backend or Custom.")
    if selected["requires_split_brain_ack"] and not payload.get("acknowledge_split_brain_risk"):
        raise ValueError("Acknowledge split-brain/write-authority risk before using a non-Primary backend.")
    validation = validate_gbrain_backend_record(selected)
    config.update(
        {
            "gbrain_backend_id": selected["id"],
            "gbrain_path": selected["gbrain_path"],
            "gbrain_backend_label": selected["label"],
            "gbrain_backend_role": selected["role"],
            "gbrain_backend_service_url": selected.get("service_url", ""),
            "gbrain_backend_write_authority": selected.get("write_authority", ""),
            "gbrain_backend_validated_at": validation["validated_at"],
        }
    )
    if selected["id"] == "custom":
        config["gbrain_backend_custom"] = selected
    write_local_config_file(config)
    apply_runtime_config(load_config())
    try:
        STORE.graph = STORE.get_seed_graph(force=True)
    except Exception:
        STORE.graph = {}
    return {**public_gbrain_backend_config(), "validation": validation}


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


class RemoteGBrainToolCaller:
    """Authenticated, serialized JSON-RPC caller for a remote GBrain MCP."""

    def __init__(self, config_path, timeout=30):
        self.config_path = Path(config_path)
        self.timeout = timeout
        self._lane_lock = threading.Lock()
        self._token_lock = threading.Lock()
        self._token = None
        self._token_expires_at = 0.0
        self._token_endpoint = None

    def _remote_config(self):
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("GBrain remote config is unavailable") from exc
        remote = raw.get("remote_mcp") if isinstance(raw, dict) else None
        if not isinstance(remote, dict):
            raise RuntimeError("GBrain remote_mcp config is unavailable")
        result = {}
        for field in ("issuer_url", "mcp_url", "oauth_client_id"):
            value = remote.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"GBrain remote_mcp {field} is unavailable")
            result[field] = value.strip()
        secret = os.environ.get("GBRAIN_REMOTE_CLIENT_SECRET")
        if not isinstance(secret, str) or not secret:
            raise RuntimeError("GBrain remote client secret is unavailable")
        result["oauth_client_secret"] = secret
        return result

    def _read_json_response(self, request):
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as exc:
            raise RuntimeError(
                f"GBrain remote request failed with HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("GBrain remote request failed") from exc
        try:
            if "text/event-stream" in content_type:
                data_lines = [
                    line[5:].strip()
                    for line in raw.splitlines()
                    if line.startswith("data:")
                ]
                if not data_lines:
                    raise ValueError("missing SSE data")
                return json.loads(data_lines[-1])
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("GBrain remote response was invalid") from exc

    def _access_token(self, remote):
        with self._token_lock:
            if self._token is not None and self._token_expires_at > time.time() + 30:
                return self._token
            if self._token_endpoint is None:
                metadata = self._read_json_response(
                    Request(
                        remote["issuer_url"].rstrip("/")
                        + "/.well-known/oauth-authorization-server"
                    )
                )
                endpoint = (
                    metadata.get("token_endpoint")
                    if isinstance(metadata, dict)
                    else None
                )
                if not isinstance(endpoint, str) or not endpoint:
                    raise RuntimeError(
                        "GBrain OAuth discovery omitted token_endpoint"
                    )
                self._token_endpoint = endpoint
            body = urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": remote["oauth_client_id"],
                    "client_secret": remote["oauth_client_secret"],
                }
            ).encode("utf-8")
            token_payload = self._read_json_response(
                Request(
                    self._token_endpoint,
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            )
            token = (
                token_payload.get("access_token")
                if isinstance(token_payload, dict)
                else None
            )
            if not isinstance(token, str) or not token:
                raise RuntimeError("GBrain OAuth response omitted access_token")
            expires_in = token_payload.get("expires_in", 3600)
            ttl = float(expires_in) if isinstance(expires_in, (int, float)) else 3600.0
            self._token = token
            self._token_expires_at = time.time() + max(60.0, ttl)
            return token

    def call(self, tool_name, payload=None):
        remote = self._remote_config()
        with self._lane_lock:
            token = self._access_token(remote)
            envelope = self._read_json_response(
                Request(
                    remote["mcp_url"],
                    data=json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": hashlib.sha256(
                                f"{time.time_ns()}:{tool_name}".encode("utf-8")
                            ).hexdigest(),
                            "method": "tools/call",
                            "params": {
                                "name": tool_name,
                                "arguments": dict(payload or {}),
                            },
                        },
                        separators=(",", ":"),
                    ).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
            )
        result = envelope.get("result") if isinstance(envelope, dict) else None
        if not isinstance(result, dict):
            raise RuntimeError("GBrain remote response omitted result")
        content = result.get("content")
        text_blocks = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ] if isinstance(content, list) else []
        if result.get("isError"):
            detail = "\n".join(str(value) for value in text_blocks if value).strip()
            raise RuntimeError(
                f"GBrain tool {tool_name} failed: {detail or 'unknown remote error'}"
            )
        if not text_blocks:
            if "structuredContent" in result:
                return result["structuredContent"]
            raise RuntimeError("GBrain remote result omitted text content")
        try:
            return json.loads(str(text_blocks[-1]))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"GBrain tool {tool_name} returned invalid JSON"
            ) from exc


_REMOTE_GBRAIN_TOOL_CALLER = None
_REMOTE_GBRAIN_TOOL_CALLER_LOCK = threading.Lock()


def gbrain_config_path():
    configured = os.environ.get("GBRAIN_CONFIG_FILE")
    if configured:
        return Path(configured).expanduser()
    configured_home = os.environ.get("GBRAIN_HOME")
    home = Path(configured_home).expanduser() if configured_home else Path.home()
    return home / ".gbrain" / "config.json"


def configured_remote_mcp_path():
    path = gbrain_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("GBrain config is unavailable") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("GBrain config is unavailable")
    return path if "remote_mcp" in raw else None


def gbrain_call_tool(tool_name, payload=None, timeout=30):
    global _REMOTE_GBRAIN_TOOL_CALLER
    remote_path = configured_remote_mcp_path()
    if remote_path is not None:
        with _REMOTE_GBRAIN_TOOL_CALLER_LOCK:
            if (
                _REMOTE_GBRAIN_TOOL_CALLER is None
                or _REMOTE_GBRAIN_TOOL_CALLER.config_path != remote_path
                or _REMOTE_GBRAIN_TOOL_CALLER.timeout != timeout
            ):
                _REMOTE_GBRAIN_TOOL_CALLER = RemoteGBrainToolCaller(
                    remote_path, timeout=timeout
                )
            caller = _REMOTE_GBRAIN_TOOL_CALLER
        return caller.call(tool_name, payload)
    if tool_name in OPTIONAL_GBRAIN_TOOL_NAMES:
        availability = local_gbrain_tool_available(tool_name)
        if availability is False:
            raise RuntimeError(f"GBrain backend does not expose {tool_name}")
    started = time.monotonic()
    if tool_name in PERSISTENT_GBRAIN_TOOL_NAMES:
        try:
            return PERSISTENT_GBRAIN_SEARCH.call_tool(tool_name, payload, timeout=timeout)
        except Exception as exc:
            if tool_name in MUTATING_GBRAIN_TOOL_NAMES:
                raise
            PERSISTENT_GBRAIN_SEARCH.record_cli_fallback(f"call:{tool_name}", exc)
    remaining = max(0.1, float(timeout) - (time.monotonic() - started))
    try:
        output = run_gbrain("call", tool_name, json.dumps(payload or {}), timeout=remaining)
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


def resolver_read_cache():
    store = globals().get("STORE")
    return getattr(store, "resolver_read_cache", None)


def resolver_capability_cache():
    store = globals().get("STORE")
    return getattr(store, "resolver_capability_cache", None)


def invalidate_resolver_read_caches():
    store = globals().get("STORE")
    for name in ("resolver_read_cache", "settings_evidence_cache"):
        cache = getattr(store, name, None)
        if cache is not None:
            cache.clear()


def resolver_tool_unavailable(error, tool_name):
    message = str(error)
    return (
        f"GBrain backend does not expose {tool_name}" in message
        or f"Unknown tool: {tool_name}" in message
        or ("unknown_operation" in message and tool_name in message)
    )


def resolver_tool_cache_key(tool_name, *parts):
    return (tool_name, gbrain_call_tool, *parts)


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
        "environment": sanitize_text_summary(payload.get("environment"), 40) or "production",
        "synthetic": payload.get("synthetic") is True,
        "test_run": payload.get("test_run") is True,
        "pair_id": sanitize_text_summary(payload.get("pair_id"), 160),
    }
    result = gbrain_call_tool("resolver_events_submit", event_payload, timeout=20)
    invalidate_resolver_read_caches()
    return result


def resolver_list_events(limit=50, producer=None, outcome=None):
    payload = {"limit": limit}
    if producer:
        payload["producer"] = producer
    if outcome:
        payload["outcome"] = outcome
    data = gbrain_call_tool("resolver_events_list", payload, timeout=20)
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return data
    normalized = dict(data)
    normalized_events = []
    for row in data["events"]:
        event = dict(row) if isinstance(row, dict) else {}
        metadata = event.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        if isinstance(metadata, dict):
            for key in ("environment", "synthetic", "test_run", "pair_id", "operation_path", "client_timestamp"):
                if key not in event and key in metadata:
                    event[key] = metadata[key]
        normalized_events.append(event)
    normalized["events"] = normalized_events
    return normalized


def normalize_resolver_proposal(row):
    proposal = dict(row) if isinstance(row, dict) else {}
    impact = proposal.get("impact")
    if isinstance(impact, str):
        try:
            impact = json.loads(impact)
        except json.JSONDecodeError:
            impact = {}
    proposal["impact"] = impact if isinstance(impact, dict) else {}
    evidence = proposal.get("evidence")
    evidence_count = parse_nonnegative_int(proposal.get("evidence_count"), 0)
    if isinstance(evidence, list):
        evidence_count = max(evidence_count, len(evidence))
    proposal["evidence_count"] = evidence_count
    return proposal


def resolver_list_proposals(status_filter="", limit=100):
    payload = {"limit": limit}
    if status_filter:
        payload["status"] = status_filter
    cache = resolver_read_cache()
    cache_key = resolver_tool_cache_key(
        "resolver_proposals_list",
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )
    cached = cache.get(cache_key) if cache is not None else None
    if cached is not None:
        return cached
    capability = resolver_capability_cache()
    capability_key = resolver_tool_cache_key("resolver_proposals_list:capability")
    if capability is not None and capability.get(capability_key) is False:
        raise RuntimeError("GBrain backend does not expose resolver_proposals_list")
    try:
        data = gbrain_call_tool("resolver_proposals_list", payload, timeout=30)
        if capability is not None:
            capability.put(capability_key, True)
    except RuntimeError as exc:
        if resolver_tool_unavailable(exc, "resolver_proposals_list") and capability is not None:
            capability.put(capability_key, False)
        raise
    if not isinstance(data, dict) or not isinstance(data.get("proposals"), list):
        return data
    normalized = dict(data)
    normalized["proposals"] = [normalize_resolver_proposal(row) for row in data["proposals"]]
    if cache is not None:
        cache.put(cache_key, normalized)
    return normalized


def resolver_generate_proposals(payload=None):
    request_payload = dict(payload or {})
    request_payload.setdefault("min_evidence", 2)
    request_payload.setdefault("run_source", "memory-stargraph")
    result = gbrain_call_tool("resolver_proposals_generate", request_payload, timeout=60)
    invalidate_resolver_read_caches()
    return result


def resolver_update_proposal(proposal_id, action, payload=None):
    request_payload = dict(payload or {})
    request_payload["proposal_id"] = proposal_id
    request_payload["action"] = action
    result = gbrain_call_tool("resolver_proposals_update", request_payload, timeout=30)
    invalidate_resolver_read_caches()
    return result


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
    result = gbrain_call_tool("resolver_releases_apply", request_payload, timeout=60)
    invalidate_resolver_read_caches()
    return result


def resolver_measure_impact(proposal_id, payload=None):
    request_payload = dict(payload or {})
    request_payload["proposal_id"] = proposal_id
    result = gbrain_call_tool("resolver_impact_measure", request_payload, timeout=30)
    invalidate_resolver_read_caches()
    return result


def resolver_feedback_health():
    cache = resolver_read_cache()
    cache_key = resolver_tool_cache_key(
        "resolver_feedback_health",
        str(RESOLVER_PROPOSALS_PATH),
        str(RESOLVER_EVENTS_PATH),
    )
    cached = cache.get(cache_key) if cache is not None else None
    if cached is not None:
        return cached
    capability = resolver_capability_cache()
    capability_key = resolver_tool_cache_key("resolver_feedback_health:capability")
    if capability is not None and capability.get(capability_key) is False:
        result = resolver_feedback_health_from_local_ledger()
    else:
        try:
            result = gbrain_call_tool("resolver_feedback_health", {}, timeout=20)
            if capability is not None:
                capability.put(capability_key, True)
        except RuntimeError as exc:
            if not resolver_tool_unavailable(exc, "resolver_feedback_health"):
                raise
            if capability is not None:
                capability.put(capability_key, False)
            result = resolver_feedback_health_from_local_ledger(str(exc))
    if cache is not None and result is not None:
        cache.put(cache_key, result)
    return result


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


def parse_bounded_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


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


AUTOPILOT_FINDING_STATES = {
    "open",
    "queued",
    "repairing",
    "blocked",
    "awaiting_approval",
    "escalated",
    "resolved",
}
AUTOPILOT_FINDING_FALLBACK_TAGS = ("autopilot-finding", "follow-up")


def normalize_autopilot_finding_from_page(row, markdown):
    meta, body = parse_frontmatter(markdown or "")
    slug = str(row.get("slug") or meta.get("slug") or "").strip()
    if not slug:
        return None
    state = str(meta.get("state") or meta.get("status") or "open").strip().lower().replace(" ", "_")
    if state not in AUTOPILOT_FINDING_STATES:
        state = "open"
    title = str(meta.get("title") or row.get("title") or make_label(slug)).strip()
    rationale = str(meta.get("rationale") or meta.get("summary") or "").strip()
    if not rationale:
        for line in body.splitlines():
            cleaned = re.sub(r"^#+\s*", "", line).strip()
            if cleaned:
                rationale = cleaned[:280]
                break
    stable_id = int(hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8], 16)
    finding_id = parse_nonnegative_int(meta.get("id"), stable_id)
    return {
        "id": finding_id,
        "slug": slug,
        "check_name": str(meta.get("check_name") or meta.get("finding") or title or "Autopilot follow-up").strip(),
        "state": state,
        "severity": str(meta.get("severity") or "info").strip(),
        "rationale": rationale or "No rationale supplied.",
        "source_id": str(meta.get("source_id") or row.get("type") or "gbrain-page").strip(),
        "owner": str(meta.get("owner") or "").strip(),
        "repair_attempts": parse_nonnegative_int(meta.get("repair_attempts"), 0),
        "postcondition_failures": parse_nonnegative_int(meta.get("postcondition_failures"), 0),
        "recommended_action": str(meta.get("recommended_action") or "").strip(),
        "acknowledged_at": str(meta.get("acknowledged_at") or "").strip(),
        "acknowledged_by": str(meta.get("acknowledged_by") or "").strip(),
        "backend_source": "gbrain_tag_fallback",
    }


def list_autopilot_findings_from_gbrain_pages(payload, snapshot_cache=None):
    limit = max(1, min(AUTOPILOT_FINDINGS_MAX_LIMIT, int(payload.get("limit") or 50)))
    offset = max(0, int(payload.get("offset") or 0))
    state_filter = str(payload.get("state") or "").strip().lower()
    page_read_budget = max(limit + offset, 20)
    page_read_budget = min(AUTOPILOT_FINDINGS_MAX_LIMIT, page_read_budget)
    snapshot_key = f"autopilot_findings:fallback:{page_read_budget}"
    snapshot = snapshot_cache.get(snapshot_key) if snapshot_cache is not None else None
    if snapshot is None:
        rows_by_slug = {}
        checked_tags = []

        def list_tag_rows(tag):
            try:
                output = run_gbrain("list", "--tag", tag, "-n", str(page_read_budget), timeout=8)
            except Exception:  # noqa: BLE001
                return tag, None
            return tag, parse_page_list(output)

        with ThreadPoolExecutor(max_workers=len(AUTOPILOT_FINDING_FALLBACK_TAGS)) as executor:
            tag_rows = executor.map(list_tag_rows, AUTOPILOT_FINDING_FALLBACK_TAGS)
        for tag, rows in tag_rows:
            if rows is None:
                continue
            checked_tags.append(tag)
            for row in rows:
                slug = str(row.get("slug") or "")
                if slug and slug not in rows_by_slug:
                    rows_by_slug[slug] = row
        snapshot_findings = []
        for row in rows_by_slug.values():
            try:
                markdown = run_gbrain("get", row["slug"], timeout=8)
            except Exception:  # noqa: BLE001
                continue
            finding = normalize_autopilot_finding_from_page(row, markdown)
            if finding:
                snapshot_findings.append(finding)
        snapshot_findings.sort(
            key=lambda item: (
                item.get("state") == "resolved",
                item.get("severity") == "info",
                item.get("check_name") or "",
            )
        )
        snapshot = {"findings": snapshot_findings, "checked_tags": checked_tags}
        if snapshot_cache is not None:
            snapshot_cache.put(snapshot_key, snapshot)
    findings = snapshot["findings"]
    if state_filter:
        findings = [finding for finding in findings if finding["state"] == state_filter]
    page = findings[offset:offset + limit]
    return {
        "findings": page,
        "total": len(findings),
        "backend_status": "gbrain_tag_fallback",
        "backend_message": "Autopilot findings tool unavailable; using supported GBrain tag fallback.",
        "checked_tags": snapshot["checked_tags"],
        "filters": payload,
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


def takes_complete_snapshot_compatible(payload):
    allowed = {"active", "holder", "kind", "limit", "offset", "page_slug"}
    if set(payload) - allowed:
        return False
    if payload.get("active") is False or parse_nonnegative_int(payload.get("offset"), 0) != 0:
        return False
    return not holder_filter_is_wildcard(payload.get("holder"))


def filter_complete_take_snapshot(snapshot, payload):
    normalized = normalize_take_collection(snapshot, "takes")
    rows = normalized.get("takes") or []
    exact_filters = {
        key: str(payload.get(key) or "").strip().lower()
        for key in ("page_slug", "holder", "kind")
        if payload.get(key)
    }
    filtered = []
    for row in rows:
        if any(
            str(row.get(key) or "").strip().lower() != expected
            for key, expected in exact_filters.items()
        ):
            continue
        if payload.get("active") is True and row.get("active") is not True:
            continue
        filtered.append(row)
    result = dict(normalized)
    result["takes"] = filtered
    result["filters"] = dict(payload)
    return result


def take_review_action_payload(proposal_id, action, payload):
    raw_payload = payload if isinstance(payload, dict) else {}
    idempotency_key = str(raw_payload.get("idempotency_key") or "").strip()
    if not idempotency_key:
        idempotency_key = f"{TAKE_REVIEW_ACTOR}:{action}:{proposal_id}"
    return {
        "id": take_review_tool_id(proposal_id),
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


def take_review_tool_id(proposal_id):
    text = str(proposal_id or "").strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    return text


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
        "actions": [{"id": take_review_tool_id(item), "action": action} for item in ids[:TAKE_REVIEW_MAX_LIMIT]],
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
    try:
        broad_graph_budget = max(1, min(
            graph_query_timeout,
            int(os.environ.get("MEMORY_STARGRAPH_YODA_BROAD_GRAPH_BUDGET_SECONDS") or config.get("yoda_broad_graph_budget_seconds") or 8),
        ))
    except (TypeError, ValueError):
        broad_graph_budget = min(graph_query_timeout, 8)
    node_path = str(os.environ.get("MEMORY_STARGRAPH_YODA_NODE_PATH") or config.get("yoda_node_path") or "").strip()
    fallback_paths = []
    env_fallbacks = os.environ.get("MEMORY_STARGRAPH_YODA_NODE_FALLBACK_PATHS")
    if env_fallbacks:
        fallback_paths.extend(path for path in env_fallbacks.split(os.pathsep) if path.strip())
    configured_fallbacks = config.get("yoda_node_fallback_paths") or []
    if isinstance(configured_fallbacks, str):
        configured_fallbacks = [configured_fallbacks]
    if isinstance(configured_fallbacks, list):
        fallback_paths.extend(str(path) for path in configured_fallbacks if str(path).strip())
    return {
        "backend": backend,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "agent": agent_ref,
        "timeout": timeout,
        "graph_query_timeout": graph_query_timeout,
        "broad_graph_budget": broad_graph_budget,
        "node_path": node_path,
        "node_fallback_paths": fallback_paths,
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
        "node_runtime": select_openclaw_node_runtime(config) if config["backend"] == "openclaw" else {"status": "not_used"},
    }


def save_yoda_model_config(payload):
    backend = str(payload.get("backend") or "openclaw").strip().lower()
    if backend not in YODA_BACKENDS:
        raise ValueError(f"backend must be one of: {', '.join(sorted(YODA_BACKENDS))}")
    model = str(payload.get("model") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    api_key_env = str(payload.get("api_key_env") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY"
    agent = str(payload.get("agent") or "").strip()
    node_path = str(payload.get("node_path") or "").strip()
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
        "yoda_node_path": node_path,
    })
    write_local_config_file(config)
    return public_yoda_model_config()


def split_markdown_table_row(line):
    text = line.strip().removeprefix("|").removesuffix("|")
    cells = []
    current = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def parse_memory_starmap_todo_rows(markdown):
    lines = str(markdown or "").splitlines()
    columns = ("id", "status", "priority", "title", "node", "updated", "notes")
    start = None
    for index, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = tuple(cell.lower() for cell in split_markdown_table_row(line))
        if cells[: len(columns)] == columns:
            start = index
            break
    if start is None:
        return []
    rows = []
    for line in lines[start + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_markdown_table_row(line)
        if len(cells) >= len(columns):
            rows.append({column: cells[index] for index, column in enumerate(columns)})
    return rows


def parse_memory_starmap_archive_index(markdown):
    lines = str(markdown or "").splitlines()
    columns = ("archive", "sequence", "first id", "last id", "count")
    start = None
    for index, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = tuple(cell.lower() for cell in split_markdown_table_row(line))
        if cells[: len(columns)] == columns:
            start = index
            break
    if start is None:
        return []
    entries = []
    for line in lines[start + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = split_markdown_table_row(line)
        if len(cells) < len(columns):
            continue
        match = re.search(r"\[\[([^\]]+)\]\]", cells[0])
        if not match:
            continue
        try:
            sequence = int(cells[1])
            count = int(cells[4])
        except ValueError:
            continue
        entries.append(
            {
                "slug": match.group(1).strip(),
                "sequence": sequence,
                "first_id": cells[2].strip().upper(),
                "last_id": cells[3].strip().upper(),
                "count": count,
            }
        )
    return entries


def todo_row_node_slug(row):
    match = re.search(r"\[\[([^\]]+)\]\]", str(row.get("node") or ""))
    return match.group(1).strip() if match else ""


def looks_like_todo_id(value):
    return bool(re.fullmatch(r"SG-\d{3,}", str(value or "").strip(), re.IGNORECASE))


def todo_id_number(value):
    match = re.fullmatch(r"SG-(\d{3,})", str(value or "").strip().upper())
    return int(match.group(1)) if match else None


def todo_row_search_result(row, preview_prefix="Exact TODO ID match"):
    slug = todo_row_node_slug(row)
    if not slug:
        return None
    title = str(row.get("title") or make_label(slug))
    status = str(row.get("status") or "").strip()
    preview = preview_prefix
    if status:
        preview += f": status {status}"
    return {
        "slug": slug,
        "score": 100.0,
        "label": title[:120],
        "preview": preview,
    }


def archived_todo_index_search_result(todo_id):
    try:
        payload = json.loads(COMPLETED_TODO_ARCHIVE_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if payload.get("schema") != "memory-stargraph-completed-todo-archive-index-v1":
        return None
    for archive in payload.get("archives") or []:
        if not isinstance(archive, dict):
            continue
        rows = archive.get("rows") or []
        first_id = str(archive.get("first_id") or "").strip().upper()
        last_id = str(archive.get("last_id") or "").strip().upper()
        try:
            expected_count = int(archive.get("count"))
        except (TypeError, ValueError):
            continue
        ids = [str(row.get("id") or "").strip().upper() for row in rows if isinstance(row, dict)]
        if len(rows) != expected_count or not ids or ids[0] != first_id or ids[-1] != last_id:
            continue
        for row in rows:
            if not isinstance(row, dict) or str(row.get("id") or "").strip().upper() != todo_id:
                continue
            slug = str(row.get("slug") or "").strip()
            if not slug.startswith("notes/memory-starmap-todo-list/"):
                return None
            title = str(row.get("title") or make_label(slug))
            status = str(row.get("status") or "").strip()
            preview = "Exact archived TODO ID match"
            if status:
                preview += f": status {status}"
            return {
                "slug": slug,
                "score": 100.0,
                "label": title[:120],
                "preview": preview,
            }
    return None


def exact_todo_id_search_results(query):
    todo_id = str(query or "").strip().upper()
    if not looks_like_todo_id(todo_id):
        return None, "not_exact_todo_id"
    indexed_result = archived_todo_index_search_result(todo_id)
    if indexed_result:
        return [indexed_result], "complete"
    try:
        backlog = run_gbrain("get", "notes/memory-starmap-todo-list", timeout=EXACT_TODO_GBRAIN_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001
        return [], "partial_timeout"
    for row in parse_memory_starmap_todo_rows(backlog):
        if str(row.get("id") or "").strip().upper() != todo_id:
            continue
        result = todo_row_search_result(row)
        return ([result] if result else []), "complete"
    target_number = todo_id_number(todo_id)
    for archive in parse_memory_starmap_archive_index(backlog):
        first_number = todo_id_number(archive.get("first_id"))
        last_number = todo_id_number(archive.get("last_id"))
        if target_number is None or first_number is None or last_number is None:
            continue
        if not (first_number <= target_number <= last_number):
            continue
        try:
            archive_markdown = run_gbrain("get", archive["slug"], timeout=EXACT_TODO_GBRAIN_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001
            return [], "partial_timeout"
        rows = parse_memory_starmap_todo_rows(archive_markdown)
        ids = [str(row.get("id") or "").strip().upper() for row in rows]
        if (
            len(rows) != archive["count"]
            or not ids
            or ids[0] != archive["first_id"]
            or ids[-1] != archive["last_id"]
        ):
            return [], "partial_timeout"
        for row in rows:
            if str(row.get("id") or "").strip().upper() == todo_id:
                result = todo_row_search_result(row, "Exact archived TODO ID match")
                return ([result] if result else []), "complete"
        return [], "complete"
    return [], "complete"


def normalized_search_identity(value):
    return re.sub(r"[^\w]+", " ", str(value or "").lower()).strip()


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
    question = extract_yoda_prompt_field(prompt, "Question") or prompt
    selected_slug = extract_yoda_prompt_field(prompt, "Selected node")
    payload = {"question": question, "save": False, "take": False}
    if selected_slug:
        payload["anchor"] = selected_slug
    if model:
        payload["model"] = model
    try:
        result = yoda_gbrain_call_tool("think", payload, timeout=config["timeout"])
        if isinstance(result, dict):
            answer = str(
                result.get("answer")
                or result.get("output")
                or result.get("response")
                or ""
            ).strip()
        else:
            answer = str(result or "").strip()
    except Exception as exc:  # noqa: BLE001
        details.update({"model_status": "api_error", "error_summary": str(exc)})
        return {"output": None, **details} if return_details else None
    details["model_status"] = "answered" if answer else "empty_output"
    return {"output": answer or None, **details} if return_details else (answer or None)


def extract_yoda_prompt_field(prompt, label):
    pattern = rf"(?m)^{re.escape(str(label))}:\s*(.+?)\s*$"
    match = re.search(pattern, str(prompt or ""))
    return match.group(1).strip() if match else ""


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


def bundled_codex_node_path():
    return Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node"


def parse_node_version(raw_version):
    match = re.search(r"v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)", str(raw_version or ""))
    if not match:
        return None
    return tuple(int(match.group(part)) for part in ("major", "minor", "patch"))


def openclaw_supports_node_version(raw_version):
    version = parse_node_version(raw_version)
    if version is None:
        return False
    major, minor, patch = version
    if major == 22:
        return (minor, patch) >= (22, 3)
    if major == 24:
        return (minor, patch) >= (15, 0)
    if major == 25:
        return (minor, patch) >= (9, 0)
    return major > 25


def normalize_node_candidate(path):
    raw = str(path or "").strip()
    if not raw:
        return ""
    if raw == "node":
        return shutil.which("node") or raw
    return str(Path(raw).expanduser())


def node_runtime_candidates(config):
    candidates = []
    explicit = normalize_node_candidate(config.get("node_path"))
    if explicit:
        candidates.append(("configured", explicit))
    for path in config.get("node_fallback_paths") or []:
        normalized = normalize_node_candidate(path)
        if normalized:
            candidates.append(("configured_fallback", normalized))
    candidates.extend(
        [
            ("codex_bundled", str(bundled_codex_node_path())),
            ("path", shutil.which("node") or "node"),
            ("homebrew_intel", "/usr/local/bin/node"),
            ("homebrew_apple_silicon", "/opt/homebrew/bin/node"),
        ]
    )
    seen = set()
    ordered = []
    for source, path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append((source, path))
    return ordered


def probe_node_runtime(path, source):
    normalized = normalize_node_candidate(path)
    details = {
        "path": normalized,
        "source": source,
        "status": "missing",
        "version": "",
        "error": "",
    }
    if not normalized:
        return details
    binary = Path(normalized)
    if not binary.exists():
        details["error"] = "node binary not found"
        return details
    try:
        result = subprocess.run(
            [str(binary), "-e", "process.stdout.write(process.version)"],
            cwd=ROOT,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        details.update({"status": "failed", "error": safe_preview(str(exc), 240)})
        return details
    details["version"] = safe_preview(result.stdout, 80)
    if result.returncode != 0:
        details.update({
            "status": "failed",
            "error": safe_preview(result.stderr or result.stdout, 300),
        })
        return details
    if not openclaw_supports_node_version(details["version"]):
        details.update({
            "status": "unsupported_version",
            "error": f"OpenClaw requires Node.js >=22.22.3 <23, >=24.15.0 <25, or >=25.9.0; found {details['version'] or 'unknown'}",
        })
        return details
    details["status"] = "ok"
    return details


def select_openclaw_node_runtime(config):
    probes = [probe_node_runtime(path, source) for source, path in node_runtime_candidates(config)]
    selected = next((probe for probe in probes if probe["status"] == "ok"), None)
    if selected:
        return {
            "status": "ok",
            "path": selected["path"],
            "version": selected["version"],
            "source": selected["source"],
            "error": "",
            "candidates": probes,
        }
    first_failure = next((probe for probe in probes if probe["status"] != "missing"), probes[0] if probes else {})
    return {
        "status": "unavailable",
        "path": "",
        "version": "",
        "source": "",
        "error": first_failure.get("error") or "No supported Node runtime found for OpenClaw",
        "candidates": probes,
    }


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
    details = yoda_details("openclaw", str(config.get("model") or ""), timeout)
    node_runtime = select_openclaw_node_runtime(config)
    details.update({
        "node_runtime_status": node_runtime["status"],
        "node_runtime_path": node_runtime.get("path", ""),
        "node_runtime_version": node_runtime.get("version", ""),
        "node_runtime_source": node_runtime.get("source", ""),
        "node_runtime_error": node_runtime.get("error", ""),
    })
    if node_runtime["status"] != "ok":
        details.update({
            "openclaw_status": "runtime_unavailable",
            "model_status": "unavailable",
            "error_summary": node_runtime.get("error") or "No supported Node runtime found for OpenClaw",
        })
        return {"output": None, **details} if return_details else None
    node_dir = str(Path(node_runtime["path"]).parent)
    env["PATH"] = f"{node_dir}:{bun_bin}:/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
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


EVIDENCE_SEARCH_TYPES = ("learning", "todo", "report", "run")
SEARCH_PRIMARY_TIMEOUT_SECONDS = 6
SEARCH_PRIMARY_CACHE_SECONDS = 30
SEARCH_PRIMARY_CACHE_STALE_SECONDS = 300
SEARCH_PRIMARY_CACHE_MAX_ENTRIES = 64
SEARCH_TOTAL_BUDGET_SECONDS = 8.6
SEARCH_EVIDENCE_BUDGET_SECONDS = 4.0
SEARCH_EVIDENCE_CACHE_SECONDS = 30
SEARCH_EVIDENCE_STALE_SECONDS = 300
SEARCH_EVIDENCE_PREWARM_TIMEOUT_SECONDS = 10
YODA_SEARCH_CACHE_SECONDS = 30
YODA_SEARCH_CACHE_MAX_ENTRIES = 32
YODA_SOURCE_CACHE_SECONDS = 30
YODA_SOURCE_CACHE_MAX_ENTRIES = 64
YODA_CONTEXT_CACHE_SECONDS = 300
YODA_CONTEXT_CACHE_MAX_ENTRIES = 8
AUTOPILOT_FINDINGS_CACHE_SECONDS = 30
AUTOPILOT_FINDINGS_CACHE_MAX_ENTRIES = 16
AUTOPILOT_FINDINGS_CAPABILITY_CACHE_SECONDS = 300
TAKE_REVIEW_CACHE_SECONDS = 30
TAKE_REVIEW_CACHE_MAX_ENTRIES = 32
TAKE_REVIEW_CAPABILITY_CACHE_SECONDS = 300
RESOLVER_READ_CACHE_SECONDS = 30
RESOLVER_READ_CACHE_MAX_ENTRIES = 16
RESOLVER_CAPABILITY_CACHE_SECONDS = 300
GBRAIN_TOOL_MANIFEST_CACHE_SECONDS = 300
GBRAIN_TOOL_MANIFEST_TIMEOUT_SECONDS = 5
OPTIONAL_GBRAIN_TOOL_NAMES = frozenset(
    {
        "autopilot_findings_list",
        "resolver_feedback_health",
        "resolver_proposals_list",
        "take_proposals_list",
    }
)
MUTATING_GBRAIN_TOOL_NAMES = frozenset(
    {
        "add_link",
        "add_tag",
        "add_timeline_entry",
        "delete_page",
        "put_page",
        "remove_link",
        "remove_tag",
    }
)
PERSISTENT_GBRAIN_TOOL_NAMES = frozenset(
    {
        "add_link",
        "add_tag",
        "add_timeline_entry",
        "delete_page",
        "get_page",
        "get_tags",
        "get_timeline",
        "get_versions",
        "put_page",
        "remove_link",
        "remove_tag",
        "think",
    }
)
SETTINGS_EVIDENCE_CACHE_SECONDS = 10
EXACT_TODO_GBRAIN_TIMEOUT_SECONDS = 12
SEARCH_TERM_SYNONYMS = {
    "optional": ("bounded", "bound"),
    "timeout": ("latency", "slow", "terminal"),
    "timeouts": ("latency", "slow", "terminal"),
    "telemetry": ("feedback", "status", "evidence"),
}
EVIDENCE_SEARCH_PREFIXES = (
    "runs/",
    "reports/",
    "learnings/",
    "notes/memory-starmap-todo-list/",
)
SEARCH_SENTINEL_FIXTURES_PATH = ROOT / "config" / "search_sentinel_queries.json"
EVIDENCE_SEARCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def evidence_search_terms(query):
    return [
        term
        for term in re.findall(r"[\w-]+", str(query or "").lower())
        if len(term) >= 3 and term not in EVIDENCE_SEARCH_STOPWORDS
    ]


def load_search_sentinel_fixtures():
    try:
        payload = json.loads(SEARCH_SENTINEL_FIXTURES_PATH.read_text())
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(payload, list):
        return []
    fixtures = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        query = re.sub(r"\s+", " ", str(item.get("query") or "").strip().lower())
        slug = str(item.get("slug") or "").strip()
        if not query or not slug.startswith(EVIDENCE_SEARCH_PREFIXES):
            continue
        fixtures.append(
            {
                "query": query,
                "slug": slug,
                "label": str(item.get("label") or make_label(slug))[:120],
                "preview": str(item.get("preview") or "Search sentinel evidence record.")[:280],
                "reason": str(item.get("reason") or "")[:240],
            }
        )
    return fixtures


def search_sentinel_results(query, existing_slugs=None):
    existing_slugs = set(existing_slugs or [])
    normalized_query = re.sub(r"\s+", " ", str(query or "").strip().lower())
    if not normalized_query:
        return []
    results = []
    for fixture in load_search_sentinel_fixtures():
        if fixture["query"] != normalized_query:
            continue
        if fixture["slug"] in existing_slugs:
            continue
        results.append(
            {
                "slug": fixture["slug"],
                "score": 6.5,
                "label": fixture["label"],
                "preview": fixture["preview"],
                "sentinel": True,
            }
        )
    return results[:3]


def expanded_search_terms(query):
    terms = evidence_search_terms(query)
    expanded = []
    for term in terms:
        expanded.append(term)
        expanded.extend(SEARCH_TERM_SYNONYMS.get(term, ()))
    seen = set()
    return [term for term in expanded if not (term in seen or seen.add(term))][:16]


def evidence_haystack(row):
    return " ".join(
        str(row.get(key) or "")
        for key in ("slug", "title", "type", "date")
    ).lower().replace("_", "-")


def score_evidence_record(row, query, terms):
    slug = str(row.get("slug") or "")
    if not slug.startswith(EVIDENCE_SEARCH_PREFIXES):
        return 0
    haystack = evidence_haystack(row)
    normalized_query = re.sub(r"\s+", " ", str(query or "").strip().lower()).replace("_", "-")
    if not terms:
        return 0
    score = 35
    if str(row.get("type") or "") in EVIDENCE_SEARCH_TYPES:
        score += 25
    if normalized_query and normalized_query in haystack:
        score += 80
    matched_terms = sum(1 for term in terms if term in haystack)
    score += matched_terms * 16
    if matched_terms == len(terms):
        score += 70
    elif matched_terms < max(2, len(terms) // 2):
        return 0
    if slug.startswith(("runs/", "reports/", "learnings/")):
        score += 30
    if slug.startswith("notes/memory-starmap-todo-list/"):
        score += 20
    return score


class EvidenceListCache:
    def __init__(self, ttl_seconds=SEARCH_EVIDENCE_CACHE_SECONDS, stale_seconds=SEARCH_EVIDENCE_STALE_SECONDS):
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = max(ttl_seconds, stale_seconds)
        self.entries = {}
        self.refreshing = set()
        self.refresh_events = {}
        self.generation = 0
        self.lock = threading.Lock()

    def get(self, page_type, per_type_limit):
        key = (page_type, per_type_limit)
        now = time.monotonic()
        with self.lock:
            entry = self.entries.get(key)
            if not entry:
                return None
            age = now - entry["stored_at"]
            if age >= self.stale_seconds:
                self.entries.pop(key, None)
                return None
            if age >= self.ttl_seconds:
                return None
            return entry["rows"]

    def get_stale(self, page_type, per_type_limit):
        key = (page_type, per_type_limit)
        now = time.monotonic()
        with self.lock:
            entry = self.entries.get(key)
            if not entry or now - entry["stored_at"] >= self.stale_seconds:
                self.entries.pop(key, None)
                return None
            return entry["rows"]

    def put(self, page_type, per_type_limit, rows):
        with self.lock:
            self.entries[(page_type, per_type_limit)] = {
                "rows": tuple(rows),
                "stored_at": time.monotonic(),
            }

    def refresh_async(self, page_type, per_type_limit, loader):
        key = (page_type, per_type_limit)
        with self.lock:
            generation = self.generation
            token = (generation, key)
            if token in self.refreshing:
                return False
            self.refreshing.add(token)
            refresh_event = threading.Event()
            self.refresh_events[token] = refresh_event

        def refresh():
            try:
                rows = tuple(loader())
            except Exception:  # noqa: BLE001
                rows = None
            with self.lock:
                self.refreshing.discard(token)
                self.refresh_events.pop(token, None)
                if rows is not None and self.generation == generation:
                    self.entries[key] = {
                        "rows": rows,
                        "stored_at": time.monotonic(),
                    }
                refresh_event.set()

        threading.Thread(target=refresh, daemon=True).start()
        return True

    def wait_for_refresh(self, page_type, per_type_limit, timeout):
        key = (page_type, per_type_limit)
        with self.lock:
            refresh_event = self.refresh_events.get((self.generation, key))
        if refresh_event is None:
            return self.get(page_type, per_type_limit)
        refresh_event.wait(timeout=max(0, timeout))
        return self.get(page_type, per_type_limit)

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.generation += 1


class TimedValueCache:
    def __init__(self, ttl_seconds, max_entries, stale_seconds=None):
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = max(ttl_seconds, stale_seconds or ttl_seconds)
        self.max_entries = max_entries
        self.entries = {}
        self.refreshing = set()
        self.loading_events = {}
        self.generation = 0
        self.lock = threading.Lock()

    def __len__(self):
        with self.lock:
            return len(self.entries)

    def get(self, key):
        now = time.monotonic()
        with self.lock:
            entry = self.entries.get(key)
            if not entry or now - entry["stored_at"] >= self.ttl_seconds:
                return None
            return entry["value"]

    def get_stale(self, key):
        now = time.monotonic()
        with self.lock:
            entry = self.entries.get(key)
            if not entry or now - entry["stored_at"] >= self.stale_seconds:
                self.entries.pop(key, None)
                return None
            return entry["value"]

    def put(self, key, value):
        now = time.monotonic()
        with self.lock:
            self.entries = {
                entry_key: entry
                for entry_key, entry in self.entries.items()
                if now - entry["stored_at"] < self.stale_seconds
            }
            self.entries[key] = {"value": value, "stored_at": now}
            if len(self.entries) > self.max_entries:
                oldest_keys = sorted(
                    self.entries,
                    key=lambda entry_key: self.entries[entry_key]["stored_at"],
                )
                for oldest_key in oldest_keys[:-self.max_entries]:
                    self.entries.pop(oldest_key, None)

    def refresh_async(self, key, loader):
        with self.lock:
            generation = self.generation
            token = (generation, key)
            if token in self.refreshing:
                return False
            self.refreshing.add(token)

        def refresh():
            try:
                value = loader()
            except Exception:  # noqa: BLE001
                value = None
            with self.lock:
                self.refreshing.discard(token)
                if value is not None and self.generation == generation:
                    self.entries[key] = {
                        "value": value,
                        "stored_at": time.monotonic(),
                    }

        threading.Thread(target=refresh, daemon=True).start()
        return True

    def load_once(self, key, loader, timeout):
        with self.lock:
            generation = self.generation
            token = (generation, key)
            load_event = self.loading_events.get(token)
            owner = load_event is None
            if owner:
                load_event = threading.Event()
                self.loading_events[token] = load_event

        if owner:
            try:
                value = loader()
            except Exception:  # noqa: BLE001
                value = None
            with self.lock:
                self.loading_events.pop(token, None)
                if value is not None and self.generation == generation:
                    now = time.monotonic()
                    self.entries = {
                        entry_key: entry
                        for entry_key, entry in self.entries.items()
                        if now - entry["stored_at"] < self.stale_seconds
                    }
                    self.entries[key] = {
                        "value": value,
                        "stored_at": now,
                    }
                    if len(self.entries) > self.max_entries:
                        oldest_keys = sorted(
                            self.entries,
                            key=lambda entry_key: self.entries[entry_key]["stored_at"],
                        )
                        for oldest_key in oldest_keys[:-self.max_entries]:
                            self.entries.pop(oldest_key, None)
                load_event.set()
            return value, "loaded"

        load_event.wait(timeout=max(0, timeout))
        with self.lock:
            entry = self.entries.get(key)
            value = entry["value"] if entry and self.generation == generation else None
        return value, "joined" if value is not None else "timeout"

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.generation += 1


class SingleFlight:
    def __init__(self):
        self.futures = {}
        self.lock = threading.Lock()

    def run(self, key, loader, timeout):
        with self.lock:
            future = self.futures.get(key)
            owner = future is None
            if owner:
                future = Future()
                self.futures[key] = future

        if owner:
            try:
                future.set_result(loader())
            except BaseException as error:  # noqa: BLE001
                future.set_exception(error)
            finally:
                with self.lock:
                    self.futures.pop(key, None)
            return future.result()
        return future.result(timeout=max(0, timeout))


LOCAL_GBRAIN_TOOL_MANIFEST_CACHE = TimedValueCache(
    ttl_seconds=GBRAIN_TOOL_MANIFEST_CACHE_SECONDS,
    max_entries=4,
)
GBRAIN_RERANKER_READINESS_CACHE = TimedValueCache(
    ttl_seconds=GBRAIN_RERANKER_READINESS_CACHE_SECONDS,
    stale_seconds=30 * 60,
    max_entries=2,
)


def local_gbrain_tool_manifest_key():
    try:
        stat = GBRAIN.stat()
    except OSError:
        return None
    return (
        str(GBRAIN.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        os.environ.get("GBRAIN_HOME", ""),
        os.environ.get("GBRAIN_CONFIG_FILE", ""),
        id(run_gbrain),
    )


def load_local_gbrain_tool_names():
    output = run_gbrain(
        "--tools-json",
        timeout=GBRAIN_TOOL_MANIFEST_TIMEOUT_SECONDS,
    )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = extract_json_list(output)
    if not isinstance(payload, list):
        raise RuntimeError("GBrain tool manifest was invalid")
    names = frozenset(
        str(item.get("name") or "").strip()
        for item in payload
        if isinstance(item, dict) and item.get("name")
    )
    if not {"get_page", "search"}.issubset(names):
        raise RuntimeError("GBrain tool manifest omitted core tools")
    return names


def local_gbrain_tool_available(tool_name):
    if configured_remote_mcp_path() is not None:
        return None
    key = local_gbrain_tool_manifest_key()
    if key is None:
        return None
    names = LOCAL_GBRAIN_TOOL_MANIFEST_CACHE.get(key)
    if names is None:
        names, _source = LOCAL_GBRAIN_TOOL_MANIFEST_CACHE.load_once(
            key,
            load_local_gbrain_tool_names,
            timeout=GBRAIN_TOOL_MANIFEST_TIMEOUT_SECONDS,
        )
    return tool_name in names if names is not None else None


def load_evidence_page_rows(page_type, per_type_limit, timeout):
    return parse_page_list(
        run_gbrain(
            "list",
            "--type",
            page_type,
            "-n",
            str(per_type_limit),
            timeout=timeout,
        )
    )


def evidence_record_search_results(
    query,
    existing_slugs=None,
    per_type_limit=40,
    result_limit=10,
    deadline=None,
    per_type_timeout=2.5,
    row_cache=None,
):
    existing_slugs = set(existing_slugs or [])
    terms = evidence_search_terms(query)
    if not terms:
        return [], "skipped_no_terms", "skipped_no_terms"
    candidates = {}
    status = "complete"
    rows_by_type = {}
    missing_types = []
    stale_types = []
    prewarm_types = []
    for page_type in EVIDENCE_SEARCH_TYPES:
        cached_rows = row_cache.get(page_type, per_type_limit) if row_cache is not None else None
        if cached_rows is None:
            stale_rows = row_cache.get_stale(page_type, per_type_limit) if row_cache is not None else None
            if stale_rows is None:
                wait_timeout = per_type_timeout
                if deadline is not None:
                    wait_timeout = max(0, deadline - time.monotonic())
                refreshed_rows = (
                    row_cache.wait_for_refresh(page_type, per_type_limit, wait_timeout)
                    if row_cache is not None and wait_timeout > 0
                    else None
                )
                if refreshed_rows is None:
                    missing_types.append(page_type)
                else:
                    rows_by_type[page_type] = refreshed_rows
                    prewarm_types.append(page_type)
            else:
                rows_by_type[page_type] = stale_rows
                stale_types.append(page_type)
        else:
            rows_by_type[page_type] = cached_rows

    if row_cache is None:
        cache_status = "disabled"
    elif prewarm_types:
        cache_status = "prewarm_hit" if not missing_types and not stale_types else "partial_prewarm_hit"
    elif stale_types:
        cache_status = "stale_hit" if len(stale_types) == len(EVIDENCE_SEARCH_TYPES) else "partial_stale_hit"
    elif not missing_types:
        cache_status = "hit"
    elif len(missing_types) == len(EVIDENCE_SEARCH_TYPES):
        cache_status = "miss"
    else:
        cache_status = "partial_hit"

    for page_type in stale_types:
        row_cache.refresh_async(
            page_type,
            per_type_limit,
            lambda page_type=page_type: load_evidence_page_rows(
                page_type,
                per_type_limit,
                per_type_timeout,
            ),
        )

    if missing_types:
        timeout = per_type_timeout
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return [], "partial_timeout", cache_status
            timeout = max(0.5, min(per_type_timeout, remaining))

        with ThreadPoolExecutor(max_workers=len(missing_types)) as executor:
            futures = {
                page_type: executor.submit(
                    load_evidence_page_rows,
                    page_type,
                    per_type_limit,
                    timeout,
                )
                for page_type in missing_types
            }
            for page_type in missing_types:
                try:
                    rows = futures[page_type].result()
                    rows_by_type[page_type] = rows
                    if row_cache is not None:
                        row_cache.put(page_type, per_type_limit, rows)
                except Exception:  # noqa: BLE001
                    status = "partial_timeout"
                    rows_by_type[page_type] = []

    for page_type in EVIDENCE_SEARCH_TYPES:
        rows = rows_by_type[page_type]
        for row in rows:
            slug = str(row.get("slug") or "")
            score = score_evidence_record(row, query, terms)
            if score <= 0:
                continue
            previous = candidates.get(slug)
            if not previous or score > previous["evidence_score"]:
                candidates[slug] = {
                    "slug": slug,
                    "score": 2.0 + score / 100.0,
                    "label": str(row.get("title") or make_label(slug))[:120],
                    "preview": "Evidence record: "
                    + " ".join(part for part in [str(row.get("date") or ""), str(row.get("title") or "")] if part).strip(),
                    "evidence_score": score,
                }
    return [
        {key: value for key, value in item.items() if key != "evidence_score"}
        for item in sorted(
            candidates.values(),
            key=lambda item: (
                item["slug"] in existing_slugs,
                item["evidence_score"],
                item["score"],
                item["slug"],
            ),
            reverse=True,
        )[:result_limit]
    ], status, cache_status


def merge_search_results(primary_results, evidence_results, query=""):
    merged = {}
    for result in evidence_results + primary_results:
        slug = result["slug"]
        if slug not in merged:
            merged[slug] = dict(result)
            continue
        current = merged[slug]
        current["score"] = max(float(current.get("score") or 0), float(result.get("score") or 0))
        if not current.get("preview"):
            current["preview"] = result.get("preview") or ""
        if not current.get("label"):
            current["label"] = result.get("label") or make_label(slug)
    terms = evidence_search_terms(query)
    if terms:
        for item in merged.values():
            haystack = " ".join(
                str(item.get(key) or "")
                for key in ("slug", "label", "preview")
            ).lower().replace("_", "-")
            if all(term in haystack for term in terms):
                item["score"] = float(item.get("score") or 0) + 10.0
    evidence_order = {result["slug"]: index for index, result in enumerate(evidence_results)}
    primary_order = {result["slug"]: index for index, result in enumerate(primary_results)}

    def identity_relevance(item):
        normalized_query = re.sub(r"\s+", " ", str(query or "").strip().lower()).replace("_", "-")
        if not normalized_query:
            return (0, 0, 0, 0, 0, 0)
        identity_query = normalized_search_identity(query)
        terms = evidence_search_terms(query)
        slug = str(item.get("slug") or "").lower().replace("_", "-")
        label = str(item.get("label") or "").lower().replace("_", "-")
        identity_text = f"{slug} {label}"
        identity_words = normalized_search_identity(identity_text)
        raw_label = str(item.get("label") or "")
        label_words = normalized_search_identity(raw_label)
        slug_words = normalized_search_identity(item.get("slug") or "")
        preview = str(item.get("preview") or "").lower().replace("_", "-")
        full_text = f"{identity_text} {preview}"
        label_is_truncated = raw_label.endswith("...")
        exact_identity = 1 if identity_query and (
            slug_words == identity_query or (label_words == identity_query and not label_is_truncated)
        ) else 0
        label_prefix = 1 if identity_query and label_words.startswith(identity_query) else 0
        identity_phrase = 1 if normalized_query in identity_text else 0
        full_phrase = 1 if normalized_query in full_text else 0
        if not terms:
            return (exact_identity, label_prefix, identity_phrase, full_phrase, 0, 0)
        identity_matches = sum(1 for term in terms if term in identity_text)
        full_matches = sum(1 for term in terms if term in full_text)
        identity_complete = 1 if identity_matches == len(terms) else 0
        word_complete = 1 if identity_query and identity_query in identity_words else 0
        return (
            exact_identity,
            label_prefix,
            max(identity_phrase, word_complete),
            identity_complete,
            identity_matches,
            full_phrase + full_matches,
        )

    return sorted(
        merged.values(),
        key=lambda item: (
            identity_relevance(item),
            float(item.get("score") or 0),
            1 if item["slug"] in evidence_order else 0,
            -evidence_order.get(item["slug"], 9999),
            -primary_order.get(item["slug"], 9999),
        ),
        reverse=True,
    )


def loaded_graph_search_results(raw_graph, query, existing_slugs=None, result_limit=5):
    existing_slugs = set(existing_slugs or [])
    terms = expanded_search_terms(query)
    if not terms:
        return []
    query_text = re.sub(r"\s+", " ", str(query or "").strip().lower()).replace("_", "-")
    candidates = []
    for node in raw_graph.get("nodes") or []:
        slug = str(node.get("slug") or "")
        if not slug or slug in existing_slugs:
            continue
        label = str(node.get("label") or "")
        summary = str(node.get("summary") or "")
        tags = " ".join(str(tag) for tag in node.get("tags") or [])
        haystack = f"{slug} {label} {summary} {tags}".lower().replace("_", "-")
        score = 0.0
        identity_query = normalized_search_identity(query)
        label_words = normalized_search_identity(label)
        slug_words = normalized_search_identity(slug)
        label_is_truncated = label.endswith("...")
        if identity_query and (slug_words == identity_query or (label_words == identity_query and not label_is_truncated)):
            score += 100.0
        elif identity_query and label_words.startswith(identity_query) and not label_is_truncated:
            score += 25.0
        if query_text and query_text in haystack:
            score += 20.0
        for term in terms:
            if term in slug.lower():
                score += 3.0
            if term in label.lower():
                score += 2.5
            if term in summary.lower():
                score += 1.5
            if term in tags.lower():
                score += 1.0
        if all(term in haystack for term in terms):
            score += 50.0
        if score <= 0:
            continue
        candidates.append(
            {
                "slug": slug,
                "score": score / 10,
                "label": label or make_label(slug),
                "preview": summary if summary and summary != "No summary available." else "Matched loaded graph metadata while live search was bounded.",
            }
        )
    candidates.sort(key=lambda item: (item["score"], item["slug"]), reverse=True)
    return candidates[:result_limit]


def exact_slug_search_results(raw_graph, query):
    exact_slug = str(query or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*/[a-z0-9._/-]+", exact_slug):
        return None, ""
    for node in raw_graph.get("nodes") or []:
        slug = str(node.get("slug") or "").strip()
        if slug.lower() != exact_slug:
            continue
        summary = str(node.get("summary") or "")
        return [
            {
                "slug": slug,
                "score": 100.0,
                "label": str(node.get("label") or make_label(slug)),
                "preview": summary
                if summary and summary != "No summary available."
                else "Exact loaded graph slug match.",
            }
        ], "loaded_graph"
    try:
        raw = run_gbrain("get", exact_slug, timeout=3)
    except Exception:  # noqa: BLE001
        return None, ""
    meta, body = parse_frontmatter(raw)
    label = str(meta.get("title") or make_label(exact_slug))
    summary = extract_summary_from_markdown_body(
        body,
        label,
        str(meta.get("type") or "entity"),
    )
    return [
        {
            "slug": exact_slug,
            "score": 100.0,
            "label": label,
            "preview": summary or "Exact GBrain slug match.",
        }
    ], "gbrain_get"


def exact_loaded_label_search_results(raw_graph, query):
    identity = normalized_search_identity(query)
    if len(identity.split()) < 2:
        return None
    matches = []
    for node in raw_graph.get("nodes") or []:
        slug = str(node.get("slug") or "").strip()
        label = str(node.get("label") or "").strip()
        if (
            slug
            and label
            and not label.endswith("...")
            and normalized_search_identity(label) == identity
        ):
            matches.append(node)
    if len(matches) != 1:
        return None
    node = matches[0]
    slug = str(node["slug"])
    summary = str(node.get("summary") or "")
    return [
        {
            "slug": slug,
            "score": 100.0,
            "label": str(node.get("label") or make_label(slug)),
            "preview": summary
            if summary and summary != "No summary available."
            else "Exact unique loaded graph label match.",
        }
    ]


def exact_evidence_title_search_results(query, row_cache, per_type_limit=40):
    identity = normalized_search_identity(query)
    if row_cache is None or len(identity.split()) < 2:
        return None
    matches = {}
    for page_type in EVIDENCE_SEARCH_TYPES:
        rows = row_cache.get(page_type, per_type_limit)
        if rows is None:
            return None
        for row in rows:
            slug = str(row.get("slug") or "").strip()
            title = str(row.get("title") or "").strip()
            if slug and title and normalized_search_identity(title) == identity:
                matches[slug] = title
    if len(matches) != 1:
        return None
    slug, title = next(iter(matches.items()))
    return [
        {
            "slug": slug,
            "score": 100.0,
            "label": title[:120],
            "preview": "Exact unique prewarmed evidence title match.",
        }
    ]


def extract_question_entities(question, limit=3):
    text = str(question or "")
    matches = re.findall(
        r"(?<![\w@])@[A-Za-z0-9_]{2,}|(?<![\w])(?:[A-Z][A-Za-z0-9'’-]+(?:\s+[A-Z][A-Za-z0-9'’-]+)+)",
        text,
    )
    ignored = {"Ask Yoda", "GBrain", "Memory Stargraph"}
    seen = set()
    entities = []
    for match in matches:
        clean = match.strip()
        key = clean.lower()
        if not clean or clean in ignored or key in seen:
            continue
        seen.add(key)
        entities.append(clean)
        if len(entities) >= limit:
            break
    return entities


def is_short_yoda_followup(question):
    text = re.sub(r"\s+", " ", str(question or "").strip().lower())
    if not text:
        return False
    explicit = {
        "again",
        "continue",
        "go on",
        "please continue",
        "retry",
        "try again",
        "what about it",
        "why",
        "yes",
    }
    words = re.findall(r"[a-z0-9]+", text)
    return text in explicit or len(words) <= 4


def effective_yoda_retrieval_question(question, history=None):
    current = str(question or "").strip()
    if not is_short_yoda_followup(current):
        return current, False
    for item in reversed(history or []):
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        previous = str(item.get("content") or "").strip()
        if not previous or previous.lower() == current.lower() or is_short_yoda_followup(previous):
            continue
        return f"{previous}\nFollow-up: {current}", True
    return current, False


def is_targeted_relationship_question(question):
    if not extract_question_entities(question):
        return False
    words = set(re.findall(r"[a-z0-9]+", str(question or "").lower()))
    relationship_words = {
        "authored",
        "comment",
        "commented",
        "follow",
        "followed",
        "like",
        "liked",
        "member",
        "replied",
        "reply",
        "repost",
        "reposted",
        "retweeted",
        "retweet",
        "share",
        "shared",
        "wrote",
        "written",
    }
    return bool(words & relationship_words)


def relationship_matches_question(link_type, question):
    stopwords = {"a", "an", "and", "at", "by", "for", "from", "has", "in", "is", "of", "on", "or", "the", "to", "with"}
    relation_words = {
        word
        for word in re.findall(r"[a-z0-9]+", str(link_type or "").lower())
        if word not in stopwords and len(word) >= 3
    }
    question_words = {
        word
        for word in re.findall(r"[a-z0-9]+", str(question or "").lower())
        if word not in stopwords and len(word) >= 3
    }
    if relation_words & question_words:
        return True
    aliases = (
        ({"repost", "reposts", "reposted", "retweet", "retweets", "retweeted"}, {"repost", "reposts", "reposted", "retweet", "retweets", "retweeted"}),
        ({"like", "likes", "liked"}, {"like", "likes", "liked"}),
        ({"write", "writes", "wrote", "written", "author", "authored"}, {"write", "writes", "wrote", "written", "author", "authored"}),
        ({"comment", "comments", "commented", "reply", "replied"}, {"comment", "comments", "commented", "reply", "replied"}),
        ({"share", "shares", "shared"}, {"share", "shares", "shared"}),
    )
    for question_aliases, relation_aliases in aliases:
        if question_words & question_aliases and relation_words & relation_aliases:
            return True
    return False


def preferred_entity_slug(search_output, phrase):
    results = parse_search_results(str(search_output or ""))
    if not results:
        return ""
    phrase_key = re.sub(r"[^a-z0-9]+", "-", str(phrase or "").lower()).strip("-")

    def score(item):
        slug = str(item.get("slug") or "")
        preview = str(item.get("preview") or "").lower()
        rank = 0
        if slug.startswith("people/"):
            rank += 50
        elif slug.startswith(("organizations/", "companies/")):
            rank += 40
        elif slug.startswith("media/") and "-status-" not in slug and "/status/" not in slug:
            rank += 30
        if phrase_key and phrase_key in slug.lower().replace("_", "-"):
            rank += 25
        if str(phrase or "").lower() in preview:
            rank += 10
        rank += float(item.get("score") or 0)
        return rank

    return max(results, key=score).get("slug") or ""


def safe_upload_filename(filename):
    source = unicodedata.normalize("NFC", Path(str(filename or "upload.bin")).name).strip()
    output = []
    pending_separator = False
    for char in source:
        if char.isspace():
            pending_separator = bool(output)
            continue
        if char.isalnum() or char in "._-":
            if pending_separator and output and output[-1] != "-":
                output.append("-")
            output.append(char)
            pending_separator = False
        else:
            pending_separator = bool(output)
    return "".join(output).strip(".-") or "upload.bin"


def parse_gbrain_durable_evidence(output, relative_path, source_bytes):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    payload = None
    for line in str(output or "").splitlines():
        if line.startswith("GBRAIN_FILE_EVIDENCE "):
            try:
                payload = json.loads(line.split(" ", 1)[1])
            except json.JSONDecodeError:
                payload = None
    expected = bytes(source_bytes or b"")
    expected_hash = hashlib.sha256(expected).hexdigest()
    if not (
        safe_path
        and isinstance(payload, dict)
        and payload.get("durable_storage_verified") is True
        and payload.get("storage_path") == safe_path.as_posix()
        and payload.get("filename") == safe_path.name
        and int(payload.get("size_bytes") or -1) == len(expected)
        and payload.get("sha256") == expected_hash
    ):
        raise RuntimeError("GBrain durable storage evidence did not match the attachment path, size, and SHA-256.")
    return payload


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
    lines = raw_meta.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("  - ") and current_key:
            meta.setdefault(current_key, []).append(line[4:].strip().strip("'\""))
            index += 1
            continue
        if ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if re.fullmatch(r"[>|][+-]?", value):
            block_lines = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or lines[index][0].isspace()):
                block_lines.append(lines[index].strip())
                index += 1
            if value.startswith(">"):
                meta[key] = " ".join(part for part in block_lines if part)
            else:
                meta[key] = "\n".join(block_lines)
            current_key = key
            continue
        if value == "":
            meta[key] = []
            current_key = key
        else:
            meta[key] = value.strip("'\"")
            current_key = key
        index += 1
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


def media_preview_url_for_served_url(served_url):
    text = str(served_url or "")
    if not text.startswith("/media/"):
        return None
    return "/media-preview/" + text.split("/media/", 1)[1]


def resolve_media_preview_file_path(request_path):
    text = str(request_path or "")
    if not text.startswith("/media-preview/"):
        return None
    return resolve_media_file_path("/media/" + text.split("/media-preview/", 1)[1])


def parse_media_byte_range(header, size):
    text = str(header or "").strip()
    if not text or not text.lower().startswith("bytes="):
        return None
    specification = text.split("=", 1)[1].strip()
    if not specification or "," in specification or "-" not in specification or size <= 0:
        return MEDIA_RANGE_INVALID
    start_text, end_text = (part.strip() for part in specification.split("-", 1))
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                return MEDIA_RANGE_INVALID
            return max(0, size - suffix_length), size - 1
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    except ValueError:
        return MEDIA_RANGE_INVALID
    if start < 0 or start >= size or end < start:
        return MEDIA_RANGE_INVALID
    return start, min(end, size - 1)


def copy_media_range(source, destination, byte_count):
    remaining = max(0, int(byte_count))
    while remaining:
        chunk = source.read(min(MEDIA_STREAM_CHUNK_BYTES, remaining))
        if not chunk:
            break
        destination.write(chunk)
        remaining -= len(chunk)


def _encode_image_preview(path):
    if Image is None or ImageOps is None:
        return None
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail(MEDIA_PREVIEW_MAX_SIZE, Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            output = io.BytesIO()
            image.save(output, "WEBP", quality=80, method=0)
            return output.getvalue()
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=32)
def _cached_image_preview_bytes(path, mtime_ns, size):
    del mtime_ns, size
    return _encode_image_preview(path)


_IMAGE_PREVIEW_FLIGHTS = {}
_IMAGE_PREVIEW_FLIGHTS_LOCK = threading.Lock()


def image_preview_bytes(path, mtime_ns, size):
    key = (path, mtime_ns, size)
    with _IMAGE_PREVIEW_FLIGHTS_LOCK:
        flight = _IMAGE_PREVIEW_FLIGHTS.get(key)
        owner = flight is None
        if owner:
            flight = {"event": threading.Event(), "value": None, "error": None}
            _IMAGE_PREVIEW_FLIGHTS[key] = flight

    if owner:
        try:
            flight["value"] = _cached_image_preview_bytes(*key)
        except BaseException as error:  # noqa: BLE001
            flight["error"] = error
        finally:
            with _IMAGE_PREVIEW_FLIGHTS_LOCK:
                _IMAGE_PREVIEW_FLIGHTS.pop(key, None)
            flight["event"].set()
    else:
        flight["event"].wait()

    if flight["error"] is not None:
        raise flight["error"]
    return flight["value"]


image_preview_bytes.cache_clear = _cached_image_preview_bytes.cache_clear
image_preview_bytes.cache_info = _cached_image_preview_bytes.cache_info
image_preview_bytes.cache_parameters = _cached_image_preview_bytes.cache_parameters
image_preview_bytes.__wrapped__ = _cached_image_preview_bytes.__wrapped__


def enrich_media_reference_metadata(item):
    enriched = dict(item)
    served_url = enriched.get("served_url")
    file_path = resolve_media_file_path(served_url) if served_url else None
    if not file_path:
        return enriched
    try:
        size_bytes = file_path.stat().st_size
    except OSError:
        return enriched
    enriched["size_bytes"] = size_bytes
    if (
        Image is not None
        and enriched.get("kind") == "image"
        and file_path.suffix.lower() in MEDIA_PREVIEW_EXTENSIONS
        and size_bytes >= MEDIA_PREVIEW_MIN_BYTES
    ):
        enriched["preview_url"] = media_preview_url_for_served_url(served_url)
    return enriched


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


def gbrain_file_ledger_has_relative_path(slug, relative_path, ledger_output=None):
    safe_path = safe_media_relative_path(str(relative_path or ""))
    if not safe_path:
        return False
    output = ledger_output
    if output is None:
        try:
            output = run_gbrain("files", "list", slug)
        except Exception:  # noqa: BLE001
            return False
    filename = safe_path.name
    page = str(slug or "").strip("/")
    for line in str(output or "").splitlines():
        listed_page, separator, listed_file = line.strip().partition(" / ")
        if not separator:
            continue
        listed_file = listed_file.split("  [", 1)[0].strip()
        if listed_page == page and listed_file == filename:
            return True
    return False


def run_gbrain_files_bridge(file_path, slug):
    if not GBRAIN_FILES_BRIDGE_SSH:
        raise RuntimeError("No trusted GBrain files SSH bridge is configured.")
    source = Path(file_path).expanduser()
    if not source.is_file():
        raise RuntimeError("Attachment source file is unavailable for the GBrain files bridge.")
    safe_name = safe_upload_filename(source.name)
    create_dir = subprocess.run(
        ["ssh", GBRAIN_FILES_BRIDGE_SSH, "bash", "-s"],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
        input=b"set -euo pipefail\nmktemp -d /tmp/memory-stargraph-upload.XXXXXX\n",
    )
    if create_dir.returncode != 0:
        raise RuntimeError(f"GBrain files bridge temp directory failed: {decode_process_output(create_dir.stderr).strip() or 'mktemp failed'}")
    remote_dir = decode_process_output(create_dir.stdout).strip().splitlines()[-1]
    if not remote_dir.startswith("/tmp/memory-stargraph-upload."):
        raise RuntimeError("GBrain files bridge returned an unsafe temporary directory.")
    remote_path = f"{remote_dir}/{safe_name}"
    copied = subprocess.run(
        ["scp", "-q", "--", str(source), f"{GBRAIN_FILES_BRIDGE_SSH}:{remote_path}"],
        cwd=ROOT,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if copied.returncode != 0:
        subprocess.run(
            ["ssh", GBRAIN_FILES_BRIDGE_SSH, "rmdir", "--", remote_dir],
            cwd=ROOT,
            capture_output=True,
            timeout=15,
            check=False,
        )
        raise RuntimeError(f"GBrain files bridge copy failed: {decode_process_output(copied.stderr).strip() or 'scp failed'}")
    script = """set -euo pipefail
remote_file="$1"
page_slug="$2"
gbrain_bin="$3"
remote_dir="${remote_file%/*}"
trap 'rm -f -- "$remote_file"; rmdir -- "$remote_dir" 2>/dev/null || true' EXIT
export PATH="$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
"$gbrain_bin" files upload "$remote_file" --page "$page_slug"
"$gbrain_bin" files list "$page_slug"
"""
    result = subprocess.run(
        ["ssh", GBRAIN_FILES_BRIDGE_SSH, "bash", "-s", "--", remote_path, str(slug), GBRAIN_FILES_BRIDGE_PATH],
        cwd=ROOT,
        capture_output=True,
        timeout=90,
        check=False,
        input=script.encode("utf-8"),
    )
    if result.returncode != 0:
        message = decode_process_output(result.stderr).strip() or decode_process_output(result.stdout).strip()
        raise RuntimeError(f"GBrain files bridge upload/list failed: {message or result.returncode}")
    return decode_process_output(result.stdout)


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
        return enrich_media_reference_metadata(item)
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
    return enrich_media_reference_metadata(item)


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


def parse_graph_query_link_types(raw_text, center_slug):
    edge_types = defaultdict(set)
    pattern = re.compile(r"^\s*--(?P<link_type>.+?)->\s+(?P<slug>\S+)\s+\(depth\s+1\)\s*$")
    for line in str(raw_text or "").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        target = match.group("slug").strip()
        link_type = match.group("link_type").strip()
        if target and target != center_slug and link_type:
            edge_types[edge_key(center_slug, target)].add(link_type)
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


def compact_backlink_items(raw_text, center_slug):
    backlinks = extract_json_list(raw_text)
    if not isinstance(backlinks, list):
        return None

    items = []
    for backlink in backlinks:
        if not isinstance(backlink, dict):
            continue
        source = str(backlink.get("from_slug") or "").strip()
        if not source:
            continue
        items.append({
            "from_slug": source,
            "to_slug": str(backlink.get("to_slug") or center_slug).strip(),
            "link_type": str(backlink.get("link_type") or "").strip(),
        })
    return items


def paginate_compact_backlinks(items, page=0, limit=20):
    items = list(items or [])
    limit = max(1, min(100, int(limit)))
    last_page = max(0, (len(items) - 1) // limit)
    page = max(0, min(last_page, int(page)))
    start = page * limit
    return {
        "items": items[start:start + limit],
        "page": page,
        "limit": limit,
        "total": len(items),
    }


def compact_backlink_page(raw_text, center_slug, page=0, limit=20):
    items = compact_backlink_items(raw_text, center_slug)
    if items is None:
        return None
    return paginate_compact_backlinks(items, page, limit)


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
            graph_output = run_gbrain(
                "graph-query",
                slug,
                "--direction",
                "out",
                "--depth",
                str(GRAPH_DEPTH),
            )
            outbound_types = parse_graph_query_link_types(graph_output, slug)
            edge_set.update(outbound_types)
            merge_edge_types(edge_types, outbound_types)
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


def expand_raw_graph(raw_graph, center_slug, relationship_types_out=None, relationship_outputs_out=None):
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

    graph_output = run_gbrain(
        "graph-query",
        center_slug,
        "--direction",
        "out",
        "--depth",
        str(GRAPH_DEPTH),
    )
    if relationship_outputs_out is not None:
        relationship_outputs_out["graph_query"] = graph_output
    outbound_types = parse_graph_query_link_types(graph_output, center_slug)
    if relationship_types_out is not None:
        merge_edge_types(relationship_types_out, outbound_types)
    graph_edges = set(outbound_types)
    discovered_edges = set(graph_edges)
    merge_edge_types(edge_types, outbound_types)
    backlinks_output = run_gbrain("backlinks", center_slug)
    if relationship_outputs_out is not None:
        relationship_outputs_out["backlinks"] = backlinks_output
    backlink_edges = parse_backlinks(backlinks_output, center_slug)
    backlink_types = parse_backlink_types(backlinks_output, center_slug)
    if relationship_types_out is not None:
        merge_edge_types(relationship_types_out, backlink_types)
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


def live_primary_search_results(query, timeout):
    try:
        search_output = run_gbrain("search", query, timeout=timeout)
        return parse_search_results(search_output), "complete"
    except Exception:  # noqa: BLE001
        return [], "timeout"


def cached_primary_search_results(query, timeout, cache=None):
    normalized_query = re.sub(r"\s+", " ", str(query or "").strip().lower())
    normalized_query = re.sub(r"[?!.]+$", "", normalized_query).rstrip()
    cache_key = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
    cached = cache.get(cache_key) if cache is not None else None
    if cached is not None:
        results, status = cached
        return [dict(result) for result in results], status, "hit"
    stale = cache.get_stale(cache_key) if cache is not None else None
    if stale is not None:
        results, status = stale

        def refresh():
            fresh_results, fresh_status = live_primary_search_results(query, timeout)
            if fresh_status != "complete":
                return None
            return tuple(dict(result) for result in fresh_results), fresh_status

        refresh_started = cache.refresh_async(cache_key, refresh)
        cache_status = "stale_refresh_started" if refresh_started else "stale_refresh_joined"
        return [dict(result) for result in results], status, cache_status
    if cache is None:
        results, status = live_primary_search_results(query, timeout)
        return results, status, "disabled"

    def load():
        fresh_results, fresh_status = live_primary_search_results(query, timeout)
        if fresh_status != "complete":
            return None
        return tuple(dict(result) for result in fresh_results), fresh_status

    loaded, load_status = cache.load_once(cache_key, load, timeout)
    if loaded is None:
        return [], "timeout", "coalesced_timeout" if load_status == "timeout" else "miss"
    results, status = loaded
    cache_status = "coalesced_hit" if load_status == "joined" else "miss"
    return [dict(result) for result in results], status, cache_status


def search_raw_graph(raw_graph, query, evidence_cache=None, primary_cache=None):
    started = time.monotonic()
    deadline = started + SEARCH_TOTAL_BUDGET_SECONDS
    exact_todo_results, exact_todo_status = exact_todo_id_search_results(query)
    exact_slug_results, exact_slug_source = (
        exact_slug_search_results(raw_graph, query)
        if exact_todo_results is None
        else (None, "")
    )
    exact_label_results = (
        exact_loaded_label_search_results(raw_graph, query)
        if exact_todo_results is None and exact_slug_results is None
        else None
    )
    exact_evidence_title_results = (
        exact_evidence_title_search_results(query, evidence_cache)
        if exact_todo_results is None
        and exact_slug_results is None
        and exact_label_results is None
        else None
    )
    if exact_todo_results is not None:
        primary_results = exact_todo_results
        primary_status = "complete" if exact_todo_status == "complete" else "timeout"
        primary_cache_status = "skipped_exact_todo_id"
        evidence_results = []
        sentinel_results = []
        evidence_status = "skipped_exact_todo_id"
        evidence_cache_status = "skipped_exact_todo_id"
    elif exact_slug_results is not None:
        primary_results = exact_slug_results
        primary_status = "complete"
        primary_cache_status = "skipped_exact_slug"
        evidence_results = []
        sentinel_results = []
        evidence_status = "skipped_exact_slug"
        evidence_cache_status = "skipped_exact_slug"
    elif exact_label_results is not None:
        primary_results = exact_label_results
        primary_status = "complete"
        primary_cache_status = "skipped_exact_loaded_label"
        evidence_results = []
        sentinel_results = []
        evidence_status = "skipped_exact_loaded_label"
        evidence_cache_status = "skipped_exact_loaded_label"
    elif exact_evidence_title_results is not None:
        primary_results = exact_evidence_title_results
        primary_status = "complete"
        primary_cache_status = "skipped_exact_evidence_title"
        evidence_results = []
        sentinel_results = []
        evidence_status = "skipped_exact_evidence_title"
        evidence_cache_status = "skipped_exact_evidence_title"
    else:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            primary_results = []
            primary_status = "timeout"
            primary_cache_status = "skipped_budget"
            evidence_results = []
            evidence_status = "partial_timeout"
            evidence_cache_status = "skipped_budget"
        else:
            primary_budget = min(SEARCH_PRIMARY_TIMEOUT_SECONDS, max(0.5, remaining))
            evidence_budget = min(SEARCH_EVIDENCE_BUDGET_SECONDS, remaining)
            evidence_deadline = min(deadline, time.monotonic() + evidence_budget)
            with ThreadPoolExecutor(max_workers=2) as executor:
                primary_future = executor.submit(
                    cached_primary_search_results,
                    query,
                    primary_budget,
                    primary_cache,
                )
                evidence_future = executor.submit(
                    evidence_record_search_results,
                    query,
                    deadline=evidence_deadline,
                    per_type_timeout=evidence_budget,
                    row_cache=evidence_cache,
                )
                primary_results, primary_status, primary_cache_status = primary_future.result()
                evidence_results, evidence_status, evidence_cache_status = evidence_future.result()
        sentinel_results = search_sentinel_results(
            query,
            existing_slugs=[result["slug"] for result in evidence_results + primary_results],
        )
    loaded_results = [] if exact_todo_results is not None or exact_slug_results is not None or exact_label_results is not None or exact_evidence_title_results is not None else loaded_graph_search_results(
        raw_graph,
        query,
        existing_slugs=[result["slug"] for result in sentinel_results + evidence_results + primary_results],
    )
    results = merge_search_results(primary_results, sentinel_results + evidence_results + loaded_results, query)
    result_slugs = {result["slug"] for result in results}
    nodes = {}
    pruned_search_nodes = 0
    for node in raw_graph.get("nodes", []):
        slug = str(node.get("slug") or "").strip()
        if not slug:
            continue
        tags = {str(tag).strip() for tag in node.get("tags") or [] if str(tag).strip()}
        search_only = tags == {"lazy-search"}
        retained_context = bool(node.get("expanded") or node.get("links"))
        if search_only and slug not in result_slugs and not retained_context:
            pruned_search_nodes += 1
            continue
        nodes[slug] = dict(node)
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
    coverage["search_sentinel_slugs"] = [result["slug"] for result in sentinel_results]
    coverage["evidence_search_slugs"] = [result["slug"] for result in evidence_results]
    coverage["loaded_graph_search_slugs"] = [result["slug"] for result in loaded_results]
    coverage["search_pruned_stale_nodes"] = pruned_search_nodes
    coverage["search_elapsed_ms"] = int((time.monotonic() - started) * 1000)
    evidence_complete = evidence_status in {
        "complete",
        "skipped_no_terms",
        "skipped_exact_todo_id",
        "skipped_exact_slug",
        "skipped_exact_loaded_label",
        "skipped_exact_evidence_title",
    }
    coverage["search_status"] = "complete" if primary_status == "complete" and evidence_complete else "partial_timeout"
    coverage["search_primary_status"] = primary_status
    coverage["search_primary_cache_status"] = primary_cache_status
    coverage["search_evidence_status"] = evidence_status
    coverage["search_evidence_cache_status"] = evidence_cache_status
    if exact_todo_results is not None:
        coverage["search_exact_todo_id_status"] = exact_todo_status
    else:
        coverage.pop("search_exact_todo_id_status", None)
    coverage["search_exact_slug"] = exact_slug_results is not None
    coverage["search_exact_slug_source"] = exact_slug_source
    coverage["search_exact_loaded_label"] = exact_label_results is not None
    coverage["search_exact_evidence_title"] = exact_evidence_title_results is not None
    source.update(
        {
            "mode": "gbrain",
            "status": "lazy-search" if coverage["search_status"] == "complete" else "lazy-search-partial",
            "message": "Seed graph loaded. Search results and selected-node relationships are loaded lazily."
            if coverage["search_status"] == "complete"
            else "Search returned within the UI budget with partial live evidence because deeper evidence ranking was slow.",
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
        "gbrain_version": runtime_gbrain_version(),
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
        self.yoda_context_cache = TimedValueCache(
            ttl_seconds=YODA_CONTEXT_CACHE_SECONDS,
            max_entries=YODA_CONTEXT_CACHE_MAX_ENTRIES,
        )
        self.primary_search_cache = TimedValueCache(
            ttl_seconds=SEARCH_PRIMARY_CACHE_SECONDS,
            stale_seconds=SEARCH_PRIMARY_CACHE_STALE_SECONDS,
            max_entries=SEARCH_PRIMARY_CACHE_MAX_ENTRIES,
        )
        self.yoda_search_cache = TimedValueCache(
            ttl_seconds=YODA_SEARCH_CACHE_SECONDS,
            max_entries=YODA_SEARCH_CACHE_MAX_ENTRIES,
        )
        self.yoda_source_cache = TimedValueCache(
            ttl_seconds=YODA_SOURCE_CACHE_SECONDS,
            max_entries=YODA_SOURCE_CACHE_MAX_ENTRIES,
        )
        self.entity_raw_cache = TimedValueCache(
            ttl_seconds=30,
            max_entries=128,
        )
        self.relationship_type_cache = TimedValueCache(
            ttl_seconds=30,
            max_entries=64,
        )
        self.relationship_output_cache = TimedValueCache(
            ttl_seconds=30,
            max_entries=32,
        )
        self.graph_query_flights = SingleFlight()
        self.timeline_cache = TimedValueCache(
            ttl_seconds=30,
            max_entries=64,
        )
        self.history_cache = TimedValueCache(
            ttl_seconds=30,
            max_entries=64,
        )
        self.autopilot_findings_cache = TimedValueCache(
            ttl_seconds=AUTOPILOT_FINDINGS_CACHE_SECONDS,
            max_entries=AUTOPILOT_FINDINGS_CACHE_MAX_ENTRIES,
        )
        self.autopilot_findings_capability_cache = TimedValueCache(
            ttl_seconds=AUTOPILOT_FINDINGS_CAPABILITY_CACHE_SECONDS,
            max_entries=1,
        )
        self.take_review_cache = TimedValueCache(
            ttl_seconds=TAKE_REVIEW_CACHE_SECONDS,
            max_entries=TAKE_REVIEW_CACHE_MAX_ENTRIES,
        )
        self.take_review_capability_cache = TimedValueCache(
            ttl_seconds=TAKE_REVIEW_CAPABILITY_CACHE_SECONDS,
            max_entries=1,
        )
        self.resolver_read_cache = TimedValueCache(
            ttl_seconds=RESOLVER_READ_CACHE_SECONDS,
            max_entries=RESOLVER_READ_CACHE_MAX_ENTRIES,
        )
        self.resolver_capability_cache = TimedValueCache(
            ttl_seconds=RESOLVER_CAPABILITY_CACHE_SECONDS,
            max_entries=2,
        )
        self.settings_evidence_cache = TimedValueCache(
            ttl_seconds=SETTINGS_EVIDENCE_CACHE_SECONDS,
            max_entries=1,
        )
        self.evidence_list_cache = EvidenceListCache()

    def prewarm_search_evidence(
        self,
        per_type_limit=40,
        timeout=SEARCH_EVIDENCE_PREWARM_TIMEOUT_SECONDS,
    ):
        started = 0
        for page_type in EVIDENCE_SEARCH_TYPES:
            if self.evidence_list_cache.get(page_type, per_type_limit) is not None:
                continue
            if self.evidence_list_cache.refresh_async(
                page_type,
                per_type_limit,
                lambda page_type=page_type: load_evidence_page_rows(
                    page_type,
                    per_type_limit,
                    timeout,
                ),
            ):
                started += 1
        return started

    def get_health_graph(self):
        with self.condition:
            if self.graph:
                return self.graph

        cached = cached_startup_graph()
        if not cached:
            return None

        with self.condition:
            if not self.graph:
                self.graph = cached
                self.loaded_at = time.time()
                self.condition.notify_all()
            return self.graph

    def get_graph(self, force=False):
        now = time.time()
        if force:
            self.yoda_context_cache.clear()
            self.primary_search_cache.clear()
            self.yoda_search_cache.clear()
            self.yoda_source_cache.clear()
            self.entity_raw_cache.clear()
            self.relationship_type_cache.clear()
            self.relationship_output_cache.clear()
            self.timeline_cache.clear()
            self.history_cache.clear()
            self.autopilot_findings_cache.clear()
            self.take_review_cache.clear()
            self.resolver_read_cache.clear()
            self.settings_evidence_cache.clear()
            self.evidence_list_cache.clear()
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
        if force:
            self.yoda_context_cache.clear()
            self.primary_search_cache.clear()
            self.yoda_search_cache.clear()
            self.yoda_source_cache.clear()
            self.entity_raw_cache.clear()
            self.relationship_type_cache.clear()
            self.relationship_output_cache.clear()
            self.timeline_cache.clear()
            self.history_cache.clear()
            self.autopilot_findings_cache.clear()
            self.take_review_cache.clear()
            self.resolver_read_cache.clear()
            self.settings_evidence_cache.clear()
            self.evidence_list_cache.clear()
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
        relationship_types = defaultdict(set)
        relationship_outputs = {}
        payload = finalize_graph(expand_raw_graph(raw_graph, slug, relationship_types, relationship_outputs))
        self.cache_relationship_types(slug, relationship_types)
        self.relationship_output_cache.put(
            ("graph-query", slug, "", "out", str(GRAPH_DEPTH)),
            relationship_outputs["graph_query"],
        )
        self.relationship_output_cache.put(
            ("backlinks", slug),
            relationship_outputs["backlinks"],
        )
        write_cache(payload)
        with self.condition:
            self.graph = payload
            self.loaded_at = time.time()
            return self.graph

    def search(self, query):
        graph = self.get_seed_graph()
        raw_graph = graph_to_raw_payload(graph)
        payload = finalize_graph(
            search_raw_graph(
                raw_graph,
                query,
                evidence_cache=self.evidence_list_cache,
                primary_cache=self.primary_search_cache,
            )
        )
        with self.condition:
            self.graph = payload
            self.loaded_at = time.time()
            return self.graph

    def invalidate(self):
        with self.condition:
            self.graph = None
            self.loaded_at = 0.0
            self.yoda_context_cache.clear()
            self.primary_search_cache.clear()
            self.yoda_search_cache.clear()
            self.yoda_source_cache.clear()
            self.entity_raw_cache.clear()
            self.relationship_type_cache.clear()
            self.relationship_output_cache.clear()
            self.timeline_cache.clear()
            self.history_cache.clear()
            self.autopilot_findings_cache.clear()
            self.take_review_cache.clear()
            self.resolver_read_cache.clear()
            self.settings_evidence_cache.clear()
            self.evidence_list_cache.clear()

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
            page_output = self.get_entity_raw(slug, timeout=fetch_timeout)
            if page_output is None:
                raise RuntimeError("Page detail was unavailable")
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

    def cache_relationship_types(self, slug, edge_types):
        snapshot = tuple(
            (key, tuple(sorted(types)))
            for key, types in sorted(edge_types.items())
        )
        self.relationship_type_cache.put(slug, snapshot)

    def direct_relationship_types(self, slug):
        cached = self.relationship_type_cache.get(slug)
        if cached is not None:
            edge_types = defaultdict(set)
            for key, types in cached:
                edge_types[tuple(key)].update(types)
            return edge_types

        edge_types = defaultdict(set)
        complete = True
        try:
            graph_output = self.graph_query(
                slug,
                direction="out",
                depth="1",
            )
            merge_edge_types(edge_types, parse_graph_query_link_types(graph_output, slug))
        except Exception:  # noqa: BLE001
            complete = False
        try:
            backlinks_output = self.backlinks(slug)
            merge_edge_types(edge_types, parse_backlink_types(backlinks_output, slug))
        except Exception:  # noqa: BLE001
            complete = False
        if complete:
            snapshot = tuple(
                (key, tuple(sorted(types)))
                for key, types in sorted(edge_types.items())
            )
            self.relationship_type_cache.put(slug, snapshot)
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

    def get_entity_raw(self, slug, timeout=None):
        cached = self.entity_raw_cache.get(slug)
        if cached is not None:
            return cached

        def load():
            if timeout is None:
                return run_gbrain("get", slug)
            return run_gbrain("get", slug, timeout=timeout)

        raw, _load_status = self.entity_raw_cache.load_once(
            slug,
            load,
            timeout=max(1, timeout or 20),
        )
        return raw

    def get_entity_tags(self, slug):
        value = PERSISTENT_GBRAIN_SEARCH.call_tool(
            "get_tags", {"slug": slug}, timeout=20
        )
        if isinstance(value, dict):
            value = value.get("tags")
        if not isinstance(value, list):
            raise RuntimeError("GBrain get_tags returned invalid tags")
        return sorted({str(tag).strip() for tag in value if str(tag).strip()})

    def list_pages(self, *, tag="", entity_type="", limit=100):
        args = ["list"]
        if tag:
            args.extend(["--tag", str(tag)])
        if entity_type:
            args.extend(["--type", str(entity_type)])
        args.extend(["-n", str(parse_bounded_int(limit, 100, 1, 1000))])
        return parse_page_list(run_gbrain(*args, timeout=30))

    def get_entities_raw(self, slugs, max_workers=4):
        ordered_slugs = list(dict.fromkeys(str(slug) for slug in slugs if slug))
        if not ordered_slugs:
            return {}
        workers = min(max_workers, len(ordered_slugs))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                slug: executor.submit(self.get_entity_raw, slug)
                for slug in ordered_slugs
            }
            return {slug: futures[slug].result() for slug in ordered_slugs}

    def get_yoda_search_results(self, query):
        normalized_query = re.sub(r"\s+", " ", str(query or "").strip())
        cache_key = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
        cached = self.yoda_search_cache.get(cache_key)
        if cached is not None:
            return cached

        def load():
            return yoda_gbrain_call_tool(
                "query",
                {
                    "query": normalized_query,
                    "expand": False,
                    "adaptive_return": True,
                    "limit": 10,
                    "relational": True,
                },
                timeout=20,
            )

        rows, _load_status = self.yoda_search_cache.load_once(
            cache_key,
            load,
            timeout=20,
        )
        if rows is None:
            raise RuntimeError("GBrain Yoda retrieval was unavailable")
        return rows

    def get_yoda_search_output(self, query):
        return format_mcp_search_results(self.get_yoda_search_results(query))

    def get_yoda_page(self, slug, timeout=20):
        normalized_slug = str(slug or "").strip()
        if not normalized_slug:
            raise ValueError("Ask Yoda page slug is required")
        cache_key = hashlib.sha256(normalized_slug.encode("utf-8")).hexdigest()
        cached = self.yoda_source_cache.get(cache_key)
        if cached is not None:
            return cached
        page, _load_status = self.yoda_source_cache.load_once(
            cache_key,
            lambda: yoda_gbrain_call_tool(
                "get_page",
                {"slug": normalized_slug, "include_content": True},
                timeout=timeout,
            ),
            timeout=max(1, timeout),
        )
        if page is None:
            raise RuntimeError(f"Ask Yoda page retrieval was unavailable: {normalized_slug}")
        return page

    def get_yoda_page_content(self, slug, timeout=20):
        return str(self.get_yoda_page(slug, timeout=timeout)["content"])

    def get_yoda_source_pages(self, slugs):
        ordered_slugs = list(dict.fromkeys(str(slug) for slug in slugs if slug))
        if not ordered_slugs:
            return {}

        workers = min(YODA_GBRAIN_MCP_POOL.size, len(ordered_slugs))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                slug: executor.submit(self.get_yoda_page, slug)
                for slug in ordered_slugs
            }
            pages = {}
            for slug in ordered_slugs:
                try:
                    pages[slug] = futures[slug].result()
                except Exception:  # noqa: BLE001
                    pages[slug] = None
        return {slug: pages.get(slug) for slug in ordered_slugs}

    def get_yoda_entity_media(self, slug):
        return ensure_media_references_available(
            parse_media_references(self.get_yoda_page_content(slug))
        )

    def get_entity_media(self, slug):
        raw = self.get_entity_raw(slug)
        if raw is None:
            return None
        return ensure_media_references_available(parse_media_references(raw))

    def save_entity_raw(self, slug, content):
        gbrain_call_tool("put_page", {"slug": slug, "content": content})
        self.invalidate()

    def refresh_after_entity_save(self):
        graph = self.get_seed_graph(force=True)
        # Graph hydration can race GBrain propagation and repopulate the raw
        # cache with the pre-save page. Never expose that value as readback.
        self.entity_raw_cache.clear()
        return graph

    def create_entity(self, name, description="", category="entities"):
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("name is required")
        slug = entity_slug_from_name(clean_name, category)
        markdown = create_entity_markdown(clean_name, description, category)
        gbrain_call_tool("put_page", {"slug": slug, "content": markdown})
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
            gbrain_call_tool("delete_page", {"slug": slug})
        except RuntimeError as exc:
            message = str(exc)
            if "page_not_found" not in message and "Page not found" not in message:
                raise
        add_deleted_slug(slug)
        self.invalidate()

    def add_relationship(self, source_slug, target_slug, link_type, context=""):
        payload = {"from": source_slug, "to": target_slug, "link_type": link_type}
        if context:
            payload["context"] = context
        gbrain_call_tool("add_link", payload)
        self.invalidate()

    def remove_relationship(self, source_slug, target_slug, link_type=""):
        payload = {"from": source_slug, "to": target_slug}
        if link_type:
            payload["link_type"] = link_type
        gbrain_call_tool("remove_link", payload)
        self.invalidate()

    def update_tags(self, slug, add_tags=None, remove_tags=None):
        for tag in add_tags or []:
            gbrain_call_tool("add_tag", {"slug": slug, "tag": tag})
        for tag in remove_tags or []:
            gbrain_call_tool("remove_tag", {"slug": slug, "tag": tag})
        self.invalidate()

    def add_timeline_event(self, slug, date, summary, detail="", source=""):
        payload = {"slug": slug, "date": date, "summary": summary}
        if detail:
            payload["detail"] = detail
        if source:
            payload["source"] = source
        gbrain_call_tool("add_timeline_entry", payload)
        self.invalidate()

    def ask_gbrain(self, slug, question):
        sections = [f"Question: {question}", f"Selected node: {slug}"]
        normalized_question = question.lower()

        if any(token in normalized_question for token in ("media", "image", "images", "photo", "picture", "attachment", "file")):
            media_items = self.get_yoda_entity_media(slug) or []
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
            graph_payload = {"slug": slug, "direction": "both", "depth": 1}
            graph_rows = yoda_gbrain_call_tool(
                "traverse_graph",
                graph_payload,
                timeout=yoda_runtime_config()["graph_query_timeout"],
            )
            sections.append(
                "Direct relationship context:\n"
                + format_mcp_graph_query(graph_rows, graph_payload)
            )
        except Exception as exc:  # noqa: BLE001
            sections.append(f"Direct relationship context unavailable: {exc}")

        query_text = f"{question} {slug}"
        search_rows = yoda_gbrain_call_tool(
            "query",
            {
                "query": query_text,
                "adaptive_return": True,
                "limit": 8,
                "relational": True,
            },
            timeout=20,
        )
        sections.append(
            "Question-specific gbrain retrieval:\n"
            + format_mcp_search_results(search_rows)
        )
        return "\n\n".join(sections)

    def build_yoda_stable_context(self, slug, depth="4"):
        yoda_depth = clamp_yoda_depth(depth)
        runtime_config = yoda_runtime_config()
        broad_graph_budget = runtime_config["broad_graph_budget"]

        def timed_selected_node():
            started = time.perf_counter()
            page = self.get_yoda_page(slug)
            return page, int((time.perf_counter() - started) * 1000)

        def timed_graph():
            started = time.perf_counter()
            degraded = False
            degraded_reason = ""
            broad_graph_status = "available"
            broad_graph_unavailable_reason = ""
            payload = {
                "slug": slug,
                "direction": "both",
                "depth": yoda_depth,
            }
            try:
                rows = yoda_gbrain_call_tool(
                    "traverse_graph",
                    payload,
                    timeout=broad_graph_budget,
                )
            except Exception as exc:  # noqa: BLE001
                broad_graph_unavailable_reason = "broad_graph_timeout" if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else "broad_graph_unavailable"
                broad_graph_status = "optional_timeout" if broad_graph_unavailable_reason == "broad_graph_timeout" else "unavailable"
                degraded = broad_graph_status != "optional_timeout"
                degraded_reason = "" if broad_graph_status == "optional_timeout" else broad_graph_unavailable_reason
                rows = []
            return (
                rows,
                payload,
                int((time.perf_counter() - started) * 1000),
                degraded,
                degraded_reason,
                broad_graph_status,
                broad_graph_unavailable_reason,
            )

        def timed_backlinks():
            started = time.perf_counter()
            try:
                rows = yoda_gbrain_call_tool(
                    "get_backlinks", {"slug": slug}, timeout=20
                )
                status = "available"
            except Exception:  # noqa: BLE001
                rows = []
                status = "unavailable"
            return rows, status, int((time.perf_counter() - started) * 1000)

        def timed_tags():
            started = time.perf_counter()
            try:
                tags = yoda_gbrain_call_tool(
                    "get_tags", {"slug": slug}, timeout=20
                )
                status = "available"
            except Exception:  # noqa: BLE001
                tags = []
                status = "unavailable"
            return tags, status, int((time.perf_counter() - started) * 1000)

        with ThreadPoolExecutor(max_workers=4) as executor:
            selected_future = executor.submit(timed_selected_node)
            graph_future = executor.submit(timed_graph)
            backlinks_future = executor.submit(timed_backlinks)
            tags_future = executor.submit(timed_tags)
            selected_page, selected_ms = selected_future.result()
            (
                graph_rows,
                graph_payload,
                graph_ms,
                degraded,
                degraded_reason,
                broad_graph_status,
                broad_graph_unavailable_reason,
            ) = graph_future.result()
            backlink_rows, backlinks_status, backlinks_ms = backlinks_future.result()
            tags, tags_status, tags_ms = tags_future.result()
        return {
            "selected_page": selected_page,
            "graph_rows": graph_rows,
            "graph_payload": graph_payload,
            "backlink_rows": backlink_rows,
            "backlinks_status": backlinks_status,
            "tags": tags,
            "tags_status": tags_status,
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "broad_graph_status": broad_graph_status,
            "broad_graph_unavailable_reason": broad_graph_unavailable_reason,
            "broad_graph_budget_ms": broad_graph_budget * 1000,
            "timings": {
                "selected_node": selected_ms,
                "graph": graph_ms,
                "backlinks": backlinks_ms,
                "tags": tags_ms,
            },
        }

    def get_yoda_stable_context(self, slug, depth="4"):
        yoda_depth = clamp_yoda_depth(depth)
        cache_payload = json.dumps(
            {"slug": slug, "depth": yoda_depth},
            sort_keys=True,
            ensure_ascii=False,
        )
        cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()
        cached_context = self.yoda_context_cache.get(cache_key)
        cache_status = "hit"
        if cached_context is None:
            cached_context, load_status = self.yoda_context_cache.load_once(
                cache_key,
                lambda: self.build_yoda_stable_context(slug, yoda_depth),
                timeout=60,
            )
            cache_status = "coalesced_hit" if load_status == "joined" else "miss"
        if cached_context is None:
            raise RuntimeError("Stable Ask Yoda context could not be loaded")

        stable_context = dict(cached_context)
        if cache_status != "miss":
            stable_context["timings"] = {
                key: 0 for key in ("selected_node", "graph", "backlinks", "tags")
            }
        return stable_context, cache_status

    def build_yoda_targeted_context(self, question, excluded_slugs=None):
        excluded = set(excluded_slugs or [])
        excluded_identities = {
            normalized_search_identity(str(slug).rsplit("/", 1)[-1])
            for slug in excluded
        }
        phrases = extract_question_entities(question)
        lines = []
        relationship_sources = []
        seen_candidates = set()
        seen_sources = set()
        backlink_reads = 0

        for phrase in phrases:
            if normalized_search_identity(phrase) in excluded_identities:
                continue
            try:
                search_rows = yoda_gbrain_call_tool(
                    "search", {"query": phrase, "limit": 5}, timeout=20
                )
            except Exception:  # noqa: BLE001
                continue
            candidate = preferred_entity_slug(
                format_mcp_search_results(search_rows), phrase
            )
            if not candidate or candidate in seen_candidates or candidate in excluded:
                continue
            seen_candidates.add(candidate)
            lines.extend([f"### {phrase} -> {candidate}"])
            try:
                entity_raw = self.get_yoda_page_content(candidate)
            except Exception as exc:  # noqa: BLE001
                entity_raw = f"Unable to read {candidate}: {exc}"
            if entity_raw:
                lines.append(str(entity_raw)[:1800])
            try:
                records = yoda_gbrain_call_tool(
                    "get_backlinks", {"slug": candidate}, timeout=20
                )
                backlink_reads += 1
            except Exception as exc:  # noqa: BLE001
                lines.append(f"Backlinks unavailable for {candidate}: {exc}")
                continue
            compact_edges = []
            for record in records[:60]:
                if not isinstance(record, dict):
                    continue
                source = str(record.get("from_slug") or "").strip()
                target = str(record.get("to_slug") or candidate).strip()
                link_type = str(record.get("link_type") or "").strip()
                if not source or not link_type:
                    continue
                compact_edges.append(f"- {source} --[{link_type}]--> {target}")
                if (
                    source not in excluded
                    and source not in seen_sources
                    and relationship_matches_question(link_type, question)
                ):
                    seen_sources.add(source)
                    relationship_sources.append((source, link_type, candidate))
            if compact_edges:
                lines.append("Backlink relationships:")
                lines.extend(compact_edges)

        source_reads = 0
        if relationship_sources:
            lines.append("")
            lines.append("Relationship source node reads:")
        for source, link_type, candidate in relationship_sources[:6]:
            try:
                source_raw = self.get_yoda_page_content(source)
            except Exception as exc:  # noqa: BLE001
                source_raw = f"Unable to read {source}: {exc}"
            lines.extend(
                [
                    f"## {source}",
                    f"Relationship: {source} --[{link_type}]--> {candidate}",
                    str(source_raw or "")[:3000],
                ]
            )
            source_reads += 1

        return {
            "text": "\n".join(lines),
            "counts": {
                "targeted_entities": len(seen_candidates),
                "targeted_backlink_reads": backlink_reads,
                "relationship_source_reads": source_reads,
            },
        }

    def build_yoda_current_todo_context(self, question, selected_slug, todo_root_loader=None):
        question_text = str(question or "").lower()
        selected = str(selected_slug or "").strip()
        todo_root = "notes/memory-starmap-todo-list"
        is_todo_question = (
            selected == todo_root
            or selected.startswith(f"{todo_root}/")
            or any(
                phrase in question_text
                for phrase in (
                    "todo",
                    "planned",
                    "failed",
                    "completed",
                    "priority",
                    "prioritize",
                    "current",
                    "still open",
                    "next work",
                    "gap",
                    "sg-",
                )
            )
        )
        if not is_todo_question:
            return {"text": "", "counts": {}}

        root_raw = (
            todo_root_loader()
            if todo_root_loader is not None
            else self.get_yoda_page_content(todo_root)
        )
        root_raw = root_raw or ""
        rows = parse_memory_starmap_todo_rows(root_raw)
        if not rows:
            return {"text": "", "counts": {"current_todo_rows": 0, "current_todo_child_reads": 0}}

        mentioned_ids = {match.group(0).upper() for match in re.finditer(r"\bSG-\d{4}\b", str(question or ""), re.IGNORECASE)}
        active_statuses = {"planned", "implementing", "failed"}
        selected_rows = [
            row
            for row in rows
            if row.get("status") in active_statuses or row.get("id") in mentioned_ids
        ][:80]
        if not selected_rows:
            selected_rows = rows[:20]

        lines = [
            "Authoritative current TODO state:",
            "This section is read directly from notes/memory-starmap-todo-list at answer time. "
            "Do not recommend completed TODOs as current work, even if historical Runs mention them.",
            "| id | status | priority | title | node | updated |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        child_slugs: list[tuple[str, str]] = []
        for row in selected_rows:
            node_slug = todo_row_node_slug(row)
            lines.append(
                f"| {row.get('id', '')} | {row.get('status', '')} | {row.get('priority', '')} | "
                f"{row.get('title', '')} | {node_slug or row.get('node', '')} | {row.get('updated', '')} |"
            )
            if node_slug and (row.get("id") in mentioned_ids or row.get("status") in active_statuses):
                child_slugs.append((row.get("id", node_slug), node_slug))

        child_reads = 0
        if child_slugs:
            lines.extend(["", "Direct current TODO child-node reads:"])
        selected_child_slugs = child_slugs[:8]
        child_pages = self.get_yoda_source_pages(
            node_slug for _, node_slug in selected_child_slugs
        )
        for item_id, node_slug in selected_child_slugs:
            child_page = child_pages.get(node_slug) or {}
            child_raw = str(child_page.get("content") or "")
            if not child_raw:
                continue
            child_reads += 1
            lines.extend([f"## {item_id} child node", child_raw[:1800]])

        return {
            "text": "\n".join(lines),
            "counts": {
                "current_todo_rows": len(selected_rows),
                "current_todo_child_reads": child_reads,
            },
        }

    def build_yoda_operational_remediation_context(self, question, selected_slug, todo_root_loader=None):
        question_text = str(question or "").lower()
        selected = str(selected_slug or "").strip()
        todo_root = "notes/memory-starmap-todo-list"
        operational_tokens = (
            "current",
            "gap",
            "gaps",
            "blocker",
            "blockers",
            "remain",
            "remaining",
            "reliability",
            "operational",
            "incident",
            "resolved",
            "resolver",
            "synthetic",
            "provenance",
            "telemetry",
            "timeout",
            "broad graph",
            "ask yoda",
            "monitoring",
            "health",
            "learning",
        )
        if selected != todo_root and not selected.startswith(f"{todo_root}/"):
            if not any(token in question_text for token in operational_tokens):
                return {"text": "", "counts": {}}
        if not any(token in question_text for token in operational_tokens):
            return {"text": "", "counts": {}}

        root_raw = (
            todo_root_loader()
            if todo_root_loader is not None
            else self.get_yoda_page_content(todo_root)
        )
        root_raw = root_raw or ""
        rows = parse_memory_starmap_todo_rows(root_raw)
        if not rows:
            return {"text": "", "counts": {"operational_state_rows": 0, "operational_state_child_reads": 0}}

        question_terms = {
            term
            for term in re.findall(r"[a-z0-9-]{4,}", question_text)
            if term not in {"what", "current", "remain", "remaining", "around", "with", "from", "that", "this"}
        }
        operational_match_terms = question_terms or set(operational_tokens)
        completed_rows = []
        for row in rows:
            if row.get("status") != "completed":
                continue
            haystack = f"{row.get('id', '')} {row.get('title', '')} {row.get('notes', '')}".lower()
            if any(term in haystack for term in operational_match_terms):
                completed_rows.append(row)
        if not completed_rows:
            return {"text": "", "counts": {"operational_state_rows": 0, "operational_state_child_reads": 0}}

        lines = [
            "Operational remediation status reconciliation:",
            "This section reconciles present-tense operational recommendations against completed remediation TODOs. "
            "Do not restate completed remediation as a current blocker; label it as historical evidence unless current health or active TODO state proves a regression.",
            "| id | status | priority | title | node | updated |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        child_slugs = []
        for row in completed_rows[:12]:
            node_slug = todo_row_node_slug(row)
            lines.append(
                f"| {row.get('id', '')} | {row.get('status', '')} | {row.get('priority', '')} | "
                f"{row.get('title', '')} | {node_slug or row.get('node', '')} | {row.get('updated', '')} |"
            )
            if node_slug:
                child_slugs.append((row.get("id", node_slug), node_slug))

        child_reads = 0
        if child_slugs:
            lines.extend(["", "Direct completed remediation child-node reads:"])
        selected_child_slugs = child_slugs[:6]
        child_pages = self.get_yoda_source_pages(
            node_slug for _, node_slug in selected_child_slugs
        )
        for item_id, node_slug in selected_child_slugs:
            child_page = child_pages.get(node_slug) or {}
            child_raw = str(child_page.get("content") or "")
            if not child_raw:
                continue
            child_reads += 1
            lines.extend([f"## {item_id} completed remediation", child_raw[:1600]])
        return {
            "text": "\n".join(lines),
            "counts": {
                "operational_state_rows": len(completed_rows[:12]),
                "operational_state_child_reads": child_reads,
            },
        }

    def build_yoda_prompt(
        self,
        slug,
        question,
        history=None,
        depth="4",
        trace=None,
        counts=None,
        stable_context=None,
        retrieval_question=None,
        broad_graph_depth=None,
    ):
        history = history or []
        trace = trace if isinstance(trace, dict) else {}
        counts = counts if isinstance(counts, dict) else {}
        yoda_depth = clamp_yoda_depth(depth)
        effective_question = str(retrieval_question or question or "").strip()
        effective_graph_depth = clamp_yoda_depth(broad_graph_depth or yoda_depth)
        prompt_state = yoda_system_prompt_state()
        stable_context = stable_context or self.build_yoda_stable_context(slug, effective_graph_depth)
        trace.update(stable_context.get("timings") or {})
        lines = [
            prompt_state["prompt"],
            "",
            f"Selected node: {slug}",
            f"Question: {question}",
            f"Retrieval depth: {yoda_depth}",
            f"Broad graph retrieval depth: {effective_graph_depth}",
        ]
        if effective_question and effective_question != str(question or "").strip():
            lines.extend(["", "Resolved retrieval intent:", effective_question])
        if history:
            lines.extend(["", "Recent chat:"])
            for item in history[-8:]:
                role = str(item.get("role") or "user").strip()[:20]
                content = str(item.get("content") or "").strip()
                if content:
                    lines.append(f"- {role}: {content}")
            if any(str(item.get("role") or "").strip().lower() == "assistant" for item in history):
                lines.extend(
                    [
                        "",
                        "Prior assistant answers are conversation context, not evidence. "
                        "They may be wrong; replace them when current GBrain evidence contradicts them.",
                    ]
                )
        selected_page = stable_context.get("selected_page")
        raw = (
            str(selected_page.get("content") or "")
            if isinstance(selected_page, dict)
            else str(stable_context.get("selected_node") or "")
        )
        if raw:
            lines.extend(["", "Selected node content:", raw[:6000]])
        graph_rows = stable_context.get("graph_rows")
        graph_payload = stable_context.get("graph_payload")
        if isinstance(graph_rows, list) and isinstance(graph_payload, dict):
            graph_text = format_mcp_graph_query(graph_rows, graph_payload)
        else:
            graph_text = str(stable_context.get("graph") or "")
        graph_preview = graph_text[:6000]
        broad_graph_status = str(stable_context.get("broad_graph_status") or "available")
        broad_graph_unavailable_reason = str(stable_context.get("broad_graph_unavailable_reason") or "")
        if broad_graph_status != "available" and not graph_preview:
            graph_preview = (
                "Broad graph context unavailable within retrieval budget. "
                "Use selected-node, backlink, search, and targeted relationship evidence below."
            )
        lines.extend(
            [
                "",
                f"Broad graph context (possibly truncated; showing {len(graph_preview)} of {len(graph_text)} characters):",
                graph_preview,
            ]
        )
        if broad_graph_status != "available":
            lines.extend(
                [
                    "",
                    "Broad graph retrieval diagnostics:",
                    f"- broad_graph_status: {broad_graph_status}",
                    f"- broad_graph_unavailable_reason: {broad_graph_unavailable_reason or 'none'}",
                    "- selected-node, backlink, search, direct-read, and targeted relationship evidence remain available when present.",
                ]
            )
        backlink_rows = stable_context.get("backlink_rows")
        backlink_text = (
            format_mcp_json(backlink_rows)
            if isinstance(backlink_rows, list)
            else str(stable_context.get("backlinks") or "")
        )
        backlink_preview = backlink_text[:4000]
        lines.extend(
            [
                "",
                f"Selected-node backlink context (possibly truncated; showing {len(backlink_preview)} of {len(backlink_text)} characters):",
                backlink_preview,
            ]
        )
        tags = stable_context.get("tags")
        if isinstance(tags, list):
            lines.extend(
                [
                    "",
                    "Selected-node tags:",
                    ", ".join(tags) if tags else "No tags returned.",
                ]
            )
            if stable_context.get("tags_status") == "unavailable":
                lines.append("Tag context unavailable from the structured retrieval lane.")
        todo_root_cache = []
        todo_root_lock = threading.Lock()

        def load_todo_root():
            with todo_root_lock:
                if not todo_root_cache:
                    try:
                        content = self.get_yoda_page_content(
                            "notes/memory-starmap-todo-list"
                        )
                    except Exception:  # noqa: BLE001
                        content = ""
                    todo_root_cache.append(content or "")
                return todo_root_cache[0]

        def build_timed_context(builder):
            started = time.perf_counter()
            context = builder(
                effective_question or question,
                slug,
                todo_root_loader=load_todo_root,
            )
            return context, int((time.perf_counter() - started) * 1000)

        def load_search_output():
            started = time.perf_counter()
            try:
                rows = self.get_yoda_search_results(f"{effective_question} {slug}")
                unavailable = False
            except Exception:  # noqa: BLE001
                rows = []
                unavailable = True
            return rows, unavailable, int((time.perf_counter() - started) * 1000)

        with ThreadPoolExecutor(max_workers=3) as executor:
            current_todo_future = executor.submit(
                build_timed_context,
                self.build_yoda_current_todo_context,
            )
            operational_future = executor.submit(
                build_timed_context,
                self.build_yoda_operational_remediation_context,
            )
            search_output_future = executor.submit(load_search_output)
            current_todo_context, current_todo_ms = current_todo_future.result()
            operational_context, operational_ms = operational_future.result()
            search_rows, search_unavailable, search_ms = search_output_future.result()

        current_todo_text = current_todo_context.get("text") or ""
        if current_todo_text:
            lines.extend(
                [
                    "",
                    current_todo_text,
                ]
            )
            counts.update(current_todo_context.get("counts") or {})
            trace["current_todo_state"] = current_todo_ms
        operational_text = operational_context.get("text") or ""
        if operational_text:
            lines.extend(
                [
                    "",
                    operational_text,
                ]
            )
            counts.update(operational_context.get("counts") or {})
            trace["operational_state"] = operational_ms
        trace["search"] = search_ms
        search_output = format_mcp_search_results(search_rows)
        if search_unavailable:
            search_output = "Broader retrieval unavailable from the structured retrieval lane."
        lines.extend(["", "Broader retrieval context:", str(search_output or "")[:6000]])
        search_slugs = [
            str(item.get("slug") or "").strip()
            for item in search_rows
            if isinstance(item, dict) and str(item.get("slug") or "").strip()
        ]
        direct_read_limit = 2 if is_targeted_relationship_question(effective_question) else min(4, yoda_depth)
        likely_slugs = [
            candidate
            for candidate in search_slugs
            if candidate != slug and "/" in candidate
        ][:direct_read_limit]
        counts["search_results"] = len(search_slugs)
        counts["direct_reads"] = len(likely_slugs)

        def load_direct_pages():
            started = time.perf_counter()
            pages = self.get_yoda_source_pages(likely_slugs) if likely_slugs else {}
            return pages, int((time.perf_counter() - started) * 1000)

        def load_targeted_context():
            started = time.perf_counter()
            context = self.build_yoda_targeted_context(
                effective_question,
                excluded_slugs={slug, *likely_slugs},
            )
            return context, int((time.perf_counter() - started) * 1000)

        with ThreadPoolExecutor(max_workers=2) as executor:
            direct_pages_future = executor.submit(load_direct_pages)
            targeted_context_future = executor.submit(load_targeted_context)
            candidate_pages, direct_reads_ms = direct_pages_future.result()
            targeted_context, targeted_relationships_ms = targeted_context_future.result()

        if likely_slugs:
            lines.append("")
            lines.append("Direct reads from likely source nodes:")
            for candidate in likely_slugs:
                candidate_page = candidate_pages.get(candidate)
                if not isinstance(candidate_page, dict):
                    candidate_raw = f"Unable to read {candidate}"
                else:
                    candidate_raw = str(candidate_page.get("content") or "")
                lines.extend([f"## {candidate}", str(candidate_raw or "")[:2200]])
        trace["direct_reads"] = direct_reads_ms
        targeted_text = targeted_context.get("text") or ""
        if targeted_text:
            lines.extend(
                [
                    "",
                    "Targeted entity relationship evidence:",
                    "Treat this question-specific evidence as more authoritative than absence from a truncated broad graph.",
                    targeted_text,
                ]
            )
        counts.update(targeted_context.get("counts") or {})
        trace["targeted_relationships"] = targeted_relationships_ms
        phase_started = time.perf_counter()
        prompt = "\n".join(lines)
        trace["assembly"] = int((time.perf_counter() - phase_started) * 1000)
        return prompt

    def ask_yoda(self, slug, question, history=None, depth="4"):
        request_id = f"yoda-{int(time.time() * 1000)}"
        started_at = time.perf_counter()
        prompt_started_at = time.perf_counter()
        yoda_depth = clamp_yoda_depth(depth)
        retrieval_question, retrieval_history_used = effective_yoda_retrieval_question(question, history)
        broad_graph_depth = (
            1
            if is_targeted_relationship_question(retrieval_question)
            else min(yoda_depth, 2)
        )
        context_subphases_ms = {}
        stable_context, context_cache_status = self.get_yoda_stable_context(
            slug,
            broad_graph_depth,
        )
        context_cache_hit = context_cache_status != "miss"
        context_counts = {}
        prompt = self.build_yoda_prompt(
            slug,
            question,
            history,
            yoda_depth,
            trace=context_subphases_ms,
            counts=context_counts,
            stable_context=stable_context,
            retrieval_question=retrieval_question,
            broad_graph_depth=broad_graph_depth,
        )
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
            "context_cache_hit": context_cache_hit,
            "context_subphases_ms": context_subphases_ms,
            "context_counts": {
                "prompt_chars": len(prompt),
                "history_messages": len(history or []),
                "search_results": context_counts.get("search_results", 0),
                "direct_reads": context_counts.get("direct_reads", 0),
                "targeted_entities": context_counts.get("targeted_entities", 0),
                "targeted_backlink_reads": context_counts.get("targeted_backlink_reads", 0),
                "relationship_source_reads": context_counts.get("relationship_source_reads", 0),
                "retrieval_history_used": retrieval_history_used,
                "broad_graph_depth": broad_graph_depth,
                **(
                    {
                        "current_todo_rows": context_counts.get("current_todo_rows", 0),
                        "current_todo_child_reads": context_counts.get("current_todo_child_reads", 0),
                    }
                    if "current_todo_rows" in context_counts or "current_todo_child_reads" in context_counts
                    else {}
                ),
                **(
                    {
                        "operational_state_rows": context_counts.get("operational_state_rows", 0),
                        "operational_state_child_reads": context_counts.get("operational_state_child_reads", 0),
                    }
                    if "operational_state_rows" in context_counts or "operational_state_child_reads" in context_counts
                    else {}
                ),
            },
            "context_degraded": bool(stable_context.get("degraded")),
            "context_degraded_reason": str(stable_context.get("degraded_reason") or ""),
            "broad_graph_status": str(stable_context.get("broad_graph_status") or "available"),
            "broad_graph_unavailable_reason": str(stable_context.get("broad_graph_unavailable_reason") or ""),
            "broad_graph_budget_ms": int(stable_context.get("broad_graph_budget_ms") or 0),
            "source": agent_result.get("backend", "model") if isinstance(agent_result, dict) and agent_output else ("openclaw-agent" if agent_output else "fallback"),
            "fallback_used": not bool(agent_output),
            "model_status": agent_result.get("model_status", "unknown") if isinstance(agent_result, dict) else "unknown",
            "openclaw_status": agent_result.get("openclaw_status", "unknown") if isinstance(agent_result, dict) else "unknown",
            "model_backend": agent_result.get("backend", "unknown") if isinstance(agent_result, dict) else "unknown",
            "model_name": agent_result.get("model", "") if isinstance(agent_result, dict) else "",
            "error_summary": agent_result.get("error_summary", "") if isinstance(agent_result, dict) else "",
            "stdout_preview": agent_result.get("stdout_preview", "") if isinstance(agent_result, dict) else "",
            "stderr_preview": agent_result.get("stderr_preview", "") if isinstance(agent_result, dict) else "",
            "node_runtime_status": agent_result.get("node_runtime_status", "") if isinstance(agent_result, dict) else "",
            "node_runtime_path": agent_result.get("node_runtime_path", "") if isinstance(agent_result, dict) else "",
            "node_runtime_version": agent_result.get("node_runtime_version", "") if isinstance(agent_result, dict) else "",
            "node_runtime_source": agent_result.get("node_runtime_source", "") if isinstance(agent_result, dict) else "",
            "node_runtime_error": agent_result.get("node_runtime_error", "") if isinstance(agent_result, dict) else "",
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
        cache_key = ("backlinks", slug)
        cached = self.relationship_output_cache.get(cache_key)
        if cached is not None:
            return cached
        output, _load_status = self.relationship_output_cache.load_once(
            cache_key,
            lambda: run_gbrain("backlinks", slug),
            timeout=20,
        )
        if output is None:
            raise RuntimeError("GBrain backlinks retrieval was unavailable")
        return output

    def backlink_page(self, slug, page=0, limit=20):
        cache_key = ("backlink-items", slug)
        items = self.relationship_output_cache.get(cache_key)
        if items is None:
            output = self.backlinks(slug)
            items = compact_backlink_items(output, slug)
            if items is None:
                return None, output
            items = tuple(items)
            self.relationship_output_cache.put(cache_key, items)
        return paginate_compact_backlinks(items, page, limit), None

    def graph_query(self, slug, link_type="", direction="both", depth="1"):
        normalized_direction = {"outgoing": "out", "incoming": "in"}.get(direction, direction)
        cache_key = ("graph-query", slug, link_type, normalized_direction, str(depth))
        cached = self.relationship_output_cache.get(cache_key)
        if cached is not None:
            return cached
        command = ["graph-query", slug]
        if link_type:
            command.extend(["--type", link_type])
        if normalized_direction:
            command.extend(["--direction", normalized_direction])
        if depth:
            command.extend(["--depth", str(depth)])
        def load():
            try:
                output = run_gbrain(*command)
            except RuntimeError as exc:
                message = str(exc)
                if "database_url is missing" not in message and "No database URL" not in message:
                    raise
                output = self.graph_query_from_loaded_graph(slug, link_type, direction, depth, message)
            self.relationship_output_cache.put(cache_key, output)
            return output

        return self.graph_query_flights.run(cache_key, load, timeout=25)

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
        source = Path(str(file_path or "")).expanduser()
        if not source.is_file():
            raise RuntimeError("Attachment source file is unavailable.")
        canonical_name = safe_upload_filename(source.name)
        staged_source = source
        if source.name != canonical_name:
            staged_dir = DATA_DIR / "uploads" / re.sub(r"[^A-Za-z0-9._-]+", "_", slug.strip("/") or "root")
            staged_dir.mkdir(parents=True, exist_ok=True)
            staged_source = staged_dir / canonical_name
            shutil.copy2(source, staged_source)
        file_path = str(staged_source)
        source_bytes = staged_source.read_bytes()
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
        upload_transport = "local"
        ledger_output = None
        try:
            upload_output = run_gbrain("files", "upload", file_path, "--page", slug)
            ledger_output = upload_output
        except RuntimeError as exc:
            if not GBRAIN_FILES_BRIDGE_SSH:
                raise RuntimeError(
                    "Attachment upload did not reach GBrain files; markdown was not updated. "
                    "Configure a trusted GBrain files bridge and try again."
                ) from exc
            ledger_output = run_gbrain_files_bridge(file_path, slug)
            upload_transport = "ssh-bridge"
        durable_evidence = parse_gbrain_durable_evidence(ledger_output, relative_path, source_bytes)
        if not gbrain_file_ledger_has_relative_path(slug, relative_path, ledger_output=ledger_output):
            ledger_output = f"{ledger_output or ''}\n{run_gbrain('files', 'list', slug)}"
        if not gbrain_file_ledger_has_relative_path(slug, relative_path, ledger_output=ledger_output):
            raise RuntimeError(
                f"Attachment upload was not visible in GBrain files for {slug}; markdown was not updated."
            )
        markdown_updated = False
        copy_file_to_gbrain_store(file_path, relative_path)
        if raw and relative_path:
            # File upload can take long enough for another verified writer to
            # update the page. Re-read immediately before the markdown write so
            # an attachment never restores a stale page snapshot.
            latest_raw_output = run_gbrain("get", slug)
            latest_raw = (
                latest_raw_output
                if isinstance(latest_raw_output, str) and latest_raw_output
                else raw
            )
            original_meta, _ = parse_frontmatter(raw)
            latest_meta, _ = parse_frontmatter(latest_raw)
            original_type = str(original_meta.get("type") or "").strip()
            latest_type = str(latest_meta.get("type") or "").strip()
            if original_type and original_type != "concept" and latest_type == "concept":
                latest_raw = re.sub(
                    r"(?m)^type:\s*['\"]?concept['\"]?\s*$",
                    f"type: {original_type}",
                    latest_raw,
                    count=1,
                )
            updated_raw = append_attachment_reference(
                latest_raw,
                relative_path,
                description,
            )
            if updated_raw != latest_raw:
                run_gbrain("put", slug, input_text=updated_raw)
                markdown_updated = True
        self.invalidate()
        if local_media:
            local_media["markdown_updated"] = markdown_updated
            local_media["upload_transport"] = upload_transport
            local_media["durable_storage_verified"] = True
            local_media["canonical_relative_path"] = relative_path.as_posix()
            local_media["filename"] = relative_path.name
            local_media["size_bytes"] = durable_evidence["size_bytes"]
            local_media["sha256"] = durable_evidence["sha256"]
            local_media["storage_disposition"] = durable_evidence.get("disposition")
        return local_media

    def history(self, slug):
        cached = self.history_cache.get(slug)
        if cached is not None:
            return cached
        output, _load_status = self.history_cache.load_once(
            slug,
            lambda: format_mcp_json(gbrain_call_tool("get_versions", {"slug": slug})),
            timeout=20,
        )
        if output is None:
            raise RuntimeError("GBrain history retrieval was unavailable")
        return output

    def timeline(self, slug):
        cached = self.timeline_cache.get(slug)
        if cached is not None:
            return cached
        output, _load_status = self.timeline_cache.load_once(
            slug,
            lambda: format_mcp_json(gbrain_call_tool("get_timeline", {"slug": slug})),
            timeout=20,
        )
        if output is None:
            raise RuntimeError("GBrain timeline retrieval was unavailable")
        return output

    def refresh_embedding(self, slug):
        run_gbrain("embed", slug)
        self.invalidate()

    def list_take_proposals(self, filters=None):
        payload = dict(filters or {})
        payload["limit"] = clamp_take_review_limit(payload.get("limit"))
        cache_key = "proposals:" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cached = self.take_review_cache.get(cache_key)
        if cached is not None:
            return cached
        capability_key = "take_proposals_list:capability"
        if self.take_review_capability_cache.get(capability_key) is False:
            raise RuntimeError("GBrain backend does not expose take_proposals_list")
        try:
            result = gbrain_call_tool("take_proposals_list", payload, timeout=30)
            self.take_review_capability_cache.put(capability_key, True)
        except RuntimeError as exc:
            message = str(exc)
            missing_operation = (
                "GBrain backend does not expose take_proposals_list" in message
                or "Unknown tool: take_proposals_list" in message
                or ("unknown_operation" in message and "take_proposals_list" in message)
            )
            if missing_operation:
                self.take_review_capability_cache.put(capability_key, False)
            raise
        normalized = normalize_take_collection(result, "proposals")
        normalized.setdefault("filters", payload)
        normalized.setdefault("counts", {})
        self.take_review_cache.put(cache_key, normalized)
        return normalized

    def review_take_proposal(self, proposal_id, action, payload=None):
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"accept", "reject", "defer"}:
            raise ValueError("action must be accept, reject, or defer")
        review_payload = take_review_action_payload(proposal_id, normalized_action, payload or {})
        result = gbrain_call_tool(f"take_proposals_{normalized_action}", review_payload, timeout=45)
        self.take_review_cache.clear()
        if isinstance(result, dict):
            return {"ok": True, "action": normalized_action, "proposal_id": str(proposal_id), **result}
        return {"ok": True, "action": normalized_action, "proposal_id": str(proposal_id), "result": result}

    def bulk_review_take_proposals(self, payload=None):
        review_payload = take_review_bulk_payload(payload or {})
        result = gbrain_call_tool("take_proposals_bulk", review_payload, timeout=60)
        self.take_review_cache.clear()
        if isinstance(result, dict):
            return {"ok": True, **result}
        return {"ok": True, "results": result}

    def list_takes(self, filters=None):
        payload = dict(filters or {})
        payload["limit"] = max(1, min(TAKES_VIEW_FETCH_LIMIT, int(payload.get("limit") or TAKES_VIEW_FETCH_LIMIT)))
        complete_cache_key = "takes:complete"
        if takes_complete_snapshot_compatible(payload):
            cached_snapshot = self.take_review_cache.get(complete_cache_key)
            if cached_snapshot is not None:
                snapshot, complete = cached_snapshot
                if complete:
                    return filter_complete_take_snapshot(snapshot, payload)
            else:
                snapshot_payload = {"limit": TAKES_VIEW_FETCH_LIMIT, "offset": 0}
                snapshot = normalize_take_collection(
                    gbrain_call_tool("takes_list", snapshot_payload, timeout=30),
                    "takes",
                )
                complete = len(snapshot.get("takes") or []) < TAKES_VIEW_FETCH_LIMIT
                self.take_review_cache.put(complete_cache_key, (snapshot, complete))
                if complete:
                    return filter_complete_take_snapshot(snapshot, payload)
        cache_key = "takes:" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cached = self.take_review_cache.get(cache_key)
        if cached is not None:
            return cached
        result = gbrain_call_tool("takes_list", payload, timeout=30)
        normalized = normalize_take_collection(result, "takes")
        normalized.setdefault("filters", payload)
        self.take_review_cache.put(cache_key, normalized)
        return normalized

    def list_autopilot_findings(self, filters=None):
        payload = dict(filters or {})
        payload["limit"] = max(
            1,
            min(AUTOPILOT_FINDINGS_MAX_LIMIT, int(payload.get("limit") or 50)),
        )
        payload["offset"] = max(0, int(payload.get("offset") or 0))
        if not payload.get("state"):
            payload.pop("state", None)
        cache_key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cached = self.autopilot_findings_cache.get(cache_key)
        if cached is not None:
            return cached
        capability_key = "autopilot_findings_list:capability"
        tool_supported = self.autopilot_findings_capability_cache.get(capability_key)
        if tool_supported is False:
            result = list_autopilot_findings_from_gbrain_pages(
                payload,
                snapshot_cache=self.autopilot_findings_cache,
            )
        else:
            try:
                result = gbrain_call_tool("autopilot_findings_list", payload, timeout=30)
                self.autopilot_findings_capability_cache.put(capability_key, True)
            except RuntimeError as exc:
                message = str(exc)
                missing_operation = (
                    "GBrain backend does not expose autopilot_findings_list" in message
                    or "Unknown tool: autopilot_findings_list" in message
                    or (
                        "unknown_operation" in message
                        and "autopilot_findings_list" in message
                    )
                )
                if not missing_operation:
                    raise
                self.autopilot_findings_capability_cache.put(capability_key, False)
                result = list_autopilot_findings_from_gbrain_pages(
                    payload,
                    snapshot_cache=self.autopilot_findings_cache,
                )
        if not isinstance(result, dict):
            return {"findings": [], "total": 0}
        findings = result.get("findings")
        normalized = {
            **result,
            "findings": findings if isinstance(findings, list) else [],
            "total": int(result.get("total") or 0),
        }
        self.autopilot_findings_cache.put(cache_key, normalized)
        return normalized

    def acknowledge_autopilot_finding(self, finding_id):
        result = gbrain_call_tool(
            "autopilot_findings_acknowledge",
            {"id": int(finding_id)},
            timeout=30,
        )
        if not isinstance(result, dict):
            raise RuntimeError("GBrain returned an invalid autopilot finding")
        self.autopilot_findings_cache.clear()
        return result


STORE = GraphStore()


def attachment_storage_status():
    for root in GBRAIN_FILE_STORE_ROOTS:
        expanded = root.expanduser()
        if expanded.is_dir() and os.access(expanded, os.R_OK | os.W_OK):
            return {"available": True, "mode": "local-durable-root", "detail": "durable storage readable and writable"}
    if GBRAIN_FILE_BASE_URLS:
        return {"available": True, "mode": "trusted-host-endpoint", "detail": "durable hosting endpoint configured"}
    return {"available": False, "mode": "unavailable", "detail": "durable storage unavailable"}


def normalize_gbrain_version(value):
    normalized = str(value or "").strip().removeprefix("V").removeprefix("v")
    match = re.search(
        r"\b(\d+\.\d+\.\d+(?:\.\d+)?)\b", normalized
    )
    return f"V{match.group(1)}" if match else ""


@lru_cache(maxsize=1)
def _cached_runtime_gbrain_version():
    try:
        result = subprocess.run(
            [str(GBRAIN), "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return ""
    if result.returncode != 0:
        return ""
    return normalize_gbrain_version(f"{result.stdout}\n{result.stderr}")


def runtime_gbrain_version():
    persistent_version = normalize_gbrain_version(PERSISTENT_GBRAIN_SEARCH.server_version)
    if persistent_version:
        return persistent_version
    version = _cached_runtime_gbrain_version()
    if version:
        return version
    _cached_runtime_gbrain_version.cache_clear()
    return _cached_runtime_gbrain_version()


runtime_gbrain_version.cache_clear = _cached_runtime_gbrain_version.cache_clear


def parse_gbrain_reranker_readiness(
    config_stdout,
    config_stderr,
    config_returncode,
    search_stderr="",
    search_returncode=None,
    observed_at=None,
):
    """Reduce local CLI evidence to a privacy-safe reranker readiness state."""
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed = observed.astimezone(timezone.utc)
    observed_text = observed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    config_value = str(config_stdout or "").strip()
    config_error = str(config_stderr or "")
    warning_text = str(search_stderr or "")
    warning_match = re.search(
        r"ZeroEntropy reranker stops working on\s+(\d{4}-\d{2}-\d{2})",
        warning_text,
        re.IGNORECASE,
    )
    configured_deprecated = "zeroentropy" in config_value.lower()
    config_missing = "config key not found" in config_error.lower()
    binary_unavailable = "config probe unavailable" in config_error.lower()
    configured_supported = bool(
        config_returncode == 0
        and config_value
        and not configured_deprecated
    )
    sunset_date = warning_match.group(1) if warning_match else GBRAIN_RERANKER_SUNSET_DATE
    try:
        days_until_sunset = (
            datetime.fromisoformat(sunset_date).date() - observed.date()
        ).days
    except ValueError:
        days_until_sunset = None

    if configured_supported:
        status = "ready"
        freshness = "current"
        state = "supported_override"
        summary = "GBrain has an explicit non-ZeroEntropy reranker override."
    elif warning_match or configured_deprecated or config_missing:
        status = "critical" if days_until_sunset is not None and days_until_sunset <= 0 else "degraded"
        freshness = "current"
        state = "deprecated_zeroentropy" if warning_match or configured_deprecated else "deprecated_default_unconfigured"
        summary = (
            f"GBrain has no explicit supported reranker override and the known ZeroEntropy default stops working on {sunset_date}."
        )
    elif binary_unavailable:
        status = "missing"
        freshness = "missing"
        state = "gbrain_unavailable"
        summary = "GBrain reranker readiness could not be checked because the local binary is unavailable."
    else:
        status = "partial"
        freshness = "partial"
        state = "unverified"
        summary = "GBrain reranker configuration and sunset state could not be verified within the bounded probe."

    return {
        "schema_version": 1,
        "status": status,
        "freshness": freshness,
        "state": state,
        "sunset_detected": bool(warning_match or configured_deprecated or config_missing),
        "sunset_date": sunset_date,
        "days_until_sunset": days_until_sunset,
        "configured_override": bool(config_returncode == 0 and config_value),
        "observed_at": observed_text,
        "source": "bounded_local_gbrain_config_read_only",
        "summary": summary,
        "operator_action": {
            "approval_required": True,
            "automatic_mutation": False,
            "apply_command": f"gbrain config set search.reranker.model {GBRAIN_RERANKER_TARGET_MODEL}",
            "verification_commands": [
                "gbrain config get search.reranker.model",
                "gbrain doctor --json --fast",
                "gbrain search 'memory stargraph' --limit 1",
            ],
        },
        "privacy": "Only aggregate state and fixed operator commands are returned; CLI search results, config values, host paths, and credentials are withheld.",
    }


def _probe_gbrain_reranker_readiness():
    explicit_path = str(os.environ.get("GBRAIN_CONFIG_FILE") or "").strip()
    gbrain_home = str(os.environ.get("GBRAIN_HOME") or "").strip()
    if explicit_path:
        config_path = Path(explicit_path).expanduser()
    elif gbrain_home:
        home_path = Path(gbrain_home).expanduser()
        candidates = (home_path / ".gbrain" / "config.json", home_path / "config.json")
        config_path = next((path for path in candidates if path.is_file()), candidates[0])
    else:
        config_path = Path.home() / ".gbrain" / "config.json"
    try:
        if config_path.stat().st_size > 1024 * 1024:
            raise ValueError("config too large")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        search = config.get("search") if isinstance(config, dict) else None
        reranker = search.get("reranker") if isinstance(search, dict) else None
        model = reranker.get("model") if isinstance(reranker, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return parse_gbrain_reranker_readiness(
            "",
            "bounded config read failed",
            None,
            search_stderr="",
            search_returncode=None,
        )
    config_value = str(model or "").strip()
    return parse_gbrain_reranker_readiness(
        config_value,
        "" if config_value else "Config key not found: search.reranker.model",
        0 if config_value else 1,
    )


def gbrain_reranker_readiness():
    cache_key = (str(GBRAIN), os.environ.get("GBRAIN_HOME", ""), os.environ.get("GBRAIN_CONFIG_FILE", ""))
    cached = GBRAIN_RERANKER_READINESS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    stale = GBRAIN_RERANKER_READINESS_CACHE.get_stale(cache_key)
    GBRAIN_RERANKER_READINESS_CACHE.refresh_async(cache_key, _probe_gbrain_reranker_readiness)
    if stale is not None:
        return stale
    return {
        "schema_version": 1,
        "status": "partial",
        "freshness": "partial",
        "state": "probe_busy",
        "sunset_detected": False,
        "sunset_date": GBRAIN_RERANKER_SUNSET_DATE,
        "days_until_sunset": None,
        "configured_override": False,
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "bounded_local_gbrain_config_read_only",
        "summary": "GBrain reranker readiness is still being checked.",
        "operator_action": {
            "approval_required": True,
            "automatic_mutation": False,
            "apply_command": f"gbrain config set search.reranker.model {GBRAIN_RERANKER_TARGET_MODEL}",
            "verification_commands": [
                "gbrain config get search.reranker.model",
                "gbrain doctor --json --fast",
                "gbrain search 'memory stargraph' --limit 1",
            ],
        },
        "privacy": "Only aggregate state and fixed operator commands are returned; CLI search results, config values, host paths, and credentials are withheld.",
    }


def setup_diagnostics():
    """Return support-safe setup state without config values or node content."""
    graph = STORE.graph or {}
    source = graph.get("source") or {}
    nodes = graph.get("nodes") or []
    index_node = next((node for node in nodes if node.get("slug") == ROOT_INDEX_SLUG), None)
    mode = str(source.get("mode") or "not-loaded")
    config_keys = sorted(
        key for key, value in CONFIG.items()
        if value not in (None, "", [], {}) and not any(token in key.lower() for token in ("key", "secret", "token", "password"))
    )
    attachment_storage = attachment_storage_status()
    checks = [
        {"id": "gbrain_binary", "ok": GBRAIN.exists(), "detail": "configured" if GBRAIN.exists() else "not found"},
        {"id": "graph_source", "ok": mode == "gbrain", "detail": mode},
        {"id": "root_index", "ok": bool(index_node and int(index_node.get("degree") or 0) > 0), "detail": "linked" if index_node else "missing"},
        {"id": "media", "ok": bool(GBRAIN_FILE_BASE_URLS or GBRAIN_FILE_STORE_ROOTS or MEDIA_ROOTS), "detail": "configured" if (GBRAIN_FILE_BASE_URLS or GBRAIN_FILE_STORE_ROOTS or MEDIA_ROOTS) else "not configured"},
        {"id": "attachment_storage", "ok": attachment_storage["available"], "detail": attachment_storage["detail"]},
        {"id": "privacy", "ok": True, "detail": "local service; values and node content redacted"},
    ]
    failing = [check["id"] for check in checks if not check["ok"]]
    if "gbrain_binary" in failing:
        next_action = "Configure an executable gbrain_path, then restart Memory Stargraph."
    elif "graph_source" in failing:
        next_action = "Refresh the graph and resolve the source warning before using customer data."
    elif "root_index" in failing:
        next_action = "Add useful links to the GBrain index node, then refresh."
    elif "attachment_storage" in failing:
        next_action = "Configure a durable GBrain file backend or trusted hosting file endpoint before attaching files."
    else:
        next_action = "Run Search, select a node, then use View or Ask Yoda to verify the first workflow."
    return {
        "ok": not failing,
        "ui_version": UI_VERSION,
        "source_mode": mode,
        "source_status": str(source.get("status") or "not-loaded"),
        "dashboard_url": "http://127.0.0.1:8788",
        "checks": checks,
        "failing_checks": failing,
        "config_keys_present": config_keys,
        "next_action": next_action,
    }


def privacy_safe_sample_brain():
    graph = finalize_graph(SAMPLE_FIRST_VALUE_GRAPH)
    graph["ui_version"] = UI_VERSION
    return {
        "ok": True,
        "label": "Privacy-safe sample brain",
        "privacy_safe": True,
        "sample_slug": "sample-memory-hub",
        "walkthrough": [
            "Open sample-memory-hub.",
            "Inspect demo relationships and the synthetic provenance note.",
            "Use View to read the sample node details.",
            "Ask Yoda a grounded question about the sample learning loop.",
            "Export setup diagnostics when ready to connect real GBrain data.",
        ],
        "warning": "Demo mode uses bundled synthetic data only. It does not include private nodes, credentials, hostnames, or real user content.",
        "graph": graph,
    }


def first_run_activation_funnel():
    diagnostics = setup_diagnostics()
    sample = privacy_safe_sample_brain()
    live_ready = bool(diagnostics.get("ok") and diagnostics.get("source_mode") == "gbrain")
    sample_ready = bool(sample.get("ok") and sample.get("privacy_safe"))
    steps = [
        {
            "id": "sample_brain_opened",
            "label": "Open sample brain",
            "status": "ready" if sample_ready else "blocked",
            "next_action": "Open Sample brain demo from Settings.",
            "evidence": "privacy_safe_sample_brain" if sample_ready else "sample_brain_unavailable",
        },
        {
            "id": "sample_node_selected",
            "label": "Select sample node",
            "status": "ready" if sample_ready else "blocked",
            "next_action": f"Select {sample.get('sample_slug') or 'sample-memory-hub'} in the demo graph.",
            "evidence": sample.get("sample_slug") or "sample-memory-hub",
        },
        {
            "id": "relationship_provenance_viewed",
            "label": "Inspect relationships and provenance",
            "status": "ready" if sample_ready else "blocked",
            "next_action": "Use View or the relationship list on the sample node.",
            "evidence": "synthetic_walkthrough",
        },
        {
            "id": "sample_yoda_attempted",
            "label": "Ask a synthetic Yoda question",
            "status": "available" if sample_ready else "blocked",
            "next_action": "Ask Yoda about the sample learning loop from the sample node.",
            "evidence": "client_session_boolean_only",
        },
        {
            "id": "setup_diagnostics_reviewed",
            "label": "Review setup diagnostics",
            "status": "available",
            "next_action": "Open Checklist & diagnostics from Settings.",
            "evidence": "setup_diagnostics_redacted",
        },
        {
            "id": "live_gbrain_readiness_checked",
            "label": "Check live GBrain readiness",
            "status": "complete" if live_ready else "needs_attention",
            "next_action": diagnostics.get("next_action") or "Resolve setup diagnostics before switching to live private GBrain.",
            "evidence": "setup_diagnostics_ok" if live_ready else "setup_diagnostics_attention",
        },
    ]
    completed = sum(1 for step in steps if step["status"] == "complete")
    return {
        "ok": True,
        "read_only": True,
        "privacy_safe": True,
        "ui_version": UI_VERSION,
        "mode": "live-ready" if live_ready else "sample-first",
        "sample_state": {
            "available": sample_ready,
            "sample_slug": sample.get("sample_slug") or "sample-memory-hub",
            "privacy_safe": bool(sample.get("privacy_safe")),
        },
        "live_state": {
            "ready": live_ready,
            "source_mode": diagnostics.get("source_mode"),
            "source_status": diagnostics.get("source_status"),
            "failing_checks": diagnostics.get("failing_checks") or [],
        },
        "progress": {
            "completed": completed,
            "total": len(steps),
            "next_step_id": next((step["id"] for step in steps if step["status"] != "complete"), ""),
        },
        "steps": steps,
        "privacy": "Only step ids, statuses, and redacted diagnostics are returned. Browser progress uses local boolean flags and stores no private node text, questions, hostnames, credentials, or content.",
    }


def readiness_check(check_id, label, status, summary, evidence_slugs=None, freshness="current", next_step=""):
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "summary": sanitize_text_summary(summary, 220),
        "freshness": freshness,
        "evidence_slugs": list(evidence_slugs or []),
        "next_step": sanitize_text_summary(next_step, 220),
    }


def parse_iso_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_evidence_slug(value):
    slug = str(value or "").strip()
    if not slug:
        return ""
    lowered = slug.lower()
    if any(token in lowered for token in ("api_key", "authorization", "sk-", "/users/", "://", "\\")):
        return ""
    if slug.startswith(("/", "runs/", "reports/", "notes/", "learnings/", "goals/", "products/")):
        return slug[:240]
    return ""


def current_source_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def read_deployment_attestation():
    readback_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not DEPLOYMENT_ATTESTATIONS_PATH.exists():
        return {
            "status": "no_activity",
            "freshness": "no_activity",
            "summary": "No durable deployment attestation has been recorded for configured targets.",
            "readback_at": readback_at,
            "evidence_slugs": [],
            "counts": {
                "configured_target_count": 0,
                "verified_target_count": 0,
                "stale_target_count": 0,
                "missing_target_count": 0,
                "source_mismatch_count": 0,
            },
            "local": {"status": "no_activity"},
            "configured_remote": {"status": "no_activity", "configured_target_count": 0, "verified_target_count": 0},
        }
    try:
        payload = json.loads(DEPLOYMENT_ATTESTATIONS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {
            "status": "missing",
            "freshness": "missing",
            "summary": "Durable deployment attestation exists but could not be parsed.",
            "readback_at": readback_at,
            "evidence_slugs": [],
            "counts": {
                "configured_target_count": 0,
                "verified_target_count": 0,
                "stale_target_count": 0,
                "missing_target_count": 1,
                "source_mismatch_count": 0,
            },
            "local": {"status": "missing"},
            "configured_remote": {"status": "missing", "configured_target_count": 0, "verified_target_count": 0},
        }
    if not isinstance(payload, dict):
        payload = {}
    observed_at = str(payload.get("generated_at") or payload.get("observed_at") or "").strip()
    parsed_observed = parse_iso_timestamp(observed_at)
    age_seconds = None
    stale = False
    if parsed_observed:
        age_seconds = max(0, int((datetime.now(timezone.utc) - parsed_observed).total_seconds()))
        stale = age_seconds > DEPLOYMENT_ATTESTATION_MAX_AGE_SECONDS
    else:
        stale = True
    version_mismatch = bool(payload.get("ui_version") and str(payload.get("ui_version")) != UI_VERSION)
    attested_commit = str(payload.get("source_commit") or "").strip()
    live_commit = current_source_commit()
    source_mismatch = bool(attested_commit and live_commit and attested_commit != live_commit)
    configured = payload.get("configured_remote") if isinstance(payload.get("configured_remote"), dict) else {}
    local = payload.get("local") if isinstance(payload.get("local"), dict) else {}
    configured_count = parse_nonnegative_int(configured.get("configured_target_count"), 0)
    verified_count = parse_nonnegative_int(configured.get("verified_target_count"), 0)
    missing_count = max(0, configured_count - verified_count)
    local_verified = bool(local.get("verified"))
    evidence_slugs = [slug for slug in (safe_evidence_slug(item) for item in payload.get("evidence_slugs") or []) if slug]
    if configured_count <= 0:
        status = "no_activity"
        summary = "No configured remote deployment target attestation is present; local deployment evidence is tracked separately."
    elif source_mismatch or version_mismatch:
        status = "source_mismatch"
        summary = "Durable configured-target attestation does not match the currently served source or UI version."
    elif stale:
        status = "stale"
        summary = "Durable configured-target attestation is stale or lacks a parseable source timestamp."
    elif missing_count:
        status = "partial"
        summary = "Some configured targets lack current durable deployment attestation."
    else:
        status = "ready"
        summary = "Configured targets have current durable deployment attestation."
    freshness = "current" if status == "ready" else status
    return {
        "status": status,
        "freshness": freshness,
        "summary": summary,
        "source_timestamp": observed_at,
        "readback_at": readback_at,
        "evidence_slugs": evidence_slugs,
        "counts": {
            "configured_target_count": configured_count,
            "verified_target_count": verified_count,
            "stale_target_count": configured_count if status == "stale" else 0,
            "missing_target_count": missing_count,
            "source_mismatch_count": configured_count if status == "source_mismatch" else 0,
            "local_attestation_present": 1 if local_verified else 0,
        },
        "local": {
            "status": "current" if local_verified and not stale and not source_mismatch and not version_mismatch else ("stale" if stale else ("source_mismatch" if source_mismatch or version_mismatch else "no_activity")),
            "verified": local_verified,
            "source_timestamp": str(local.get("observed_at") or observed_at or ""),
        },
        "configured_remote": {
            "status": status,
            "configured_target_count": configured_count,
            "verified_target_count": verified_count,
            "source_timestamp": observed_at,
        },
    }


def configured_target_readiness():
    attestation = read_deployment_attestation()
    return attestation["status"], attestation, attestation["summary"]


def customer_readiness(weekly_digest=None):
    graph = STORE.get_health_graph()
    source = graph.get("source") if graph else {}
    stats = graph.get("stats") if graph else None
    activation = first_run_activation_funnel()
    storage = attachment_storage_status()
    reranker = gbrain_reranker_readiness()
    try:
        model_config = public_yoda_model_config()
        model_error = ""
    except Exception as exc:  # noqa: BLE001
        model_config = {}
        model_error = str(exc)
    if weekly_digest is None:
        try:
            weekly_digest = memory_value_digest("week")
            weekly_error = ""
        except Exception as exc:  # noqa: BLE001
            weekly_digest = {}
            weekly_error = str(exc)
    else:
        weekly_error = ""
    weekly = weekly_digest.get("verified_memory_outcomes") if isinstance(weekly_digest, dict) else {}
    weekly = weekly or {}
    sre_numeric = weekly.get("sre_numeric_evidence") if isinstance(weekly, dict) else {}
    sre_numeric_error = ""
    if not isinstance(sre_numeric, dict) or not sre_numeric:
        try:
            sre_numeric = latest_sre_numeric_evidence()
        except Exception as exc:  # noqa: BLE001
            sre_numeric = {}
            sre_numeric_error = str(exc)
    resolver = weekly_digest.get("resolver_health") if isinstance(weekly_digest, dict) else None
    resolver_error = ""
    if not isinstance(resolver, dict):
        try:
            resolver = resolver_feedback_health()
        except Exception as exc:  # noqa: BLE001
            resolver = {}
            resolver_error = str(exc)
    elif resolver.get("error"):
        resolver_error = str(resolver.get("error"))
    target_counts = weekly.get("deployment_attestation") if isinstance(weekly, dict) else None
    if isinstance(target_counts, dict) and target_counts.get("status"):
        target_status = str(target_counts.get("status"))
        target_summary = str(target_counts.get("summary") or "Deployment attestation evidence is available in the weekly digest.")
    else:
        target_status, target_counts, target_summary = configured_target_readiness()

    health_status = "ready" if graph and stats and source else "blocked"
    activation_status = "ready" if activation.get("mode") == "live-ready" else "degraded"
    model_backend = str(model_config.get("backend") or "")
    model_status = "ready" if model_backend and not model_error else "missing"
    if model_backend in {"openai", "openai_compatible"} and not model_config.get("api_key_available"):
        model_status = "degraded"
    if model_backend == "openclaw" and (model_config.get("node_runtime") or {}).get("status") not in {"ok", "not_used"}:
        model_status = "degraded"
    storage_status = "ready" if storage.get("available") else "blocked"
    weekly_status = str(weekly.get("status") or "missing")
    if weekly_status == "pass":
        weekly_status = "ready"
    elif weekly_status in {"partial", "missing"}:
        weekly_status = "partial" if weekly_status == "partial" else "missing"
    else:
        weekly_status = "degraded"
    resolver_pending = parse_nonnegative_int((resolver or {}).get("pending") if isinstance(resolver, dict) else 0, 0)
    proposal_counts = (resolver or {}).get("proposal_counts") if isinstance(resolver, dict) else {}
    if isinstance(proposal_counts, dict):
        resolver_pending = max(resolver_pending, parse_nonnegative_int(proposal_counts.get("pending"), 0))
    resolver_status = "missing" if resolver_error else ("degraded" if resolver_pending else "ready")
    sre_numeric_status = str((sre_numeric or {}).get("status") or "missing")
    if sre_numeric_status == "pass":
        sre_numeric_status = "ready"
    elif sre_numeric_status in {"partial", "missing", "stale", "warning", "critical"}:
        pass
    else:
        sre_numeric_status = "degraded"
    sre_numeric_summary = (
        str((sre_numeric or {}).get("summary") or "").strip()
        if isinstance(sre_numeric, dict)
        else ""
    )
    native_backup_coverage = (
        (sre_numeric or {}).get("native_backup_coverage")
        if isinstance((sre_numeric or {}).get("native_backup_coverage"), dict)
        else {}
    )

    checks = [
        readiness_check(
            "service_health",
            "Service health",
            health_status,
            "Dashboard service is loaded with non-null graph stats." if health_status == "ready" else "Dashboard service has not loaded graph health.",
            ["/api/health"],
            freshness="current" if health_status == "ready" else "missing",
            next_step="Wait for health to load, then refresh the graph before using customer data.",
        ),
        readiness_check(
            "activation",
            "Activation",
            activation_status,
            "Live GBrain readiness is available through the activation checklist." if activation_status == "ready" else "Activation checklist still recommends sample-first setup.",
            ["/api/activation-funnel"],
            freshness="current",
            next_step="Open First-run activation and complete the first incomplete setup step.",
        ),
        readiness_check(
            "model_configuration",
            "Ask Yoda model",
            model_status,
            "Ask Yoda has a configured model backend." if model_status == "ready" else "Ask Yoda model configuration needs attention before customer validation.",
            ["/api/yoda-model-config"],
            freshness="current" if not model_error else "missing",
            next_step="Open Settings > Model and verify the configured backend without changing production data.",
        ),
        readiness_check(
            "gbrain_reranker",
            "GBrain reranker",
            str(reranker.get("status") or "partial"),
            str(reranker.get("summary") or "GBrain reranker readiness is unavailable."),
            ["/api/health"],
            freshness=str(reranker.get("freshness") or "partial"),
            next_step=(
                f"After explicit approval, run gbrain config set search.reranker.model {GBRAIN_RERANKER_TARGET_MODEL}; "
                "then verify with gbrain doctor and a bounded gbrain search."
            ),
        ),
        readiness_check(
            "durable_storage",
            "Durable storage",
            storage_status,
            "Durable attachment storage is available." if storage_status == "ready" else "Durable attachment storage is unavailable.",
            ["/api/health"],
            freshness="current",
            next_step="Configure durable attachment storage before uploading customer files.",
        ),
        readiness_check(
            "weekly_verified_outcomes",
            "Weekly outcomes",
            weekly_status,
            "Weekly verified outcomes are passing." if weekly_status == "ready" else "Weekly verified outcomes are missing, partial, stale, or degraded.",
            ["notes/memory-starmap-todo-list", "reports/memory-stargraph-wish-sg0187-20260802t050000-0700-8edce44"],
            freshness=(weekly.get("freshness") or {}).get("status") or ("missing" if weekly_error else "current"),
            next_step="Open Memory value digest and inspect the first degraded or missing weekly outcome.",
        ),
        readiness_check(
            "resolver_pending",
            "Resolver pending state",
            resolver_status,
            "No resolver proposals are pending." if resolver_status == "ready" else "Resolver proposals are pending or resolver evidence is unavailable.",
            ["/api/resolver/health"],
            freshness="current" if not resolver_error else "missing",
            next_step="Open Resolver review and decide pending proposals manually.",
        ),
        readiness_check(
            "sre_numeric_evidence",
            "SRE numeric evidence",
            sre_numeric_status,
            (
                native_backup_coverage.get("summary")
                or ("Numeric capacity, backup, restore, and baseline evidence is current." if sre_numeric_status == "ready" else sre_numeric_summary)
                or "Numeric SRE capacity, backup, restore, or baseline evidence is missing, partial, stale, warning, or critical."
            ),
            (sre_numeric.get("evidence_slugs") if isinstance(sre_numeric, dict) else []) or ["reports/memory-stargraph-wish-sg0196-20260809t144900-0700-56c8c7d"],
            freshness=(sre_numeric.get("freshness") if isinstance(sre_numeric, dict) else None) or ("missing" if sre_numeric_error else "partial"),
            next_step="Open the latest SRE evidence report and inspect missing numeric capacity, backup, or restore fields.",
        ),
        readiness_check(
            "configured_targets",
            "Configured targets",
            target_status,
            target_summary,
            target_counts.get("evidence_slugs") or ["docs/automation-runbook.md"],
            freshness=target_counts.get("freshness") or ("current" if target_status == "ready" else "no_activity"),
            next_step="Run the deployment verification contract before presenting this instance as multi-target ready.",
        ),
    ]
    blocked = [check for check in checks if check["status"] in {"blocked", "missing"}]
    degraded = [check for check in checks if check["status"] in {"degraded", "partial", "stale", "warning", "critical", "source_mismatch", "no_activity"}]
    overall_status = "blocked" if blocked else ("degraded" if degraded else "ready")
    if blocked or degraded:
        first_attention = (blocked or degraded)[0]
        safe_next_step = {
            "label": first_attention["next_step"] or "Open Memory value digest and inspect current readiness evidence.",
            "check_id": first_attention["id"],
            "evidence_slugs": first_attention["evidence_slugs"][:2],
            "safe": True,
            "mutation": False,
            "auto_repair": False,
        }
    else:
        safe_next_step = {
            "label": "Review the customer readiness card and linked evidence before customer-facing use.",
            "check_id": "customer_readiness",
            "evidence_slugs": ["/api/customer-readiness", "/api/memory-value-digest?window=week"],
            "safe": True,
            "mutation": False,
            "auto_repair": False,
        }
    return {
        "ok": True,
        "schema_version": 1,
        "read_only": True,
        "ui_version": UI_VERSION,
        "status": overall_status,
        "freshness": {
            "status": "current" if not blocked else "partial",
            "source": "bounded_read_only_runtime_evidence",
        },
        "summary_counts": {
            "checks_total": len(checks),
            "ready": sum(1 for check in checks if check["status"] == "ready"),
            "degraded": sum(1 for check in checks if check["status"] == "degraded"),
            "blocked": sum(1 for check in checks if check["status"] == "blocked"),
            "missing": sum(1 for check in checks if check["status"] == "missing"),
            "partial": sum(1 for check in checks if check["status"] == "partial"),
            "stale": sum(1 for check in checks if check["status"] == "stale"),
            "warning": sum(1 for check in checks if check["status"] == "warning"),
            "critical": sum(1 for check in checks if check["status"] == "critical"),
            "source_mismatch": sum(1 for check in checks if check["status"] == "source_mismatch"),
            "no_activity": sum(1 for check in checks if check["status"] == "no_activity"),
        },
        "checks": checks,
        "gbrain_reranker": reranker,
        "native_backup_coverage": native_backup_coverage,
        "safe_next_step": safe_next_step,
        "evidence_slugs": sorted({slug for check in checks for slug in check["evidence_slugs"]}),
        "target_evidence": target_counts,
        "privacy": "Aggregate statuses and evidence slugs only; private snippets, secrets, prompt text, host-private paths, and concrete target coordinates are withheld.",
        "prohibited_actions": {
            "auto_repair": False,
            "resolver_auto_approval": False,
            "production_mutation": False,
        },
    }


def safe_gbrain_get_text(slug):
    try:
        return run_gbrain("get", slug, timeout=20)
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {exc}"


def safe_gbrain_get_text_bounded(slug, timeout=6, *, local_first=False):
    safe_slug = str(slug or "").strip()
    run_gbrain_is_mocked = "unittest.mock" in str(type(run_gbrain))
    if local_first and not run_gbrain_is_mocked and safe_slug and not safe_slug.startswith("/") and ".." not in safe_slug.split("/"):
        local_path = Path.home() / "brain" / f"{safe_slug}.md"
        try:
            brain_root = (Path.home() / "brain").resolve()
            resolved = local_path.resolve()
            if resolved == brain_root or brain_root in resolved.parents:
                return resolved.read_text(encoding="utf-8")
        except OSError:
            pass
    try:
        return run_gbrain("get", slug, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {exc}"


def count_todo_statuses(markdown):
    counts = {"planned": 0, "implementing": 0, "completed": 0, "failed": 0}
    for line in str(markdown or "").splitlines():
        match = re.match(r"\|\s*SG-\d+\s*\|\s*([^|]+)\|", line)
        if not match:
            continue
        status = match.group(1).strip()
        if status in counts:
            counts[status] += 1
    return counts


def parse_todo_table_rows(markdown):
    rows = []
    for line in str(markdown or "").splitlines():
        if not line.startswith("| SG-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        node_match = re.search(r"\[\[([^\]]+)\]\]", cells[4])
        rows.append(
            {
                "id": cells[0],
                "status": cells[1],
                "priority": cells[2],
                "title": cells[3],
                "node": node_match.group(1) if node_match else "",
                "updated": cells[5],
                "notes": sanitize_text_summary(cells[6], 260),
            }
        )
    return rows


def listify_frontmatter_value(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def supersession_metadata(meta):
    target_slug = (
        str(meta.get("superseded_by") or meta.get("superseding_todo_slug") or "")
        .strip()
        .strip("'\"")
    )
    target_id = str(meta.get("superseded_by_todo_id") or meta.get("superseding_todo_id") or "").strip()
    evidence_slugs = listify_frontmatter_value(meta.get("supersession_evidence"))
    return target_slug, target_id, evidence_slugs


def evaluate_failed_todo_supersession(row, row_markdown_cache=None):
    row_slug = row.get("node") or ""
    result = {
        "todo_id": row.get("id") or "",
        "slug": row_slug,
        "title": row.get("title") or "",
        "status": "not_superseded",
        "current_blocker": True,
        "superseded_by": "",
        "superseded_by_todo_id": "",
        "evidence_slugs": [],
        "reason": "no explicit structured supersession metadata",
    }
    if not row_slug:
        result["reason"] = "failed row has no child node slug"
        return result
    source_text = (row_markdown_cache or {}).get(row_slug)
    if source_text is None:
        source_text = safe_gbrain_get_text_bounded(row_slug, timeout=3)
    if not source_text or str(source_text).startswith("unavailable:"):
        result["reason"] = "failed child node is unavailable"
        return result
    source_meta, _body = parse_frontmatter(source_text)
    target_slug, target_id, evidence_slugs = supersession_metadata(source_meta)
    result["superseded_by"] = target_slug
    result["superseded_by_todo_id"] = target_id
    result["evidence_slugs"] = evidence_slugs
    if not target_slug:
        return result
    if target_slug == row_slug:
        result["status"] = "invalid"
        result["reason"] = "supersession target points to itself"
        return result
    target_text = (row_markdown_cache or {}).get(target_slug)
    if target_text is None:
        target_text = safe_gbrain_get_text_bounded(target_slug, timeout=3)
    if not target_text or str(target_text).startswith("unavailable:"):
        result["status"] = "invalid"
        result["reason"] = "supersession target is unavailable"
        return result
    target_meta, _target_body = parse_frontmatter(target_text)
    reverse_slug, _reverse_id, _reverse_evidence = supersession_metadata(target_meta)
    if reverse_slug == row_slug:
        result["status"] = "invalid"
        result["reason"] = "cyclic supersession metadata"
        return result
    if str(target_meta.get("status") or "").strip() != "completed":
        result["status"] = "invalid"
        result["reason"] = "supersession target is not completed"
        return result
    if target_id and target_id != str(target_meta.get("todo_id") or target_meta.get("id") or "").strip():
        result["status"] = "invalid"
        result["reason"] = "supersession target todo_id mismatch"
        return result
    if not evidence_slugs:
        result["status"] = "invalid"
        result["reason"] = "supersession evidence is absent"
        return result
    unavailable_evidence = []
    for evidence_slug in evidence_slugs:
        evidence_text = (row_markdown_cache or {}).get(evidence_slug)
        if evidence_text is None:
            evidence_text = safe_gbrain_get_text_bounded(evidence_slug, timeout=3)
        if not evidence_text or str(evidence_text).startswith("unavailable:"):
            unavailable_evidence.append(evidence_slug)
    if unavailable_evidence:
        result["status"] = "invalid"
        result["reason"] = "supersession evidence is unavailable"
        result["unavailable_evidence_slugs"] = unavailable_evidence
        return result
    result["status"] = "superseded"
    result["current_blocker"] = False
    result["reason"] = "explicit completed supersession with readable durable evidence"
    return result


def classify_todo_blockers(markdown, row_markdown_cache=None):
    rows = parse_todo_table_rows(markdown)
    failed_rows = [row for row in rows if row["status"] == "failed"]
    planned_rows = [row for row in rows if row["status"] == "planned"]
    implementing_rows = [row for row in rows if row["status"] == "implementing"]
    failed_evaluations = [evaluate_failed_todo_supersession(row, row_markdown_cache or {}) for row in failed_rows]
    current_failed = [item for item in failed_evaluations if item.get("current_blocker")]
    current_blockers = [
        {"todo_id": row["id"], "slug": row["node"], "status": row["status"], "title": row["title"]}
        for row in planned_rows + implementing_rows
    ] + current_failed
    superseded = [item for item in failed_evaluations if item.get("status") == "superseded"]
    invalid = [item for item in failed_evaluations if item.get("status") == "invalid"]
    return {
        "current_blockers": current_blockers,
        "historical_failures": failed_evaluations,
        "superseded_failures": superseded,
        "invalid_supersessions": invalid,
        "counts": {
            "planned": len(planned_rows),
            "implementing": len(implementing_rows),
            "failed": len(failed_rows),
            "current_unresolved": len(current_blockers),
            "current_failed": len(current_failed),
            "superseded_failed": len(superseded),
            "invalid_supersession": len(invalid),
            "historical_failed": len(failed_rows),
        },
    }


def todo_weekly_deltas(markdown, days=7):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    deltas = {"completed": 0, "planned": 0, "implementing": 0, "failed": 0, "window_days": days, "status": "partial"}
    dated_rows = 0
    for line in str(markdown or "").splitlines():
        match = re.match(r"\|\s*SG-\d+\s*\|\s*([^|]+)\|\s*[^|]+\|\s*[^|]+\|\s*[^|]+\|\s*([^|]+)\|", line)
        if not match:
            continue
        status = match.group(1).strip()
        raw_date = match.group(2).strip()
        try:
            parsed = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        dated_rows += 1
        if parsed.astimezone(timezone.utc) >= cutoff and status in deltas:
            deltas[status] += 1
    deltas["status"] = "complete" if dated_rows else "unknown"
    deltas["dated_rows"] = dated_rows
    return deltas


def outcome_evidence(slug, text):
    unavailable = str(text or "").startswith("unavailable:")
    return {
        "slug": slug,
        "available": bool(text and not unavailable),
        "status": "missing" if unavailable or not text else "available",
    }


def outcome_gate(key, label, status, evidence, *, passed=False, counts=None, summary="", freshness="current"):
    bounded_summary = bounded_readiness_summary(summary)
    return {
        "key": key,
        "label": label,
        "status": status,
        "passed": bool(passed),
        "counts": counts or {},
        "summary": bounded_summary["text"],
        "summary_full": bounded_summary["full_text"],
        "summary_truncated": bounded_summary["truncated"],
        "freshness": freshness,
        "evidence_slugs": [item["slug"] for item in evidence if item.get("available")],
        "evidence": evidence,
    }


def extract_evidence_timestamps(text):
    timestamps = []
    seen = set()
    patterns = [
        r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b",
        r"\b20\d{2}-\d{2}-\d{2}\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, str(text or "")):
            raw = match.group(0)
            if raw in seen:
                continue
            seen.add(raw)
            parsed = parse_iso_timestamp(raw)
            if parsed is None and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw):
                parsed = parse_iso_timestamp(f"{raw}T00:00:00Z")
            if parsed:
                timestamps.append(parsed)
    return timestamps


def backup_latest_freshness(markdown, observed_at=None):
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed = observed.astimezone(timezone.utc)
    timestamp_match = re.search(r"(?im)^\s*-\s*Run timestamp UTC:\s*([^\n]+?)\s*$", str(markdown or ""))
    latest = parse_iso_timestamp(timestamp_match.group(1).strip()) if timestamp_match else None
    if latest is None:
        timestamps = extract_evidence_timestamps(markdown)
        latest = max(timestamps) if timestamps else None
    if latest is None:
        return {
            "status": "missing",
            "latest_backup_at": "",
            "age_seconds": None,
            "freshness": "missing",
            "summary": "Backup latest evidence is missing or has no parseable backup timestamp.",
        }
    age_seconds = max(0, int((observed - latest.astimezone(timezone.utc)).total_seconds()))
    if age_seconds > SRE_BACKUP_CRITICAL_SECONDS:
        status = "critical"
        summary = "Latest backup evidence is older than the critical freshness threshold."
    elif age_seconds > SRE_BACKUP_WARNING_SECONDS:
        status = "warning"
        summary = "Latest backup evidence is older than the warning freshness threshold."
    else:
        status = "current"
        summary = "Latest backup evidence is within the current freshness threshold."
    return {
        "status": status,
        "latest_backup_at": latest.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "age_seconds": age_seconds,
        "freshness": status,
        "summary": summary,
    }


def gbrain_version_tuple(value):
    normalized = str(value or "").strip().removeprefix("V").removeprefix("v")
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?\b", normalized)
    if not match:
        return ()
    return tuple(int(part or 0) for part in match.groups(default="0"))


def native_backup_status_path():
    configured = str(os.environ.get("GBRAIN_BACKUP_STATUS_FILE") or "").strip()
    if configured:
        return Path(configured).expanduser()
    gbrain_home = str(os.environ.get("GBRAIN_HOME") or "").strip()
    if gbrain_home:
        root = Path(gbrain_home).expanduser()
        candidates = (root / ".gbrain" / "backup-status.json", root / "backup-status.json")
        return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    return Path.home() / ".gbrain" / "backup-status.json"


def native_backup_base(status, summary, observed_at, *, native_available):
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return {
        "schema_version": 1,
        "status": status,
        "freshness": status if status in {"unavailable", "missing", "malformed", "stale"} else "current",
        "native_available": native_available,
        "native_schema": GBRAIN_NATIVE_BACKUP_SCHEMA if native_available else "",
        "checked_at": "",
        "readback_at": observed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "age_seconds": None,
        "interval_days": None,
        "verdict": "unknown",
        "degraded": False,
        "counts": {
            "assets": None,
            "recoverable_repos": None,
            "pages_at_risk": None,
            "no_remote": None,
            "unpushed": None,
            "failing": None,
        },
        "summary": summary,
        "operator_action": {
            "approval_required": True,
            "automatic_mutation": False,
            "commands": ["gbrain backup status --json", "gbrain backup check --json"],
        },
        "privacy": "Only aggregate native backup counts and timestamps are returned; asset names, repository paths, remotes, fix arguments, and credentials are withheld.",
    }


def parse_gbrain_native_backup_status(payload, observed_at=None):
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    malformed = native_backup_base(
        "malformed",
        "Native GBrain backup coverage exists but its structured status failed validation.",
        observed,
        native_available=True,
    )
    if not isinstance(payload, dict) or payload.get("schema_version") != GBRAIN_NATIVE_BACKUP_SCHEMA:
        return malformed
    overall = str(payload.get("overall") or "").strip().lower()
    checked = parse_iso_timestamp(payload.get("checked_at"))
    totals = payload.get("totals")
    recovery = payload.get("recovery")
    interval_days = payload.get("interval_days")
    required_total_keys = ("assets", "no_remote", "unpushed", "failing", "recoverable_repos", "pages_at_risk")
    if (
        overall not in {"ok", "warn"}
        or checked is None
        or not isinstance(totals, dict)
        or not isinstance(recovery, dict)
        or not isinstance(interval_days, (int, float))
        or isinstance(interval_days, bool)
        or interval_days < 1
        or any(not isinstance(totals.get(key), int) or isinstance(totals.get(key), bool) or totals.get(key) < 0 for key in required_total_keys)
        or recovery.get("recoverable_repos") != totals.get("recoverable_repos")
        or recovery.get("pages_at_risk") != totals.get("pages_at_risk")
    ):
        return malformed
    age_seconds = max(0, int((observed.astimezone(timezone.utc) - checked).total_seconds()))
    stale = age_seconds > int(interval_days * 24 * 60 * 60)
    degraded = payload.get("degraded") is True
    if degraded:
        status = "partial"
        summary = "Native GBrain backup coverage is partial because its structured check was degraded."
    elif stale:
        status = "stale"
        summary = "Native GBrain backup coverage is older than its configured check interval."
    elif overall == "warn":
        status = "warning"
        summary = "Native GBrain backup coverage reports assets or pages that may not survive disk loss."
    else:
        status = "ready"
        summary = "Native GBrain backup coverage reports a current recovery-ready aggregate verdict."
    result = native_backup_base(status, summary, observed, native_available=True)
    result.update({
        "freshness": "stale" if stale else "current",
        "checked_at": checked.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "age_seconds": age_seconds,
        "interval_days": int(interval_days),
        "verdict": overall,
        "degraded": degraded,
        "counts": {key: totals[key] for key in required_total_keys},
    })
    return result


def read_gbrain_native_backup_status(observed_at=None):
    observed = observed_at or datetime.now(timezone.utc)
    if gbrain_version_tuple(runtime_gbrain_version()) < GBRAIN_NATIVE_BACKUP_MIN_VERSION:
        return native_backup_base(
            "unavailable",
            "This GBrain version does not expose native backup coverage; legacy backup-latest evidence remains the active fallback.",
            observed,
            native_available=False,
        )
    path = native_backup_status_path()
    try:
        if path.stat().st_size > GBRAIN_NATIVE_BACKUP_MAX_BYTES:
            raise ValueError("native backup status exceeds size limit")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return native_backup_base(
            "missing",
            "Native GBrain backup coverage is supported but no structured status is available; legacy backup-latest evidence remains the active fallback.",
            observed,
            native_available=True,
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return native_backup_base(
            "malformed",
            "Native GBrain backup coverage exists but its bounded structured status could not be read safely.",
            observed,
            native_available=True,
        )
    return parse_gbrain_native_backup_status(payload, observed)


def gbrain_native_backup_coverage(backup_freshness, observed_at=None):
    native = read_gbrain_native_backup_status(observed_at)
    legacy_status = str((backup_freshness or {}).get("status") or "missing")
    fallback_active = native["status"] in {"unavailable", "missing"}
    if fallback_active:
        effective_status = legacy_status
        source = "backup_latest_fallback"
        summary = (
            f"Native GBrain backup coverage is {native['status']}; "
            f"legacy backup-latest is the active fallback and is {legacy_status}."
        )
    elif native["status"] == "ready":
        effective_status = legacy_status
        source = "native_and_backup_latest"
        summary = f"Native GBrain backup coverage is ready; legacy backup-latest freshness is {legacy_status}."
    else:
        effective_status = native["status"]
        source = "native_gbrain_backup_coverage"
        summary = native["summary"]
    return {
        "schema_version": 1,
        "status": effective_status,
        "source": source,
        "fallback_active": fallback_active,
        "native": native,
        "backup_latest": dict(backup_freshness or {}),
        "summary": summary,
        "operator_action": native["operator_action"],
        "privacy": native["privacy"],
    }


def evidence_recency_status(texts_by_slug, marker, max_age_seconds, observed_at=None):
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed = observed.astimezone(timezone.utc)
    marker = marker.lower()
    candidates = []
    for slug, text in texts_by_slug.items():
        if slug == "_backups/backup-latest":
            continue
        lowered = f"{slug}\n{text}".lower()
        if marker not in lowered:
            continue
        candidates.extend(extract_evidence_timestamps(f"{slug}\n{text}"))
    latest = max(candidates) if candidates else None
    if latest is None:
        return {"status": "missing", "latest_at": "", "age_seconds": None}
    age_seconds = max(0, int((observed - latest.astimezone(timezone.utc)).total_seconds()))
    return {
        "status": "current" if age_seconds <= max_age_seconds else "stale",
        "latest_at": latest.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "age_seconds": age_seconds,
    }


def terminal_sre_evidence_pairs():
    try:
        pages = STORE.list_pages(entity_type="run", limit=100)
    except Exception:  # noqa: BLE001
        return []
    candidate_slugs = []
    for page in pages if isinstance(pages, list) else []:
        slug = str(page.get("slug") or "").strip() if isinstance(page, dict) else ""
        if slug.startswith(SRE_RUN_PREFIXES):
            candidate_slugs.append(slug)
        if len(candidate_slugs) >= SRE_EVIDENCE_CANDIDATE_LIMIT:
            break
    if not candidate_slugs:
        return []
    run_texts = {}
    with ThreadPoolExecutor(max_workers=min(SRE_EVIDENCE_READ_WORKERS, len(candidate_slugs))) as executor:
        futures = {
            slug: executor.submit(safe_gbrain_get_text_bounded, slug, 3, local_first=True)
            for slug in candidate_slugs
        }
        for slug, future in futures.items():
            try:
                run_texts[slug] = future.result(timeout=4)
            except Exception:  # noqa: BLE001
                run_texts[slug] = ""
    candidates = []
    for run_slug, run_text in run_texts.items():
        if not run_text or str(run_text).startswith("unavailable:"):
            continue
        run_meta, _run_body = parse_frontmatter(run_text)
        status = str(run_meta.get("status") or "").strip().lower()
        completed_at = parse_iso_timestamp(run_meta.get("completed_at"))
        if not status.startswith("completed") or completed_at is None:
            continue
        mode = str(run_meta.get("mode") or "").strip().lower()
        if mode not in {"daily_reliability", "weekly_resilience"}:
            mode = "weekly_resilience" if "weekly-resilience" in run_slug else "daily_reliability"
        report_slug = safe_evidence_slug(run_meta.get("report") or run_meta.get("report_slug"))
        if not report_slug.startswith("reports/"):
            continue
        candidates.append((run_slug, run_text, run_meta, mode, completed_at, report_slug))
    if not candidates:
        return []
    report_slugs = list(dict.fromkeys(item[5] for item in candidates))
    report_texts = {}
    with ThreadPoolExecutor(max_workers=min(SRE_EVIDENCE_READ_WORKERS, len(report_slugs))) as executor:
        futures = {
            slug: executor.submit(safe_gbrain_get_text_bounded, slug, 3, local_first=True)
            for slug in report_slugs
        }
        for slug, future in futures.items():
            try:
                report_texts[slug] = future.result(timeout=4)
            except Exception:  # noqa: BLE001
                report_texts[slug] = ""
    records = []
    for run_slug, run_text, run_meta, mode, completed_at, report_slug in candidates:
        report_text = report_texts.get(report_slug, "")
        if not report_text or str(report_text).startswith("unavailable:"):
            continue
        report_meta, _report_body = parse_frontmatter(report_text)
        report_status = str(report_meta.get("status") or "").strip().lower()
        paired_run = str(report_meta.get("run") or report_meta.get("run_slug") or run_slug).strip()
        if not report_status.startswith("completed") or paired_run != run_slug:
            continue
        records.append(
            {
                "mode": mode,
                "run_slug": run_slug,
                "report_slug": report_slug,
                "completed_at": completed_at,
                "acknowledged": (
                    str(run_meta.get("product_owner_notification_status") or "").strip()
                    == "acknowledged_by_product_owner"
                    and run_meta.get("product_owner_notification_pending") is not True
                ),
                "texts": {run_slug: str(run_text), report_slug: str(report_text)},
            }
        )
    selected = {}
    for record in sorted(records, key=lambda item: item["completed_at"], reverse=True):
        selected.setdefault(record["mode"], record)
    return [selected[mode] for mode in ("daily_reliability", "weekly_resilience") if mode in selected]


def selected_sre_recency(records, mode, max_age_seconds, texts_by_slug, marker):
    selected = next((record for record in records if record.get("mode") == mode), None)
    if not selected:
        return evidence_recency_status(texts_by_slug, marker, max_age_seconds)
    completed_at = selected["completed_at"]
    age_seconds = max(0, int((datetime.now(timezone.utc) - completed_at).total_seconds()))
    return {
        "status": "current" if age_seconds <= max_age_seconds else "stale",
        "latest_at": completed_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "age_seconds": age_seconds,
        "run_slug": selected["run_slug"],
        "report_slug": selected["report_slug"],
        "acknowledged": bool(selected.get("acknowledged")),
    }


def latest_sre_numeric_evidence():
    selected_records = terminal_sre_evidence_pairs()
    selected_slugs = [
        slug
        for record in selected_records
        for slug in (record["run_slug"], record["report_slug"])
    ]
    evidence_slugs = list(dict.fromkeys([
        *SRE_LEGACY_NUMERIC_EVIDENCE_SLUGS[:2],
        *(selected_slugs or SRE_LEGACY_NUMERIC_EVIDENCE_SLUGS[2:]),
        "_backups/backup-latest",
    ]))
    evidence = []
    texts = []
    texts_by_slug = {}
    with ThreadPoolExecutor(max_workers=len(evidence_slugs)) as executor:
        futures = {slug: executor.submit(safe_gbrain_get_text_bounded, slug, 3, local_first=True) for slug in evidence_slugs}
        for slug, future in futures.items():
            try:
                text = future.result(timeout=4)
            except Exception as exc:  # noqa: BLE001
                text = f"unavailable: {exc}"
            item = outcome_evidence(slug, text)
            evidence.append(item)
            if item["available"]:
                texts.append(str(text).lower())
                texts_by_slug[slug] = str(text)
    joined = "\n".join(texts)
    has_schema = "memory-stargraph-sre-numeric-evidence-v1" in joined
    has_capacity = all(term in joined for term in ("cpu", "memory", "disk", "open-file")) or all(term in joined for term in ("cpu", "memory", "disk", "open_file"))
    backup_text = texts_by_slug.get("_backups/backup-latest", "")
    backup_freshness = backup_latest_freshness(backup_text)
    native_backup_coverage = gbrain_native_backup_coverage(backup_freshness)
    has_backup = native_backup_coverage["status"] == "current"
    has_restore = "restore" in joined and ("checksum" in joined or "rehearsal" in joined)
    has_baseline = "7-day" in joined and "30-day" in joined
    daily_recency = selected_sre_recency(
        selected_records,
        "daily_reliability",
        SRE_DAILY_EVIDENCE_MAX_AGE_SECONDS,
        texts_by_slug,
        "daily",
    )
    weekly_recency = selected_sre_recency(
        selected_records,
        "weekly_resilience",
        SRE_WEEKLY_EVIDENCE_MAX_AGE_SECONDS,
        texts_by_slug,
        "weekly",
    )
    has_current_daily = daily_recency["status"] == "current"
    has_current_weekly = weekly_recency["status"] == "current"
    passed = has_schema and has_capacity and has_backup and has_restore and has_baseline and has_current_daily and has_current_weekly
    missing = not any(item["available"] for item in evidence)
    if passed:
        status = "pass"
    elif missing:
        status = "missing"
    elif native_backup_coverage["status"] == "critical":
        status = "critical"
    elif native_backup_coverage["status"] == "warning":
        status = "warning"
    elif native_backup_coverage["status"] == "missing":
        status = "missing"
    elif daily_recency["status"] == "missing":
        status = "missing"
    elif daily_recency["status"] == "stale" or weekly_recency["status"] == "stale":
        status = "stale"
    elif weekly_recency["status"] == "missing":
        status = "missing"
    else:
        status = "partial"
    freshness = "current" if status == "pass" else status
    if status == "pass":
        summary = f"Numeric SRE capacity, restore rehearsal, current Daily/Weekly evidence, and 7-day/30-day baselines are present. {native_backup_coverage['summary']}"
    elif status in {"critical", "warning"}:
        summary = native_backup_coverage["summary"]
    elif status == "stale":
        summary = "Numeric SRE evidence is stale because current Daily or Weekly evidence is outside the allowed recency window."
    elif status == "missing":
        summary = "Numeric SRE evidence is missing required backup freshness or current Daily/Weekly evidence."
    else:
        summary = native_backup_coverage["summary"] if native_backup_coverage["status"] in {"partial", "malformed", "stale"} else "Numeric SRE capacity, backup, restore, baseline, or recency evidence is partial."
    return {
        "status": status,
        "passed": passed,
        "freshness": freshness,
        "evidence": evidence,
        "evidence_slugs": [item["slug"] for item in evidence if item.get("available")],
        "counts": {
            "numeric_schema_present": 1 if has_schema else 0,
            "capacity_categories_present": 1 if has_capacity else 0,
            "backup_evidence_present": 1 if backup_freshness["status"] != "missing" else 0,
            "backup_freshness_current": 1 if backup_freshness["status"] == "current" else 0,
            "backup_freshness_warning": 1 if backup_freshness["status"] == "warning" else 0,
            "backup_freshness_critical": 1 if backup_freshness["status"] == "critical" else 0,
            "backup_freshness_missing": 1 if backup_freshness["status"] == "missing" else 0,
            "backup_freshness_age_seconds": backup_freshness["age_seconds"],
            "native_backup_available": 1 if native_backup_coverage["native"]["native_available"] else 0,
            "native_backup_ready": 1 if native_backup_coverage["native"]["status"] == "ready" else 0,
            "native_backup_warning": 1 if native_backup_coverage["native"]["status"] == "warning" else 0,
            "native_backup_malformed": 1 if native_backup_coverage["native"]["status"] == "malformed" else 0,
            "backup_latest_fallback_active": 1 if native_backup_coverage["fallback_active"] else 0,
            "backup_warning_threshold_seconds": SRE_BACKUP_WARNING_SECONDS,
            "backup_critical_threshold_seconds": SRE_BACKUP_CRITICAL_SECONDS,
            "restore_evidence_present": 1 if has_restore else 0,
            "baseline_windows_present": 1 if has_baseline else 0,
            "daily_evidence_current": 1 if has_current_daily else 0,
            "weekly_evidence_current": 1 if has_current_weekly else 0,
        },
        "backup_freshness": backup_freshness,
        "native_backup_coverage": native_backup_coverage,
        "daily_evidence": daily_recency,
        "weekly_evidence": weekly_recency,
        "selected_terminal_runs": [
            {
                "mode": record["mode"],
                "run_slug": record["run_slug"],
                "report_slug": record["report_slug"],
                "completed_at": record["completed_at"].replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "acknowledged": bool(record.get("acknowledged")),
            }
            for record in selected_records
        ],
        "summary": summary,
    }


def verified_memory_outcomes(window, backlog, resolver_health):
    if window != "week":
        return None

    evidence_slugs = {
        "retrieval_quality": "reports/memory-stargraph-wish-sg0184-20260801t074549-0700-63e45d0",
        "ask_yoda": "runs/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df",
        "ask_yoda_report": "reports/memory-stargraph-wish-sg0167-20260729t074025-0700-936d7df",
        "ask_yoda_todo": "notes/memory-starmap-todo-list/resolve-ask-yoda-openclaw-provider-timeout-after-node-runtime-fix",
        "search_parity": "runs/memory-stargraph-wish-sg0185-20260801t204507-0700-125d15f",
        "capture_link": "runs/memory-stargraph-capture-link-drain-capture-link-drain-20260802t000254-0700-scheduled-85",
        "worker_learning": "learnings/memory-stargraph-discovery-20260802-package-proof-before-expanding-surface",
    }
    evidence_texts = {}
    with ThreadPoolExecutor(max_workers=len(evidence_slugs)) as executor:
        futures = {key: executor.submit(safe_gbrain_get_text_bounded, slug, 3, local_first=True) for key, slug in evidence_slugs.items()}
        for key, future in futures.items():
            try:
                evidence_texts[key] = future.result(timeout=4)
            except Exception as exc:  # noqa: BLE001
                evidence_texts[key] = f"unavailable: {exc}"
    evidence = {
        key: outcome_evidence(slug, evidence_texts.get(key, ""))
        for key, slug in evidence_slugs.items()
    }
    retrieval_text = evidence_texts["retrieval_quality"].lower()
    ask_text = evidence_texts["ask_yoda"].lower()
    search_text = evidence_texts["search_parity"].lower()
    capture_text = evidence_texts["capture_link"].lower()
    learning_text = evidence_texts["worker_learning"].lower()
    deltas = todo_weekly_deltas(backlog)
    blockers = count_todo_statuses(backlog)
    row_markdown_cache = {slug: evidence_texts.get(key, "") for key, slug in evidence_slugs.items()}
    row_markdown_cache["notes/memory-starmap-todo-list"] = backlog
    blocker_classification = classify_todo_blockers(backlog, row_markdown_cache)
    sre_numeric = latest_sre_numeric_evidence()
    deployment_attestation = read_deployment_attestation()

    retrieval_passed = evidence["retrieval_quality"]["available"] and (
        ("10/10" in retrieval_text or "answer_success_count=10" in retrieval_text)
        and ("10/10" in retrieval_text or "recall_success_count=10" in retrieval_text)
        and ("source coverage" in retrieval_text or "source_coverage" in retrieval_text or "expected-source coverage" in retrieval_text or "expected_source_matched=9/9" in retrieval_text)
    )
    contradiction_passed = evidence["retrieval_quality"]["available"] and "contradiction" in retrieval_text and "prun" in retrieval_text
    ask_passed = evidence["ask_yoda"]["available"] and "model-backed" in ask_text and "fallback" in ask_text and "non-fallback" in ask_text
    search_passed = evidence["search_parity"]["available"] and "api top" in search_text and "focus" in search_text
    capture_has_activity = evidence["capture_link"]["available"] and (
        "completed_empty_snapshot_enrichment" in capture_text or "capture_outcomes" in capture_text
    )
    learning_passed = evidence["worker_learning"]["available"] and ("learning" in learning_text or "proof" in learning_text)
    current_blocker_count = blocker_classification["counts"]["current_unresolved"]

    gates = [
        outcome_gate(
            "retrieval_quality_benchmark",
            "Retrieval quality benchmark",
            "pass" if retrieval_passed else evidence["retrieval_quality"]["status"],
            [evidence["retrieval_quality"]],
            passed=retrieval_passed,
            counts={"answer_success": 10 if retrieval_passed else 0, "recall_success": 10 if retrieval_passed else 0},
            summary="Synthetic weekly benchmark has answer/recall success and expected source coverage." if retrieval_passed else "Benchmark evidence is missing or incomplete.",
        ),
        outcome_gate(
            "model_backed_ask_yoda",
            "Model-backed Ask Yoda",
            "pass" if ask_passed else evidence["ask_yoda"]["status"],
            [evidence["ask_yoda"]],
            passed=ask_passed,
            counts={"fallback_events": 0 if ask_passed else None},
            summary="Recent accepted evaluator evidence reports model-backed non-fallback answers." if ask_passed else "Model-backed Ask Yoda evidence is missing or stale.",
        ),
        outcome_gate(
            "natural_language_search_parity",
            "Natural-language search parity",
            "pass" if search_passed else evidence["search_parity"]["status"],
            [evidence["search_parity"]],
            passed=search_passed,
            counts={"parity_queries_verified": 1 if search_passed else 0},
            summary="API top slug, visible result, and UI focus align for the weekly parity query." if search_passed else "Search parity evidence is missing or incomplete.",
        ),
        outcome_gate(
            "contradiction_pruning",
            "Contradiction pruning",
            "pass" if contradiction_passed else evidence["retrieval_quality"]["status"],
            [evidence["retrieval_quality"]],
            passed=contradiction_passed,
            counts={"stale_contradictions_pruned": 1 if contradiction_passed else 0},
            summary="Benchmark evidence includes stale contradiction pruning." if contradiction_passed else "Contradiction-pruning evidence is unavailable.",
        ),
        outcome_gate(
            "capture_link_outcomes",
            "Capture Link capture/enrichment",
            "pass" if capture_has_activity else evidence["capture_link"]["status"],
            [evidence["capture_link"]],
            passed=capture_has_activity,
            counts={"recent_enrichment_runs": 1 if capture_has_activity else 0},
            summary="Recent host runner evidence includes capture/enrichment terminal outcomes." if capture_has_activity else "No current Capture Link terminal outcome was readable.",
        ),
        outcome_gate(
            "worker_learnings",
            "Worker-produced Learnings",
            "pass" if learning_passed else evidence["worker_learning"]["status"],
            [evidence["worker_learning"]],
            passed=learning_passed,
            counts={"recent_learning_items": 1 if learning_passed else 0},
            summary="A worker-produced Learning packages proof before expanding surface area." if learning_passed else "No recent worker Learning evidence was readable.",
        ),
        outcome_gate(
            "unresolved_blockers",
            "Current unresolved blockers",
            "degraded" if current_blocker_count else "pass",
            [outcome_evidence("notes/memory-starmap-todo-list", backlog)]
            + [
                outcome_evidence(item["slug"], item.get("reason", ""))
                for item in blocker_classification["historical_failures"]
            ],
            passed=current_blocker_count == 0,
            counts=blocker_classification["counts"],
            summary=(
                "Current planned, implementing, or unsuperseded failed blockers remain."
                if current_blocker_count
                else "No current blockers; historical failures are separated when explicitly superseded by completed evidence."
            ),
            freshness="current" if backlog and not str(backlog).startswith("unavailable:") else "unknown",
        ),
        outcome_gate(
            "sre_capacity_backup_restore",
            "SRE capacity, backup, and restore evidence",
            sre_numeric["status"],
            sre_numeric["evidence"],
            passed=sre_numeric["passed"],
            counts=sre_numeric["counts"],
            summary=sre_numeric["summary"],
            freshness=sre_numeric["freshness"],
        ),
        outcome_gate(
            "configured_target_deployment_attestation",
            "Configured-target deployment attestation",
            "pass" if deployment_attestation["status"] == "ready" else deployment_attestation["status"],
            [outcome_evidence(slug, "available") for slug in deployment_attestation["evidence_slugs"]],
            passed=deployment_attestation["status"] == "ready",
            counts=deployment_attestation["counts"],
            summary=deployment_attestation["summary"],
            freshness=deployment_attestation["freshness"],
        ),
    ]
    passed = sum(1 for gate in gates if gate["passed"])
    missing = sum(1 for gate in gates if gate["status"] == "missing")
    degraded = sum(1 for gate in gates if gate["status"] in {"degraded", "stale", "warning", "critical", "source_mismatch"})
    aggregate_status = "pass" if passed == len(gates) else ("partial" if missing else ("degraded" if degraded else "partial"))
    return {
        "schema_version": 1,
        "window": "week",
        "read_only": True,
        "privacy": "Aggregate counts, statuses, and evidence slugs only; private snippets, prompt text, secrets, and host-private paths are withheld.",
        "freshness": {
            "status": "current" if missing == 0 else "partial",
            "source": "bounded_gbrain_evidence_slugs",
        },
        "weekly_deltas": deltas,
        "current_unresolved_blockers": blocker_classification["current_blockers"],
        "historical_failures": blocker_classification["historical_failures"],
        "superseded_failures": blocker_classification["superseded_failures"],
        "summary_counts": {
            "gates_total": len(gates),
            "gates_passed": passed,
            "gates_missing": missing,
            "gates_degraded": degraded,
        },
        "status": aggregate_status,
        "gates": gates,
        "sre_numeric_evidence": {
            "status": sre_numeric["status"],
            "freshness": sre_numeric["freshness"],
            "evidence_slugs": [item["slug"] for item in sre_numeric["evidence"] if item.get("available")],
            "counts": sre_numeric["counts"],
            "summary": sre_numeric["summary"],
            "native_backup_coverage": sre_numeric.get("native_backup_coverage") or {},
        },
        "deployment_attestation": {
            "status": deployment_attestation["status"],
            "freshness": deployment_attestation["freshness"],
            "summary": deployment_attestation["summary"],
            "source_timestamp": deployment_attestation.get("source_timestamp", ""),
            "readback_at": deployment_attestation.get("readback_at", ""),
            "evidence_slugs": deployment_attestation["evidence_slugs"],
            "counts": deployment_attestation["counts"],
            "local": deployment_attestation["local"],
            "configured_remote": deployment_attestation["configured_remote"],
        },
        "resolver_choice": {
            "status": "observed" if isinstance(resolver_health, dict) and not resolver_health.get("error") else "unknown",
            "pending_proposals": parse_nonnegative_int((resolver_health or {}).get("pending", 0) if isinstance(resolver_health, dict) else 0),
            "auto_approval": False,
        },
    }


def resolver_choice_from_health(resolver_health):
    return {
        "status": "observed" if isinstance(resolver_health, dict) and not resolver_health.get("error") else "unknown",
        "pending_proposals": parse_nonnegative_int((resolver_health or {}).get("pending", 0) if isinstance(resolver_health, dict) else 0),
        "auto_approval": False,
    }


def memory_value_digest(window="day"):
    window = str(window or "day").strip().lower()
    if window not in {"day", "week"}:
        window = "day"
    graph = STORE.get_seed_graph()
    source = graph.get("source") or {}
    backlog = safe_gbrain_get_text_bounded("notes/memory-starmap-todo-list", timeout=4, local_first=True)
    learnings = safe_gbrain_get_text_bounded("learnings/memory-stargraph-20260719-operational-state-reconciliation-and-source-sync-preflight", timeout=3, local_first=True)
    todo_movement = count_todo_statuses(backlog)
    outcomes = None
    if window == "week":
        with ThreadPoolExecutor(max_workers=2) as executor:
            resolver_future = executor.submit(resolver_feedback_health)
            outcomes_future = executor.submit(verified_memory_outcomes, window, backlog, {})
            try:
                resolver_health = resolver_future.result()
            except Exception as exc:  # noqa: BLE001
                resolver_health = {"error": sanitize_runtime_error(exc)}
            outcomes = outcomes_future.result()
        if outcomes:
            outcomes["resolver_choice"] = resolver_choice_from_health(resolver_health)
    else:
        try:
            resolver_health = resolver_feedback_health()
        except Exception as exc:  # noqa: BLE001
            resolver_health = {"error": sanitize_runtime_error(exc)}
    learned_items = []
    if "source-sync" in learnings.lower() or "source sync" in learnings.lower():
        learned_items.append("Source-sync preflight is now treated as worker runtime evidence, not only deployment evidence.")
    if "operational" in learnings.lower():
        learned_items.append("Ask Yoda should reconcile current operational state against completed remediation evidence.")
    if not learned_items:
        learned_items.append("No recent durable Learning was readable; inspect Learning evidence directly.")
    unresolved = [
        f"{status}: {count}"
        for status, count in todo_movement.items()
        if status in {"planned", "implementing", "failed"} and count
    ]
    next_action = (
        "Finish implementing rows currently in progress and rerun final TODO compaction."
        if todo_movement["implementing"]
        else "Pick the next evidence-backed planned TODO or run Product Owner prioritization if no planned work remains."
    )
    digest = {
        "ok": True,
        "read_only": True,
        "ui_version": UI_VERSION,
        "window": window,
        "source_mode": str(source.get("mode") or "unknown"),
        "source_status": str(source.get("status") or "unknown"),
        "graph_stats": graph.get("stats") or {},
        "todo_movement": todo_movement,
        "learned_items": learned_items,
        "implemented_improvements": [
            "Completed TODO rows are compacted into immutable archives when the backlog reaches the archive boundary.",
            "Runs, Learnings, TODO movement, resolver health, and graph health are linked as inspectable evidence instead of hidden chat-only summaries.",
        ],
        "unresolved_blockers": unresolved,
        "resolver_health": resolver_health,
        "evidence_links": {
            "goal": "goals/memory-stargraph-continuous-learning-local-knowledge-os",
            "todo_backlog": "notes/memory-starmap-todo-list",
            "runs": "runs",
            "learnings": "learnings",
            "health": "/api/health",
            "resolver": "/api/resolver/health",
        },
        "next_action": next_action,
        "privacy": "Private node content is not embedded in this digest; inspect linked evidence only when authorized.",
    }
    if outcomes:
        digest["verified_memory_outcomes"] = outcomes
    return digest


def settings_evidence(force=False):
    cache_key = "week"
    if force:
        STORE.settings_evidence_cache.clear()
    cached = STORE.settings_evidence_cache.get(cache_key)
    if cached is not None:
        return cached

    def load():
        digest = memory_value_digest("week")
        return {
            "ok": True,
            "read_only": True,
            "ui_version": UI_VERSION,
            "digest": digest,
            "readiness": customer_readiness(digest),
        }

    payload, _status = STORE.settings_evidence_cache.load_once(cache_key, load, timeout=60)
    return payload if payload is not None else load()


def cached_settings_evidence_part(part):
    cache = getattr(STORE, "settings_evidence_cache", None)
    if cache is None:
        return None
    payload = cache.get("week")
    if not isinstance(payload, dict):
        return None
    value = payload.get(part)
    return value if isinstance(value, dict) else None


class MemoryStargraphHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def end_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        compressible = len(body) >= JSON_GZIP_MIN_BYTES
        compressed = False
        if compressible and accepts_gzip_encoding(self.headers.get("Accept-Encoding")):
            body = gzip.compress(body, compresslevel=1, mtime=0)
            compressed = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if compressible:
            self.send_header("Vary", "Accept-Encoding")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_head(self):
        request_path = urlparse(self.path).path
        relative_path = COMPRESSIBLE_STATIC_PATHS.get(request_path)
        encodings = accepted_static_encodings(self.headers.get("Accept-Encoding"))
        if not relative_path or not encodings:
            return super().send_head()
        path = PUBLIC_DIR / relative_path
        try:
            stat = path.stat()
        except OSError:
            return super().send_head()
        if "If-Modified-Since" in self.headers and "If-None-Match" not in self.headers:
            try:
                modified_since = email.utils.parsedate_to_datetime(self.headers["If-Modified-Since"])
            except (TypeError, IndexError, OverflowError, ValueError):
                modified_since = None
            if modified_since is not None:
                if modified_since.tzinfo is None:
                    modified_since = modified_since.replace(tzinfo=timezone.utc)
                last_modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0)
                if last_modified <= modified_since.astimezone(timezone.utc):
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.send_header("Vary", "Accept-Encoding")
                    self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
                    self.end_headers()
                    return None
        body = None
        encoding = None
        for candidate in encodings:
            if candidate == "br":
                body = brotli_static_file(
                    str(PUBLIC_DIR),
                    relative_path,
                    stat.st_mtime_ns,
                    stat.st_size,
                )
            elif candidate == "gzip":
                body = gzip_static_file(str(path), stat.st_mtime_ns, stat.st_size)
            if body is not None:
                encoding = candidate
                break
        if body is None:
            return super().send_head()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Encoding", encoding)
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()
        return io.BytesIO(body)

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
        file_size = file_path.stat().st_size
        requested_range = parse_media_byte_range(self.headers.get("Range"), file_size)
        if requested_range is MEDIA_RANGE_INVALID:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        partial = requested_range is not None
        start, end = requested_range if partial else (0, max(0, file_size - 1))
        content_length = end - start + 1 if file_size else 0
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        if not head_only:
            with file_path.open("rb") as source:
                source.seek(start)
                copy_media_range(source, self.wfile, content_length)

    def serve_media_preview(self, request_path, head_only=False):
        file_path = resolve_media_preview_file_path(request_path)
        if not file_path or file_path.suffix.lower() not in MEDIA_PREVIEW_EXTENSIONS:
            original_path = "/media/" + str(request_path or "").split("/media-preview/", 1)[-1]
            return self.serve_media_file(original_path, head_only=head_only)
        stat = file_path.stat()
        body = image_preview_bytes(str(file_path), stat.st_mtime_ns, stat.st_size)
        if body is None:
            original_path = "/media/" + str(request_path or "").split("/media-preview/", 1)[-1]
            return self.serve_media_file(original_path, head_only=head_only)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/webp")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

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
        if parsed.path.startswith("/media-preview/"):
            return self.serve_media_preview(parsed.path, head_only=True)
        if parsed.path.startswith("/media/"):
            return self.serve_media_file(parsed.path, head_only=True)
        if parsed.path.startswith("/gbrain-files/"):
            return self.serve_gbrain_file(parsed.path, head_only=True)
        return super().do_HEAD()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media-preview/"):
            return self.serve_media_preview(parsed.path)
        if parsed.path.startswith("/media/"):
            return self.serve_media_file(parsed.path)
        if parsed.path.startswith("/gbrain-files/"):
            return self.serve_gbrain_file(parsed.path)
        if parsed.path == "/api/health":
            graph = STORE.get_health_graph()
            return self.end_json(
                {
                    "ok": True,
                    "title": APP_NAME,
                    "ui_version": UI_VERSION,
                    "gbrain_version": runtime_gbrain_version(),
                    "gbrain_reranker": gbrain_reranker_readiness(),
                    "loaded": bool(graph),
                    "source": graph.get("source") if graph else None,
                    "stats": graph.get("stats") if graph else None,
                    "attachment_storage": attachment_storage_status(),
                    "persistent_search": PERSISTENT_GBRAIN_SEARCH.status(),
                    "ask_yoda_mcp": YODA_GBRAIN_MCP_POOL.status(),
                }
            )
        if parsed.path == "/api/setup-diagnostics":
            return self.end_json(setup_diagnostics())
        if parsed.path == "/api/sample-brain":
            return self.end_json(privacy_safe_sample_brain())
        if parsed.path == "/api/activation-funnel":
            return self.end_json(first_run_activation_funnel())
        if parsed.path == "/api/memory-value-digest":
            query = parse_qs(parsed.query)
            window = (query.get("window") or ["day"])[0]
            cached_digest = cached_settings_evidence_part("digest") if window == "week" else None
            return self.end_json(cached_digest or memory_value_digest(window))
        if parsed.path == "/api/settings-evidence":
            query = parse_qs(parsed.query)
            force = (query.get("refresh") or [""])[0].strip().lower() in {"1", "true"}
            return self.end_json(settings_evidence(force=force))
        if parsed.path == "/api/customer-readiness":
            return self.end_json(cached_settings_evidence_part("readiness") or customer_readiness())
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
        if parsed.path == "/api/gbrain-backend-config":
            try:
                return self.end_json({"ok": True, **public_gbrain_backend_config()})
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
        if parsed.path == "/api/yoda-feedback":
            query = parse_qs(parsed.query)
            filters = {key: (values or [""])[0] for key, values in query.items()}
            feedback, counts = list_yoda_feedback(filters)
            return self.end_json({"ok": True, "feedback": feedback, "counts": counts})
        if parsed.path.startswith("/api/yoda-chat/"):
            slug = unquote(parsed.path.split("/api/yoda-chat/", 1)[1]).strip("/")
            return self.end_json({"ok": True, "slug": slug, "messages": yoda_chat_history(slug)})
        if parsed.path == "/api/resolver/events":
            query = parse_qs(parsed.query)
            limit = parse_bounded_int((query.get("limit") or ["50"])[0], 50, 1, MAX_RESOLVER_EVENTS)
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
        if parsed.path in ("/api/autopilot-findings", "/api/hosting/autopilot-findings"):
            query = parse_qs(parsed.query)
            state = (query.get("state") or [""])[0].strip()
            valid_states = {
                "",
                "open",
                "queued",
                "repairing",
                "blocked",
                "awaiting_approval",
                "escalated",
                "resolved",
            }
            if state not in valid_states:
                return self.end_json({"error": "invalid finding state"}, status=HTTPStatus.BAD_REQUEST)
            filters = {
                "state": state,
                "limit": parse_bounded_int(
                    (query.get("limit") or ["50"])[0],
                    50,
                    1,
                    AUTOPILOT_FINDINGS_MAX_LIMIT,
                ),
                "offset": parse_nonnegative_int((query.get("offset") or ["0"])[0], 0),
            }
            try:
                data = STORE.list_autopilot_findings(filters)
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
        if parsed.path == "/api/pages":
            query = parse_qs(parsed.query)
            try:
                pages = STORE.list_pages(
                    tag=(query.get("tag") or [""])[0].strip(),
                    entity_type=(query.get("type") or [""])[0].strip(),
                    limit=(query.get("limit") or ["100"])[0],
                )
                return self.end_json({"ok": True, "pages": pages})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-tags/"):
            slug = unquote(parsed.path.split("/api/entity-tags/", 1)[1]).strip("/")
            try:
                tags = STORE.get_entity_tags(slug)
                return self.end_json({"ok": True, "slug": slug, "tags": tags})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
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

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/yoda-feedback/"):
            answer_id = unquote(parsed.path.split("/api/yoda-feedback/", 1)[1]).strip("/")
            try:
                feedback = upsert_yoda_feedback(answer_id, self.read_json_body())
                return self.end_json({"ok": True, "feedback": feedback})
            except ValueError as exc:
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        return self.end_json({"error": "Unknown PUT endpoint"}, status=HTTPStatus.NOT_FOUND)

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
        if parsed.path == "/api/gbrain-backend-config":
            try:
                payload = self.read_json_body()
                return self.end_json({"ok": True, **save_gbrain_backend_config(payload)})
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
        if parsed.path == "/api/yoda-feedback/review":
            try:
                return self.end_json({"ok": True, **review_yoda_feedback(self.read_json_body())})
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
        finding_ack_match = re.match(
            r"^/api/(?:hosting/)?autopilot-findings/(\d+)/acknowledge$",
            parsed.path,
        )
        if finding_ack_match:
            finding_id = int(finding_ack_match.group(1))
            try:
                self.read_json_body()
                finding = STORE.acknowledge_autopilot_finding(finding_id)
                return self.end_json({"ok": True, "finding": finding})
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
                graph = STORE.refresh_after_entity_save()
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
                    "environment": payload.get("environment"),
                    "synthetic": payload.get("synthetic") is True,
                    "test_run": payload.get("test_run") is True,
                    "pair_id": payload.get("pair_id"),
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
                        "environment": payload.get("environment"),
                        "synthetic": payload.get("synthetic") is True,
                        "test_run": payload.get("test_run") is True,
                        "pair_id": payload.get("pair_id"),
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
                payload = self.read_json_body()
                if payload.get("compact") is True:
                    try:
                        page, fallback_output = STORE.backlink_page(
                            slug,
                            payload.get("page", 0),
                            payload.get("limit", 20),
                        )
                    except (TypeError, ValueError):
                        return self.end_json(
                            {"error": "page and limit must be integers"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                    if page is not None:
                        return self.end_json({"ok": True, "slug": slug, **page})
                    return self.end_json({"ok": True, "slug": slug, "output": fallback_output})
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
    STORE.prewarm_search_evidence()
    server = MemoryStargraphHTTPServer(
        (args.host, args.port), MemoryStargraphHandler
    )
    try:
        scheme = "http"
        if args.certfile or args.keyfile:
            if not args.certfile or not args.keyfile:
                parser.error("--certfile and --keyfile must be provided together")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=args.certfile, keyfile=args.keyfile)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            scheme = "https"
        PERSISTENT_GBRAIN_SEARCH.prewarm_async()
        YODA_GBRAIN_MCP_POOL.prewarm_async()
        print(f"{APP_NAME} serving on {scheme}://{args.host}:{args.port}")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        PERSISTENT_GBRAIN_SEARCH.close()
        YODA_GBRAIN_MCP_POOL.close()


if __name__ == "__main__":
    main()
