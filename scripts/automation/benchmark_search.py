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


def run_evidence_case(query: str) -> dict[str, object]:
    started = time.perf_counter()
    results, status = server.evidence_record_search_results(query, per_type_timeout=10)
    return {
        "query": query,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "status": status,
        "result_count": len(results),
        "top_slug": results[0]["slug"] if results else None,
    }


def run_full_case(query: str) -> dict[str, object]:
    store = server.GraphStore()
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
        "evidence_status": coverage.get("search_evidence_status"),
        "top_slug": (coverage.get("search_slugs") or [None])[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Memory Stargraph Search against the local GBrain store.")
    parser.add_argument("--mode", choices=("evidence", "full"), default="full")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--query", action="append", dest="queries")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    runner = run_evidence_case if args.mode == "evidence" else run_full_case
    results = [runner(query) for _ in range(args.repeat) for query in (args.queries or DEFAULT_QUERIES)]
    elapsed_values = [int(result["elapsed_ms"]) for result in results]
    payload = {
        "mode": args.mode,
        "repeat": args.repeat,
        "case_count": len(results),
        "median_elapsed_ms": round(statistics.median(elapsed_values)),
        "complete_count": sum(1 for result in results if result["status"] == "complete"),
        "results": results,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
