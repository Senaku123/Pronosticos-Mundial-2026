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
import sys
from dataclasses import dataclass

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from wc26.backtesting.tournament_level import (
    ChampionAssessment,
    PlayedMatch,
    assess_champion,
    block_bootstrap_mean,
    format_uniform_cumulative,
    infer_deepest_stages,
    mean_stage_rps,
    validate_groups_against_matches,
)
from wc26.database.base import get_session_factory
from wc26.database.models import BacktestMetric, BacktestRun
from wc26.evaluation.live_scoring import world_cup_matches
from wc26.models.engine_config import fit_engine, load_team_elos
from wc26.simulation.structure32 import WC_EDITIONS, WorldCupEdition
from wc26.simulation.tournament32 import run_monte_carlo32
from wc26.utils.provenance import git_sha as _git_sha

SEED = 20260611
RUN_ID = "tournament_level_v1"
ENGINE = "dixon_coles_calibrated"
REFERENCE = "format_uniform"


@dataclass(frozen=True)
class EditionResult:
    """One edition's backtest outcome (engine vs format-uniform reference)."""

    year: int
    n_matches: int
    rps_engine: float
    rps_uniform: float
    champion: ChampionAssessment

    @property
    def champion_log_loss(self) -> float:
        return -math.log(max(self.champion.probability, 1e-12))


def _load_edition_matches(session: Session, edition: WorldCupEdition) -> list[PlayedMatch]:
    rows = session.execute(
        world_cup_matches(start=edition.start_date, end=edition.end_date, played=True)
    ).all()
    return [
        PlayedMatch(r.match_date, r.home, r.away, int(r.home_score), int(r.away_score))
        for r in rows
    ]


def main(argv: list[str]) -> int:
    n_sims = int(argv[0]) if argv else 50000
    uniform = format_uniform_cumulative()

    per_edition: list[EditionResult] = []
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

            probabilities = run_monte_carlo32(
                edition, elos, config, n_sims, SEED + edition.year, calibrator, progress=True
            )

            champion = assess_champion(probabilities, edition.champion)
            uniform_probs = {team: uniform for team in probabilities}
            result = EditionResult(
                year=edition.year,
                n_matches=len(matches),
                rps_engine=mean_stage_rps(probabilities, actual),
                rps_uniform=mean_stage_rps(uniform_probs, actual),
                champion=champion,
            )
            per_edition.append(result)
            print(
                f"  rps engine={result.rps_engine:.4f}  uniform={result.rps_uniform:.4f}  "
                f"champion {edition.champion}: p={champion.probability:.3f} "
                f"rank={champion.rank}/{champion.n_teams}"
            )

        engine_boot = block_bootstrap_mean([r.rps_engine for r in per_edition])
        uniform_boot = block_bootstrap_mean([r.rps_uniform for r in per_edition])
        skill = 1.0 - engine_boot.mean / uniform_boot.mean if uniform_boot.mean else 0.0
        champion_ll_mean = sum(r.champion_log_loss for r in per_edition) / len(per_edition)
        uniform_ll = math.log(32.0)
        sane = all(r.champion.rank <= 5 for r in per_edition)

        # Persist run + metrics (long format), replacing any previous Phase 11 run.
        session.execute(delete(BacktestRun).where(BacktestRun.run_id == RUN_ID))
        session.flush()
        run = BacktestRun(
            run_id=RUN_ID,
            backtest_level="tournament",
            test_from=WC_EDITIONS[0].start_date,
            n_matches=sum(r.n_matches for r in per_edition),
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=json.dumps(
                {
                    "engine": ENGINE,
                    "reference": REFERENCE,
                    "n_simulations": n_sims,
                    "seed": SEED,
                    "editions": [r.year for r in per_edition],
                    "sane": sane,
                }
            ),
        )
        session.add(run)
        session.flush()
        metric_rows = []
        for r in per_edition:
            for metric, value in (
                (f"rps_{r.year}", r.rps_engine),
                (f"champion_prob_{r.year}", r.champion.probability),
                (f"champion_rank_{r.year}", float(r.champion.rank)),
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
                    "metric": f"rps_{r.year}",
                    "value": r.rps_uniform,
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
    for r in per_edition:
        print(
            f"{r.year:<9}{r.rps_engine:>11.4f}{r.rps_uniform:>11.4f}"
            f"{r.champion.probability:>10.3f}{r.champion.rank:>6}"
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
