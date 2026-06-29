#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import subprocess
import threading
import time
from collections import defaultdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.parse import parse_qs


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
VIEW_SCHEMA_VERSION = 5
UI_VERSION = "V1.0.8"
ROOT_INDEX_SLUG = "index"
PART_SLUG_RE = re.compile(r"^(?P<base>.+?)/part-\d{1,3}$", re.IGNORECASE)
PART_LABEL_RE = re.compile(r"^(?P<base>.+?)\s*[-–]\s*Part\s+\d{1,3}$", re.IGNORECASE)
GBRAIN_USAGE_RE = re.compile(r"^agent/reports/gbrain-usage-\d{4}-\d{2}-\d{2}$", re.IGNORECASE)
BLOCKED_SLUGS = {"people/tony-gu"}
BLOCKED_LABELS = {"people/tony gu", "people/tony-gu", "tony gu"}


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


def run_gbrain(*args, input_text=None):
    if not GBRAIN.exists():
        raise FileNotFoundError(f"gbrain not found at {GBRAIN}")
    command = [str(GBRAIN), *args]
    env = os.environ.copy()
    env["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=env,
        input=input_text,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        message = stderr or stdout or f"gbrain exited with status {result.returncode}"
        raise RuntimeError(message)
    return result.stdout


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


def parse_neighbors(raw_text, center_slug):
    try:
        graph_nodes = json.loads(raw_text)
    except json.JSONDecodeError:
        graph_nodes = None
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
                if target and target != source:
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
    try:
        graph_nodes = json.loads(raw_text)
    except json.JSONDecodeError:
        graph_nodes = None
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
            if source and target and source != target and link_type:
                edge_types[edge_key(source, target)].add(link_type)
    return edge_types


def parse_backlinks(raw_text, center_slug):
    edges = set()
    try:
        backlinks = json.loads(raw_text)
    except json.JSONDecodeError:
        backlinks = None

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
    try:
        backlinks = json.loads(raw_text)
    except json.JSONDecodeError:
        backlinks = None
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


def make_label(slug):
    slug_text = str(slug or "").strip().rstrip("/")
    leaf = slug_text.split("/")[-1] if "/" in slug_text else slug_text
    cleaned = leaf.replace("-", " ").replace("_", " ").strip()
    words = [word.capitalize() for word in cleaned.split()]
    return " ".join(words) if words else slug_text


def friendly_label(slug, label=None):
    slug_text = str(slug or "").strip()
    label_text = str(label or "").strip()
    if not label_text:
        return make_label(slug_text)
    category = slug_text.split("/", 1)[0].lower() if "/" in slug_text else ""
    if category and label_text.lower().startswith(f"{category}/"):
        return make_label(slug_text)
    return label_text


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
    discovered_edges = parse_neighbors(graph_output, center_slug)
    merge_edge_types(edge_types, parse_link_types(graph_output, center_slug))
    backlinks_output = run_gbrain("backlinks", center_slug)
    discovered_edges.update(parse_backlinks(backlinks_output, center_slug))
    merge_edge_types(edge_types, parse_backlink_types(backlinks_output, center_slug))
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
        item_label = friendly_label(normalized_slug, item.get("label"))
        if normalized_slug in deleted_slugs or is_blocked_entity(normalized_slug, item_label):
            continue
        item_label = friendly_label(normalized_slug, item.get("label"))
        group_slug, group_label, collapsed, collapse_kind = graph_identity(normalized_slug, item_label)
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

    def get_entity(self, slug):
        graph = self.get_seed_graph()
        node_map = {node["slug"]: node for node in graph["nodes"]}
        if slug not in node_map:
            return None
        node = node_map[slug]
        if not node.get("summary") or node.get("summary") == "No summary available.":
            try:
                page_output = run_gbrain("get", slug)
                meta, body = parse_frontmatter(page_output)
                if meta.get("title"):
                    node["label"] = str(meta["title"])
                if meta.get("type"):
                    node["type"] = str(meta["type"])
                blocks = [re.sub(r"^#+\s*", "", block.strip()) for block in re.split(r"\n\s*\n", body)]
                summary = next((block for block in blocks if block and block != node["label"]), "")
                node["summary"] = summary[:720] if summary else node.get("summary", "No summary available.")
            except Exception as exc:  # noqa: BLE001
                node["summary"] = f"{node.get('summary') or 'No summary available.'} Detail refresh failed: {exc}"
        edge_types = {edge_key(edge["source"], edge["target"]): edge.get("types") or [] for edge in graph.get("edges", [])}
        neighbors = []
        for item in node["links"]:
            if item not in node_map:
                continue
            neighbor = dict(node_map[item])
            neighbor["link_types"] = sorted(edge_types.get(edge_key(slug, item), []))
            neighbors.append(neighbor)
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
        graph = self.get_seed_graph()
        if slug not in {node["slug"] for node in graph["nodes"]}:
            return None
        return run_gbrain("get", slug)

    def save_entity_raw(self, slug, content):
        run_gbrain("put", slug, input_text=content)
        self.invalidate()

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
        return run_gbrain("query", f"{question} Related node: {slug}")

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
        return run_gbrain(*command)

    def attach_file(self, slug, file_path):
        run_gbrain("files", "upload", file_path, "--page", slug)
        self.invalidate()

    def history(self, slug):
        return run_gbrain("history", slug)

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

    def do_GET(self):
        parsed = urlparse(self.path)
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
        if parsed.path.startswith("/api/entity-ask/"):
            slug = unquote(parsed.path.split("/api/entity-ask/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                question = str(payload.get("question") or "").strip()
                if not question:
                    return self.end_json({"error": "question is required"}, status=HTTPStatus.BAD_REQUEST)
                output = STORE.ask_gbrain(slug, question)
                return self.end_json({"ok": True, "slug": slug, "output": output})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
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
                output = STORE.graph_query(
                    slug,
                    str(payload.get("link_type") or "").strip(),
                    str(payload.get("direction") or "both").strip(),
                    str(payload.get("depth") or "1").strip(),
                )
                return self.end_json({"ok": True, "slug": slug, "output": output})
            except Exception as exc:  # noqa: BLE001
                return self.end_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
        if parsed.path.startswith("/api/entity-attach-file/"):
            slug = unquote(parsed.path.split("/api/entity-attach-file/", 1)[1]).strip("/")
            try:
                payload = self.read_json_body()
                file_path = str(payload.get("file_path") or "").strip()
                if not file_path:
                    return self.end_json({"error": "file_path is required"}, status=HTTPStatus.BAD_REQUEST)
                STORE.attach_file(slug, file_path)
                graph = STORE.get_seed_graph(force=True)
                return self.end_json({"ok": True, "slug": slug, "graph": graph})
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
    args = parser.parse_args()

    ensure_data_dir()
    server = ThreadingHTTPServer((args.host, args.port), MemoryStargraphHandler)
    print(f"{APP_NAME} serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
