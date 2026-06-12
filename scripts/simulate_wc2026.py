"""Simulate the 2026 World Cup by Monte Carlo and store stage probabilities (Phase 10).

Usage:
    uv run python scripts/simulate_wc2026.py [n_simulations]

Loads each team's as-of Elo (the strength going into the tournament), fits Dixon-Coles rho AND
the Platt calibration layer on matches strictly before the tournament (the configuration that won
the Phase 8 go/no-go), runs the Monte Carlo simulator on calibrated matrices and stores per-team
stage probabilities. Prints the title odds. Requires elo_ratings + match_features seeded.
"""

from __future__ import annotations

import platform
import sys

from sqlalchemy import delete, insert, select

from wc26.database.base import get_session_factory
from wc26.database.models import SimulationResult, Team, TournamentSimulation
from wc26.models.engine_config import engine_config_json, fit_engine, load_team_elos
from wc26.simulation.structure import GROUPS_2026, STAGES, TOURNAMENT_START
from wc26.simulation.tournament import run_monte_carlo
from wc26.utils.provenance import git_sha as _git_sha

SEED = 20260611


def main(argv: list[str]) -> int:
    n_sims = int(argv[0]) if argv else 50000
    session_factory = get_session_factory()
    with session_factory() as session:
        # Fit rho AND the Platt calibrator on matches strictly before the tournament cutoff.
        cfg, calibrator = fit_engine(session, TOURNAMENT_START)

        # As-of Elo for the 48 teams + their team ids (unknown names raise; no silent default).
        team_ids = {
            name: tid for name, tid in session.execute(select(Team.canonical_name, Team.id)).all()
        }
        teams = [team for group in GROUPS_2026.values() for team in group]
        team_elos = load_team_elos(session, teams, TOURNAMENT_START)

        print(
            f"[ok] running {n_sims} simulations (rho={cfg.rho:.4f}, calibrated, hosts at home) ..."
        )
        probabilities = run_monte_carlo(team_elos, cfg, n_sims, SEED, calibrator, progress=True)

        # Persist run + aggregated results.
        session.execute(delete(TournamentSimulation).where(TournamentSimulation.run_id == "wc2026"))
        session.flush()
        sim = TournamentSimulation(
            run_id="wc2026",
            n_simulations=n_sims,
            random_seed=SEED,
            cutoff_date=TOURNAMENT_START,
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=engine_config_json(cfg, calibrator, hosts_home_advantage="group_stage"),
        )
        session.add(sim)
        session.flush()
        rows = [
            {
                "tournament_simulation_id": sim.id,
                "team_id": team_ids[team],
                "stage": stage,
                "probability": stage_probs[stage],
            }
            for team, stage_probs in probabilities.items()
            for stage in STAGES
        ]
        if rows:
            session.execute(insert(SimulationResult), rows)
        session.commit()

    champions = sorted(probabilities.items(), key=lambda kv: kv[1]["champion"], reverse=True)
    print("\n2026 World Cup — title odds (Monte Carlo, Dixon-Coles):\n")
    print(f"{'team':<22}{'champion':>9}{'final':>8}{'semi':>8}{'quarter':>9}{'R16':>7}")
    print("-" * 63)
    for team, sp in champions[:16]:
        print(
            f"{team:<22}{sp['champion'] * 100:>8.1f}%{sp['final'] * 100:>7.1f}%"
            f"{sp['semifinal'] * 100:>7.1f}%{sp['quarterfinal'] * 100:>8.1f}%"
            f"{sp['round_of_16'] * 100:>6.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
