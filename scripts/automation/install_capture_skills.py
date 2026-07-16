#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


SKILLS = ("add-capture-link", "get-capture-link")


def install(repo_root: Path, codex_home: Path, openclaw_home: Path) -> dict:
    sources = {name: repo_root / "skills" / name for name in SKILLS}
    for source in sources.values():
        if not (source / "SKILL.md").is_file():
            raise RuntimeError(f"missing canonical skill: {source}")

    for name, source in sources.items():
        for home in (codex_home, openclaw_home):
            destination = home / "skills" / name
            temporary = destination.with_name(destination.name + ".new")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(temporary, ignore_errors=True)
            shutil.copytree(source, temporary, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if destination.exists():
                shutil.rmtree(destination)
            temporary.rename(destination)
    return {"ok": True, "installed": list(SKILLS)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install repository-canonical capture skills")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--openclaw-home", type=Path, default=Path.home() / ".openclaw")
    args = parser.parse_args()
    print(json.dumps(install(args.repo_root, args.codex_home, args.openclaw_home), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
