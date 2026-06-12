"""Operate the engine during the 2026 World Cup: re-simulate, publish, score (Phase 12).

Usage:
    uv run python scripts/run_2026_simulation.py simulate [--n 50000] [--as-of YYYY-MM-DD]
    uv run python scripts/run_2026_simulation.py publish  [--as-of YYYY-MM-DD]
    uv run python scripts/run_2026_simulation.py score    [--as-of YYYY-MM-DD]

simulate  Re-simulates the remaining tournament holding real results fixed (strict cutoff:
          only matches strictly before --as-of), with Monte Carlo error bands. Persists a dated
          ``wc2026_live_<date>`` run in tournament_simulations/simulation_results.
publish   Freezes pre-match W/D/L for every upcoming fixture (engine + Elo-only baseline, same
          as-of Elo) as dated model runs - publish BEFORE, never after.
score     Scores every published forecast whose match now has a result, against the baseline,
          and registers it in backtest_runs with backtest_level='live'.

Daily operation order: download_snapshots -> ingest_results -> compute_elo -> score ->
publish -> simulate. The engine configuration (rho + Platt) stays the pre-tournament fit that
won the go/no-go; team strengths update via as-of Elo as results are ingested.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess

from sqlalchemy import delete, insert, select
from tqdm import tqdm

from wc26.database.base import get_session_factory
from wc26.database.models import SimulationResult, Team, TournamentSimulation
from wc26.evaluation.live_scoring import (
    BASELINE_MODEL,
    ENGINE_MODEL,
    TOURNAMENT_START,
    load_known_results,
    monte_carlo_half_width,
    publish_match_forecasts,
    score_published_forecasts,
    summarize_known,
)
from wc26.models.engine_config import fit_engine, load_team_elos
from wc26.simulation.structure import GROUPS_2026, STAGES
from wc26.simulation.tournament import run_monte_carlo


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def _simulate(as_of: dt.date, n_sims: int) -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        config, calibrator = fit_engine(session, TOURNAMENT_START)
        known, warnings = load_known_results(session, as_of)
        for warning in warnings:
            print(f"[warn] {warning}")
        print(f"[ok] conditioning: {summarize_known(known, warnings)}")

        teams = [t for group in GROUPS_2026.values() for t in group]
        elos = load_team_elos(session, teams, as_of)

        seed = int(as_of.strftime("%Y%m%d"))
        print(f"[ok] running {n_sims} simulations as of {as_of} (rho={config.rho:.4f}) ...")
        with tqdm(total=1, desc="Monte Carlo", unit="run") as bar:
            probabilities = run_monte_carlo(elos, config, n_sims, seed, calibrator, known)
            bar.update(1)

        run_id = f"wc2026_live_{as_of.isoformat()}"
        session.execute(delete(TournamentSimulation).where(TournamentSimulation.run_id == run_id))
        session.flush()
        simulation = TournamentSimulation(
            run_id=run_id,
            n_simulations=n_sims,
            random_seed=seed,
            cutoff_date=as_of,
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=json.dumps(
                {
                    "model": ENGINE_MODEL,
                    "rho": round(config.rho, 4),
                    "calibration": "platt_pre_tournament",
                    "platt": {k: round(v, 4) for k, v in calibrator.to_dict().items()},
                    "hosts_home_advantage": "group_stage",
                    "known": summarize_known(known, warnings),
                }
            ),
        )
        session.add(simulation)
        session.flush()
        team_ids = {
            name: team_id
            for name, team_id in session.execute(select(Team.canonical_name, Team.id)).all()
        }
        session.execute(
            insert(SimulationResult),
            [
                {
                    "tournament_simulation_id": simulation.id,
                    "team_id": team_ids[team],
                    "stage": stage,
                    "probability": stage_probs[stage],
                }
                for team, stage_probs in probabilities.items()
                for stage in STAGES
            ],
        )
        session.commit()

    band = monte_carlo_half_width
    champions = sorted(probabilities.items(), key=lambda kv: kv[1]["champion"], reverse=True)
    print(f"\n2026 World Cup - title odds as of {as_of} ({n_sims} sims, 95% MC bands):\n")
    print(f"{'team':<22}{'champion':>16}{'final':>8}{'semi':>8}{'quarter':>9}{'R16':>7}")
    print("-" * 70)
    for team, sp in champions[:16]:
        champ = sp["champion"]
        print(
            f"{team:<22}{champ * 100:>7.1f}% ±{band(champ, n_sims) * 100:>4.1f}%"
            f"{sp['final'] * 100:>7.1f}%{sp['semifinal'] * 100:>7.1f}%"
            f"{sp['quarterfinal'] * 100:>8.1f}%{sp['round_of_16'] * 100:>6.1f}%"
        )
    return 0


def _publish(as_of: dt.date) -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        config, calibrator = fit_engine(session, TOURNAMENT_START)
        published = publish_match_forecasts(
            session,
            as_of,
            config,
            calibrator,
            git_sha=_git_sha(),
            python_version=platform.python_version(),
        )
        session.commit()

    print(f"\nPublished {len(published)} frozen forecasts as of {as_of} (engine + baseline):\n")
    print(f"{'date':<12}{'home':<22}{'away':<22}{'Hwin':>6}{'Draw':>6}{'Awin':>6}  score")
    print("-" * 82)
    for fx in published:
        print(
            f"{fx.match_date.isoformat():<12}{fx.home[:21]:<22}{fx.away[:21]:<22}"
            f"{fx.probs[0] * 100:>5.0f}%{fx.probs[1] * 100:>5.0f}%{fx.probs[2] * 100:>5.0f}%"
            f"  {fx.predicted_score[0]}-{fx.predicted_score[1]}"
        )
    return 0


def _score(as_of: dt.date) -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        report = score_published_forecasts(
            session, as_of, git_sha=_git_sha(), python_version=platform.python_version()
        )
        session.commit()

    if report.n_scored == 0:
        print("No published forecasts have results yet - nothing to score.")
        return 0
    print(f"\nLive scoring as of {as_of} (n={report.n_scored} matches):\n")
    print(f"{'model':<24}{'logloss':>9}{'brier':>8}{'rps':>8}{'ece':>8}{'acc':>7}")
    print("-" * 64)
    for model in (ENGINE_MODEL, BASELINE_MODEL):
        e = report.evaluations[model]
        print(
            f"{model:<24}{e.log_loss:>9.4f}{e.brier:>8.4f}{e.rps:>8.4f}{e.ece:>8.4f}"
            f"{e.accuracy:>7.3f}"
        )
    print(
        f"\nPaired bootstrap (engine vs baseline, per-match log loss): "
        f"mean diff {report.paired.mean_difference:+.5f} "
        f"95% CI [{report.paired.ci_low:+.5f}, {report.paired.ci_high:+.5f}] "
        f"p={report.paired.p_value:.4f}"
        f"\nNOTE: early-tournament n is small; conclusions firm up as rounds complete."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("simulate", "publish", "score"):
        command = sub.add_parser(name)
        command.add_argument("--as-of", type=dt.date.fromisoformat, default=dt.date.today())
        if name == "simulate":
            command.add_argument("--n", type=int, default=50000)
    args = parser.parse_args()
    if args.command == "simulate":
        return _simulate(args.as_of, args.n)
    if args.command == "publish":
        return _publish(args.as_of)
    return _score(args.as_of)


if __name__ == "__main__":
    raise SystemExit(main())
