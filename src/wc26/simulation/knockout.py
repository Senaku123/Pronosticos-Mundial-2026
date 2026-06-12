"""Knockout resolution: a tie must produce a winner (addendum §5).

90 minutes (Dixon-Coles scoreline) -> extra time (reduced goal rate) -> penalties (~50/50).
The extra-time fraction and the penalty tilt are hypotheses to validate against historical
extra-time/penalty frequencies (Phase 11).
"""

from __future__ import annotations

import numpy as np

from wc26.models.baselines import elo_to_lambdas
from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.match_sampler import sample_match

EXTRA_TIME_FRACTION = 1.0 / 3.0  # 30 of 90 minutes
PENALTY_ELO_TILT = 0.0  # ~50/50; penalties are near-random. Set >0 for a slight strength tilt.

HOME, AWAY = 0, 1


def resolve_knockout(
    elo_home: float,
    elo_away: float,
    neutral: bool,
    config: DixonColesConfig,
    rng: np.random.Generator,
) -> int:
    """Return HOME (0) or AWAY (1) as the team that advances. Never a draw."""
    home_goals, away_goals = sample_match(elo_home, elo_away, neutral, config, rng)
    if home_goals != away_goals:
        return HOME if home_goals > away_goals else AWAY

    lambda_home, lambda_away = elo_to_lambdas(elo_home, elo_away, neutral, config.base)
    et_home = int(rng.poisson(lambda_home * EXTRA_TIME_FRACTION))
    et_away = int(rng.poisson(lambda_away * EXTRA_TIME_FRACTION))
    if et_home != et_away:
        return HOME if et_home > et_away else AWAY

    p_home = min(max(0.5 + PENALTY_ELO_TILT * (elo_home - elo_away), 0.35), 0.65)
    return HOME if float(rng.random()) < p_home else AWAY
