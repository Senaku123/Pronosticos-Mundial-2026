"""Monte Carlo simulation of a historical 32-team World Cup (tournament-level backtest input).

Same engine as the 2026 simulator (calibrated Dixon-Coles scorelines, group cascade, knockout
90'/ET/penalties), played on the 8-group format and fixed R16 bracket of 2010-2022. The host
gets home advantage in the group stage and the knockout is neutral for everyone, mirroring the
documented 2026 policy. One documented approximation: groups are ranked with the 2026 Article 13
cascade (head-to-head before overall goal difference), while 2010-2022 used overall goal
difference first; the orders only diverge on rare exact point-ties and this engine exists to
validate propagation, never to select models (addendum §3).
"""

from __future__ import annotations

import numpy as np
from tqdm import tqdm

from wc26.models.calibration import PlattCalibrator
from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.groups import simulate_group
from wc26.simulation.knockout import HOME, resolve_knockout
from wc26.simulation.structure32 import (
    FINAL_32,
    QUARTERFINALS_32,
    R16_MATCHES_32,
    SEMIFINALS_32,
    STAGES_32,
    WorldCupEdition,
)


def simulate_tournament32(
    edition: WorldCupEdition,
    team_elos: dict[str, float],
    config: DixonColesConfig,
    rng: np.random.Generator,
    calibrator: PlattCalibrator | None = None,
) -> dict[str, str]:
    """Simulate one historical edition once; return each team's deepest stage reached."""
    reached: dict[str, str] = {team: "group" for group in edition.groups.values() for team in group}

    placed: dict[tuple[str, str], str] = {}
    for letter, teams in edition.groups.items():
        elos = {t: team_elos[t] for t in teams}
        standings = simulate_group(elos, config, rng, hosts=edition.hosts, calibrator=calibrator)
        placed[("W", letter)] = standings[0].team
        placed[("RU", letter)] = standings[1].team

    winner_of: dict[int, str] = {}
    for match_no, home_slot, away_slot in R16_MATCHES_32:
        home = placed[home_slot]
        away = placed[away_slot]
        reached[home] = "round_of_16"
        reached[away] = "round_of_16"
        result = resolve_knockout(team_elos[home], team_elos[away], True, config, rng, calibrator)
        winner_of[match_no] = home if result == HOME else away

    for stage, matches in (
        ("quarterfinal", QUARTERFINALS_32),
        ("semifinal", SEMIFINALS_32),
        ("final", FINAL_32),
    ):
        for match_no, source_home, source_away in matches:
            home = winner_of[source_home]
            away = winner_of[source_away]
            reached[home] = stage
            reached[away] = stage
            result = resolve_knockout(
                team_elos[home], team_elos[away], True, config, rng, calibrator
            )
            winner_of[match_no] = home if result == HOME else away

    reached[winner_of[FINAL_32[0][0]]] = "champion"
    return reached


def run_monte_carlo32(
    edition: WorldCupEdition,
    team_elos: dict[str, float],
    config: DixonColesConfig,
    n_simulations: int,
    seed: int,
    calibrator: PlattCalibrator | None = None,
    progress: bool = False,
) -> dict[str, dict[str, float]]:
    """Run ``n_simulations`` of one edition; return cumulative stage probabilities per team."""
    expected = {team for group in edition.groups.values() for team in group}
    missing = expected - set(team_elos)
    if missing:
        raise ValueError(f"team_elos is missing WC {edition.year} teams: {sorted(missing)}")

    rng = np.random.default_rng(seed)
    counts = {team: dict.fromkeys(STAGES_32, 0) for team in expected}
    iterations = tqdm(
        range(n_simulations), desc=f"Monte Carlo {edition.year}", unit="sim", disable=not progress
    )
    for _ in iterations:
        reached = simulate_tournament32(edition, team_elos, config, rng, calibrator)
        for team, stage in reached.items():
            for s in STAGES_32[: STAGES_32.index(stage) + 1]:
                counts[team][s] += 1
    return {team: {s: counts[team][s] / n_simulations for s in STAGES_32} for team in expected}
