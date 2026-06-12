"""Sample concrete scorelines from the (calibrated) Dixon-Coles model for Monte Carlo.

The tournament engine needs goals (not just W/D/L) because group ranking depends on goal
difference and goals scored. Each match draws a scoreline from the Dixon-Coles matrix — the
single source of truth (addendum §2) — optionally rescaled by the Platt calibrator so the
simulator inherits the calibration that won the go/no-go (Phase 8).
"""

from __future__ import annotations

from functools import cache

import numpy as np

from wc26.models.baselines import elo_to_lambdas
from wc26.models.calibration import PlattCalibrator, calibrate_matrix
from wc26.models.dixon_coles import DixonColesConfig, dixon_coles_matrix


def sample_scoreline(matrix: list[list[float]], rng: np.random.Generator) -> tuple[int, int]:
    """Draw a (home_goals, away_goals) scoreline from a probability matrix."""
    threshold = float(rng.random())
    cumulative = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, prob in enumerate(row):
            cumulative += prob
            if threshold <= cumulative:
                return home_goals, away_goals
    last = len(matrix) - 1
    return last, last


@cache
def match_matrix(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int,
    calibrator: PlattCalibrator | None,
) -> list[list[float]]:
    """Memoized (optionally calibrated) scoreline matrix for one lambda pair."""
    matrix = dixon_coles_matrix(lambda_home, lambda_away, rho, max_goals)
    if calibrator is not None:
        matrix = calibrate_matrix(matrix, calibrator)
    return matrix


def sample_match(
    elo_home: float,
    elo_away: float,
    neutral: bool,
    config: DixonColesConfig,
    rng: np.random.Generator,
    calibrator: PlattCalibrator | None = None,
) -> tuple[int, int]:
    """Sample one scoreline for a match from the (calibrated) Dixon-Coles matrix."""
    lambda_home, lambda_away = elo_to_lambdas(elo_home, elo_away, neutral, config.base)
    matrix = match_matrix(lambda_home, lambda_away, config.rho, config.base.max_goals, calibrator)
    return sample_scoreline(matrix, rng)
