"""Run-provenance helpers (addendum §8): metadata recorded against every persisted run."""

from __future__ import annotations

import subprocess


def git_sha() -> str | None:
    """Current git HEAD SHA, or None when git is unavailable (recorded, never fatal)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None
