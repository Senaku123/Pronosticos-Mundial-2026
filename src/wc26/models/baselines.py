"""Baseline models: the simple predictors that the real engine must beat (addendum §3, §4).

All baselines map (elo_home, elo_away, neutral) -> W/D/L probabilities. ``simple_poisson`` also
yields expected goals and a most-likely scoreline. Every constant here is a STARTING HYPOTHESIS to
be validated by backtesting (Phase 8), never fixed blindly. These functions are pure.

``fifa_ranking_baseline`` is intentionally absent for now: the FIFA ranking is an external source
we have not ingested yet (see docs/DATA_SOURCES.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from wc26.models.elo import EloConfig, predict_expected


@dataclass(frozen=True)
class BaselineConfig:
    """Hypothesis constants for the baselines (validated later by backtesting)."""

    home_advantage: float = 65.0
    naive_favorite_win: float = 0.50
    naive_draw: float = 0.27
    draw_peak: float = 0.30  # draw probability when the two teams are perfectly even
    mu_total_goals: float = 2.6  # average total goals in an international match
    goals_per_elo_unit: float = 0.9  # goal supremacy per 400-Elo gap
    max_goals: int = 10


@dataclass(frozen=True)
class Prediction:
    """A baseline's output for one match."""

    p_home_win: float
    p_draw: float
    p_away_win: float
    expected_goals_home: float | None
    expected_goals_away: float | None
    predicted_home_score: int | None
    predicted_away_score: int | None


def naive_favorite(
    elo_home: float, elo_away: float, neutral: bool, config: BaselineConfig | None = None
) -> Prediction:
    """No-skill floor: a fixed split that just favours the stronger (by Elo) team."""
    cfg = config or BaselineConfig()
    home_field = 0.0 if neutral else cfg.home_advantage
    lose = 1.0 - cfg.naive_draw - cfg.naive_favorite_win
    if elo_home + home_field >= elo_away:
        p_home, p_away = cfg.naive_favorite_win, lose
    else:
        p_home, p_away = lose, cfg.naive_favorite_win
    return Prediction(p_home, cfg.naive_draw, p_away, None, None, None, None)


def elo_only(
    elo_home: float, elo_away: float, neutral: bool, config: BaselineConfig | None = None
) -> Prediction:
    """Elo expected score split into W/D/L with a simple even-match draw model."""
    cfg = config or BaselineConfig()
    e = predict_expected(elo_home, elo_away, neutral, EloConfig(home_advantage=cfg.home_advantage))
    p_draw = cfg.draw_peak * (1.0 - abs(2.0 * e - 1.0))
    p_home = max(e - 0.5 * p_draw, 1e-9)
    p_away = max(1.0 - e - 0.5 * p_draw, 1e-9)
    p_draw = max(p_draw, 1e-9)
    total = p_home + p_draw + p_away
    return Prediction(p_home / total, p_draw / total, p_away / total, None, None, None, None)


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def elo_to_lambdas(
    elo_home: float, elo_away: float, neutral: bool, config: BaselineConfig
) -> tuple[float, float]:
    """Map Elo to each team's expected goals (lambda) for a Poisson scoreline."""
    home_field = 0.0 if neutral else config.home_advantage
    supremacy = (elo_home + home_field - elo_away) / 400.0
    expected_goal_diff = supremacy * config.goals_per_elo_unit
    lambda_home = max(0.15, (config.mu_total_goals + expected_goal_diff) / 2.0)
    lambda_away = max(0.15, (config.mu_total_goals - expected_goal_diff) / 2.0)
    return lambda_home, lambda_away


def poisson_scoreline_matrix(
    lambda_home: float, lambda_away: float, max_goals: int
) -> list[list[float]]:
    """Independent-Poisson scoreline matrix P[i][j] = P(home i, away j), renormalized."""
    home = [_poisson_pmf(i, lambda_home) for i in range(max_goals + 1)]
    away = [_poisson_pmf(j, lambda_away) for j in range(max_goals + 1)]
    matrix = [[home[i] * away[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    total = sum(sum(row) for row in matrix)
    return [[value / total for value in row] for row in matrix]


def wdl_from_matrix(matrix: list[list[float]]) -> tuple[float, float, float]:
    """Sum scoreline zones into (P home win, P draw, P away win) (addendum §2)."""
    p_home = p_draw = p_away = 0.0
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if i > j:
                p_home += value
            elif i == j:
                p_draw += value
            else:
                p_away += value
    return p_home, p_draw, p_away


def most_likely_score(matrix: list[list[float]]) -> tuple[int, int]:
    """Return the (home, away) scoreline with the highest probability."""
    best = (0, 0)
    best_p = -1.0
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if value > best_p:
                best_p = value
                best = (i, j)
    return best


def simple_poisson(
    elo_home: float, elo_away: float, neutral: bool, config: BaselineConfig | None = None
) -> Prediction:
    """Elo -> expected goals -> Poisson scoreline -> W/D/L + most-likely score."""
    cfg = config or BaselineConfig()
    lambda_home, lambda_away = elo_to_lambdas(elo_home, elo_away, neutral, cfg)
    matrix = poisson_scoreline_matrix(lambda_home, lambda_away, cfg.max_goals)
    p_home, p_draw, p_away = wdl_from_matrix(matrix)
    home_goals, away_goals = most_likely_score(matrix)
    return Prediction(p_home, p_draw, p_away, lambda_home, lambda_away, home_goals, away_goals)


BASELINES = {
    "naive_favorite": naive_favorite,
    "elo_only": elo_only,
    "simple_poisson": simple_poisson,
}
