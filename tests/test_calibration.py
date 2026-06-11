"""Tests for probability calibration and reliability metrics (Phase 7b)."""

from __future__ import annotations

from wc26.models.calibration import (
    PlattCalibrator,
    brier_score,
    expected_calibration_error,
    log_loss,
    reliability_bins,
)


def test_calibrated_probabilities_sum_to_one() -> None:
    cal = PlattCalibrator(1.0, 0.0, 1.0, 0.0, 1.0, 0.0)
    c_home, c_draw, c_away = cal.calibrate(0.5, 0.3, 0.2)
    assert abs(c_home + c_draw + c_away - 1.0) < 1e-9


def test_platt_corrects_overconfidence() -> None:
    # Build an overconfident-but-ordered set: model says 0.9 home but home only wins ~60%.
    probs = [(0.9, 0.05, 0.05)] * 60 + [(0.9, 0.05, 0.05)] * 40
    outcomes = [0] * 60 + [2] * 40  # home wins 60%, away 40% despite "0.9 home"
    cal = PlattCalibrator.fit(probs, outcomes)
    calibrated_home = cal.calibrate(0.9, 0.05, 0.05)[0]
    # Calibration should pull the inflated 0.9 down toward the true ~0.6.
    assert calibrated_home < 0.9
    assert calibrated_home > 0.4


def test_ece_zero_for_perfect_calibration() -> None:
    # Predicted 0.5 and exactly half are positive -> ECE 0.
    probs = [0.5] * 100
    labels = [1] * 50 + [0] * 50
    assert expected_calibration_error(probs, labels) < 1e-9


def test_ece_positive_for_miscalibration() -> None:
    probs = [0.9] * 100
    labels = [1] * 50 + [0] * 50  # claims 90% but only 50% happen
    assert expected_calibration_error(probs, labels) > 0.3


def test_reliability_bins_cover_samples() -> None:
    probs = [0.05, 0.15, 0.95]
    labels = [0, 0, 1]
    bins = reliability_bins(probs, labels, n_bins=10)
    assert sum(count for *_, count in bins) == 3


def test_log_loss_and_brier_reward_truth() -> None:
    confident_right = [(0.8, 0.1, 0.1)]
    confident_wrong = [(0.1, 0.1, 0.8)]
    outcomes = [0]
    assert log_loss(confident_right, outcomes) < log_loss(confident_wrong, outcomes)
    assert brier_score(confident_right, outcomes) < brier_score(confident_wrong, outcomes)
