"""Tests for tournament-level backtest metrics and actual-stage inference (Phase 11)."""

from __future__ import annotations

import datetime as dt

import pytest

from wc26.backtesting.tournament_level import (
    PlayedMatch,
    assess_champion,
    block_bootstrap_mean,
    format_uniform_cumulative,
    infer_deepest_stages,
    mean_stage_rps,
    stage_rps,
    validate_groups_against_matches,
)
from wc26.simulation.structure32 import (
    FINAL_32,
    QUARTERFINALS_32,
    R16_MATCHES_32,
    SEMIFINALS_32,
    STAGES_32,
    WorldCupEdition,
)


def _synthetic_edition(champion: str = "D1") -> tuple[WorldCupEdition, list[PlayedMatch]]:
    """A full deterministic 64-match tournament: seeds 1-2 advance, first slot wins knockouts.

    The final (A1 v D1) is a 2-2 draw decided by the edition's recorded champion, mirroring how
    results.csv records shootout finals (e.g. 2022). The third-place match is the day before.
    """
    groups = {letter: [f"{letter}{i}" for i in range(1, 5)] for letter in "ABCDEFGH"}
    edition = WorldCupEdition(
        year=2099,
        start_date=dt.date(2099, 6, 1),
        end_date=dt.date(2099, 6, 13),
        hosts=frozenset(),
        groups=groups,
        champion=champion,
    )

    matches: list[PlayedMatch] = []
    for teams in groups.values():
        pairs_by_day = {
            1: [(teams[0], teams[1]), (teams[2], teams[3])],
            2: [(teams[0], teams[2]), (teams[1], teams[3])],
            3: [(teams[0], teams[3]), (teams[1], teams[2])],
        }
        for day, pairs in pairs_by_day.items():
            for home, away in pairs:
                # The lower seed (earlier in the group list) always wins 2-0.
                home_wins = teams.index(home) < teams.index(away)
                matches.append(
                    PlayedMatch(
                        dt.date(2099, 6, day),
                        home,
                        away,
                        2 if home_wins else 0,
                        0 if home_wins else 2,
                    )
                )

    placed = {}
    for letter, teams in groups.items():
        placed[("W", letter)] = teams[0]
        placed[("RU", letter)] = teams[1]
    winner_of: dict[int, str] = {}
    for match_no, home_slot, away_slot in R16_MATCHES_32:
        home, away = placed[home_slot], placed[away_slot]
        matches.append(PlayedMatch(dt.date(2099, 6, 5), home, away, 1, 0))
        winner_of[match_no] = home
    for day, stage_matches in ((8, QUARTERFINALS_32), (10, SEMIFINALS_32)):
        for match_no, source_home, source_away in stage_matches:
            home, away = winner_of[source_home], winner_of[source_away]
            matches.append(PlayedMatch(dt.date(2099, 6, day), home, away, 1, 0))
            winner_of[match_no] = home
    sf_losers = [
        winner_of[src]
        for _, h, a in SEMIFINALS_32
        for src in (h, a)
        if winner_of[src] not in (winner_of[61], winner_of[62])
    ]
    matches.append(PlayedMatch(dt.date(2099, 6, 12), sf_losers[0], sf_losers[1], 1, 0))
    final_no, sf1, sf2 = FINAL_32[0]
    matches.append(PlayedMatch(dt.date(2099, 6, 13), winner_of[sf1], winner_of[sf2], 2, 2))
    return edition, matches


def test_infer_deepest_stages_full_synthetic_tournament() -> None:
    edition, matches = _synthetic_edition(champion="D1")  # the AWAY finalist (drawn final)
    stages = infer_deepest_stages(edition, matches)
    assert stages["D1"] == "champion"
    assert stages["A1"] == "final"
    assert stages["E1"] == "semifinal"
    assert stages["F1"] == "semifinal"
    assert sum(1 for s in stages.values() if s == "group") == 16
    assert sum(1 for s in stages.values() if s == "round_of_16") == 8
    assert sum(1 for s in stages.values() if s == "quarterfinal") == 4


def test_infer_deepest_stages_rejects_champion_not_in_final() -> None:
    edition, matches = _synthetic_edition(champion="E1")  # semifinalist, not a finalist
    with pytest.raises(ValueError, match="not one of the finalists"):
        infer_deepest_stages(edition, matches)


def test_validate_groups_against_matches_detects_wrong_group() -> None:
    edition, matches = _synthetic_edition()
    validate_groups_against_matches(edition, matches)  # the true structure passes

    tampered = dict(edition.groups)
    tampered["A"], tampered["B"] = (
        ["A1", "A2", "A3", "B4"],
        ["B1", "B2", "B3", "A4"],
    )
    wrong = WorldCupEdition(
        edition.year,
        edition.start_date,
        edition.end_date,
        edition.hosts,
        tampered,
        edition.champion,
    )
    with pytest.raises(ValueError, match="disagrees with the data"):
        validate_groups_against_matches(wrong, matches)


def test_stage_rps_perfect_forecast_is_zero() -> None:
    # All mass on "quarterfinal": reaches QF with certainty, never the semifinal.
    cumulative = {s: 1.0 for s in STAGES_32[:3]} | {s: 0.0 for s in STAGES_32[3:]}
    assert stage_rps(cumulative, "quarterfinal") == pytest.approx(0.0)


def test_stage_rps_rewards_closer_forecasts() -> None:
    sharp = {s: 1.0 for s in STAGES_32[:3]} | {s: 0.0 for s in STAGES_32[3:]}
    uniform = format_uniform_cumulative()
    confident_wrong = {s: 1.0 for s in STAGES_32}  # "certain champion"
    actual = "quarterfinal"
    assert (
        stage_rps(sharp, actual) < stage_rps(uniform, actual) < stage_rps(confident_wrong, actual)
    )


def test_format_uniform_cumulative_base_rates() -> None:
    uniform = format_uniform_cumulative()
    assert uniform["group"] == 1.0
    assert uniform["round_of_16"] == 0.5
    assert uniform["champion"] == 1.0 / 32.0


def test_mean_stage_rps_requires_same_teams() -> None:
    uniform = format_uniform_cumulative()
    with pytest.raises(ValueError, match="different teams"):
        mean_stage_rps({"A": uniform}, {"B": "group"})


def test_block_bootstrap_mean_is_deterministic_and_brackets_the_mean() -> None:
    summary = block_bootstrap_mean([0.1, 0.2, 0.3, 0.4])
    assert summary.mean == pytest.approx(0.25)
    assert summary.n_blocks == 4
    assert summary.ci_low <= summary.mean <= summary.ci_high
    again = block_bootstrap_mean([0.1, 0.2, 0.3, 0.4])
    assert (again.ci_low, again.ci_high) == (summary.ci_low, summary.ci_high)


def test_assess_champion_rank_and_probability() -> None:
    probs = {
        "Strong": {"champion": 0.4},
        "Middle": {"champion": 0.3},
        "Actual": {"champion": 0.2},
        "Weak": {"champion": 0.1},
    }
    result = assess_champion(probs, "Actual")
    assert result.rank == 3
    assert result.probability == pytest.approx(0.2)
    assert result.n_teams == 4
