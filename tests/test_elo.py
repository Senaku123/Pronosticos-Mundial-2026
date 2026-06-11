"""Tests for the internal Elo math."""

from __future__ import annotations

import datetime as dt

from wc26.models.elo import (
    EloConfig,
    MatchInput,
    compute_elo_history,
    expected_score,
    goal_difference_multiplier,
    predict_expected,
)


def test_predict_expected_applies_home_advantage() -> None:
    # On a neutral field equal ratings -> 0.5; with home advantage the home team is favoured.
    assert predict_expected(1500, 1500, neutral=True) == 0.5
    assert predict_expected(1500, 1500, neutral=False) > 0.5
    # Home advantage must match the training convention (expected_score with the bonus added).
    cfg = EloConfig()
    assert predict_expected(1500, 1500, neutral=False, config=cfg) == expected_score(
        1500 + cfg.home_advantage, 1500
    )


def test_expected_score_symmetry() -> None:
    assert expected_score(1500, 1500) == 0.5
    assert abs(expected_score(1600, 1400) + expected_score(1400, 1600) - 1.0) < 1e-9
    assert expected_score(1900, 1500) > expected_score(1600, 1500)


def test_goal_difference_multiplier() -> None:
    assert goal_difference_multiplier(0) == 1.0
    assert goal_difference_multiplier(1) == 1.0
    assert goal_difference_multiplier(-2) == 1.5
    assert goal_difference_multiplier(3) == (11.0 + 3) / 8.0


def test_single_update_zero_sum() -> None:
    # Equal ratings, neutral venue, home wins by 1, importance 1.0, base_k 40 -> delta = 20.
    match = MatchInput(1, dt.date(2020, 1, 1), 10, 20, 1, 0, neutral=True, importance_weight=1.0)
    records = compute_elo_history([match], EloConfig(base_k=40.0))
    home = next(r for r in records if r.team_id == 10)
    away = next(r for r in records if r.team_id == 20)
    assert home.rating_pre == 1500.0
    assert home.rating_post == 1520.0
    assert away.rating_post == 1480.0
    # Zero-sum: total rating is conserved.
    assert home.rating_post + away.rating_post == home.rating_pre + away.rating_pre
