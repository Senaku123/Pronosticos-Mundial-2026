"""Tests for the full 2026 tournament simulation (Phase 10)."""

from __future__ import annotations

import numpy as np

from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.structure import GROUPS_2026, STAGES, THIRD_SLOTS
from wc26.simulation.tournament import assign_thirds, run_monte_carlo, simulate_tournament


def _team_elos() -> dict[str, float]:
    elos = {}
    for teams in GROUPS_2026.values():
        for seed, team in enumerate(teams):
            elos[team] = 1900.0 - 100.0 * seed  # pot-1 strongest within each group
    return elos


def test_assign_thirds_respects_slot_constraints() -> None:
    allowed = dict(THIRD_SLOTS)
    assignment = assign_thirds(set("ABCDEFGH"))
    assert len(assignment) == 8
    assert len(set(assignment.values())) == 8  # eight distinct groups
    for match_no, group in assignment.items():
        assert group in allowed[match_no]  # no same-group rematch, valid slot


def test_simulate_tournament_has_exactly_one_champion() -> None:
    reached = simulate_tournament(_team_elos(), DixonColesConfig(), np.random.default_rng(7))
    assert len(reached) == 48
    counts: dict[str, int] = {}
    for stage in reached.values():
        counts[stage] = counts.get(stage, 0) + 1
    assert counts.get("champion", 0) == 1
    assert counts.get("final", 0) == 1  # the losing finalist
    assert counts.get("semifinal", 0) == 2
    assert counts.get("quarterfinal", 0) == 4
    assert counts.get("round_of_16", 0) == 8
    assert counts.get("round_of_32", 0) == 16


def test_monte_carlo_stage_probabilities_are_monotonic_and_sum() -> None:
    probs = run_monte_carlo(_team_elos(), DixonColesConfig(), n_simulations=200, seed=1)
    assert len(probs) == 48
    for stage_probs in probs.values():
        values = [stage_probs[s] for s in STAGES]
        assert all(values[i] >= values[i + 1] - 1e-9 for i in range(len(values) - 1))
    assert abs(sum(sp["champion"] for sp in probs.values()) - 1.0) < 1e-9
    assert abs(sum(sp["round_of_16"] for sp in probs.values()) - 16.0) < 1e-9
