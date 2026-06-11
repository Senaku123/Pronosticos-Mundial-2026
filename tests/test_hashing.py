"""Tests for deterministic hashing helpers."""

from __future__ import annotations

from wc26.utils.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_known_vector() -> None:
    # SHA-256 of the empty input is a fixed, well-known digest.
    assert sha256_bytes(b"") == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_sha256_file_matches_bytes(tmp_path) -> None:
    payload = b"world cup 2026"
    file_path = tmp_path / "sample.bin"
    file_path.write_bytes(payload)
    assert sha256_file(file_path) == sha256_bytes(payload)
