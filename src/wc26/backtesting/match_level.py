"""Match-level backtesting metrics and significance tests (Phase 8, addendum §3, §4).

Primary metrics are probabilistic (log loss, Brier, RPS) and calibration (ECE) - accuracy is
descriptive only, because in a 3-class problem with a ~25% draw rate accuracy can reward the worst
probabilistic model. Models are compared by skill score against the Elo-only baseline, and the
key difference is tested with a paired bootstrap (is the improvement real or noise?).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wc26.models.calibration import (
    ProbTriplet,
    brier_score,
    expected_calibration_error,
    log_loss,
)

CLASSES = (("home", 0), ("draw", 1), ("away", 2))


def ranked_probability_score(probs: ProbTriplet, outcome: int) -> float:
    """RPS for the ordered outcome [home, draw, away] (rewards being close on the ordinal scale)."""
    observed = [0.0, 0.0, 0.0]
    observed[outcome] = 1.0
    cum_p = 0.0
    cum_o = 0.0
    total = 0.0
    for i in range(len(probs) - 1):
        cum_p += probs[i]
        cum_o += observed[i]
        total += (cum_p - cum_o) ** 2
    return total / (len(probs) - 1)


def mean_rps(probs: list[ProbTriplet], outcomes: list[int]) -> float:
    if not probs:
        return 0.0
    return sum(ranked_probability_score(p, o) for p, o in zip(probs, outcomes, strict=True)) / len(
        probs
    )


def accuracy(probs: list[ProbTriplet], outcomes: list[int]) -> float:
    """Descriptive only: share of matches whose argmax class matched the outcome."""
    if not probs:
        return 0.0
    hits = sum(
        1 for p, o in zip(probs, outcomes, strict=True) if max(range(3), key=p.__getitem__) == o
    )
    return hits / len(probs)


def average_ece(probs: list[ProbTriplet], outcomes: list[int]) -> float:
    total = 0.0
    for _, c in CLASSES:
        class_probs = [p[c] for p in probs]
        labels = [1 if o == c else 0 for o in outcomes]
        total += expected_calibration_error(class_probs, labels)
    return total / len(CLASSES)


def skill_score(model_loss: float, baseline_loss: float) -> float:
    """1 - model/baseline: positive means the model improves on the baseline (for loss metrics)."""
    if baseline_loss == 0:
        return 0.0
    return 1.0 - model_loss / baseline_loss


def per_match_log_loss(probs: list[ProbTriplet], outcomes: list[int]) -> list[float]:
    """Per-match log losses, the paired-test input (public: the live flow pairs on these too)."""
    return [log_loss([p], [o]) for p, o in zip(probs, outcomes, strict=True)]


@dataclass(frozen=True)
class PairedTest:
    """Result of a paired bootstrap comparing a model's loss to a baseline's, per match."""

    mean_difference: float  # model - baseline; negative means the model is better
    ci_low: float
    ci_high: float
    p_value: float  # probability the model is NOT better (mean difference >= 0)


def paired_bootstrap(
    model_losses: list[float],
    baseline_losses: list[float],
    n_boot: int = 2000,
    seed: int = 20260611,
) -> PairedTest:
    """Bootstrap the mean per-match loss difference (model - baseline)."""
    diff = np.asarray(model_losses, dtype=float) - np.asarray(baseline_losses, dtype=float)
    n = len(diff)
    if n == 0:
        return PairedTest(0.0, 0.0, 0.0, 1.0)
    rng = np.random.default_rng(seed)
    means = np.array([diff[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    return PairedTest(
        mean_difference=float(diff.mean()),
        ci_low=float(np.percentile(means, 2.5)),
        ci_high=float(np.percentile(means, 97.5)),
        p_value=float(np.mean(means >= 0.0)),
    )


@dataclass(frozen=True)
class ModelEvaluation:
    """All match-level metrics for one model on a test set."""

    model_name: str
    n: int
    log_loss: float
    brier: float
    rps: float
    ece: float
    accuracy: float


def evaluate_model(
    model_name: str, probs: list[ProbTriplet], outcomes: list[int]
) -> ModelEvaluation:
    return ModelEvaluation(
        model_name=model_name,
        n=len(probs),
        log_loss=log_loss(probs, outcomes),
        brier=brier_score(probs, outcomes),
        rps=mean_rps(probs, outcomes),
        ece=average_ece(probs, outcomes),
        accuracy=accuracy(probs, outcomes),
    )


def evaluation_metric_rows(
    backtest_run_id: int, evaluations: dict[str, ModelEvaluation], baseline: str
) -> list[dict[str, object]]:
    """Long-format ``backtest_metrics`` rows for evaluations vs a baseline.

    The single source of the metric names: the live scoring (Phase 12) must persist exactly the
    Phase 8 names or the live-vs-backtest comparison silently drifts.
    """
    base = evaluations[baseline]
    rows: list[dict[str, object]] = []
    for name, evaluation in evaluations.items():
        values = {
            "log_loss": evaluation.log_loss,
            "brier": evaluation.brier,
            "rps": evaluation.rps,
            "ece": evaluation.ece,
            "accuracy": evaluation.accuracy,
            "skill_log_loss_vs_elo": skill_score(evaluation.log_loss, base.log_loss),
            "skill_brier_vs_elo": skill_score(evaluation.brier, base.brier),
        }
        rows.extend(
            {"backtest_run_id": backtest_run_id, "model_name": name, "metric": m, "value": v}
            for m, v in values.items()
        )
    return rows
