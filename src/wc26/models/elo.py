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
from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby

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


def predict_expected(
    home_rating: float,
    away_rating: float,
    neutral: bool,
    config: EloConfig | None = None,
) -> float:
    """Home-team expected score, re-applying home advantage exactly as in training.

    Use this (never bare ``expected_score`` on raw ratings) when predicting a match from
    as-of ratings, so the home advantage is applied consistently with ``compute_elo_history``.
    """
    cfg = config or EloConfig()
    home_field = 0.0 if neutral else cfg.home_advantage
    return expected_score(home_rating + home_field, away_rating)


def compute_elo_history(
    matches: list[MatchInput], config: EloConfig | None = None
) -> list[EloRecord]:
    """Replay matches chronologically and return the full per-team rating history.

    The matches MUST be sorted by non-decreasing ``match_date`` (a ``ValueError`` is raised
    otherwise). Because the data has only day granularity (no kickoff time), each day is
    processed **atomically**: every match on a day uses that day's *start* ratings as its
    ``rating_pre``, and each team's same-day deltas are applied together at day end. This means:

    - ``rating_pre`` depends ONLY on strictly-earlier days (no same-day leakage, even for the
      138 cases where a team plays twice in one day), and exactly equals ``get_rating_as_of``;
    - ``rating_post`` is the team's end-of-day rating (consumed only by strictly-later days).

    Sequential replay also makes earlier records immutable to later matches, so a full-history
    seed yields the same as-of ratings as any per-cutoff seed (no per-cutoff reseed needed).
    """
    cfg = config or EloConfig()

    previous_date: dt.date | None = None
    for m in matches:
        if previous_date is not None and m.match_date < previous_date:
            raise ValueError(
                f"matches must be sorted by non-decreasing match_date; "
                f"{m.match_date} follows {previous_date}"
            )
        previous_date = m.match_date

    ratings: dict[int, float] = {}
    records: list[EloRecord] = []

    for _day, group in groupby(matches, key=lambda m: m.match_date):
        day_matches = list(group)
        day_start = {
            team: ratings.get(team, cfg.base_rating)
            for m in day_matches
            for team in (m.home_team_id, m.away_team_id)
        }
        deltas: defaultdict[int, float] = defaultdict(float)
        for m in day_matches:
            home_field = 0.0 if m.neutral else cfg.home_advantage
            expected_home = expected_score(
                day_start[m.home_team_id] + home_field, day_start[m.away_team_id]
            )
            result_home = _result_for_home(m.home_score, m.away_score)
            k = (
                cfg.base_k
                * m.importance_weight
                * goal_difference_multiplier(m.home_score - m.away_score)
            )
            delta = k * (result_home - expected_home)
            deltas[m.home_team_id] += delta
            deltas[m.away_team_id] -= delta

        day_end = {team: day_start[team] + deltas[team] for team in day_start}
        for m in day_matches:
            records.append(
                EloRecord(
                    m.match_id,
                    m.home_team_id,
                    m.match_date,
                    day_start[m.home_team_id],
                    day_end[m.home_team_id],
                    True,
                )
            )
            records.append(
                EloRecord(
                    m.match_id,
                    m.away_team_id,
                    m.match_date,
                    day_start[m.away_team_id],
                    day_end[m.away_team_id],
                    False,
                )
            )
        ratings.update(day_end)

    return records
