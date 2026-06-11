"""Anti-leakage tests (addendum §1): Elo ratings must be strictly causal in time."""

from __future__ import annotations

import datetime as dt

from wc26.models.elo import EloConfig, MatchInput, compute_elo_history


def test_no_future_leakage() -> None:
    """Every team's rating_pre at a match equals its previous rating_post (base if first).

    This proves the recursion never uses information from the future: the strength a team
    brings into match N is exactly what it left match N-1 with, nothing later.
    """
    matches = [
        MatchInput(1, dt.date(2020, 1, 1), 10, 20, 2, 0, neutral=False, importance_weight=1.0),
        MatchInput(2, dt.date(2020, 2, 1), 20, 30, 1, 1, neutral=True, importance_weight=0.7),
        MatchInput(3, dt.date(2020, 3, 1), 10, 30, 0, 1, neutral=False, importance_weight=0.3),
        MatchInput(4, dt.date(2020, 4, 1), 30, 10, 3, 0, neutral=True, importance_weight=1.0),
    ]
    base = EloConfig().base_rating
    records = compute_elo_history(matches)

    last_post: dict[int, float] = {}
    for rec in records:
        expected_pre = last_post.get(rec.team_id, base)
        assert rec.rating_pre == expected_pre, (
            f"team {rec.team_id} at match {rec.match_id}: "
            f"rating_pre={rec.rating_pre} but expected {expected_pre}"
        )
        last_post[rec.team_id] = rec.rating_post


def test_matches_processed_in_order_are_deterministic() -> None:
    matches = [
        MatchInput(1, dt.date(2018, 6, 1), 1, 2, 1, 0, neutral=False, importance_weight=1.0),
        MatchInput(2, dt.date(2018, 6, 5), 2, 1, 2, 2, neutral=True, importance_weight=1.0),
    ]
    first = compute_elo_history(matches)
    second = compute_elo_history(matches)
    assert first == second
