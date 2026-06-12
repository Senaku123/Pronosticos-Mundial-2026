"""Simulate the 2026 World Cup by Monte Carlo and store stage probabilities (Phase 10).

Usage:
    uv run python scripts/simulate_wc2026.py [n_simulations]

Loads each team's as-of Elo (the strength going into the tournament), fits Dixon-Coles rho AND
the Platt calibration layer on matches strictly before the tournament (the configuration that won
the Phase 8 go/no-go), runs the Monte Carlo simulator on calibrated matrices and stores per-team
stage probabilities. Prints the title odds. Requires elo_ratings + match_features seeded.
"""

from __future__ import annotations

import datetime as dt
import platform
import subprocess
import sys

from sqlalchemy import delete, insert, select
from tqdm import tqdm

from wc26.database.base import get_session_factory
from wc26.database.models import (
    Match,
    MatchFeature,
    SimulationResult,
    Team,
    TournamentSimulation,
)
from wc26.features.cutoff import get_rating_as_of
from wc26.models.baselines import BaselineConfig, elo_to_lambdas
from wc26.models.calibration import PlattCalibrator
from wc26.models.dixon_coles import DixonColesConfig, fit_rho, predict_dixon_coles
from wc26.simulation.structure import GROUPS_2026, STAGES
from wc26.simulation.tournament import run_monte_carlo

TOURNAMENT_START = dt.date(2026, 6, 11)
SEED = 20260611


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def main(argv: list[str]) -> int:
    n_sims = int(argv[0]) if argv else 50000
    base = BaselineConfig()
    session_factory = get_session_factory()
    with session_factory() as session:
        # Fit rho AND the Platt calibrator on matches strictly before the tournament cutoff.
        training = session.execute(
            select(
                MatchFeature.elo_home,
                MatchFeature.elo_away,
                MatchFeature.is_neutral,
                Match.home_score,
                Match.away_score,
            )
            .join(Match, Match.id == MatchFeature.match_id)
            .where(Match.match_date < TOURNAMENT_START)
        ).all()
        samples = []
        for elo_home, elo_away, neutral, hs, away_s in training:
            lh, la = elo_to_lambdas(elo_home, elo_away, neutral, base)
            samples.append((lh, la, int(hs), int(away_s)))
        cfg = DixonColesConfig(rho=fit_rho(samples))

        print("[ok] fitting Platt calibration on pre-tournament matches ...")
        cal_probs = []
        cal_outcomes = []
        for elo_home, elo_away, neutral, hs, away_s in tqdm(
            training, desc="calibration fit", unit="match"
        ):
            pred, _ = predict_dixon_coles(elo_home, elo_away, neutral, cfg)
            cal_probs.append((pred.p_home_win, pred.p_draw, pred.p_away_win))
            cal_outcomes.append(
                0 if int(hs) > int(away_s) else (1 if int(hs) == int(away_s) else 2)
            )
        calibrator = PlattCalibrator.fit(cal_probs, cal_outcomes)

        # As-of Elo for the 48 teams + their team ids.
        team_ids = {
            name: tid for name, tid in session.execute(select(Team.canonical_name, Team.id)).all()
        }
        team_elos: dict[str, float] = {}
        missing = []
        for teams in GROUPS_2026.values():
            for team in teams:
                if team not in team_ids:
                    missing.append(team)
                team_elos[team] = get_rating_as_of(
                    session, team_ids.get(team, -1), TOURNAMENT_START
                )
        if missing:
            print(f"[warn] teams not found in DB (using base Elo): {missing}")

        print(
            f"[ok] running {n_sims} simulations (rho={cfg.rho:.4f}, calibrated, hosts at home) ..."
        )
        with tqdm(total=1, desc="Monte Carlo", unit="run") as bar:
            probabilities = run_monte_carlo(team_elos, cfg, n_sims, SEED, calibrator)
            bar.update(1)

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
            config_json=(
                f'{{"rho": {cfg.rho:.4f}, "model": "dixon_coles_calibrated", '
                f'"calibration": "platt_pre_tournament", "hosts_home_advantage": "group_stage"}}'
            ),
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
            if team in team_ids
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
