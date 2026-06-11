"""Download immutable raw snapshots for the registered V1 sources.

Usage:
    uv run python scripts/download_snapshots.py [source_name ...]

With no arguments, downloads every source in the registry. Files land under
data/raw/<source>/<YYYY-MM-DD>/ with a manifest.json (URL + SHA-256 + size).
"""

from __future__ import annotations

import sys

from wc26.data.snapshots import download_to_snapshot
from wc26.data.sources import REGISTRY
from wc26.utils.config import get_settings


def main(argv: list[str]) -> int:
    settings = get_settings()
    names = argv or list(REGISTRY)
    for name in names:
        spec = REGISTRY.get(name)
        if spec is None:
            print(f"[skip] unknown source: {name}")
            continue
        manifest = download_to_snapshot(spec.name, spec.url, settings.data_raw_dir)
        print(
            f"[ok] {spec.name}: {manifest.file} "
            f"sha256={manifest.sha256[:12]}... ({manifest.bytes} bytes)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
