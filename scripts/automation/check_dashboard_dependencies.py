#!/usr/bin/env python3
"""Fail closed unless the dashboard-managed Python supplies queue dependencies."""
from importlib import metadata


def main(version=metadata.version):
    try:
        installed = version("nats-py")
    except metadata.PackageNotFoundError as error:
        raise SystemExit(
            "nats-py==2.15.0 is required by the dashboard runtime"
        ) from error
    if installed != "2.15.0":
        raise SystemExit("dashboard runtime must use nats-py==2.15.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
