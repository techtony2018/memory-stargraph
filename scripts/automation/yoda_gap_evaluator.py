#!/usr/bin/env python3
"""Daily Ask Yoda gap evaluator helper.

This helper deliberately does not call a Codex/ChatGPT API. The Daily Learning
Intake worker is the Codex-side reviewer: it runs the Yoda API questions, fills
or reviews Codex comparison fields, then creates bounded TODOs only when gaps are
evidence-qualified.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


DEFAULT_BASE_URL = "http://127.0.0.1:8788"
DEFAULT_DEPTH = 4
DEFAULT_MIN_QUESTIONS = 10
DEFAULT_QUESTION_LOG = Path("data/yoda_gap_evaluator_question_log.json")
PACIFIC = ZoneInfo("America/Los_Angeles")


Question = dict[str, str]
PostYoda = Callable[[str, dict[str, Any]], dict[str, Any]]


def pacific_run_id(now: datetime | None = None) -> str:
    current = (now or datetime.now(PACIFIC)).astimezone(PACIFIC)
    return current.strftime("%Y%m%dT%H%M%S%z")


def default_question_suite() -> list[Question]:
    return [
        {
            "id": "dev-cycle-gaps",
            "slug": "goals/memory-stargraph-continuous-learning-local-knowledge-os",
            "intent": "daily dev gap discovery",
            "question": "From recent daily dev Runs, commits, TODO movement, and Learnings, what gaps still block Memory Stargraph from the continuous-learning local knowledge OS goal?",
        },
        {
            "id": "monitoring-gaps",
            "slug": "goals/memory-stargraph-continuous-learning-local-knowledge-os",
            "intent": "monitoring gap discovery",
            "question": "Looking at monitoring, SRE reports, health checks, backups, and resolver evidence, what reliability or observability gaps should be fixed next?",
        },
        {
            "id": "todo-priority-gaps",
            "slug": "notes/memory-starmap-todo-list",
            "intent": "TODO prioritization gap discovery",
            "question": "Which planned or failed TODOs appear under-prioritized, stale, duplicated, or missing acceptance evidence, and why?",
        },
        {
            "id": "todo-feedback-loop",
            "slug": "notes/memory-starmap-todo-list",
            "intent": "TODO feedback-loop gap discovery",
            "question": "Where does the loop from external evidence to TODO to implementation to Run evidence to durable Learning break down?",
        },
        {
            "id": "logs-learning-gaps",
            "slug": "notes/memory-stargraph-automation-runbook",
            "intent": "logs and runbook gap discovery",
            "question": "From recent worker logs and runbook rules, what repeated failure patterns are not yet turned into reliable automation behavior?",
        },
        {
            "id": "ask-yoda-quality",
            "slug": "products/memory-stargraph",
            "intent": "Ask Yoda quality gap discovery",
            "question": "What Ask Yoda answer-quality gaps are visible from recent history, logs, feedback, and retrieval behavior?",
        },
        {
            "id": "data-quality-gaps",
            "slug": "products/memory-stargraph",
            "intent": "relationship and backlink gap discovery",
            "question": "Which data-quality, relationship, backlink, or capture-quality gaps would most improve future Ask Yoda answers?",
        },
        {
            "id": "ux-gaps",
            "slug": "products/memory-stargraph",
            "intent": "user experience gap discovery",
            "question": "What usability or onboarding gaps make Memory Stargraph harder to use than it should be?",
        },
        {
            "id": "automation-governance",
            "slug": "notes/memory-stargraph-automation-runbook",
            "intent": "automation governance gap discovery",
            "question": "Which worker coordination, Product Owner watch, or human-control gaps could cause silent failures or unsafe automation?",
        },
        {
            "id": "adoption-productization",
            "slug": "products/memory-stargraph",
            "intent": "productization gap discovery",
            "question": "What productization, packaging, or customer-adoption gaps are now evident from daily dev, monitoring, TODOs, and logs?",
        },
        {
            "id": "source-sync-readiness",
            "slug": "notes/memory-stargraph-automation-runbook",
            "intent": "source-sync and worker readiness gap discovery",
            "question": "Which source-sync, checkout freshness, or worker startup safeguards still need improvement before recurring workers can run without stale local context?",
        },
        {
            "id": "sre-resilience-gaps",
            "slug": "notes/memory-stargraph-automation-runbook",
            "intent": "weekly resilience gap discovery",
            "question": "Which restore, backup, rollback, load, or capacity assumptions still lack weekly resilience evidence?",
        },
        {
            "id": "capture-quality-regressions",
            "slug": "notes/memory-starmap-capture-list",
            "intent": "capture quality gap discovery",
            "question": "Which recent capture, enrichment, title, provenance, or attachment patterns suggest a data-quality regression worth investigating?",
        },
        {
            "id": "resolver-isolation",
            "slug": "products/memory-stargraph",
            "intent": "resolver isolation gap discovery",
            "question": "Where could synthetic resolver, Ask Yoda, or worker probes contaminate production feedback or hide user-facing quality problems?",
        },
        {
            "id": "po-team-governance",
            "slug": "goals/memory-stargraph-continuous-learning-local-knowledge-os",
            "intent": "Product Owner team-governance gap discovery",
            "question": "Which repeated worker blockers show that Product Owner should evolve a prompt, runbook, automation, or permission boundary instead of forwarding the same problem again?",
        },
        {
            "id": "first-value-demo",
            "slug": "products/memory-stargraph",
            "intent": "first-value onboarding gap discovery",
            "question": "What first-value demo, sample brain, or guided onboarding gap most blocks a new user from understanding Memory Stargraph quickly?",
        },
    ]


def read_question_suite(path: Path | None, min_questions: int = DEFAULT_MIN_QUESTIONS) -> list[Question]:
    if path is None:
        suite = default_question_suite()
    else:
        data = json.loads(path.read_text())
        suite = data.get("questions", data) if isinstance(data, dict) else data
    if not isinstance(suite, list):
        raise ValueError("question suite must be a list")
    cleaned: list[Question] = []
    for index, item in enumerate(suite, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"question {index} must be an object")
        question = str(item.get("question") or "").strip()
        slug = str(item.get("slug") or "").strip()
        if not question or not slug:
            raise ValueError(f"question {index} requires slug and question")
        cleaned.append({
            "id": str(item.get("id") or f"q{index:02d}").strip(),
            "slug": slug,
            "intent": str(item.get("intent") or "gap discovery").strip(),
            "question": question,
        })
    if len(cleaned) < min_questions:
        raise ValueError(f"at least {min_questions} questions are required")
    ids = [item["id"] for item in cleaned]
    if len(set(ids)) != len(ids):
        raise ValueError("question ids must be unique")
    return cleaned


def read_question_log(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"_schema": "memory-stargraph-yoda-gap-question-log-v1", "no_noticeable_gap": {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("question log must be a JSON object")
    data.setdefault("_schema", "memory-stargraph-yoda-gap-question-log-v1")
    no_gap = data.setdefault("no_noticeable_gap", {})
    if not isinstance(no_gap, dict):
        raise ValueError("question log no_noticeable_gap must be an object")
    return data


def no_gap_question_ids(log: dict[str, Any]) -> set[str]:
    no_gap = log.get("no_noticeable_gap")
    if not isinstance(no_gap, dict):
        return set()
    return {str(key) for key in no_gap}


def select_question_suite(
    suite: list[Question],
    *,
    question_log: dict[str, Any] | None = None,
    min_questions: int = DEFAULT_MIN_QUESTIONS,
) -> list[Question]:
    suppressed = no_gap_question_ids(question_log or {})
    fresh = [item for item in suite if item["id"] not in suppressed]
    if len(fresh) >= min_questions:
        return fresh[:min_questions]
    selected_ids = {item["id"] for item in fresh}
    fallback = [item for item in suite if item["id"] not in selected_ids]
    selected = fresh + fallback[: max(0, min_questions - len(fresh))]
    if len(selected) < min_questions:
        raise ValueError(f"at least {min_questions} selectable questions are required")
    return selected


def make_http_post_yoda(base_url: str, timeout: float = 120.0) -> PostYoda:
    normalized = base_url.rstrip("/")

    def post(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{normalized}/api/entity-ask-yoda/{quote(slug, safe='')}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local/operator supplied endpoint
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ask Yoda API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Ask Yoda API request failed: {exc}") from exc

    return post


def run_suite(
    suite: list[Question],
    *,
    post_yoda: PostYoda,
    run_id: str | None = None,
    depth: int = DEFAULT_DEPTH,
    output_path: Path | None = None,
) -> dict[str, Any]:
    current_run_id = run_id or pacific_run_id()
    rows: list[dict[str, Any]] = []
    for item in suite:
        pair_id = f"yoda-evaluator:{current_run_id}:{item['id']}"
        payload = {
            "question": item["question"],
            "history": [],
            "depth": depth,
            "environment": "test",
            "synthetic": True,
            "test_run": True,
            "pair_id": pair_id,
        }
        started = time.time()
        response = post_yoda(item["slug"], payload)
        rows.append({
            **item,
            "pair_id": pair_id,
            "request_id": response.get("request_id", ""),
            "ok": response.get("ok") is not False and "error" not in response,
            "yoda_answer": response.get("output", ""),
            "yoda_source": response.get("source", ""),
            "diagnostics": response.get("diagnostics", {}),
            "timings": response.get("timings", {}),
            "elapsed_ms": round((time.time() - started) * 1000),
            "codex_answer": "",
            "gap": {
                "decision": "pending_codex_review",
                "summary": "Daily Learning Intake must answer the same question in Codex and compare before promotion.",
            },
        })
    snapshot = {
        "metadata": {
            "run_id": current_run_id,
            "created_at": datetime.now(PACIFIC).isoformat(),
            "question_count": len(rows),
            "depth": depth,
            "provenance": {
                "environment": "test",
                "synthetic": True,
                "test_run": True,
                "producer": "yoda_gap_evaluator",
            },
        },
        "questions": rows,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    return snapshot


def build_comparison_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    questions = snapshot.get("questions") if isinstance(snapshot, dict) else []
    if not isinstance(questions, list):
        questions = []
    candidates = []
    reviewed = 0
    for row in questions:
        if not isinstance(row, dict):
            continue
        gap = row.get("gap") if isinstance(row.get("gap"), dict) else {}
        decision = str(gap.get("decision") or "").strip()
        if decision and decision != "pending_codex_review":
            reviewed += 1
        if decision != "todo_candidate":
            continue
        evidence_items = gap.get("evidence") if isinstance(gap.get("evidence"), list) else []
        evidence_summary = "; ".join(str(item).strip() for item in evidence_items if str(item).strip())
        summary = str(gap.get("summary") or "Yoda/Codex comparison identified a gap.").strip()
        evidence_summary = f"{summary} Evidence: {evidence_summary}" if evidence_summary else summary
        candidates.append({
            "source_question_id": row.get("id", ""),
            "source_slug": row.get("slug", ""),
            "title": str(gap.get("title") or f"Investigate Ask Yoda gap from {row.get('id', 'question')}").strip(),
            "priority": str(gap.get("severity") or "P2").strip(),
            "question": row.get("question", ""),
            "yoda_answer_excerpt": str(row.get("yoda_answer") or "")[:500],
            "codex_answer_excerpt": str(row.get("codex_answer") or "")[:500],
            "evidence_summary": evidence_summary,
        })
    metadata = dict(snapshot.get("metadata") or {})
    metadata.update({
        "reviewed_count": reviewed,
        "candidate_count": len(candidates),
    })
    return {
        "metadata": metadata,
        "todo_candidates": candidates,
        "review_instruction": "Create or update Memory Stargraph TODOs only for bounded, deduplicated, evidence-backed candidates.",
    }


def update_no_gap_question_log(snapshot: dict[str, Any], path: Path) -> dict[str, Any]:
    log = read_question_log(path)
    no_gap = log.setdefault("no_noticeable_gap", {})
    metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
    run_id = str(metadata.get("run_id") or "").strip()
    now = datetime.now(PACIFIC).isoformat()
    added = 0
    updated = 0
    for row in snapshot.get("questions", []):
        if not isinstance(row, dict):
            continue
        gap = row.get("gap") if isinstance(row.get("gap"), dict) else {}
        if str(gap.get("decision") or "").strip() != "no_action":
            continue
        question_id = str(row.get("id") or "").strip()
        if not question_id:
            continue
        existing = no_gap.get(question_id)
        if isinstance(existing, dict):
            updated += 1
        else:
            existing = {"first_logged_at": now, "runs": []}
            no_gap[question_id] = existing
            added += 1
        runs = existing.setdefault("runs", [])
        if run_id and run_id not in runs:
            runs.append(run_id)
        existing.update({
            "last_logged_at": now,
            "slug": str(row.get("slug") or "").strip(),
            "intent": str(row.get("intent") or "").strip(),
            "question": str(row.get("question") or "").strip(),
            "decision": "no_action",
            "summary": str(gap.get("summary") or "").strip(),
            "yoda_answer_excerpt": str(row.get("yoda_answer") or "")[:500],
            "codex_answer_excerpt": str(row.get("codex_answer") or "")[:500],
        })
    log["updated_at"] = now
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n")
    return {"path": str(path), "added": added, "updated": updated, "suppressed_count": len(no_gap)}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or summarize the daily Ask Yoda gap evaluator.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run", help="Ask Yoda at least 10 synthetic evaluator questions.")
    run_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    run_parser.add_argument("--suite", type=Path)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--run-id", default="")
    run_parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    run_parser.add_argument("--min-questions", type=int, default=DEFAULT_MIN_QUESTIONS)
    run_parser.add_argument("--question-log", type=Path, default=DEFAULT_QUESTION_LOG)

    report_parser = subcommands.add_parser("report", help="Build TODO-candidate report from a Codex-reviewed snapshot.")
    report_parser.add_argument("--snapshot", type=Path, required=True)
    report_parser.add_argument("--output", type=Path, required=True)
    report_parser.add_argument("--question-log", type=Path, default=DEFAULT_QUESTION_LOG)
    report_parser.add_argument("--no-update-question-log", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            suite = read_question_suite(args.suite, args.min_questions)
            question_log = read_question_log(args.question_log)
            suite = select_question_suite(suite, question_log=question_log, min_questions=args.min_questions)
            snapshot = run_suite(
                suite,
                post_yoda=make_http_post_yoda(args.base_url),
                run_id=args.run_id or None,
                depth=args.depth,
                output_path=args.output,
            )
            print(json.dumps({
                "ok": True,
                "output": str(args.output),
                "question_log": str(args.question_log),
                "suppressed_no_gap_questions": len(no_gap_question_ids(question_log)),
                **snapshot["metadata"],
            }, sort_keys=True))
            return 0
        if args.command == "report":
            snapshot = load_json(args.snapshot)
            report = build_comparison_report(snapshot)
            if not args.no_update_question_log:
                report["metadata"]["question_log"] = update_no_gap_question_log(snapshot, args.question_log)
            write_json(args.output, report)
            print(json.dumps({"ok": True, "output": str(args.output), **report["metadata"]}, sort_keys=True))
            return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
