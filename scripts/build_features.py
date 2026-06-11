"""Build the point-in-time match_features table from played matches + internal Elo.

Usage:
    uv run python scripts/build_features.py

Optionally pass a cutoff date (YYYY-MM-DD) to only build features for matches before it:
    uv run python scripts/build_features.py 2022-11-20

Records the current git SHA for reproducibility (addendum §8). Requires elo_ratings seeded.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys

from wc26.database.base import get_session_factory
from wc26.features.match_features import seed_match_features


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def main(argv: list[str]) -> int:
    cutoff = dt.date.fromisoformat(argv[0]) if argv else None
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = seed_match_features(session, cutoff_date=cutoff, code_git_sha=_git_sha())
        session.commit()
        print(f"[ok] match_features rows={rows} cutoff={cutoff} git_sha={_git_sha()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
