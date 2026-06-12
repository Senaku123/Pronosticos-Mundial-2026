"""Tournament-level backtest over the 2010-2022 World Cups (Phase 11, sanity check only).

Usage:
    uv run python scripts/backtest_tournament_level.py [n_simulations]

For each historical edition: fits the engine (rho + Platt) strictly before the tournament,
loads as-of Elo, simulates the full 32-team bracket, and scores the per-team stage distribution
(RPS) against what actually happened, with a format-uniform reference and a block bootstrap by
tournament (N=4 declared). Persists backtest_runs/backtest_metrics with level='tournament'.

This validates the PROPAGATION ENGINE, never selects models (addendum §3): the 2026 bracket has
no historical analog (32 -> 48), so live scoring during the tournament remains the definitive
validation (BACKTESTING_STRATEGY.md §4.4).
"""

from __future__ import annotations

import json
import math
import platform
import subprocess
import sys

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session, aliased
from tqdm import tqdm

from wc26.backtesting.tournament_level import (
    PlayedMatch,
    assess_champion,
    block_bootstrap_mean,
    format_uniform_cumulative,
    infer_deepest_stages,
    mean_stage_rps,
    validate_groups_against_matches,
)
from wc26.database.base import get_session_factory
from wc26.database.models import (
    BacktestMetric,
    BacktestRun,
    Match,
    Team,
    Tournament,
    TournamentMapping,
)
from wc26.models.engine_config import fit_engine, load_team_elos
from wc26.simulation.structure32 import WC_EDITIONS, WorldCupEdition
from wc26.simulation.tournament32 import run_monte_carlo32

SEED = 20260611
RUN_ID = "tournament_level_v1"
ENGINE = "dixon_coles_calibrated"
REFERENCE = "format_uniform"


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def _load_edition_matches(session: Session, edition: WorldCupEdition) -> list[PlayedMatch]:
    home = aliased(Team)
    away = aliased(Team)
    rows = session.execute(
        select(
            Match.match_date,
            home.canonical_name.label("home"),
            away.canonical_name.label("away"),
            Match.home_score,
            Match.away_score,
        )
        .join(Tournament, Tournament.id == Match.tournament_id)
        .join(TournamentMapping, TournamentMapping.raw_tournament == Tournament.name)
        .join(home, home.id == Match.home_team_id)
        .join(away, away.id == Match.away_team_id)
        .where(
            TournamentMapping.tournament_category == "world_cup",
            Match.match_date >= edition.start_date,
            Match.match_date <= edition.end_date,
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
        )
        .order_by(Match.match_date, Match.id)
    ).all()
    return [
        PlayedMatch(r.match_date, r.home, r.away, int(r.home_score), int(r.away_score))
        for r in rows
    ]


