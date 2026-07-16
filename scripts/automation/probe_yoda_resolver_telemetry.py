#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any


def build_request_payload(
    *,
    question: str,
    depth: int,
    mode: str,
    pair_id: str,
) -> dict[str, Any]:
    stable_pair_id = str(pair_id or "").strip()
    if not stable_pair_id:
        raise ValueError("pair_id is required for auditable verification")
    if mode not in {"test", "production"}:
        raise ValueError("mode must be test or production")
    is_test = mode == "test"
    return {
        "question": str(question or "").strip(),
        "depth": max(1, min(6, int(depth))),
        "environment": "test" if is_test else "production",
        "synthetic": is_test,
        "test_run": is_test,
        "pair_id": stable_pair_id,
    }


def request_json(url: str, *, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    return metadata if isinstance(metadata, dict) else {}


def read_authoritative_events(*, limit: int = 50) -> list[dict[str, Any]]:
    payload = json.dumps({"limit": limit, "producer": "stargraph"})
    result = subprocess.run(
        ["gbrain", "call", "resolver_events_list", payload],
        check=True,
        capture_output=True,
        text=True,
    )
    start = result.stdout.find("{")
    if start < 0:
        raise RuntimeError(f"gbrain resolver event readback was not JSON: {result.stdout!r}")
    response = json.loads(result.stdout[start:])
    events = response.get("events") or []
    return events if isinstance(events, list) else []


def find_event(event_id: str, *, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in read_authoritative_events():
            if str(event.get("event_id") or "") == event_id:
                return event
        time.sleep(1)
    raise TimeoutError(f"resolver event {event_id} was not visible within {timeout}s")


def verify_classification(event: dict[str, Any], *, mode: str, pair_id: str) -> dict[str, Any]:
    metadata = event_metadata(event)
    expected_test = mode == "test"
    observed = {
        "environment": metadata.get("environment"),
        "synthetic": metadata.get("synthetic"),
        "test_run": metadata.get("test_run"),
        "pair_id": metadata.get("pair_id"),
    }
    expected = {
        "environment": "test" if expected_test else "production",
        "synthetic": expected_test,
        "test_run": expected_test,
        "pair_id": pair_id,
    }
    if observed != expected:
        raise RuntimeError(f"resolver provenance mismatch: expected={expected!r} observed={observed!r}")
    return observed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Submit one auditable Ask Yoda telemetry verification request and confirm its resolver provenance."
    )
    parser.add_argument("--service-url", default="http://127.0.0.1:8788")
    parser.add_argument("--slug", default="people/tony-guan")
    parser.add_argument("--question", required=True)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--mode", choices=("test", "production"), required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)

    payload = build_request_payload(
        question=args.question,
        depth=args.depth,
        mode=args.mode,
        pair_id=args.pair_id,
    )
    encoded_slug = urllib.parse.quote(args.slug.strip("/"), safe="")
    response = request_json(
        f"{args.service_url.rstrip('/')}/api/entity-ask-yoda/{encoded_slug}",
        payload=payload,
        timeout=args.timeout,
    )
    event_id = str(response.get("request_id") or "").strip()
    if not event_id:
        raise RuntimeError(f"Ask Yoda response did not include request_id: {response!r}")
    event = find_event(event_id, timeout=args.timeout)
    observed = verify_classification(event, mode=args.mode, pair_id=args.pair_id)
    print(json.dumps({
        "ok": True,
        "service_url": args.service_url,
        "slug": args.slug,
        "mode": args.mode,
        "event_id": event_id,
        "outcome": event.get("outcome"),
        "provenance": observed,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
