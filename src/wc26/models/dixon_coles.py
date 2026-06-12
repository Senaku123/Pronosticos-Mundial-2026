"""Dixon-Coles scoreline model: the single official source of W/D/L (addendum §2).

An independent Poisson over-predicts/under-predicts the low scores (0-0, 1-0, 0-1, 1-1) that
dominate international football. Dixon-Coles (1997) corrects exactly those four cells with a
dependence parameter ``rho``, fit by maximum likelihood. W/D/L is then derived by summing zones
of the scoreline matrix - never produced independently.

Expected goals come from Elo (same mapping as the simple_poisson baseline) so the engine stays a
single coherent pipeline; ``rho`` and the goal-mapping constants are hypotheses validated by
backtesting (Phase 8).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cache

from wc26.models.baselines import (
    BaselineConfig,
    Prediction,
    elo_to_lambdas,
    most_likely_score,
    wdl_from_matrix,
)


@dataclass(frozen=True)
class DixonColesConfig:
    """Dixon-Coles config: the goal mapping (shared with the baseline) plus the rho correction."""

    base: BaselineConfig = field(default_factory=BaselineConfig)
    rho: float = -0.10  # low-score dependence; negative lifts draws/low scores. Fit by MLE.


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def dixon_coles_tau(
    home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float
) -> float:
    """Dixon-Coles dependence factor; 1.0 outside the four low-score cells."""
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


@cache
def dixon_coles_matrix(
    lambda_home: float, lambda_away: float, rho: float, max_goals: int
) -> list[list[float]]:
    """Dixon-Coles scoreline matrix P[i][j], renormalized to sum to 1.

    Memoized: with a fixed set of team strengths the same (lambda, rho) recur across millions of
    Monte Carlo matches, so each distinct matrix is built only once. Callers must NOT mutate it.
    """
    home = [_poisson_pmf(i, lambda_home) for i in range(max_goals + 1)]
    away = [_poisson_pmf(j, lambda_away) for j in range(max_goals + 1)]
    matrix = [
        [
            max(0.0, dixon_coles_tau(i, j, lambda_home, lambda_away, rho)) * home[i] * away[j]
            for j in range(max_goals + 1)
        ]
        for i in range(max_goals + 1)
    ]
    total = sum(sum(row) for row in matrix)
    return [[value / total for value in row] for row in matrix]


def predict_dixon_coles(
    elo_home: float, elo_away: float, neutral: bool, config: DixonColesConfig | None = None
) -> tuple[Prediction, list[list[float]]]:
    """Official prediction: Elo -> lambdas -> Dixon-Coles matrix -> W/D/L (zones) + score.

    Returns the :class:`Prediction` and the scoreline matrix (for persistence/auditing).
    """
    cfg = config or DixonColesConfig()
    lambda_home, lambda_away = elo_to_lambdas(elo_home, elo_away, neutral, cfg.base)
    matrix = dixon_coles_matrix(lambda_home, lambda_away, cfg.rho, cfg.base.max_goals)
    p_home, p_draw, p_away = wdl_from_matrix(matrix)
    home_goals, away_goals = most_likely_score(matrix)
    prediction = Prediction(
        p_home, p_draw, p_away, lambda_home, lambda_away, home_goals, away_goals
    )
    return prediction, matrix


def _dc_neg_log_likelihood(
    rho: float, low_score_samples: list[tuple[float, float, int, int]]
) -> float:
    """Negative log-likelihood contribution of rho (only the four low-score cells depend on it)."""
    total = 0.0
    for lambda_home, lambda_away, home_goals, away_goals in low_score_samples:
        tau = dixon_coles_tau(home_goals, away_goals, lambda_home, lambda_away, rho)
        total += math.log(tau if tau > 1e-12 else 1e-12)
    return -total


def fit_rho(
    samples: list[tuple[float, float, int, int]], bounds: tuple[float, float] = (-0.3, 0.3)
) -> float:
    """Fit the Dixon-Coles rho by MLE. ``samples`` are (lambda_home, lambda_away, home, away).

    Restricting the likelihood to the four low-score cells is exact, not an approximation: the
    four tau corrections cancel in the matrix total (the normalization does not depend on rho),
    so only those cells carry information about rho. Caveats (documented hypotheses): no temporal
    decay weighting (all matches weigh equally, unlike the original DC paper's xi), and this is a
    CONDITIONAL MLE — lambdas come fixed from the Elo mapping, so rho also absorbs any low-score
    mis-specification of that mapping. Validity requires tau > 0 within ``bounds``, guaranteed by
    the lambda clamps in ``elo_to_lambdas``.
    """
    from scipy.optimize import minimize_scalar

    low_score = [s for s in samples if s[2] <= 1 and s[3] <= 1]
    if not low_score:
        return 0.0
    result = minimize_scalar(
        lambda r: _dc_neg_log_likelihood(r, low_score), bounds=bounds, method="bounded"
    )
    return float(result.x)
