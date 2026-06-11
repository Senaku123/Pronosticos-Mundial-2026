"""Temporal cutoff logic and point-in-time rating lookups (addendum §1).

Everything here enforces the leakage rule: training/feature data for a cutoff uses ONLY matches
strictly before that cutoff, and a team's strength as-of a date is its most recent rating from a
match strictly before that date.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from wc26.database.models import EloRating, Match, Tournament, TournamentMapping
from wc26.models.elo import BASE_RATING, EloConfig, MatchInput, compute_elo_history

# Default importance weight for any tournament not present in tournament_mapping (should be none).
_DEFAULT_WEIGHT = 0.5


def load_played_matches(session: Session, cutoff_date: dt.date | None = None) -> list[MatchInput]:
    """Load played matches (both scores present), chronologically ordered, with importance weight.

    If ``cutoff_date`` is given, only matches strictly before it are returned (no leakage).
    """
    weight = func.coalesce(TournamentMapping.match_importance_weight, _DEFAULT_WEIGHT).label(
        "weight"
    )
    stmt = (
        select(
            Match.id.label("match_id"),
            Match.match_date,
            Match.home_team_id,
            Match.away_team_id,
            Match.home_score,
            Match.away_score,
            Match.neutral,
            weight,
        )
        .join(Tournament, Tournament.id == Match.tournament_id)
        .outerjoin(TournamentMapping, TournamentMapping.raw_tournament == Tournament.name)
        .where(Match.home_score.is_not(None), Match.away_score.is_not(None))
        .order_by(Match.match_date, Match.id)
    )
    if cutoff_date is not None:
        stmt = stmt.where(Match.match_date < cutoff_date)

    matches: list[MatchInput] = []
    for row in session.execute(stmt).all():
        if row.home_score is None or row.away_score is None:
            continue
        matches.append(
            MatchInput(
                match_id=row.match_id,
                match_date=row.match_date,
                home_team_id=row.home_team_id,
                away_team_id=row.away_team_id,
                home_score=int(row.home_score),
                away_score=int(row.away_score),
                neutral=bool(row.neutral),
                importance_weight=float(row.weight),
            )
        )
    return matches


def seed_elo_ratings(
    session: Session, config: EloConfig | None = None, cutoff_date: dt.date | None = None
) -> int:
    """Recompute Elo and overwrite the ``elo_ratings`` table. Returns the row count."""
    history = compute_elo_history(load_played_matches(session, cutoff_date), config)
    session.execute(delete(EloRating))
    rows = [
        {
            "team_id": r.team_id,
            "match_id": r.match_id,
            "match_date": r.match_date,
            "rating_pre": r.rating_pre,
            "rating_post": r.rating_post,
            "is_home": r.is_home,
        }
        for r in history
    ]
    if rows:
        session.execute(insert(EloRating), rows)
    session.flush()
    return len(rows)


def get_rating_as_of(
    session: Session, team_id: int, as_of_date: dt.date, base_rating: float = BASE_RATING
) -> float:
    """Return a team's strength as-of a date: rating_post of its latest match strictly before it."""
    stmt = (
        select(EloRating.rating_post)
        .where(EloRating.team_id == team_id, EloRating.match_date < as_of_date)
        .order_by(EloRating.match_date.desc(), EloRating.match_id.desc())
        .limit(1)
    )
    latest = session.execute(stmt).scalar_one_or_none()
    return float(latest) if latest is not None else base_rating
