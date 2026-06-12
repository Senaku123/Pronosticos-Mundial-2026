"""Tests for the live flow (Phase 12): conditioning, operative forecasts, MC bands."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from wc26.evaluation.live_scoring import (
    PlayedResult,
    PublishedPrediction,
    classify_results,
    monte_carlo_half_width,
    operative_forecasts,
)
from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.conditioning import KnownResults
from wc26.simulation.groups import simulate_group
from wc26.simulation.structure import GROUPS_2026, THIRD_PLACE_DATE
from wc26.simulation.tournament import (
    assign_thirds,
    run_monte_carlo,
    simulate_tournament,
    thirds_from_real_pairings,
)


def _all_team_elos() -> dict[str, float]:
    elos = {}
    for teams in GROUPS_2026.values():
        for seed, team in enumerate(teams):
            elos[team] = 1900.0 - 100.0 * seed
    return elos


def test_simulate_group_with_all_results_known_is_deterministic() -> None:
    teams = ["A1", "A2", "A3", "A4"]
    known = {
        frozenset(pair): scores
        for pair, scores in (
            (("A1", "A2"), {"A1": 2, "A2": 0}),
            (("A1", "A3"), {"A1": 1, "A3": 1}),
            (("A1", "A4"), {"A1": 3, "A4": 0}),
            (("A2", "A3"), {"A2": 1, "A3": 0}),
            (("A2", "A4"), {"A2": 2, "A4": 2}),
            (("A3", "A4"), {"A3": 0, "A4": 1}),
        )
    }
    elos = dict.fromkeys(teams, 1500.0)
    for seed in (1, 2):  # different rng streams, same fixed results -> same standings
        standings = simulate_group(
            elos, DixonColesConfig(), np.random.default_rng(seed), known_scores=known
        )
        table = {s.team: (s.points, s.goals_for, s.goals_against) for s in standings}
        assert table == {
            "A1": (7, 6, 1),
            "A2": (4, 3, 4),
            "A3": (1, 1, 3),
            "A4": (4, 3, 5),
        }
        # A2 and A4 tie on points and head-to-head (2-2): overall GD puts A2 above A4.
        assert [s.team for s in standings] == ["A1", "A2", "A4", "A3"]


def test_known_knockout_winner_always_advances() -> None:
    # Fix groups A and B completely so RU A = "South Africa" and RU B = "Bosnia and Herzegovina"
    # meet in R32 match 73; then fix that knockout pair's winner to the WEAKER side.
    elos = _all_team_elos()
    group_scores: dict[frozenset[str], dict[str, int]] = {}
    for letter in ("A", "B"):
        teams = GROUPS_2026[letter]
        for i, first in enumerate(teams):
            for second in teams[i + 1 :]:
                # Seed order wins 1-0, so standings follow the group list order exactly.
                group_scores[frozenset((first, second))] = {first: 1, second: 0}
    runner_up_a = GROUPS_2026["A"][1]
    runner_up_b = GROUPS_2026["B"][1]
    known = KnownResults(
        group_scores=group_scores,
        knockout_winners={frozenset((runner_up_a, runner_up_b)): runner_up_b},
    )

    rng = np.random.default_rng(11)
    stage_order = [
        "group",
        "round_of_32",
        "round_of_16",
        "quarterfinal",
        "semifinal",
        "final",
        "champion",
    ]
    for _ in range(25):
        reached = simulate_tournament(elos, DixonColesConfig(), rng, known=known)
        # The fixed winner always survives match 73; the fixed loser never does.
        assert stage_order.index(reached[runner_up_b]) >= stage_order.index("round_of_16")
        assert reached[runner_up_a] == "round_of_32"


def test_run_monte_carlo_without_known_results_unchanged() -> None:
    elos = _all_team_elos()
    baseline = run_monte_carlo(elos, DixonColesConfig(), n_simulations=50, seed=9)
    with_empty = run_monte_carlo(
        elos, DixonColesConfig(), n_simulations=50, seed=9, known=KnownResults()
    )
    assert baseline == with_empty


def test_operative_forecasts_picks_latest_publication_before_kickoff() -> None:
    day = dt.date(2026, 6, 20)
    rows = [
        PublishedPrediction(1, day, dt.date(2026, 6, 15), (0.5, 0.3, 0.2), 0),
        PublishedPrediction(1, day, dt.date(2026, 6, 19), (0.6, 0.25, 0.15), 0),
        PublishedPrediction(1, day, dt.date(2026, 6, 20), (0.7, 0.2, 0.1), 0),  # match-day: ok
        PublishedPrediction(1, day, dt.date(2026, 6, 21), (0.9, 0.05, 0.05), 0),  # after: never
        PublishedPrediction(2, day, dt.date(2026, 6, 21), (0.4, 0.3, 0.3), 1),  # only after
    ]
    chosen = operative_forecasts(rows)
    assert set(chosen) == {1}
    assert chosen[1].probs == (0.7, 0.2, 0.1)


def test_monte_carlo_half_width() -> None:
    assert monte_carlo_half_width(0.5, 10000) == pytest.approx(0.0098, abs=1e-4)
    assert monte_carlo_half_width(0.0, 10000) == 0.0
    assert monte_carlo_half_width(0.5, 0) == 0.0


# --- drawn-knockout inference: the third-place match must never decide a winner ---

_SF_DAY = dt.date(2026, 7, 14)
_FINAL_DAY = dt.date(2026, 7, 19)


def _drawn_semifinal_rows(*, bronze: bool, final: bool) -> list[PlayedResult]:
    rows = [
        PlayedResult(_SF_DAY, "TeamW", "TeamL", 1, 1),  # decided on penalties: TeamW advanced
        PlayedResult(dt.date(2026, 7, 15), "OtherW", "OtherL", 2, 0),
    ]
    if bronze:
        rows.append(PlayedResult(THIRD_PLACE_DATE, "TeamL", "OtherL", 1, 0))
    if final:
        rows.append(PlayedResult(_FINAL_DAY, "TeamW", "OtherW", 0, 1))
    return rows


def test_drawn_semifinal_before_bronze_is_left_simulated() -> None:
    known, warnings = classify_results(_drawn_semifinal_rows(bronze=False, final=False))
    assert frozenset(("TeamW", "TeamL")) not in known.knockout_winners
    assert len(warnings) == 1 and "left simulated" in warnings[0]


def test_drawn_semifinal_with_bronze_played_resolves_to_the_actual_winner() -> None:
    # The regression the audit caught: the loser reappears in the bronze final, and the old
    # any-later-appearance rule fixed the LOSER as the advancer. Now the bronze identifies the
    # eliminated side instead, so the real winner is derived.
    known, warnings = classify_results(_drawn_semifinal_rows(bronze=True, final=False))
    assert known.knockout_winners[frozenset(("TeamW", "TeamL"))] == "TeamW"
    assert warnings == []


def test_drawn_semifinal_after_final_resolves_via_the_final() -> None:
    known, _ = classify_results(_drawn_semifinal_rows(bronze=True, final=True))
    assert known.knockout_winners[frozenset(("TeamW", "TeamL"))] == "TeamW"


def test_third_place_match_is_never_a_conditioning_fact() -> None:
    known, _ = classify_results(_drawn_semifinal_rows(bronze=True, final=True))
    assert frozenset(("TeamL", "OtherL")) not in known.knockout_winners


def test_drawn_final_is_left_simulated() -> None:
    rows = _drawn_semifinal_rows(bronze=True, final=False)
    rows.append(PlayedResult(_FINAL_DAY, "TeamW", "OtherW", 3, 3))  # 2022-style shootout final
    known, warnings = classify_results(rows)
    assert frozenset(("TeamW", "OtherW")) not in known.knockout_winners
    assert any("left simulated" in w for w in warnings)


# --- real R32 pairings lock the third-place slotting; unconsumed results must raise ---


def test_thirds_from_real_pairings_pins_slots_and_rejects_inconsistency() -> None:
    winners = {letter: f"W{letter}" for letter in GROUPS_2026}
    third_by_group = {letter: f"T{letter}" for letter in "ABCDEFGH"}
    # Match 74 is anchored by the group E winner; group C is in its allowed set ABCDF.
    fixed = thirds_from_real_pairings(frozenset({frozenset(("WE", "TC"))}), winners, third_by_group)
    assert fixed == {74: "C"}
    assignment = assign_thirds(set(third_by_group), fixed)
    assert assignment[74] == "C"
    assert sorted(assignment.values()) == sorted(third_by_group)

    with pytest.raises(ValueError, match="inconsistent"):
        # Group G is not allowed in match 74 (slot set ABCDF).
        thirds_from_real_pairings(frozenset({frozenset(("WE", "TG"))}), winners, third_by_group)


def test_run_monte_carlo_raises_on_unconsumed_knockout_result() -> None:
    # Fix group A completely so its last team is eliminated in groups; a real knockout result
    # involving it can then never match a simulated pairing and must raise, never be ignored.
    elos = _all_team_elos()
    teams = GROUPS_2026["A"]
    group_scores = {
        frozenset((first, second)): {first: 1, second: 0}
        for i, first in enumerate(teams)
        for second in teams[i + 1 :]
    }
    eliminated = teams[3]
    known = KnownResults(
        group_scores=group_scores,
        knockout_winners={frozenset((eliminated, GROUPS_2026["B"][0])): eliminated},
    )
    with pytest.raises(ValueError, match="never matched a simulated pairing"):
        run_monte_carlo(elos, DixonColesConfig(), n_simulations=20, seed=5, known=known)
