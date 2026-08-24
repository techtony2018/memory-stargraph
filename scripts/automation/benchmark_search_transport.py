#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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
    "current reliability and usability priorities",
    "runbooks and goals guide this product",
    "active implementation items highest priority",
    "completed work context active queue",
    "outcomes define success local knowledge os",
    "operating principles preserve human control",
    "evidence proves attachment durably stored",
    "checks before replacing an attachment",
    "current capture queue state",
    "terminal capture requests represented",
    "relationships provide strongest grounding",
    "captured post memory stargraph",
    "recover attachment bytes non host",
    "cold cache release gate",
    "major navigation hubs knowledge graph",
    "product and goal new user open first",
    "search evidence source coverage contradiction pruning",
]


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else 0


def timing_summary(rows: list[dict[str, object]], field: str) -> dict[str, int]:
    values = [int(row[field]) for row in rows]
    return {
        "median_ms": round(statistics.median(values)) if values else 0,
        "p95_ms": percentile(values, 0.95),
        "mean_ms": round(statistics.mean(values)) if values else 0,
    }


def run_cli(query: str, timeout: float) -> tuple[int, list[dict[str, object]]]:
    started = time.perf_counter()
    output = server.run_gbrain_subprocess(
        "search",
        query,
        "--limit",
        "20",
        "--snippet-chars",
        "0",
        timeout=timeout,
    )
    return round((time.perf_counter() - started) * 1000), server.parse_search_results(output)


def run_persistent(
    session: server.PersistentGBrainSearch,
    query: str,
    timeout: float,
) -> tuple[int, list[dict[str, object]]]:
    started = time.perf_counter()
    output = session.search_cli_output(
        ("search", query, "--limit", "20", "--snippet-chars", "0"),
        timeout,
    )
    return round((time.perf_counter() - started) * 1000), server.parse_search_results(output)


def benchmark(queries: list[str], timeout: float) -> dict[str, object]:
    session = server.PersistentGBrainSearch()
    try:
        prewarm_started = time.perf_counter()
        session.prewarm_async(timeout=timeout)
        deadline = time.monotonic() + timeout
        while session.prewarming and time.monotonic() < deadline:
            time.sleep(0.02)
        prewarm_ms = round((time.perf_counter() - prewarm_started) * 1000)
        if not session.status()["ready"]:
            raise RuntimeError("persistent GBrain search prewarm failed")

        rows = []
        for index, query in enumerate(queries):
            if index % 2 == 0:
                cli_ms, cli_results = run_cli(query, timeout)
                persistent_ms, persistent_results = run_persistent(session, query, timeout)
                first = "cli"
            else:
                persistent_ms, persistent_results = run_persistent(session, query, timeout)
                cli_ms, cli_results = run_cli(query, timeout)
                first = "persistent"
            rows.append(
                {
                    "query": query,
                    "first": first,
                    "cli_ms": cli_ms,
                    "persistent_ms": persistent_ms,
                    "result_count": len(cli_results),
                    "exact_result_parity": cli_results == persistent_results,
                }
            )

        with session.lock:
            original_pid = session.process.pid
            session.process.kill()
            session.process.wait(timeout=3)
        recovery_started = time.perf_counter()
        recovery_output = session.search_cli_output(
            ("search", "memory stargraph persistent process recovery", "--limit", "20"),
            timeout,
        )
        recovery_ms = round((time.perf_counter() - recovery_started) * 1000)
        with session.lock:
            recovered_pid = session.process.pid

        cli_summary = timing_summary(rows, "cli_ms")
        persistent_summary = timing_summary(rows, "persistent_ms")
        cli_median = int(cli_summary["median_ms"])
        persistent_median = int(persistent_summary["median_ms"])
        improvement = (
            round((cli_median - persistent_median) / cli_median * 100, 2)
            if cli_median
            else 0
        )
        return {
            "case_count": len(rows),
            "prewarm_ms": prewarm_ms,
            "cli": cli_summary,
            "persistent": persistent_summary,
            "median_improvement_percent": improvement,
            "exact_result_parity_count": sum(
                1 for row in rows if row["exact_result_parity"] is True
            ),
            "recovery": {
                "process_restarted": original_pid != recovered_pid,
                "elapsed_ms": recovery_ms,
                "result_count": len(server.parse_search_results(recovery_output)),
            },
            "results": rows,
        }
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare subprocess and persistent stdio GBrain Search transports."
    )
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    print(json.dumps(benchmark(args.queries or DEFAULT_QUERIES, args.timeout), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
