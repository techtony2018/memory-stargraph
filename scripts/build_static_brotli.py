#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"
OUTPUT_DIR = PUBLIC_DIR / "assets" / "precompressed"
SOURCE_NAMES = ("index.html", "app.js", "styles.css")


def build(quality):
    brotli = shutil.which("brotli")
    if not brotli:
        raise RuntimeError("brotli CLI is required to build static sidecars")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = {}
    for name in SOURCE_NAMES:
        source = PUBLIC_DIR / name
        output = OUTPUT_DIR / f"{name}.br"
        subprocess.run(
            [brotli, "-q", str(quality), "-f", "-o", str(output), str(source)],
            check=True,
        )
        source_bytes = source.read_bytes()
        assets[name] = {
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_size": len(source_bytes),
            "brotli_size": output.stat().st_size,
        }
    manifest = {"quality": quality, "assets": assets}
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description="Build validated Brotli sidecars for startup assets.")
    parser.add_argument("--quality", type=int, default=5, choices=range(0, 12))
    args = parser.parse_args()
    build(args.quality)


if __name__ == "__main__":
    main()
