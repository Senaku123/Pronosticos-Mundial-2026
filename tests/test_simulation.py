"""Tests for the Monte Carlo simulation engine (Phase 10): sampling, tie-breaks, knockout."""

from __future__ import annotations

import numpy as np

from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.groups import TeamStanding, rank_group, simulate_group
from wc26.simulation.knockout import resolve_knockout
from wc26.simulation.match_sampler import sample_scoreline


def test_sample_scoreline_in_range() -> None:
    rng = np.random.default_rng(1)
    matrix = [[0.25, 0.25], [0.25, 0.25]]
    for _ in range(50):
        i, j = sample_scoreline(matrix, rng)
        assert 0 <= i <= 1 and 0 <= j <= 1


def test_sample_scoreline_follows_mass() -> None:
    rng = np.random.default_rng(2)
    matrix = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 1.0, 0.0]]  # all mass on 2-1
    assert sample_scoreline(matrix, rng) == (2, 1)


def test_rank_group_uses_head_to_head_before_global_gd() -> None:
    # A and B tie on points; A lost head-to-head but has a big global GD. H2H must win.
    standings = {
        "A": TeamStanding("A", 1800, points=6, goals_for=10, goals_against=2),  # GD +8
        "B": TeamStanding("B", 1500, points=6, goals_for=4, goals_against=3),  # GD +1
        "C": TeamStanding("C", 1500, points=0, goals_for=0, goals_against=9),
    }
    head_to_head = {("A", "B"): (0, 1), ("A", "C"): (5, 0), ("B", "C"): (3, 1)}
    ranked = rank_group(standings, head_to_head)
    assert ranked.index("B") < ranked.index("A")  # B beat A head-to-head -> B ranks higher
    assert ranked[-1] == "C"


def test_simulate_group_returns_four_ranked_teams() -> None:
    rng = np.random.default_rng(3)
    elos = {"T1": 2000.0, "T2": 1700.0, "T3": 1500.0, "T4": 1300.0}
    standings = simulate_group(elos, DixonColesConfig(), rng)
    assert len(standings) == 4
    assert {s.team for s in standings} == set(elos)


def test_knockout_always_has_a_winner() -> None:
    rng = np.random.default_rng(4)
    for _ in range(100):
        winner = resolve_knockout(1600.0, 1600.0, True, DixonColesConfig(), rng)
        assert winner in (0, 1)


def test_stronger_team_wins_knockout_more_often() -> None:
    rng = np.random.default_rng(5)
    home_wins = sum(
        resolve_knockout(2000.0, 1400.0, True, DixonColesConfig(), rng) == 0 for _ in range(400)
    )
    assert home_wins > 300  # a 600-Elo favourite should advance well over half the time
