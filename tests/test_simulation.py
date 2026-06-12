"""Tests for the Monte Carlo simulation engine (Phase 10): sampling, tie-breaks, knockout."""

from __future__ import annotations

import numpy as np

from wc26.models.calibration import PlattCalibrator, calibrate_matrix
from wc26.models.dixon_coles import DixonColesConfig, dixon_coles_matrix
from wc26.simulation.groups import TeamStanding, orient_for_host, rank_group, simulate_group
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


def test_group_tiebreakers() -> None:
    """Article 13 Step 2: head-to-head is RE-APPLIED to the subset still tied (audit case).

    A 2-1 B, B 3-0 C, C 2-0 A, and all three beat D. Mini-table: B first (GD +2); A and C stay
    tied on (3 pts, GD -1, GF 2). FIFA re-applies head-to-head between A and C only: C beat A
    2-0, so C ranks above A even though A has a much better OVERALL goal difference (5-0 vs D).
    A single composite sort (h2h then global) would wrongly put A above C.
    """
    standings = {
        "A": TeamStanding("A", 1500, points=6, goals_for=7, goals_against=3),  # +5-0 vs D
        "B": TeamStanding("B", 1500, points=6, goals_for=5, goals_against=2),
        "C": TeamStanding("C", 1500, points=6, goals_for=3, goals_against=3),
        "D": TeamStanding("D", 1500, points=0, goals_for=0, goals_against=7),
    }
    head_to_head = {
        ("A", "B"): (2, 1),
        ("B", "C"): (3, 0),
        ("C", "A"): (2, 0),
        ("A", "D"): (5, 0),
        ("B", "D"): (1, 0),
        ("C", "D"): (1, 0),
    }
    ranked = rank_group(standings, head_to_head)
    assert ranked == ["B", "C", "A", "D"]  # C above A via re-applied head-to-head


def test_orient_for_host() -> None:
    hosts = frozenset({"Mexico"})
    assert orient_for_host("Mexico", "Chile", hosts) == ("Mexico", "Chile", False)
    assert orient_for_host("Chile", "Mexico", hosts) == ("Mexico", "Chile", False)  # swapped
    assert orient_for_host("Chile", "Peru", hosts) == ("Chile", "Peru", True)  # neutral


def test_calibrate_matrix_zones_match_calibrated_triplet() -> None:
    matrix = dixon_coles_matrix(1.6, 1.1, -0.05, max_goals=10)
    calibrator = PlattCalibrator(0.9, 0.1, 1.1, -0.05, 0.95, 0.0)
    calibrated = calibrate_matrix(matrix, calibrator)
    # Matrix still sums to 1 and zone sums equal the calibrated W/D/L triplet.
    assert abs(sum(sum(row) for row in calibrated) - 1.0) < 1e-9
    raw_zones = [0.0, 0.0, 0.0]
    cal_zones = [0.0, 0.0, 0.0]
    for i in range(len(matrix)):
        for j in range(len(matrix)):
            zone = 0 if i > j else (1 if i == j else 2)
            raw_zones[zone] += matrix[i][j]
            cal_zones[zone] += calibrated[i][j]
    expected = calibrator.calibrate(*raw_zones)
    for got, want in zip(cal_zones, expected, strict=True):
        assert abs(got - want) < 1e-9


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
