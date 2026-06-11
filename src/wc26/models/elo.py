"""Internally-recomputed Elo for national teams (addendum §1).

Why in-house: public Elo tables are backfilled/recomputed and a value downloaded *today* may
already reflect results AFTER a historical cutoff -> leakage. Recomputing from raw match results
in strict chronological order guarantees every rating depends only on prior matches.

The model follows the World Football Elo conventions (home advantage, goal-difference weighting),
with the K-factor scaled by the match-importance weight from ``tournament_mapping`` (a hypothesis
to be validated by backtesting, never fixed blindly).

These functions are pure (no DB): given an ordered list of played matches they return the full
rating history. Persistence lives in ``seed_elo_ratings``.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

BASE_RATING = 1500.0


@dataclass(frozen=True)
class EloConfig:
    """Elo hyperparameters. Defaults are a STARTING HYPOTHESIS, validated later by backtesting."""

    base_k: float = 40.0
    home_advantage: float = 65.0
    base_rating: float = BASE_RATING


@dataclass(frozen=True)
class MatchInput:
    """A played match, with its importance weight resolved from tournament_mapping."""

    match_id: int
    match_date: dt.date
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    neutral: bool
    importance_weight: float


@dataclass(frozen=True)
class EloRecord:
    """Pre/post rating of one team in one match."""

    match_id: int
    team_id: int
    match_date: dt.date
    rating_pre: float
    rating_post: float
    is_home: bool


def expected_score(rating: float, opponent_rating: float) -> float:
    """Logistic expected score (win probability incl. half for draw) for ``rating``."""
    return 1.0 / (1.0 + math.pow(10.0, -(rating - opponent_rating) / 400.0))


def goal_difference_multiplier(goal_diff: int) -> float:
    """World-Football-Elo goal-difference weighting of the K-factor."""
    g = abs(goal_diff)
    if g <= 1:
        return 1.0
    if g == 2:
        return 1.5
    return (11.0 + g) / 8.0


def _result_for_home(home_score: int, away_score: int) -> float:
    """Actual score from the home team's perspective: 1 win, 0.5 draw, 0 loss."""
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


def compute_elo_history(
    matches: list[MatchInput], config: EloConfig | None = None
) -> list[EloRecord]:
    """Replay matches in the given order and return the full per-team rating history.

    Callers MUST pass matches sorted chronologically (and deterministically tie-broken).
    For each match, the stored ``rating_pre`` is the team's intrinsic rating BEFORE the match
    (i.e. the ``rating_post`` of its previous match), which is the only leakage-safe strength.
    """
    cfg = config or EloConfig()
    ratings: dict[int, float] = {}
    records: list[EloRecord] = []

    for m in matches:
        home_pre = ratings.get(m.home_team_id, cfg.base_rating)
        away_pre = ratings.get(m.away_team_id, cfg.base_rating)

        home_field = 0.0 if m.neutral else cfg.home_advantage
        expected_home = expected_score(home_pre + home_field, away_pre)

        result_home = _result_for_home(m.home_score, m.away_score)
        k = (
            cfg.base_k
            * m.importance_weight
            * goal_difference_multiplier(m.home_score - m.away_score)
        )
        delta = k * (result_home - expected_home)

        home_post = home_pre + delta
        away_post = away_pre - delta
        ratings[m.home_team_id] = home_post
        ratings[m.away_team_id] = away_post

        records.append(
            EloRecord(m.match_id, m.home_team_id, m.match_date, home_pre, home_post, True)
        )
        records.append(
            EloRecord(m.match_id, m.away_team_id, m.match_date, away_pre, away_post, False)
        )

    return records
