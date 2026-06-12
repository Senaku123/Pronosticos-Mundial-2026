"""Sample concrete scorelines from the Dixon-Coles model for Monte Carlo simulation.

The tournament engine needs goals (not just W/D/L) because group ranking depends on goal
difference and goals scored. Each match draws a scoreline from the same Dixon-Coles matrix that
is the single source of truth (addendum §2), so the simulator and the match model agree.
"""

from __future__ import annotations

import numpy as np

from wc26.models.dixon_coles import DixonColesConfig, predict_dixon_coles


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


def sample_match(
    elo_home: float,
    elo_away: float,
    neutral: bool,
    config: DixonColesConfig,
    rng: np.random.Generator,
) -> tuple[int, int]:
    """Predict the Dixon-Coles matrix for a match and sample one scoreline from it."""
    _, matrix = predict_dixon_coles(elo_home, elo_away, neutral, config)
    return sample_scoreline(matrix, rng)
