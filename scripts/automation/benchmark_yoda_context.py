#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import server


PACIFIC = ZoneInfo("America/Los_Angeles")
DEFAULT_BASELINE_MS = 33375
DEFAULT_CASES = [
    {
        "id": "person-high-degree",
        "slug": "people/tony-guan",
        "depth": 4,
        "cold_question": "What projects and operating systems are most connected to Tony?",
        "warm_question": "Which recent Memory Stargraph work should Tony inspect next?",
        "expected_targets": ["people/tony-guan"],
        "force_slow_graph": True,
    },
    {
        "id": "todo-active",
        "slug": "notes/memory-starmap-todo-list",
        "depth": 3,
        "cold_question": "Which active implementation items are highest priority?",
        "warm_question": "What recently completed work provides context for the active queue?",
        "expected_targets": ["notes/memory-starmap-todo-list"],
        "expire_cache_before_cold": True,
    },
    {
        "id": "product",
        "slug": "products/memory-stargraph",
        "depth": 4,
        "cold_question": "What are the product's current reliability and usability priorities?",
        "warm_question": "Which runbooks and goals guide this product?",
        "expected_targets": ["products/memory-stargraph"],
    },
    {
        "id": "goal",
        "slug": "goals/memory-stargraph-continuous-learning-local-knowledge-os",
        "depth": 3,
        "cold_question": "What outcomes define success for this goal?",
        "warm_question": "Which operating principles preserve human control?",
        "expected_targets": ["goals/memory-stargraph-continuous-learning-local-knowledge-os"],
    },
    {
        "id": "attachment-runbook",
        "slug": "docs/gbrain-attachment-runbook",
        "depth": 2,
        "cold_question": "What evidence proves an attachment is durably stored?",
        "warm_question": "What must be checked before replacing an attachment?",
        "expected_targets": ["docs/gbrain-attachment-runbook"],
    },
    {
        "id": "capture-queue",
        "slug": "notes/memory-starmap-capture-list",
        "depth": 2,
        "cold_question": "What is the current capture queue state?",
        "warm_question": "How are terminal capture requests represented?",
        "expected_targets": ["notes/memory-starmap-capture-list"],
    },
    {
        "id": "organization",
        "slug": "organizations/cfer-foundation",
        "depth": 3,
        "cold_question": "Who and what is directly connected to this organization?",
        "warm_question": "Which relationships provide the strongest grounding?",
        "expected_targets": ["organizations/cfer-foundation"],
    },
    {
        "id": "captured-media",
        "slug": "media/x-ecalifornians-status-2071774149987680569",
        "depth": 2,
        "cold_question": "What does this captured post say about Memory Stargraph?",
        "warm_question": "Which authors and products are connected to this post?",
        "expected_targets": ["media/x-ecalifornians-status-2071774149987680569"],
    },
    {
        "id": "remote-media-runbook",
        "slug": "docs/memory-stargraph-remote-gbrain-media-import-runbook",
        "depth": 2,
        "cold_question": "How should a non-host recover attachment bytes?",
        "warm_question": "What does the cold-cache release gate require?",
        "expected_targets": ["docs/memory-stargraph-remote-gbrain-media-import-runbook"],
    },
    {
        "id": "root-index",
        "slug": "index",
        "depth": 2,
        "cold_question": "What are the major navigation hubs in this knowledge graph?",
        "warm_question": "Which product and goal should a new user open first?",
        "expected_targets": ["index"],
    },
]


def grounding_result(prompt: str, expected_targets: list[str]) -> dict[str, float | int]:
    matches = sum(1 for target in expected_targets if target in prompt)
    expected = len(expected_targets)
    return {
        "expected": expected,
        "matched": matches,
        "recall": round(matches / expected, 4) if expected else 1.0,
    }


def summarize_results(
    results: list[dict[str, object]],
    baseline_ms: int = DEFAULT_BASELINE_MS,
) -> dict[str, object]:
    cold_values = [int(result["cold_prompt_ms"]) for result in results]
    median_cold = int(statistics.median(cold_values)) if cold_values else 0
    ordered_cold = sorted(cold_values)
    p95_cold = ordered_cold[max(0, math.ceil(len(ordered_cold) * 0.95) - 1)] if ordered_cold else 0
    recalls = [float((result.get("grounding") or {}).get("recall", 0)) for result in results]
    improvement = ((baseline_ms - median_cold) / baseline_ms * 100) if baseline_ms else 0
    return {
        "case_count": len(results),
        "baseline_cold_prompt_ms": baseline_ms,
        "median_cold_prompt_ms": median_cold,
        "p95_cold_prompt_ms": p95_cold,
        "improvement_percent": round(improvement, 2),
        "warm_cache_hits": sum(1 for result in results if result.get("warm_cache_hit") is True),
        "mean_grounding_recall": round(statistics.mean(recalls), 4) if recalls else 0,
        "provider_down_fallbacks": sum(
            1 for result in results if result.get("provider_down_fallback") is True
        ),
        "degraded_cold_cases": sum(
            1 for result in results if result.get("cold_context_degraded") is True
        ),
        "max_cache_entries": max(
            (int(result.get("cache_entries_after_warm") or 0) for result in results),
            default=0,
        ),
    }


