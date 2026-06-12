"""Golden tests for the historical 32-team simulation engine (Phase 11)."""

from __future__ import annotations

import datetime as dt

import numpy as np

from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.structure32 import STAGES_32, WorldCupEdition
from wc26.simulation.tournament32 import run_monte_carlo32, simulate_tournament32


def _edition(groups: dict[str, list[str]] | None = None) -> WorldCupEdition:
    built = groups or {letter: [f"{letter}{i}" for i in range(1, 5)] for letter in "ABCDEFGH"}
    return WorldCupEdition(
        year=2099,
        start_date=dt.date(2099, 6, 1),
        end_date=dt.date(2099, 6, 30),
        hosts=frozenset(),
        groups=built,
        champion=built["A"][0],
    )


def _team_elos(edition: WorldCupEdition) -> dict[str, float]:
    elos = {}
    for teams in edition.groups.values():
        for seed, team in enumerate(teams):
            elos[team] = 1900.0 - 100.0 * seed
    return elos


def test_simulate_tournament32_valid_bracket_counts() -> None:
    edition = _edition()
    reached = simulate_tournament32(
        edition, _team_elos(edition), DixonColesConfig(), np.random.default_rng(7)
    )
    assert len(reached) == 32
    counts: dict[str, int] = {}
    for stage in reached.values():
        counts[stage] = counts.get(stage, 0) + 1
    assert counts.get("champion", 0) == 1
    assert counts.get("final", 0) == 1
    assert counts.get("semifinal", 0) == 2
    assert counts.get("quarterfinal", 0) == 4
    assert counts.get("round_of_16", 0) == 8
    assert counts.get("group", 0) == 16


def test_monte_carlo32_stage_probabilities_are_monotonic_and_sum() -> None:
    edition = _edition()
    probs = run_monte_carlo32(
        edition, _team_elos(edition), DixonColesConfig(), n_simulations=200, seed=1
    )
    assert len(probs) == 32
    for stage_probs in probs.values():
        values = [stage_probs[s] for s in STAGES_32]
        assert all(values[i] >= values[i + 1] - 1e-9 for i in range(len(values) - 1))
    assert abs(sum(sp["champion"] for sp in probs.values()) - 1.0) < 1e-9
    assert abs(sum(sp["round_of_16"] for sp in probs.values()) - 16.0) < 1e-9
    assert abs(sum(sp["quarterfinal"] for sp in probs.values()) - 8.0) < 1e-9


def test_monte_carlo32_dominant_team_usually_wins() -> None:
    edition = _edition()
    elos = dict.fromkeys((t for g in edition.groups.values() for t in g), 1500.0)
    elos["A1"] = 2500.0
    probs = run_monte_carlo32(edition, elos, DixonColesConfig(), n_simulations=300, seed=3)
    assert probs["A1"]["champion"] > 0.8