def main(argv: list[str]) -> int:
    n_sims = int(argv[0]) if argv else 50000
    uniform = format_uniform_cumulative()

    per_edition: list[dict[str, float]] = []
    session_factory = get_session_factory()
    with session_factory() as session:
        for edition in WC_EDITIONS:
            print(f"\n=== WC {edition.year} (cutoff {edition.start_date}) ===")
            matches = _load_edition_matches(session, edition)
            validate_groups_against_matches(edition, matches)
            actual = infer_deepest_stages(edition, matches)

            config, calibrator = fit_engine(session, edition.start_date)
            teams = [t for group in edition.groups.values() for t in group]
            elos = load_team_elos(session, teams, edition.start_date)

            with tqdm(total=1, desc=f"Monte Carlo {edition.year}", unit="run") as bar:
                probabilities = run_monte_carlo32(
                    edition, elos, config, n_sims, SEED + edition.year, calibrator
                )
                bar.update(1)

            champion = assess_champion(probabilities, edition.champion)
            uniform_probs = {team: uniform for team in probabilities}
            stats = {
                "year": float(edition.year),
                "rho": config.rho,
                "n_matches": float(len(matches)),
                "rps_engine": mean_stage_rps(probabilities, actual),
                "rps_uniform": mean_stage_rps(uniform_probs, actual),
                "champion_prob": champion.probability,
                "champion_rank": float(champion.rank),
                "champion_log_loss": -math.log(max(champion.probability, 1e-12)),
            }
            per_edition.append(stats)
            print(
                f"  rps engine={stats['rps_engine']:.4f}  uniform={stats['rps_uniform']:.4f}  "
                f"champion {edition.champion}: p={champion.probability:.3f} "
                f"rank={champion.rank}/{champion.n_teams}"
            )

        engine_boot = block_bootstrap_mean([s["rps_engine"] for s in per_edition])
        uniform_boot = block_bootstrap_mean([s["rps_uniform"] for s in per_edition])
        skill = 1.0 - engine_boot.mean / uniform_boot.mean if uniform_boot.mean else 0.0
        champion_ll_mean = sum(s["champion_log_loss"] for s in per_edition) / len(per_edition)
        uniform_ll = math.log(32.0)
        sane = all(s["champion_rank"] <= 5 for s in per_edition)

        # Persist run + metrics (long format), replacing any previous Phase 11 run.
        session.execute(delete(BacktestRun).where(BacktestRun.run_id == RUN_ID))
        session.flush()
        run = BacktestRun(
            run_id=RUN_ID,
            backtest_level="tournament",
            test_from=WC_EDITIONS[0].start_date,
            n_matches=int(sum(s["n_matches"] for s in per_edition)),
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=json.dumps(
                {
                    "engine": ENGINE,
                    "reference": REFERENCE,
                    "n_simulations": n_sims,
                    "seed": SEED,
                    "editions": [int(s["year"]) for s in per_edition],
                    "sane": sane,
                }
            ),
        )
        session.add(run)
        session.flush()
        metric_rows = []
        for stats in per_edition:
            year = int(stats["year"])
            for metric, value in (
                (f"rps_{year}", stats["rps_engine"]),
                (f"champion_prob_{year}", stats["champion_prob"]),
                (f"champion_rank_{year}", stats["champion_rank"]),
            ):
                metric_rows.append(
                    {
                        "backtest_run_id": run.id,
                        "model_name": ENGINE,
                        "metric": metric,
                        "value": value,
                    }
                )
            metric_rows.append(
                {
                    "backtest_run_id": run.id,
                    "model_name": REFERENCE,
                    "metric": f"rps_{year}",
                    "value": stats["rps_uniform"],
                }
            )
        for model, boot, ll in (
            (ENGINE, engine_boot, champion_ll_mean),
            (REFERENCE, uniform_boot, uniform_ll),
        ):
            metric_rows.extend(
                {"backtest_run_id": run.id, "model_name": model, "metric": metric, "value": value}
                for metric, value in (
                    ("rps_mean", boot.mean),
                    ("rps_ci_low", boot.ci_low),
                    ("rps_ci_high", boot.ci_high),
                    ("champion_log_loss_mean", ll),
                )
            )
        metric_rows.append(
            {
                "backtest_run_id": run.id,
                "model_name": ENGINE,
                "metric": "skill_rps_vs_uniform",
                "value": skill,
            }
        )
        session.execute(insert(BacktestMetric), metric_rows)
        session.commit()

    print(f"\nTournament-level sanity check ({len(per_edition)} editions, N={n_sims} sims each):\n")
    print(f"{'edition':<9}{'rps engine':>11}{'rps unif.':>11}{'P(champ)':>10}{'rank':>6}")
    print("-" * 47)
    for stats in per_edition:
        print(
            f"{int(stats['year']):<9}{stats['rps_engine']:>11.4f}{stats['rps_uniform']:>11.4f}"
            f"{stats['champion_prob']:>10.3f}{int(stats['champion_rank']):>6}"
        )
    print(
        f"\n  mean RPS engine  = {engine_boot.mean:.4f}  "
        f"95% block-bootstrap CI [{engine_boot.ci_low:.4f}, {engine_boot.ci_high:.4f}] (N=4)\n"
        f"  mean RPS uniform = {uniform_boot.mean:.4f}  -> skill = {skill:+.3f}\n"
        f"  champion log loss: engine {champion_ll_mean:.3f} vs uniform {uniform_ll:.3f}\n"
        f"  real champions among top-5 candidates in every edition: {sane}"
    )
    print(
        "\nNOTE (external validity): this validates bracket propagation on the 32-team format; "
        "the 48-team 2026 bracket has no historical analog. N=4 tournaments - a sanity check, "
        "NEVER a model-selection criterion (addendum §3). Live scoring is the definitive test."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
