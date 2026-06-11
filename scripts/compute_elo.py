"""Recompute internal Elo over all played matches and persist it to elo_ratings.

Usage:
    uv run python scripts/compute_elo.py

Optionally pass a cutoff date (YYYY-MM-DD) to only use matches strictly before it:
    uv run python scripts/compute_elo.py 2022-11-20
"""

from __future__ import annotations

import datetime as dt
import sys

from sqlalchemy import desc, select

from wc26.database.base import get_session_factory
from wc26.database.models import EloRating, Team
from wc26.features.cutoff import seed_elo_ratings


def main(argv: list[str]) -> int:
    cutoff = dt.date.fromisoformat(argv[0]) if argv else None
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = seed_elo_ratings(session, cutoff_date=cutoff)
        session.commit()
        print(f"[ok] elo_ratings rows={rows} cutoff={cutoff}")

        # Latest rating per team (PostgreSQL DISTINCT ON), then top 10 (sanity check).
        latest_per_team = (
            select(EloRating.team_id, EloRating.rating_post)
            .order_by(EloRating.team_id, desc(EloRating.match_date), desc(EloRating.match_id))
            .distinct(EloRating.team_id)
            .subquery()
        )
        top = (
            select(Team.canonical_name, latest_per_team.c.rating_post)
            .join(Team, Team.id == latest_per_team.c.team_id)
            .order_by(desc(latest_per_team.c.rating_post))
            .limit(10)
        )
        print("Top 10 by latest Elo:")
        for name, rating in session.execute(top).all():
            print(f"  {rating:7.1f}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
