"""Seed Phase 3 mappings: tournament categories + team identities.

Usage:
    uv run python scripts/seed_identity.py [path/to/former_names.csv]

Tournament mapping always runs (over the tournaments already in the DB). Team identities are
seeded only if a former_names.csv path is given. Requires a database with migrations applied.
"""

from __future__ import annotations

import sys

from wc26.database.base import get_session_factory
from wc26.identity.team_identity import seed_team_identities
from wc26.identity.tournament_mapping import find_unmapped_tournaments, seed_tournament_mapping


def main(argv: list[str]) -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        mapped = seed_tournament_mapping(session)
        session.commit()
        unmapped = find_unmapped_tournaments(session)
        print(f"[ok] tournament_mapping: {mapped} tournaments; unmapped={len(unmapped)}")

        if argv:
            stats = seed_team_identities(session, argv[0])
            session.commit()
            print(f"[ok] team identities: {stats}")
        else:
            print("[skip] team identities: pass a former_names.csv path to seed them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
