"""Point-in-time match features (Phase 5).

Every feature for a match is computed from ONLY strictly-earlier information, using the same
day-atomic discipline as the Elo (a team that plays twice in a day sees the same pre-day form
for both matches). This makes each row leakage-safe for predicting its own match.

``build_match_features`` is pure (matches + an Elo lookup -> feature rows); ``seed_match_features``
loads from / writes to the database.
"""

from __future__ import annotations

import datetime as dt
from collections import deque
from dataclasses import dataclass
from itertools import groupby

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from wc26.database.models import EloRating, MatchFeature
from wc26.features.cutoff import load_played_matches
from wc26.models.elo import BASE_RATING, MatchInput

FEATURE_PIPELINE_VERSION = "v1"
FORM_WINDOW = 5


@dataclass(frozen=True)
class MatchFeatureRow:
    """Computed feature vector for one match (all from pre-match information)."""

    match_id: int
    elo_home: float
    elo_away: float
    elo_diff: float
    home_form_points: float | None
    away_form_points: float | None
    home_gf_avg: float | None
    home_ga_avg: float | None
    away_gf_avg: float | None
    away_ga_avg: float | None
    home_form_n: int
    away_form_n: int
    home_rest_days: int | None
    away_rest_days: int | None
    importance_weight: float
    is_neutral: bool


def _points(goals_for: int, goals_against: int) -> int:
    if goals_for > goals_against:
        return 3
    if goals_for == goals_against:
        return 1
    return 0


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rest_days(last: dt.date | None, current: dt.date) -> int | None:
    return (current - last).days if last is not None else None


def build_match_features(
    matches: list[MatchInput],
    elo_pre: dict[tuple[int, int], float],
    form_window: int = FORM_WINDOW,
) -> list[MatchFeatureRow]:
    """Build leakage-safe feature rows. ``elo_pre`` maps (match_id, team_id) -> rating_pre.

    ``matches`` must be chronologically ordered (as produced by ``load_played_matches``).
    """
    form: dict[int, deque[tuple[int, int, int]]] = {}  # team -> recent (points, gf, ga)
    last_date: dict[int, dt.date] = {}
    rows: list[MatchFeatureRow] = []

    for _day, group in groupby(matches, key=lambda m: m.match_date):
        day_matches = list(group)

        # Features use only PRE-day state (the day is atomic).
        for m in day_matches:
            home = form.get(m.home_team_id, deque())
            away = form.get(m.away_team_id, deque())
            elo_home = elo_pre.get((m.match_id, m.home_team_id), BASE_RATING)
            elo_away = elo_pre.get((m.match_id, m.away_team_id), BASE_RATING)
            rows.append(
                MatchFeatureRow(
                    match_id=m.match_id,
                    elo_home=elo_home,
                    elo_away=elo_away,
                    elo_diff=elo_home - elo_away,
                    home_form_points=_avg([float(x[0]) for x in home]),
                    away_form_points=_avg([float(x[0]) for x in away]),
                    home_gf_avg=_avg([float(x[1]) for x in home]),
                    home_ga_avg=_avg([float(x[2]) for x in home]),
                    away_gf_avg=_avg([float(x[1]) for x in away]),
                    away_ga_avg=_avg([float(x[2]) for x in away]),
                    home_form_n=len(home),
                    away_form_n=len(away),
                    home_rest_days=_rest_days(last_date.get(m.home_team_id), m.match_date),
                    away_rest_days=_rest_days(last_date.get(m.away_team_id), m.match_date),
                    importance_weight=m.importance_weight,
                    is_neutral=m.neutral,
                )
            )

        # Update state with the day's results (after all day features are computed).
        for m in day_matches:
            form.setdefault(m.home_team_id, deque(maxlen=form_window)).append(
                (_points(m.home_score, m.away_score), m.home_score, m.away_score)
            )
            form.setdefault(m.away_team_id, deque(maxlen=form_window)).append(
                (_points(m.away_score, m.home_score), m.away_score, m.home_score)
            )
            last_date[m.home_team_id] = m.match_date
            last_date[m.away_team_id] = m.match_date

    return rows


def seed_match_features(
    session: Session,
    version: str = FEATURE_PIPELINE_VERSION,
    cutoff_date: dt.date | None = None,
    code_git_sha: str | None = None,
    form_window: int = FORM_WINDOW,
) -> int:
    """Build and overwrite the ``match_features`` table. Returns the row count."""
    matches = load_played_matches(session, cutoff_date)
    elo_pre = {
        (match_id, team_id): rating_pre
        for match_id, team_id, rating_pre in session.execute(
            select(EloRating.match_id, EloRating.team_id, EloRating.rating_pre)
        ).all()
    }
    feature_rows = build_match_features(matches, elo_pre, form_window)
    session.execute(delete(MatchFeature))
    payload = [
        {
            "match_id": r.match_id,
            "feature_pipeline_version": version,
            "cutoff_date": cutoff_date,
            "code_git_sha": code_git_sha,
            "elo_home": r.elo_home,
            "elo_away": r.elo_away,
            "elo_diff": r.elo_diff,
            "home_form_points": r.home_form_points,
            "away_form_points": r.away_form_points,
            "home_gf_avg": r.home_gf_avg,
            "home_ga_avg": r.home_ga_avg,
            "away_gf_avg": r.away_gf_avg,
            "away_ga_avg": r.away_ga_avg,
            "home_form_n": r.home_form_n,
            "away_form_n": r.away_form_n,
            "home_rest_days": r.home_rest_days,
            "away_rest_days": r.away_rest_days,
            "importance_weight": r.importance_weight,
            "is_neutral": r.is_neutral,
        }
        for r in feature_rows
    ]
    if payload:
        session.execute(insert(MatchFeature), payload)
    session.flush()
    return len(payload)
