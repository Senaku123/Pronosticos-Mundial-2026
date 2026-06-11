"""Tests for the baseline models (Phase 6)."""

from __future__ import annotations

import pytest

from wc26.models.baselines import (
    BASELINES,
    poisson_scoreline_matrix,
    simple_poisson,
    wdl_from_matrix,
)


@pytest.mark.parametrize("name", list(BASELINES))
def test_probabilities_are_a_valid_distribution(name: str) -> None:
    predict = BASELINES[name]
    p = predict(1800.0, 1500.0, False)
    assert p.p_home_win >= 0 and p.p_draw >= 0 and p.p_away_win >= 0
    assert abs(p.p_home_win + p.p_draw + p.p_away_win - 1.0) < 1e-9


@pytest.mark.parametrize("name", list(BASELINES))
def test_stronger_team_is_favoured(name: str) -> None:
    predict = BASELINES[name]
    strong_home = predict(1900.0, 1500.0, neutral=True)
    strong_away = predict(1500.0, 1900.0, neutral=True)
    assert strong_home.p_home_win > strong_home.p_away_win
    assert strong_away.p_away_win > strong_away.p_home_win


def test_home_advantage_increases_home_win() -> None:
    at_home = simple_poisson(1600.0, 1600.0, neutral=False)
    neutral = simple_poisson(1600.0, 1600.0, neutral=True)
    assert at_home.p_home_win > neutral.p_home_win


def test_scoreline_matrix_sums_to_one() -> None:
    matrix = poisson_scoreline_matrix(1.8, 1.1, max_goals=10)
    total = sum(sum(row) for row in matrix)
    assert abs(total - 1.0) < 1e-9
    p_home, p_draw, p_away = wdl_from_matrix(matrix)
    assert abs(p_home + p_draw + p_away - 1.0) < 1e-9


def test_simple_poisson_reports_goals_and_score() -> None:
    p = simple_poisson(2000.0, 1500.0, neutral=False)
    assert p.expected_goals_home is not None and p.expected_goals_home > 0
    assert p.predicted_home_score is not None and p.predicted_away_score is not None
    assert p.expected_goals_home > p.expected_goals_away  # stronger team scores more
