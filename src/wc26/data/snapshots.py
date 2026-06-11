"""Immutable raw-data snapshots with manifest + SHA-256 (addendum §8).

Each download is stored under ``data/raw/<source>/<YYYY-MM-DD>/`` together with a
``manifest.json`` recording the URL, snapshot date, file name, checksum and byte size.
The backtesting pipeline pins a snapshot (by hash), never a live source.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from wc26.utils.hashing import sha256_file


@dataclass(frozen=True)
class SnapshotManifest:
    """Provenance record for a single immutable raw snapshot file."""

    source_name: str
    url: str
    snapshot_date: str  # ISO date string
    file: str
    sha256: str
    bytes: int


def download_to_snapshot(
    source_name: str,
    url: str,
    raw_dir: str | Path,
    snapshot_date: dt.date | None = None,
    filename: str | None = None,
) -> SnapshotManifest:
    """Download ``url`` into an immutable snapshot folder and write its manifest."""
    snapshot_date = snapshot_date or dt.date.today()
    base = Path(raw_dir) / source_name / snapshot_date.isoformat()
    base.mkdir(parents=True, exist_ok=True)

    file_name = filename or url.rsplit("/", 1)[-1] or "download"
    dest = base / file_name
    urllib.request.urlretrieve(url, dest)

    manifest = SnapshotManifest(
        source_name=source_name,
        url=url,
        snapshot_date=snapshot_date.isoformat(),
        file=file_name,
        sha256=sha256_file(dest),
        bytes=dest.stat().st_size,
    )
    write_manifest(base / "manifest.json", manifest)
    return manifest


def write_manifest(path: str | Path, manifest: SnapshotManifest) -> None:
    """Serialize a :class:`SnapshotManifest` to JSON."""
    Path(path).write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")


def read_manifest(path: str | Path) -> SnapshotManifest:
    """Load a :class:`SnapshotManifest` from JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SnapshotManifest(**data)
