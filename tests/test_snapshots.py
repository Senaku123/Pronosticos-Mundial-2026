"""Tests for snapshot manifest serialization (no network required)."""

from __future__ import annotations

from wc26.data.snapshots import SnapshotManifest, read_manifest, write_manifest


def test_manifest_roundtrip(tmp_path) -> None:
    manifest = SnapshotManifest(
        source_name="martj42_results",
        url="https://example/results.csv",
        snapshot_date="2026-06-11",
        file="results.csv",
        sha256="abc123",
        bytes=42,
    )
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    assert read_manifest(path) == manifest
