#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import server


DEFAULT_QUERIES = [
    "static interface health diagnostics version mismatch",
    "optional timeout telemetry is not a todo",
    "restore weekly resilience rehearsal cadence",
]


def prepare_benchmark_store(store: server.GraphStore, transport: str, timeout: float = 15) -> dict[str, object]:
    if transport == "cli":
        server.PERSISTENT_GBRAIN_SEARCH.close()
        return {"transport": "cli", "persistent_ready": False, "evidence_types_ready": 0}

    store.prewarm_search_evidence(timeout=timeout)
    server.PERSISTENT_GBRAIN_SEARCH.prewarm_async(timeout=timeout)
    deadline = time.monotonic() + timeout
    persistent_ready = False
    while time.monotonic() < deadline:
        status = server.PERSISTENT_GBRAIN_SEARCH.status()
        if status.get("ready") and not status.get("busy"):
            persistent_ready = True
            break
        time.sleep(0.05)
    evidence_types_ready = sum(
        store.evidence_list_cache.wait_for_refresh(page_type, 40, max(0, deadline - time.monotonic()))
        is not None
        for page_type in server.EVIDENCE_SEARCH_TYPES
    )
    return {
        "transport": "persistent",
        "persistent_ready": persistent_ready,
        "evidence_types_ready": evidence_types_ready,
    }


def run_evidence_case(query: str, store: server.GraphStore | None = None) -> dict[str, object]:
    store = store or server.GraphStore()
    started = time.perf_counter()
    results, status, cache_status = server.evidence_record_search_results(
        query,
        per_type_timeout=10,
        row_cache=store.evidence_list_cache,
    )
    return {
        "query": query,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "status": status,
        "cache_status": cache_status,
        "result_count": len(results),
        "top_slug": results[0]["slug"] if results else None,
    }


def run_full_case(query: str, store: server.GraphStore | None = None) -> dict[str, object]:
    store = store or server.GraphStore()
    started = time.perf_counter()
    graph = store.search(query)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    coverage = graph["source"]["coverage"]
    return {
        "query": query,
        "elapsed_ms": elapsed_ms,
        "search_elapsed_ms": coverage.get("search_elapsed_ms"),
        "status": coverage.get("search_status"),
        "primary_status": coverage.get("search_primary_status"),
        "primary_cache_status": coverage.get("search_primary_cache_status"),
        "evidence_status": coverage.get("search_evidence_status"),
        "evidence_cache_status": coverage.get("search_evidence_cache_status"),
        "top_slug": (coverage.get("search_slugs") or [None])[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Memory Stargraph Search against the local GBrain store.")
    parser.add_argument("--mode", choices=("evidence", "full"), default="full")
    parser.add_argument("--transport", choices=("persistent", "cli"), default="persistent")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument(
        "--cold-each-case",
        action="store_true",
        help="Use a fresh GraphStore for every full-search case.",
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    store = server.GraphStore()
    preparation = prepare_benchmark_store(store, args.transport)
    try:
        if args.mode == "evidence":
            runner = lambda query: run_evidence_case(query, store)
        elif args.cold_each_case:
            runner = lambda query: run_full_case(query, server.GraphStore())
        else:
            runner = lambda query: run_full_case(query, store)
        results = [runner(query) for _ in range(args.repeat) for query in (args.queries or DEFAULT_QUERIES)]
    finally:
        if args.transport == "persistent":
            server.PERSISTENT_GBRAIN_SEARCH.close()
    elapsed_values = [int(result["elapsed_ms"]) for result in results]
    payload = {
        "mode": args.mode,
        "transport": args.transport,
        "preparation": preparation,
        "repeat": args.repeat,
        "cold_each_case": args.cold_each_case,
        "case_count": len(results),
        "median_elapsed_ms": round(statistics.median(elapsed_values)),
        "complete_count": sum(1 for result in results if result["status"] == "complete"),
        "results": results,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
