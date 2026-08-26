#!/usr/bin/env python3
"""Document the Memory Stargraph HTTP routes used by automation workers.

This helper intentionally does not perform network requests. Worker invocations
use top-level curl commands for API reads/writes so transport failures are
visible in command evidence.
"""

from __future__ import annotations

import argparse
import json


ROUTES = [
    {
        "action": "read-raw-entity",
        "method": "GET",
        "endpoint": "/api/entity-raw/<URL-encoded-slug>",
        "mutates_gbrain": False,
        "curl_shape": "curl -sS --fail <base-url>/api/entity-raw/<URL-encoded-slug>",
    },
    {
        "action": "save-raw-entity",
        "method": "POST",
        "endpoint": "/api/entity-save/<URL-encoded-slug>",
        "mutates_gbrain": True,
        "curl_shape": "curl -sS --fail -X POST -H 'Content-Type: application/json' -d @- <base-url>/api/entity-save/<URL-encoded-slug>",
    },
    {
        "action": "mutate-tags",
        "method": "POST",
        "endpoint": "/api/entity-tags/<URL-encoded-slug>",
        "mutates_gbrain": True,
        "curl_shape": "curl -sS --fail -X POST -H 'Content-Type: application/json' -d @- <base-url>/api/entity-tags/<URL-encoded-slug>",
    },
    {
        "action": "add-link",
        "method": "POST",
        "endpoint": "/api/entity-link/<URL-encoded-source-slug>",
        "mutates_gbrain": True,
        "curl_shape": "curl -sS --fail -X POST -H 'Content-Type: application/json' -d @- <base-url>/api/entity-link/<URL-encoded-source-slug>",
    },
    {
        "action": "remove-link",
        "method": "POST",
        "endpoint": "/api/entity-unlink/<URL-encoded-source-slug>",
        "mutates_gbrain": True,
        "curl_shape": "curl -sS --fail -X POST -H 'Content-Type: application/json' -d @- <base-url>/api/entity-unlink/<URL-encoded-source-slug>",
    },
    {
        "action": "graph-query",
        "method": "POST",
        "endpoint": "/api/entity-graph-query/<URL-encoded-slug>",
        "mutates_gbrain": False,
        "curl_shape": "curl -sS --fail -X POST -H 'Content-Type: application/json' -d @- <base-url>/api/entity-graph-query/<URL-encoded-slug>",
    },
    {
        "action": "health",
        "method": "GET",
        "endpoint": "/api/health",
        "mutates_gbrain": False,
        "curl_shape": "curl -sS <base-url>/api/health",
    },
    {
        "action": "resolver-events",
        "method": "GET",
        "endpoint": "/api/resolver/events",
        "mutates_gbrain": False,
        "curl_shape": "curl -sS --fail <base-url>/api/resolver/events?limit=<N>&producer=stargraph",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List Memory Stargraph worker HTTP API routes.")
    parser.add_argument("command", choices=("routes",))
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    if args.json:
        print(json.dumps({"routes": ROUTES}, indent=2, sort_keys=True))
    else:
        for route in ROUTES:
            print(f"{route['method']} {route['endpoint']} [{route['action']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
