"""Tests for match-level backtesting metrics (Phase 8)."""

from __future__ import annotations

from wc26.backtesting.match_level import (
    accuracy,
    paired_bootstrap,
    ranked_probability_score,
    skill_score,
)


def test_rps_zero_for_perfect_prediction() -> None:
    assert ranked_probability_score((1.0, 0.0, 0.0), 0) == 0.0
    assert ranked_probability_score((0.0, 0.0, 1.0), 2) == 0.0


def test_rps_penalizes_distance_on_ordinal_scale() -> None:
    # Outcome is home (index 0). Putting mass on away (far) hurts more than on draw (near).
    far = ranked_probability_score((0.0, 0.0, 1.0), 0)
    near = ranked_probability_score((0.0, 1.0, 0.0), 0)
    assert far > near


def test_skill_score_sign() -> None:
    assert skill_score(0.8, 1.0) > 0  # model better than baseline
    assert skill_score(1.2, 1.0) < 0  # model worse


def test_accuracy_counts_argmax_hits() -> None:
    probs = [(0.6, 0.2, 0.2), (0.2, 0.2, 0.6)]
    outcomes = [0, 0]  # second prediction is wrong
    assert accuracy(probs, outcomes) == 0.5


def test_paired_bootstrap_detects_consistent_improvement() -> None:
    # Model loss consistently below baseline -> mean diff negative, CI below 0, low p.
    model = [0.5] * 200
    baseline = [0.8] * 200
    result = paired_bootstrap(model, baseline, n_boot=500)
    assert result.mean_difference < 0
    assert result.ci_high < 0
    assert result.p_value < 0.05
