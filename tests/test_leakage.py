"""Anti-leakage tests (addendum §1): Elo ratings must be strictly causal in time."""

from __future__ import annotations

import datetime as dt

import pytest

from wc26.models.elo import EloConfig, MatchInput, compute_elo_history


def test_no_future_leakage() -> None:
    """Every team's rating_pre at a match equals its previous (earlier-day) rating_post."""
    matches = [
        MatchInput(1, dt.date(2020, 1, 1), 10, 20, 2, 0, neutral=False, importance_weight=1.0),
        MatchInput(2, dt.date(2020, 2, 1), 20, 30, 1, 1, neutral=True, importance_weight=0.7),
        MatchInput(3, dt.date(2020, 3, 1), 10, 30, 0, 1, neutral=False, importance_weight=0.3),
        MatchInput(4, dt.date(2020, 4, 1), 30, 10, 3, 0, neutral=True, importance_weight=1.0),
    ]
    base = EloConfig().base_rating
    last_post: dict[int, float] = {}
    for rec in compute_elo_history(matches):
        assert rec.rating_pre == last_post.get(rec.team_id, base)
        last_post[rec.team_id] = rec.rating_post


def test_same_day_matches_are_atomic() -> None:
    """A team playing twice the same day uses the SAME day-start rating_pre for both matches."""
    matches = [
        MatchInput(1, dt.date(2020, 1, 1), 1, 2, 1, 0, neutral=True, importance_weight=1.0),
        MatchInput(2, dt.date(2020, 1, 1), 1, 3, 2, 0, neutral=True, importance_weight=1.0),
    ]
    records = compute_elo_history(matches, EloConfig(base_k=40.0))
    team1 = [r for r in records if r.team_id == 1]
    assert team1[0].rating_pre == 1500.0
    assert team1[1].rating_pre == 1500.0  # NOT updated by the first same-day match
    # Both records share the end-of-day rating (both same-day deltas applied).
    assert team1[0].rating_post == team1[1].rating_post
    assert team1[0].rating_post > 1500.0


def test_unordered_matches_raise() -> None:
    """Out-of-order input is rejected, so leakage cannot slip in via bad ordering."""
    matches = [
        MatchInput(1, dt.date(2020, 2, 1), 1, 2, 1, 0, neutral=True, importance_weight=1.0),
        MatchInput(2, dt.date(2020, 1, 1), 1, 3, 1, 0, neutral=True, importance_weight=1.0),
    ]
    with pytest.raises(ValueError):
        compute_elo_history(matches)


def test_pre_cutoff_records_invariant_to_later_matches() -> None:
    """Earlier records are unchanged by later matches -> a full-history seed is as-of safe."""
    early = [
        MatchInput(1, dt.date(2018, 1, 1), 1, 2, 1, 0, neutral=False, importance_weight=1.0),
        MatchInput(2, dt.date(2018, 2, 1), 2, 3, 0, 1, neutral=True, importance_weight=0.7),
    ]
    later = [
        *early,
        MatchInput(3, dt.date(2019, 1, 1), 1, 3, 2, 0, neutral=False, importance_weight=1.0),
    ]
    early_by_key = {(r.match_id, r.team_id): r for r in compute_elo_history(early)}
    for rec in compute_elo_history(later):
        if rec.match_id in (1, 2):
            assert early_by_key[(rec.match_id, rec.team_id)] == rec


def test_get_rating_as_of_matches_stored_pre(db_session) -> None:
    """DB-level: get_rating_as_of(team, match_date) == the stored rating_pre for that match.

    Skipped automatically when no database / no seeded elo_ratings is available.
    """
    from sqlalchemy import select

    from wc26.database.models import EloRating
    from wc26.features.cutoff import get_rating_as_of

    rows = db_session.execute(
        select(EloRating.team_id, EloRating.match_date, EloRating.rating_pre).limit(300)
    ).all()
    if not rows:
        pytest.skip("elo_ratings not seeded")
    for team_id, match_date, rating_pre in rows:
        assert abs(get_rating_as_of(db_session, team_id, match_date) - rating_pre) < 1e-6
