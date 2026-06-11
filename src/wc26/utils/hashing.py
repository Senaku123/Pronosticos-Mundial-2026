"""Deterministic hashing helpers for data-snapshot provenance (addendum §8).

Used to compute the ``data_hash`` recorded against every model_run / backtest_run
and the per-source checksums stored in the snapshot manifest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: str | Path, chunk_size: int = 65536) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of a bytes object."""
    return hashlib.sha256(data).hexdigest()
