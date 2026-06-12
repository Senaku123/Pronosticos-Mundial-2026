"""Probability calibration (Platt scaling) and reliability metrics (Phase 7b, addendum §2).

A model can be sharp but miscalibrated: when it says "60%" the event may happen 50% of the time.
Platt scaling fits, per outcome (home/draw/away, one-vs-rest), a logistic map of the raw
probability's logit to a calibrated probability; the three are renormalized to sum to 1.

Calibration MUST be fit on a temporal-train block and measured on a later test block (out-of-time);
fitting and scoring on the same data flatters the model. These functions are pure.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

# Outcome encoding used throughout: 0 = home win, 1 = draw, 2 = away win.
HOME, DRAW, AWAY = 0, 1, 2

ProbTriplet = tuple[float, float, float]


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def fit_platt(raw_probs: list[float], binary_labels: list[int]) -> tuple[float, float]:
    """Fit (A, B) of calibrated = sigmoid(A * logit(p) + B) by minimizing binary cross-entropy."""
    from scipy.optimize import minimize

    p = np.clip(np.asarray(raw_probs, dtype=float), 1e-6, 1.0 - 1e-6)
    z = np.log(p / (1.0 - p))
    y = np.asarray(binary_labels, dtype=float)

    def nll(params: np.ndarray) -> float:
        a, b = params
        q = np.clip(1.0 / (1.0 + np.exp(-(a * z + b))), 1e-12, 1.0 - 1e-12)
        return float(-np.sum(y * np.log(q) + (1.0 - y) * np.log(1.0 - q)))

    result = minimize(nll, x0=np.array([1.0, 0.0]), method="Nelder-Mead")
    return float(result.x[0]), float(result.x[1])


@dataclass(frozen=True)
class PlattCalibrator:
    """Per-outcome Platt parameters; calibrate then renormalize the W/D/L triplet."""

    a_home: float
    b_home: float
    a_draw: float
    b_draw: float
    a_away: float
    b_away: float

    @classmethod
    def fit(cls, probs: list[ProbTriplet], outcomes: list[int]) -> PlattCalibrator:
        labels_home = [1 if o == HOME else 0 for o in outcomes]
        labels_draw = [1 if o == DRAW else 0 for o in outcomes]
        labels_away = [1 if o == AWAY else 0 for o in outcomes]
        a_home, b_home = fit_platt([p[0] for p in probs], labels_home)
        a_draw, b_draw = fit_platt([p[1] for p in probs], labels_draw)
        a_away, b_away = fit_platt([p[2] for p in probs], labels_away)
        return cls(a_home, b_home, a_draw, b_draw, a_away, b_away)

    def calibrate(self, p_home: float, p_draw: float, p_away: float) -> ProbTriplet:
        c_home = _sigmoid(self.a_home * _logit(p_home) + self.b_home)
        c_draw = _sigmoid(self.a_draw * _logit(p_draw) + self.b_draw)
        c_away = _sigmoid(self.a_away * _logit(p_away) + self.b_away)
        total = c_home + c_draw + c_away
        return c_home / total, c_draw / total, c_away / total

    def to_dict(self) -> dict[str, float]:
        """Six Platt parameters as a plain dict, for persisting in a run's ``config_json``."""
        return {
            "a_home": self.a_home,
            "b_home": self.b_home,
            "a_draw": self.a_draw,
            "b_draw": self.b_draw,
            "a_away": self.a_away,
            "b_away": self.b_away,
        }

    @classmethod
    def from_dict(cls, params: Mapping[str, float]) -> PlattCalibrator:
        """Rebuild a calibrator from persisted parameters (e.g. the official run's config)."""
        return cls(
            a_home=float(params["a_home"]),
            b_home=float(params["b_home"]),
            a_draw=float(params["a_draw"]),
            b_draw=float(params["b_draw"]),
            a_away=float(params["a_away"]),
            b_away=float(params["b_away"]),
        )


def calibrate_matrix(matrix: list[list[float]], calibrator: PlattCalibrator) -> list[list[float]]:
    """Rescale a scoreline matrix's W/D/L zones to the Platt-calibrated triplet.

    Cells keep their relative proportions WITHIN each zone (home-win / draw / away-win), the
    three zone totals become exactly the calibrated W/D/L, and the matrix still sums to 1. This
    lets the Monte Carlo simulator inherit the calibration that won the go/no-go while keeping
    the scoreline matrix as the single source of truth (addendum §2).
    """
    raw_home = raw_draw = raw_away = 0.0
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if i > j:
                raw_home += value
            elif i == j:
                raw_draw += value
            else:
                raw_away += value
    cal_home, cal_draw, cal_away = calibrator.calibrate(raw_home, raw_draw, raw_away)
    factor_home = cal_home / raw_home if raw_home > 0 else 0.0
    factor_draw = cal_draw / raw_draw if raw_draw > 0 else 0.0
    factor_away = cal_away / raw_away if raw_away > 0 else 0.0
    return [
        [
            value * (factor_home if i > j else (factor_draw if i == j else factor_away))
            for j, value in enumerate(row)
        ]
        for i, row in enumerate(matrix)
    ]


def reliability_bins(
    class_probs: list[float], class_labels: list[int], n_bins: int = 10
) -> list[tuple[int, float, float, int]]:
    """Return (bin, mean_predicted, observed_frequency, count) for each non-empty bin."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, y in zip(class_probs, class_labels, strict=True):
        idx = min(int(p * n_bins), n_bins - 1)
        buckets[idx].append((p, y))
    out = []
    for i, bucket in enumerate(buckets):
        if bucket:
            mean_pred = sum(p for p, _ in bucket) / len(bucket)
            observed = sum(y for _, y in bucket) / len(bucket)
            out.append((i, mean_pred, observed, len(bucket)))
    return out


def expected_calibration_error(
    class_probs: list[float], class_labels: list[int], n_bins: int = 10
) -> float:
    """Sample-weighted average gap between predicted probability and observed frequency."""
    bins = reliability_bins(class_probs, class_labels, n_bins)
    n = len(class_probs)
    if n == 0:
        return 0.0
    return sum(count * abs(mean_pred - observed) for _, mean_pred, observed, count in bins) / n


def log_loss(probs: list[ProbTriplet], outcomes: list[int]) -> float:
    """Multiclass log loss (lower is better)."""
    if not probs:
        return 0.0
    total = 0.0
    for triplet, o in zip(probs, outcomes, strict=True):
        p = min(max(triplet[o], 1e-12), 1.0)
        total -= math.log(p)
    return total / len(probs)


def brier_score(probs: list[ProbTriplet], outcomes: list[int]) -> float:
    """Multiclass Brier score (lower is better)."""
    if not probs:
        return 0.0
    total = 0.0
    for (p_home, p_draw, p_away), o in zip(probs, outcomes, strict=True):
        target = [0.0, 0.0, 0.0]
        target[o] = 1.0
        total += (p_home - target[0]) ** 2 + (p_draw - target[1]) ** 2 + (p_away - target[2]) ** 2
    return total / len(probs)