def read_health(service_url: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{service_url.rstrip('/')}/api/health", timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "ok": payload.get("ok") is True,
        "ui_version": payload.get("ui_version"),
        "attachment_storage_available": (payload.get("attachment_storage") or {}).get("available"),
    }


def run_case(
    case: dict[str, object],
    store: server.GraphStore | None = None,
) -> dict[str, object]:
    store = store or server.GraphStore()
    captured_prompts: list[str] = []

    def provider_down(prompt: str, return_details: bool = False):
        captured_prompts.append(prompt)
        details = {
            "output": None,
            "backend": "benchmark-provider-down",
            "model": "",
            "model_status": "unavailable",
            "openclaw_status": "not_used",
            "error_summary": "synthetic provider-down benchmark",
            "stdout_preview": "",
            "stderr_preview": "",
        }
        return details if return_details else None

    if case.get("expire_cache_before_cold"):
        for entry in store.yoda_context_cache.values():
            entry["created_at"] = 0

    previous_model = server.run_yoda_model
    previous_gbrain = server.run_gbrain

    def benchmark_gbrain(*args, **kwargs):
        if case.get("force_slow_graph") and args and args[0] == "graph-query":
            raise subprocess.TimeoutExpired(args, timeout=kwargs.get("timeout", 0))
        return previous_gbrain(*args, **kwargs)

    store.ask_gbrain = lambda slug, question: f"Provider-down fallback for {slug}: {question}"
    try:
        server.run_yoda_model = provider_down
        server.run_gbrain = benchmark_gbrain
        cold = store.ask_yoda(
            str(case["slug"]),
            str(case["cold_question"]),
            depth=int(case["depth"]),
        )
        warm = store.ask_yoda(
            str(case["slug"]),
            str(case["warm_question"]),
            depth=int(case["depth"]),
        )
    finally:
        server.run_yoda_model = previous_model
        server.run_gbrain = previous_gbrain

    cold_diagnostics = cold["diagnostics"]
    warm_diagnostics = warm["diagnostics"]
    return {
        "id": case["id"],
        "slug": case["slug"],
        "depth": case["depth"],
        "cold_prompt_ms": cold_diagnostics["timings"]["prompt_ms"],
        "warm_prompt_ms": warm_diagnostics["timings"]["prompt_ms"],
        "cold_cache_hit": cold_diagnostics["context_cache_hit"],
        "warm_cache_hit": warm_diagnostics["context_cache_hit"],
        "cold_subphases_ms": cold_diagnostics["context_subphases_ms"],
        "warm_subphases_ms": warm_diagnostics["context_subphases_ms"],
        "cold_counts": cold_diagnostics["context_counts"],
        "warm_counts": warm_diagnostics["context_counts"],
        "cold_context_degraded": cold_diagnostics["context_degraded"],
        "cold_degraded_reason": cold_diagnostics["context_degraded_reason"],
        "broad_graph_budget_ms": cold_diagnostics["broad_graph_budget_ms"],
        "cache_entries_after_warm": len(store.yoda_context_cache),
        "grounding": grounding_result(
            captured_prompts[0] if captured_prompts else "",
            list(case["expected_targets"]),
        ),
        "provider_down_fallback": cold.get("source") == "fallback"
        and "Provider-down fallback" in str(cold.get("fallback_output") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark privacy-safe Ask Yoda context construction against real GBrain."
    )
    parser.add_argument("--service-url", default="http://127.0.0.1:8788")
    parser.add_argument("--baseline-ms", type=int, default=DEFAULT_BASELINE_MS)
    parser.add_argument("--max-median-cold-ms", type=int, default=15000)
    parser.add_argument("--max-p95-cold-ms", type=int, default=30000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    store = server.GraphStore()
    results = [run_case(case, store=store) for case in DEFAULT_CASES]
    summary = summarize_results(results, args.baseline_ms)
    gate = {
        "median_cold_pass": summary["median_cold_prompt_ms"] <= args.max_median_cold_ms,
        "p95_cold_pass": summary["p95_cold_prompt_ms"] <= args.max_p95_cold_ms,
        "grounding_pass": summary["mean_grounding_recall"] == 1.0,
        "slow_graph_degraded_pass": summary["degraded_cold_cases"] >= 1,
        "multi_key_cache_pass": summary["max_cache_entries"] >= 2,
    }
    payload = {
        "started_at": datetime.now(PACIFIC).replace(microsecond=0).isoformat(),
        "timezone": "America/Los_Angeles",
        "service": read_health(args.service_url),
        "summary": summary,
        "gate": gate,
        "cases": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if all(gate.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
