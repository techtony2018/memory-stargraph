#!/usr/bin/env python3
"""Preflight source checkout freshness without overwriting user changes."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import NamedTuple


DEFAULT_REQUIRED_PATHS = ("scripts/automation/yoda_gap_evaluator.py",)
MAX_PATH_EVIDENCE = 100


class CheckoutSnapshot(NamedTuple):
    root: Path
    head: str
    origin_main: str
    dashboard_ui_version: str
    required_paths: tuple[str, ...] = DEFAULT_REQUIRED_PATHS
    dirty: bool = False
    divergent: bool = False
    dirty_paths: tuple[str, ...] = ()
    untracked_paths: tuple[str, ...] = ()


class SourceSyncDecision(NamedTuple):
    status: str
    action: str
    reason: str
    checkout_head: str
    origin_main: str
    dashboard_ui_version: str
    missing_paths: tuple[str, ...]
    script_path: str | None = None
    dirty_worktree: bool = False
    dirty_paths: tuple[str, ...] = ()
    untracked_paths: tuple[str, ...] = ()


def decide_source_sync(snapshot: CheckoutSnapshot) -> SourceSyncDecision:
    missing_paths = tuple(
        path for path in snapshot.required_paths if not (snapshot.root / path).exists()
    )
    script_path = (
        snapshot.required_paths[0]
        if snapshot.required_paths and not missing_paths
        else None
    )
    if snapshot.divergent:
        return SourceSyncDecision(
            status="divergent_blocked",
            action="use_verified_service_copy",
            reason=(
                "checkout diverged from origin/main; do not sync automatically; "
                "preserve unrelated changes and record source-sync blocker"
            ),
            checkout_head=snapshot.head,
            origin_main=snapshot.origin_main,
            dashboard_ui_version=snapshot.dashboard_ui_version,
            missing_paths=missing_paths,
            script_path=script_path,
            dirty_worktree=snapshot.dirty,
            dirty_paths=snapshot.dirty_paths,
            untracked_paths=snapshot.untracked_paths,
        )
    if snapshot.dirty:
        stale = snapshot.head != snapshot.origin_main or bool(missing_paths)
        return SourceSyncDecision(
            status="stale_dirty_blocked" if stale else "dirty_worktree_blocked",
            action="defer_preserve_local_changes",
            reason=(
                "checkout has tracked local changes; do not sync automatically; "
                "preserve unrelated changes and record source-sync blocker"
            ),
            checkout_head=snapshot.head,
            origin_main=snapshot.origin_main,
            dashboard_ui_version=snapshot.dashboard_ui_version,
            missing_paths=missing_paths,
            script_path=script_path,
            dirty_worktree=True,
            dirty_paths=snapshot.dirty_paths,
            untracked_paths=snapshot.untracked_paths,
        )
    if snapshot.head == snapshot.origin_main and not missing_paths:
        return SourceSyncDecision(
            status="current",
            action="use_workspace",
            reason="checkout HEAD matches origin/main and required scripts exist",
            checkout_head=snapshot.head,
            origin_main=snapshot.origin_main,
            dashboard_ui_version=snapshot.dashboard_ui_version,
            missing_paths=missing_paths,
            script_path=script_path,
            dirty_worktree=False,
            dirty_paths=(),
            untracked_paths=snapshot.untracked_paths,
        )
    return SourceSyncDecision(
        status="stale_clean_fast_forward_required",
        action="fast_forward_sync",
        reason=(
            "checkout is clean but stale or missing required scripts; "
            "fast-forward-only sync can restore source parity"
        ),
        checkout_head=snapshot.head,
        origin_main=snapshot.origin_main,
        dashboard_ui_version=snapshot.dashboard_ui_version,
        missing_paths=missing_paths,
        script_path=script_path,
        dirty_worktree=False,
        dirty_paths=(),
        untracked_paths=snapshot.untracked_paths,
    )


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    # Porcelain status uses the first two columns as data; keep leading spaces.
    return result.stdout.rstrip()


def parse_porcelain_status(output: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    dirty_paths: list[str] = []
    untracked_paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:].strip()
        if not path:
            continue
        target = untracked_paths if status == "??" else dirty_paths
        if len(target) < MAX_PATH_EVIDENCE:
            target.append(path)
    return tuple(dirty_paths), tuple(untracked_paths)


def snapshot_checkout(
    root: Path, dashboard_ui_version: str, required_paths: tuple[str, ...]
) -> CheckoutSnapshot:
    head = run_git(root, "rev-parse", "HEAD") or "unknown"
    origin_main = run_git(root, "rev-parse", "origin/main") or "unknown"
    status_output = run_git(root, "status", "--porcelain", "--untracked-files=all")
    dirty_paths, untracked_paths = parse_porcelain_status(status_output)
    dirty = bool(dirty_paths)
    merge_base = run_git(root, "merge-base", "HEAD", "origin/main")
    divergent = bool(merge_base and merge_base != head and merge_base != origin_main)
    return CheckoutSnapshot(
        root=root,
        head=head,
        origin_main=origin_main,
        dashboard_ui_version=dashboard_ui_version,
        required_paths=required_paths,
        dirty=dirty,
        divergent=divergent,
        dirty_paths=dirty_paths,
        untracked_paths=untracked_paths,
    )


def apply_fast_forward(root: Path) -> bool:
    fetch = subprocess.run(
        ("git", "fetch", "origin", "main"),
        cwd=root,
        check=False,
    )
    if fetch.returncode != 0:
        return False
    merge = subprocess.run(
        ("git", "merge", "--ff-only", "origin/main"),
        cwd=root,
        check=False,
    )
    return merge.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a persistent Memory Stargraph worker checkout matches origin/main."
    )
    parser.add_argument("--root", default=".", help="Checkout root to inspect.")
    parser.add_argument(
        "--dashboard-ui-version",
        default="unknown",
        help="Dashboard-managed Memory Stargraph ui_version observed by the worker.",
    )
    parser.add_argument(
        "--required-path",
        action="append",
        dest="required_paths",
        help="Required script/path that must exist in the worker checkout.",
    )
    parser.add_argument(
        "--sync-clean-fast-forward",
        action="store_true",
        help="If clean and stale, run git fetch origin main and git merge --ff-only origin/main.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    required_paths = tuple(args.required_paths or DEFAULT_REQUIRED_PATHS)
    snapshot = snapshot_checkout(root, args.dashboard_ui_version, required_paths)
    decision = decide_source_sync(snapshot)
    sync_applied = False
    if args.sync_clean_fast_forward and decision.action == "fast_forward_sync":
        sync_applied = apply_fast_forward(root)
        if sync_applied:
            snapshot = snapshot_checkout(root, args.dashboard_ui_version, required_paths)
            decision = decide_source_sync(snapshot)

    payload = {
        "_schema": "memory-stargraph-source-sync-preflight-v1",
        "status": decision.status,
        "action": decision.action,
        "reason": decision.reason,
        "checkout_head": decision.checkout_head,
        "origin_main": decision.origin_main,
        "dashboard_ui_version": decision.dashboard_ui_version,
        "missing_paths": list(decision.missing_paths),
        "script_path": decision.script_path,
        "dirty_state": "tracked_changes" if decision.dirty_worktree else "clean_tracked",
        "dirty_worktree": decision.dirty_worktree,
        "dirty_paths": list(decision.dirty_paths),
        "untracked_paths": list(decision.untracked_paths),
        "dirty_path_evidence_limit": MAX_PATH_EVIDENCE,
        "sync_applied": sync_applied,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "source_sync_status={status} action={action} checkout_head={head} origin_main={origin}".format(
                status=decision.status,
                action=decision.action,
                head=decision.checkout_head,
                origin=decision.origin_main,
            )
        )
        if decision.missing_paths:
            print("missing_required_paths=" + ",".join(decision.missing_paths))
        if decision.script_path:
            print("script_path=" + decision.script_path)
        print("reason=" + decision.reason)
    return 0 if decision.status in {"current", "stale_clean_fast_forward_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
